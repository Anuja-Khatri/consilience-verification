"""W0.2 unit tests for pipeline/llm.py (SPEC v2.0.1 §0.4). ALL MOCKED — no network,
no API spend. Covers: cache-hit determinism, meter arithmetic, quarantine read
restriction, replicate_tag (two entries), secondary-cache (formula fidelity + real hit).
"""
import json
import sys
from pathlib import Path

import pytest

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
import llm as L  # noqa: E402


def make_llm(tmp_path, prior_cache_dir=None):
    return L.LLM(config=L.load_config(), cache_dir=tmp_path / "cache",
                 prior_cache_dir=prior_cache_dir,
                 meter_path=tmp_path / "cost_meter.json", load_env=False)


def fake_provider(text="hi", in_tok=10, out_tok=20, provider="anthropic"):
    calls = {"n": 0}

    def _fp(self, model, system, messages, temperature, max_tokens, extra):
        calls["n"] += 1
        return {"text": text,
                "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
                "provider": provider}
    return _fp, calls


# --- 1. cache-hit determinism --------------------------------------------- #
def test_cache_hit_determinism(tmp_path, monkeypatch):
    client = make_llm(tmp_path)
    fp, calls = fake_provider()
    monkeypatch.setattr(L.LLM, "_provider_complete", fp)
    kw = dict(task_id="T", model="test-model", system="s",
              messages=[{"role": "user", "content": "u"}], replicate_tag="r0")
    r1 = client.call(**kw)
    r2 = client.call(**kw)
    assert calls["n"] == 1, "second identical call must be served from cache"
    assert r1["text"] == r2["text"] == "hi"
    assert r1["provenance"]["response_sha"] == r2["provenance"]["response_sha"]
    assert r1["provenance"]["provider_seed_honored"] is False
    assert list((tmp_path / "cache").rglob("*.json")), "cache file must be written"


# --- 2. meter arithmetic --------------------------------------------------- #
def test_meter_arithmetic(tmp_path):
    m = L.Meter(tmp_path / "cm.json", hard_total_usd=900, budgets={})
    # PRICING["test-model"] = in 1.0 / out 2.0 USD per 1e6 tokens
    c1 = m.add("T", "test-model", 1_000_000, 500_000)   # 1.0 + 1.0 = 2.0
    assert c1 == pytest.approx(2.0)
    m.add("T", "test-model", 1_000_000, 0)              # + 1.0
    t = m.data["tasks"]["T"]
    assert t["usd"] == pytest.approx(3.0)
    assert t["in_tokens"] == 2_000_000 and t["out_tokens"] == 500_000
    assert t["calls"] == 2
    assert m.data["total_usd"] == pytest.approx(3.0)
    m.flush()
    assert json.loads((tmp_path / "cm.json").read_text())["total_usd"] == pytest.approx(3.0)


def test_meter_hard_cap_refuses(tmp_path, monkeypatch):
    m = L.Meter(tmp_path / "cm.json", hard_total_usd=0.000001, budgets={})
    monkeypatch.delenv("ANU_OVERRIDE", raising=False)
    with pytest.raises(L.BudgetExceeded):
        m.preflight("T", "test-model", 1_000_000, 1_000_000)


# --- 3. quarantine read restriction --------------------------------------- #
def test_quarantine_read_restriction(tmp_path, monkeypatch):
    client = make_llm(tmp_path)
    fp, _ = fake_provider(text="secret")
    monkeypatch.setattr(L.LLM, "_provider_complete", fp)
    rec = client.call(task_id="T", model="test-model", system="s",
                      messages=[{"role": "user", "content": "u"}],
                      replicate_tag="r0", quarantine=True)
    assert rec["quarantined"] is True
    key = client.sprint_key("test-model", "s",
                            [{"role": "user", "content": "u"}], 0, 1500, {}, "r0")
    # non-quarantine caller -> raise
    with pytest.raises(L.QuarantineViolation):
        client.read_cache("test-model", key,
                          caller_file=str(SPRINT / "pipeline" / "not_quarantine.py"))
    # auto-detected caller is this test file (tests/, not quarantine) -> raise
    with pytest.raises(L.QuarantineViolation):
        client.read_cache("test-model", key)
    # a pipeline/quarantine/ caller -> allowed
    ok = client.read_cache("test-model", key,
                           caller_file=str(L.QUARANTINE_DIR / "kr2_transcribe.py"))
    assert ok["text"] == "secret"


# --- 4. replicate_tag: distinct tags -> distinct entries (v2.0.1 6a) ------- #
def test_replicate_tag_distinct_entries(tmp_path, monkeypatch):
    client = make_llm(tmp_path)
    fp, calls = fake_provider()
    monkeypatch.setattr(L.LLM, "_provider_complete", fp)
    base = dict(task_id="T", model="test-model", system="s",
                messages=[{"role": "user", "content": "u"}])
    client.call(**base, replicate_tag="11")
    client.call(**base, replicate_tag="22")
    assert calls["n"] == 2, "distinct replicate_tags must each hit the client"
    files = list((tmp_path / "cache" / "test-model").glob("*.json"))
    assert len(files) == 2, "distinct replicate_tags must write two cache entries"


def test_replicate_tag_mandatory(tmp_path):
    client = make_llm(tmp_path)
    with pytest.raises(L.HaltAsk):
        client.call(task_id="T", model="test-model",
                    messages=[{"role": "user", "content": "u"}], replicate_tag="")


# --- 5. secondary cache (v2.0.1 6b): formula fidelity + real hit ----------- #
def test_secondary_cache_formula_fidelity():
    cfg = L.load_config()
    prior_fn = L.load_authoritative_prior_cache_key(Path(cfg["paths"]["eval_prior"]))
    samples = [
        ("gpt-4.1", "sys", "user", 0.0, 1500, None),
        ("claude-sonnet-4-6", "S", "U\nmultiline", 0.0, 1024, None),
        ("gpt-4.1", "s", "u", 0.0, 1500, 3),            # with run_index
        ("claude-haiku-4-5-20251001", "x", "y", 1.0, 800, None),
    ]
    for a in samples:
        assert L.prior_cache_key(*a) == prior_fn(*a), f"formula mismatch for {a}"


def test_secondary_cache_real_hit(tmp_path):
    cfg = L.load_config()
    prior_cache = Path(cfg["paths"]["eval_prior"]) / "eval_out" / "cache"
    files = list(prior_cache.rglob("*.json"))
    assert files, "prior-eval cache expected to exist (W0.1 PASS)"
    f = files[0]
    model, key = f.parent.name, f.stem
    client = make_llm(tmp_path, prior_cache_dir=prior_cache)
    got = client.secondary_get(model, key)
    assert got == json.loads(f.read_text()), "secondary_get must return the real entry"


def test_gemini_haltask_propagates_not_failed(tmp_path, monkeypatch):
    """D-029: an empty/truncated provider response (HaltAsk) must propagate, never become a
    silent FAILED row (which would corrupt B3 panel stats)."""
    client = make_llm(tmp_path)

    def raise_halt(self, model, system, messages, temperature, max_tokens, extra):
        raise L.HaltAsk("gemini empty/truncated response (simulated)")
    monkeypatch.setattr(L.LLM, "_provider_complete", raise_halt)
    import pytest
    with pytest.raises(L.HaltAsk):
        client.call(task_id="B3", model="gemini-pro-latest",
                    messages=[{"role": "user", "content": "x"}], replicate_tag="r0")


def test_gemini_model_version_in_provenance(tmp_path, monkeypatch):
    client = make_llm(tmp_path)

    def fp(self, model, system, messages, temperature, max_tokens, extra):
        return {"text": "ok", "usage": {"input_tokens": 3, "output_tokens": 1},
                "provider": "gemini", "model_version": "gemini-3.8-flash", "finish_reason": "FinishReason.STOP"}
    monkeypatch.setattr(L.LLM, "_provider_complete", fp)
    rec = client.call(task_id="B3", model="gemini-pro-latest",
                      messages=[{"role": "user", "content": "x"}], replicate_tag="r0")
    assert rec["provenance"]["model_version"] == "gemini-3.8-flash"
    assert rec["provenance"]["finish_reason"] == "FinishReason.STOP"
