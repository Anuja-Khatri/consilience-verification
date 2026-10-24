#!/usr/bin/env python3
"""
pipeline/llm.py — the ONE wrapper for ALL model calls (SPEC v2.0.1 §0.4).

No task may call a provider SDK directly. Features (all per §0.4 as amended):
  * Cache: key = sha256 of canonical JSON (sorted keys) of the FULL request
    {model, system, messages, temperature, max_tokens, <other params sent>,
    replicate_tag}. replicate_tag is MANDATORY. Provider seed support is
    IRRELEVANT to the key (Anthropic has no seed param).
  * Secondary cache: prior eval cache (eval_out/cache/, read-only) consulted ONLY
    when replicate_tag == "r0", using the PRIOR code's own key function
    (reconstructed verbatim from eval/common.py). Hits recorded cache_source:
    prior-eval. If the prior formula cannot be reconstructed -> HALT-ASK.
  * Provenance: {model, provider, date, temperature, prompt_sha, response_sha,
    replicate_tag, provider_seed_honored}. provider_seed_honored is False for
    Anthropic.
  * Retries: 5 attempts, backoff 2/4/8/16/32s on 429/5xx; persistent failure ->
    FAILED placeholder (batch continues), surfaced in the failure report.
  * Meter: tokens + $ per call aggregated per task id -> results/cost_meter.json.
    Projected task spend > budget_usd[task] -> HALT-ASK. Hard cap $900: refuse
    beyond it unless env ANU_OVERRIDE=<reason>.
  * Temperature: default 0 everywhere EXCEPT A5 arm (a), which OMITS the param
    (pass temperature=None) -> recorded temperature: "provider-default".
  * JSON robustness: strip ``` fences, retry once with a nudge, else UNPARSEABLE.
  * Quarantine: call(..., quarantine=True) tags the record quarantined:true; such
    records may be read ONLY by scripts under pipeline/quarantine/.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import importlib.util
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

SPRINT = Path(__file__).resolve().parent.parent
CONFIG_PATH = SPRINT / "pipeline" / "config.yaml"
QUARANTINE_DIR = (SPRINT / "pipeline" / "quarantine").resolve()

PROVIDER_DEFAULT = "provider-default"

# anthropic models whose API accepts `temperature` via extra_body (v2.0.3). Empty: a live
# test showed claude-sonnet-4-6 returns 400 "temperature: Extra inputs are not permitted".
ANTHROPIC_TEMPERATURE_OK: set = set()

# Gemini thinking budget for panel/structured calls (D-029): 0 disables thinking so output
# tokens are never consumed by it (B3 wants typed labels, not reasoning).
GEMINI_THINKING_BUDGET: int = 0

# USD per 1e6 tokens (input, output). Used only for the meter; update with care.
PRICING: Dict[str, Dict[str, float]] = {
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
    "gpt-4.1": {"in": 2.00, "out": 8.00},
    "gemini-2.5-pro": {"in": 1.25, "out": 10.00},
    # gemini-3.1-pro-preview: ai.google.dev/gemini-api/docs/pricing (fetched 2026-10-23), <=200k-token tier:
    # input $2/M, output $12/M; thinking tokens bill at the OUTPUT rate ("response = output + thinking").
    "gemini-3.1-pro-preview": {"in": 2.00, "out": 12.00},
    "qwen2.5-72b-instruct": {"in": 0.90, "out": 0.90},
    "llama-3.3-70b": {"in": 0.90, "out": 0.90},
    # test fixture pricing (never a real model)
    "test-model": {"in": 1.00, "out": 2.00},
}


class HaltAsk(RuntimeError):
    """Raised on a §0.10 HALT-ASK trigger inside the wrapper."""


class QuarantineViolation(RuntimeError):
    """A non-quarantine caller tried to read a quarantined cache record (§0.4)."""


class BudgetExceeded(RuntimeError):
    """Projected task budget or the $900 hard cap would be breached (§0.4)."""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(str(p)))


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    for k, v in list(cfg.get("paths", {}).items()):
        cfg["paths"][k] = str(_expand(v))
    return cfg


def provider_of(model: str) -> str:
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith("qwen") or m.startswith("llama"):
        return "open-weight"
    return "unknown"


def strip_json_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.lstrip().lower().startswith("json"):
            t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


# --------------------------------------------------------------------------- #
# prior-eval cache-key (reconstructed verbatim from eval/common.py:cache_key)
# --------------------------------------------------------------------------- #
def prior_cache_key(model: str, system: str, user: str, temperature: float,
                    max_tokens: int, run_index: Optional[int] = None) -> str:
    """Byte-identical reimplementation of eval/common.py:cache_key (v2.0.1 6b).

    parts = [model, system, user, repr(float(temperature)), str(int(max_tokens))]
    + ["run=<i>"] if run_index is not None; sha256 of "\\x1f".join(parts).
    """
    parts = [model, system, user, repr(float(temperature)), str(int(max_tokens))]
    if run_index is not None:
        parts.append(f"run={run_index}")
    return _sha256_text("\x1f".join(parts))


def load_authoritative_prior_cache_key(eval_prior_root: Path) -> Callable:
    """Dynamically load the AUTHORITATIVE cache_key from the prior eval/common.py.

    Used by the fidelity test to prove prior_cache_key() matches the source.
    Raise HaltAsk if it cannot be loaded (-> the formula is unverifiable: §0.10).
    """
    common_py = Path(eval_prior_root) / "eval" / "common.py"
    if not common_py.exists():
        raise HaltAsk(f"prior eval/common.py not found at {common_py}; "
                      "cannot verify the secondary-cache key formula")
    spec = importlib.util.spec_from_file_location("_prior_eval_common", common_py)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # runs _assert_fingerprints() (read-only)
    except Exception as e:
        raise HaltAsk(f"failed to import prior eval/common.py: {e!r}")
    fn = getattr(mod, "cache_key", None)
    if fn is None:
        raise HaltAsk("prior eval/common.py has no cache_key(); formula unreconstructable")
    return fn


# --------------------------------------------------------------------------- #
# meter
# --------------------------------------------------------------------------- #
class Meter:
    """Tokens + $ per call aggregated per task id -> results/cost_meter.json."""

    def __init__(self, path: Path, hard_total_usd: float = 900.0,
                 budgets: Optional[Dict[str, float]] = None):
        self.path = Path(path)
        self.hard_total = float(hard_total_usd)
        self.budgets = budgets or {}
        self.data = {"tasks": {}, "total_usd": 0.0,
                     "total_in_tokens": 0, "total_out_tokens": 0,
                     "hard_total_usd": self.hard_total, "budgets": self.budgets}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except Exception:
                pass
        # keep the ceiling/budgets visible even on reload
        self.data.setdefault("hard_total_usd", self.hard_total)
        self.data.setdefault("budgets", self.budgets)

    @staticmethod
    def cost_usd(model: str, in_tokens: int, out_tokens: int) -> float:
        p = PRICING.get(model)
        if not p:
            return 0.0
        return in_tokens / 1e6 * p["in"] + out_tokens / 1e6 * p["out"]

    def preflight(self, task_id: str, model: str, est_in: int, est_out: int) -> None:
        """Refuse beyond the $900 hard cap unless ANU_OVERRIDE is set (§0.4)."""
        projected = self.data["total_usd"] + self.cost_usd(model, est_in, est_out)
        if projected > self.hard_total and not os.environ.get("ANU_OVERRIDE"):
            raise BudgetExceeded(
                f"hard cap ${self.hard_total:.0f} would be breached "
                f"(projected ${projected:.2f}); set ANU_OVERRIDE=<reason> to proceed")

    def add(self, task_id: str, model: str, in_tokens: int, out_tokens: int) -> float:
        cost = self.cost_usd(model, in_tokens, out_tokens)
        t = self.data["tasks"].setdefault(
            task_id, {"usd": 0.0, "in_tokens": 0, "out_tokens": 0, "calls": 0})
        t["usd"] += cost
        t["in_tokens"] += in_tokens
        t["out_tokens"] += out_tokens
        t["calls"] += 1
        self.data["total_usd"] += cost
        self.data["total_in_tokens"] += in_tokens
        self.data["total_out_tokens"] += out_tokens
        return cost

    def check_projection(self, task_id: str) -> None:
        """At >=25% completion, extrapolate task spend vs its budget -> HALT-ASK."""
        budget = self.budgets.get(task_id)
        t = self.data["tasks"].get(task_id)
        if not budget or not t:
            return
        if t["usd"] > budget:
            raise HaltAsk(f"task {task_id} spend ${t['usd']:.2f} exceeds "
                          f"budget ${budget:.2f} (§0.4 meter)")

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True))


# --------------------------------------------------------------------------- #
# the wrapper
# --------------------------------------------------------------------------- #
class LLM:
    def __init__(self, config: Optional[dict] = None, *,
                 cache_dir: Optional[Path] = None,
                 prior_cache_dir: Optional[Path] = None,
                 meter_path: Optional[Path] = None,
                 load_env: bool = True):
        self.cfg = config or load_config()
        if load_env and load_dotenv is not None:
            env_file = SPRINT / ".env"
            if env_file.exists():
                load_dotenv(env_file)
        self.cache_dir = Path(cache_dir) if cache_dir else SPRINT / "cache"
        if prior_cache_dir is not None:
            self.prior_cache_dir = Path(prior_cache_dir)
        else:
            self.prior_cache_dir = _expand(self.cfg["paths"]["eval_prior"]) / "eval_out" / "cache"
        self.meter = Meter(
            Path(meter_path) if meter_path else SPRINT / "results" / "cost_meter.json",
            hard_total_usd=self.cfg.get("budget_usd", {}).get("hard_total", 900),
            budgets=self.cfg.get("budget_usd", {}),
        )

    # ---- keys ---- #
    def _canonical_request(self, model, system, messages, temperature,
                           max_tokens, extra, replicate_tag) -> dict:
        req = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": PROVIDER_DEFAULT if temperature is None else temperature,
            "replicate_tag": replicate_tag,
        }
        if extra:
            req.update(extra)
        return req

    def sprint_key(self, model, system, messages, temperature, max_tokens,
                   extra, replicate_tag) -> str:
        req = self._canonical_request(model, system, messages, temperature,
                                      max_tokens, extra, replicate_tag)
        canonical = json.dumps(req, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))
        return _sha256_text(canonical)

    def _cache_path(self, model: str, key: str) -> Path:
        return self.cache_dir / model.replace("/", "_") / f"{key}.json"

    # ---- cache read with quarantine enforcement ---- #
    @staticmethod
    def _caller_file(explicit: Optional[str]) -> str:
        if explicit is not None:
            return explicit
        # first stack frame outside this module
        import inspect
        for fr in inspect.stack():
            fn = fr.filename
            if Path(fn).resolve() != Path(__file__).resolve():
                return fn
        return __file__

    def read_cache(self, model: str, key: str, *,
                   caller_file: Optional[str] = None) -> Optional[dict]:
        path = self._cache_path(model, key)
        if not path.exists():
            return None
        rec = json.loads(path.read_text())
        if rec.get("quarantined"):
            caller = Path(self._caller_file(caller_file)).resolve()
            try:
                caller.relative_to(QUARANTINE_DIR)
            except ValueError:
                raise QuarantineViolation(
                    f"quarantined cache record {key[:12]} may be read only by "
                    f"pipeline/quarantine/ scripts; caller={caller}")
        return rec

    def secondary_get(self, model: str, prior_key: str) -> Optional[dict]:
        """Read a prior-eval cache entry by its PRIOR key (read-only)."""
        path = self.prior_cache_dir / model.replace("/", "_") / f"{prior_key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    # ---- provider (lazy import; monkeypatched in tests) ---- #
    def _provider_complete(self, model, system, messages, temperature,
                           max_tokens, extra) -> dict:
        provider = provider_of(model)
        if provider == "anthropic":
            import anthropic  # lazy
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            # anthropic SDK 2.1.0 dropped the typed `temperature` kwarg. The API accepts it
            # via extra_body ONLY for models in ANTHROPIC_TEMPERATURE_OK (verified by live
            # test; claude-sonnet-4-6 returns 400 "temperature: Extra inputs are not
            # permitted" → NOT listed). For all other anthropic models temperature is omitted
            # and temperature_applied=false (v2.0.3 ruling).
            kwargs = dict(model=model, system=system, messages=messages,
                          max_tokens=max_tokens)
            applied = False
            if temperature is not None and model in ANTHROPIC_TEMPERATURE_OK:
                kwargs["extra_body"] = {**kwargs.get("extra_body", {}), "temperature": temperature}
                applied = True
            if extra:
                kwargs.update(extra)
            resp = client.messages.create(**kwargs)
            text = "".join(getattr(b, "text", "") for b in resp.content
                           if getattr(b, "type", "") == "text")
            u = getattr(resp, "usage", None)
            usage = {"input_tokens": getattr(u, "input_tokens", 0),
                     "output_tokens": getattr(u, "output_tokens", 0)}
            return {"text": text, "usage": usage, "provider": provider,
                    "temperature_applied": applied}
        if provider == "openai":
            import openai  # lazy
            client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            msgs = ([{"role": "system", "content": system}] if system else []) + messages
            kwargs = dict(model=model, messages=msgs, max_tokens=max_tokens)
            if temperature is not None:
                kwargs["temperature"] = temperature
            if extra:
                kwargs.update(extra)
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content
            usage = {"input_tokens": resp.usage.prompt_tokens,
                     "output_tokens": resp.usage.completion_tokens}
            # gpt-4.1 ACCEPTS temperature (live-verified before B3: temperature=0 → HTTP 200, no 400).
            return {"text": text, "usage": usage, "provider": provider,
                    "temperature_applied": temperature is not None}
        if provider == "gemini":
            from google import genai  # lazy (google-genai; NOT the deprecated google-generativeai)
            from google.genai import types
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"])
            ccfg = {}
            if temperature is not None:
                ccfg["temperature"] = temperature
            if max_tokens:
                ccfg["max_output_tokens"] = max_tokens
            if system:
                ccfg["system_instruction"] = system
            # B3 safeguard (D-029): disable thinking on models that ALLOW it (flash) so output is never
            # consumed by thinking. THINKING-ONLY models (gemini-3.x / *-pro) REJECT budget 0
            # ("Budget 0 is invalid. This model only works in thinking mode." — D-058) → use default
            # (dynamic) thinking and rely on a generous max_output_tokens instead.
            _thinking_only = model.startswith("gemini-3") or ("pro" in model and "flash" not in model)
            if not _thinking_only:
                try:
                    ccfg["thinking_config"] = types.ThinkingConfig(thinking_budget=GEMINI_THINKING_BUDGET)
                except Exception:
                    pass
            if extra:
                ccfg.update(extra)
            gcfg = types.GenerateContentConfig(**ccfg) if ccfg else None
            contents = "\n".join(m["content"] for m in messages if m.get("role") == "user")
            resp = client.models.generate_content(model=model, contents=contents, config=gcfg)
            text = resp.text or ""
            cands = getattr(resp, "candidates", None) or []
            finish = str(getattr(cands[0], "finish_reason", "")) if cands else ""
            um = getattr(resp, "usage_metadata", None)
            # thinking models bill thought tokens at the OUTPUT rate ("response = output + thinking",
            # ai.google.dev/gemini-api/docs/pricing) — fold thoughts into output so the meter is accurate
            # (D-058 gap: this was uncaptured at the B3-2 run, backfilled from recorded in+out only).
            _thoughts = getattr(um, "thoughts_token_count", 0) or 0
            usage = {"input_tokens": getattr(um, "prompt_token_count", 0) or 0,
                     "output_tokens": (getattr(um, "candidates_token_count", 0) or 0) + _thoughts,
                     "thinking_tokens": _thoughts}
            mv = getattr(resp, "model_version", None)
            # B3 safeguard (D-029): empty/truncated Gemini response is a HALT-ASK, NEVER a silent
            # FAILED row in panel stats.
            if not text.strip() or "MAX_TOKENS" in finish:
                raise HaltAsk(f"gemini empty/truncated response (model={model}, model_version={mv}, "
                              f"finish_reason={finish}, output_tokens={usage['output_tokens']}); "
                              "B3 panel must HALT-ASK, not drop it silently")
            return {"text": text, "usage": usage, "provider": provider,
                    "temperature_applied": temperature is not None,
                    "model_version": mv, "finish_reason": finish}
        raise HaltAsk(f"no provider adapter for model {model} (provider={provider}) — "
                      "qwen/llama (open-weight) still deferred (no TOGETHER/FIREWORKS key)")

    def _call_with_retries(self, model, system, messages, temperature,
                           max_tokens, extra, retry_delays=None) -> dict:
        # Default = the production 5-step backoff. A caller may pass a SHORTER list (e.g. B3's
        # best-effort Gemini leg under a flaky free-tier quota) to fail fast instead of blocking
        # ~62s per transient 429/503 — the result is still an honest FAILED placeholder, just sooner.
        delays = [2, 4, 8, 16, 32] if retry_delays is None else list(retry_delays)
        last = None
        for attempt in range(len(delays) + 1):
            try:
                return self._provider_complete(model, system, messages,
                                               temperature, max_tokens, extra)
            except HaltAsk:
                raise  # D-029: empty/truncated Gemini (and other HALT-ASKs) must propagate,
                       # never be swallowed into a FAILED placeholder row
            except Exception as e:  # provider/network errors
                last = e
                code = getattr(e, "status_code", None) or getattr(e, "code", None)
                retriable = code in (429, 500, 502, 503, 504) or code is None
                if attempt == len(delays) or not retriable:
                    break
                time.sleep(delays[attempt])
        return {"text": None, "usage": {"input_tokens": 0, "output_tokens": 0},
                "provider": provider_of(model), "FAILED": True,
                "error": repr(last)}

    # ---- the public entrypoint ---- #
    def call(self, *, task_id: str, model: str, messages: List[dict],
             replicate_tag: str, system: str = "", temperature: Optional[float] = 0,
             max_tokens: int = 1500, quarantine: bool = False,
             est_in: int = 0, est_out: int = 0, caller_file: Optional[str] = None,
             retry_delays: Optional[list] = None, **extra) -> dict:
        """One model call. replicate_tag MANDATORY ('r0' for single-shot). retry_delays (named, so
        it never reaches the provider and never changes the cache key) lets a caller shorten the
        backoff — used by B3's best-effort Gemini leg to fail fast on a flaky free-tier quota."""
        if not replicate_tag:
            raise HaltAsk("replicate_tag is MANDATORY (use 'r0' for single-shot)")
        key = self.sprint_key(model, system, messages, temperature, max_tokens,
                              extra, replicate_tag)

        # 1) sprint cache
        hit = self.read_cache(model, key, caller_file=caller_file)
        if hit is not None:
            return hit

        # 2) secondary (prior-eval) cache — ONLY for r0, single user string
        if replicate_tag == "r0" and not quarantine:
            user = self._single_user(messages)
            if user is not None and temperature is not None:
                pk = prior_cache_key(model, system, user, temperature, max_tokens)
                prior = self.secondary_get(model, pk)
                if prior is not None:
                    rec = self._record(model, system, temperature, replicate_tag,
                                       prior, quarantine, cache_source="prior-eval")
                    self._write(model, key, rec)  # mirror into sprint cache
                    return rec

        # 3) live call (never exercised by tests — mocked)
        self.meter.preflight(task_id, model, est_in, est_out)
        resp = self._call_with_retries(model, system, messages, temperature,
                                       max_tokens, extra, retry_delays=retry_delays)
        usage = resp.get("usage", {})
        self.meter.add(task_id, model, usage.get("input_tokens", 0),
                       usage.get("output_tokens", 0))
        self.meter.check_projection(task_id)
        self.meter.flush()
        rec = self._record(model, system, temperature, replicate_tag, resp,
                           quarantine, cache_source="sprint")
        if not resp.get("FAILED"):
            self._write(model, key, rec)
        return rec

    @staticmethod
    def _single_user(messages: List[dict]) -> Optional[str]:
        users = [m for m in messages if m.get("role") == "user"]
        if len(messages) == 1 and len(users) == 1 and isinstance(users[0].get("content"), str):
            return users[0]["content"]
        return None

    def _record(self, model, system, temperature, replicate_tag, resp,
                quarantine, cache_source) -> dict:
        text = resp.get("text")
        prov = {
            "model": model,
            "provider": resp.get("provider", provider_of(model)),
            "date": self.cfg.get("dates", {}).get("artifact_stamp", "2026-10"),
            "temperature": PROVIDER_DEFAULT if temperature is None else temperature,
            "prompt_sha": _sha256_text(system + "\x1f" + json.dumps(resp.get("_req", ""))),
            "response_sha": _sha256_text(text) if isinstance(text, str) else None,
            "replicate_tag": replicate_tag,
            "provider_seed_honored": False,  # Anthropic has no seed param; false everywhere here
            "model_version": resp.get("model_version"),  # Gemini resolved version (D-029); None otherwise
            "finish_reason": resp.get("finish_reason"),
        }
        return {
            "text": text,
            "usage": resp.get("usage", {}),
            "provenance": prov,
            "quarantined": bool(quarantine),
            "cache_source": cache_source,
            "FAILED": bool(resp.get("FAILED", False)),
        }

    def _write(self, model: str, key: str, rec: dict) -> None:
        path = self._cache_path(model, key)
        if path.exists():  # append-only: never overwrite
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False))

    def call_json(self, **kwargs) -> dict:
        """call() + JSON robustness (strip fences, one retry nudge, else UNPARSEABLE)."""
        rec = self.call(**kwargs)
        text = rec.get("text")
        if not isinstance(text, str):
            rec["parsed"] = None
            rec["json_status"] = "FAILED" if rec.get("FAILED") else "EMPTY"
            return rec
        try:
            rec["parsed"] = json.loads(strip_json_fences(text))
            rec["json_status"] = "OK"
        except Exception:
            rec["parsed"] = None
            rec["json_status"] = "UNPARSEABLE"
        return rec


# module-level default client (lazy)
_default: Optional[LLM] = None


def default() -> LLM:
    global _default
    if _default is None:
        _default = LLM()
    return _default


if __name__ == "__main__":  # smoke (no network)
    cfg = load_config()
    print("config OK; models:", cfg["models"]["extractor"], cfg["models"]["verifier"])
    print("prior cache key sample:",
          prior_cache_key("gpt-4.1", "sys", "user", 0.0, 1500)[:16], "…")
