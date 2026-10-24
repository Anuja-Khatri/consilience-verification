#!/usr/bin/env python3
"""
pipeline/b3_rerun.py — B3 FULL-COVERAGE rerun with a pinned Gemini pro model (owner: billing enabled,
Tier 1, same key). SPEC §B3 / §4.2. Runid B3-2 (supersedes the flash best-effort B3-1 at full coverage).

Billing is now on, so the §4.2 pro tier is attempted at FULL coverage (all 95 typing claims + 60 grade
items), with NO circuit-breaker and NO flash fallback. The resolved pro model_version is recorded PER CALL
(D-029 provenance). OWNER RULE: if ANY Gemini call returns a billing/quota error (or any non-parse /
HaltAsk), STOP immediately and report — do NOT silently degrade to flash or PANEL=1.

Reuses pipeline/b3_panel.py's prompts, data loaders, and b31_panel/b32_grades (monkeypatching its
`_gemini` with a strict halt-on-error variant and its `GEM` with the resolved pinned pro).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())

import b3_panel as B3  # noqa: E402  (prompts, data, b31_panel/b32_grades)
import stats as ST  # noqa: E402
from llm import HaltAsk  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402


class BillingHalt(RuntimeError):
    pass


def resolve_pro():
    """List reachable Gemini models; pick a PINNED pro (version-suffixed) over -latest. Returns (chosen, all_pro)."""
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    # TEXT gemini pros only: name starts with 'gemini', is a 'pro', supports generateContent, and is NOT a
    # media/tool variant (llm.py only adapts text gemini-* chat models; nano-banana/lyria/image/tts/customtools excluded)
    EXCLUDE = ("image", "tts", "audio", "vision", "embedding", "customtools", "aqa", "tuning", "banana", "lyria", "deep-research")
    pro = []
    for m in client.models.list():
        name = str(getattr(m, "name", "")).split("/")[-1]
        acts = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
        low = name.lower()
        if low.startswith("gemini") and "pro" in low and not any(x in low for x in EXCLUDE) \
                and (not acts or "generateContent" in acts):
            pro.append(name)
    # prefer the HIGHEST-version pinned pro (older "stable" ids like gemini-2.5-pro are 404-deprecated for
    # new users; Google directs to the current gemini-3.x pro); -latest is the last resort.
    def ver(p):
        mm = re.search(r"gemini-(\d+)\.(\d+)", p)
        v = (int(mm.group(1)), int(mm.group(2))) if mm else (0, 0)
        return (0 if p.endswith("latest") else 1, v)   # de-prioritise -latest
    chosen = sorted(pro, key=ver)[-1] if pro else None
    return chosen, sorted(set(pro))


def strict_gemini(system, user, max_tokens):
    """Halt-on-error Gemini call (owner rule). Captures model_version; raises BillingHalt on any
    quota/billing/non-parse/HaltAsk rather than degrading."""
    B3.gem["tried"] += 1
    try:
        # gemini-3.x-pro is thinking-only: give generous output headroom (thinking tokens are separate but
        # a small max_output_tokens risks a MAX_TOKENS finish → HaltAsk). D-058.
        rec = B3.CLIENT.call_json(task_id="B3", model=B3.GEM, system=system,
                                  messages=[{"role": "user", "content": user}], replicate_tag="b3rr",
                                  temperature=0, max_tokens=max(max_tokens, 3000))
    except HaltAsk as e:
        raise BillingHalt(f"gemini {B3.GEM} HaltAsk: {str(e)[:200]}")
    mv = (rec.get("provenance") or {}).get("model_version")
    if mv:
        B3.gem["versions"].add(mv)
    parsed = rec.get("parsed")
    if parsed is None:
        raise BillingHalt(f"gemini {B3.GEM} returned no parse — model_version={mv}, FAILED={rec.get('FAILED')}, "
                          f"json_status={rec.get('json_status')}, finish={(rec.get('provenance') or {}).get('finish_reason')}. "
                          f"Per owner rule, treating any Gemini billing/quota/availability failure as STOP-and-report.")
    B3.gem["got"] += 1
    return parsed


def main() -> int:
    try:
        chosen, pro = resolve_pro()
    except Exception as e:  # noqa: BLE001
        print(f"[B3-rerun] STOP — could not list Gemini models (billing/auth?): {type(e).__name__}: {str(e)[:160]}")
        return 1
    print(f"[B3-rerun] reachable Gemini pro models: {pro}")
    if not chosen:
        print("[B3-rerun] STOP — no Gemini pro model reachable even with billing; report to owner (no flash fallback per the rerun's full-coverage intent).")
        return 1
    print(f"[B3-rerun] pinned pro model resolved: {chosen}")

    B3.GEM = chosen
    B3.GEM_BREAKER = 10 ** 9
    B3.gem = {"ok": True, "consec_fail": 0, "got": 0, "tried": 0, "versions": set()}
    B3._gemini = strict_gemini  # monkeypatch → b31_panel/b32_grades resolve this global at call time

    try:
        strict_gemini("Output ONLY JSON {\"ok\": true}.", "reply ok", 400)   # liveness on the pro model
        print(f"[B3-rerun] liveness OK on {chosen} (model_version {sorted(B3.gem['versions'])})")

        idx = B3.A3D.claims_index()
        passages_by_id = {p["passage_id"]: p for ps in B3.A3D.passages_by_theory().values() for p in ps}
        claims = [idx[k] for k in sorted(idx)]
        p_rows = B3.b31_panel(claims, passages_by_id)                 # FULL coverage
        n = len(p_rows)
        cov = sum(1 for r in p_rows if r[B3.GEM] is not None)

        ge, me = B3._paired(p_rows, "entity_type")
        ga, ma = B3._paired(p_rows, "axis")
        gp, mp = B3._paired(p_rows, "polarity")
        xkappa = {"panel_entity_kappa": round(ST.cohen_kappa(ge, me), 3),
                  "panel_axis_kappa": round(ST.cohen_kappa(ga, ma), 3),
                  "panel_polarity_pabak": round(ST.pabak(gp, mp), 3)}
        gpt_e = [str(r[B3.GPT].get("entity_type")) for r in p_rows]; eng_e = [str(r["engine"]["entity_type"]) for r in p_rows]
        gpt_a = [str(r[B3.GPT].get("axis")) for r in p_rows]; eng_a = [str(r["engine"]["axis"]) for r in p_rows]

        items_all = json.loads((SPRINT / "bench" / "items.json").read_text())["items"]
        rank = sorted(range(len(items_all)),
                      key=lambda i: hashlib.sha256(f"{B3.SEED}:{items_all[i]['item_id']}".encode()).hexdigest())
        sub = [items_all[i] for i in sorted(rank[:60])]
        g_rows = B3.b32_grades(sub)
        gcov = sum(1 for r in g_rows if r[B3.GEM] is not None)
        consensus = [(r[B3.GPT], r["judge"]) for r in g_rows if r[B3.GEM] is not None and r[B3.GPT] is not None and r[B3.GPT] == r[B3.GEM]]
        modal = round(sum(1 for m, j in consensus if m == j) / len(consensus), 3) if consensus else "not-applicable"
        gpt_vs_judge = round(ST.percent_agreement([str(r[B3.GPT]) for r in g_rows], [str(r["judge"]) for r in g_rows]), 3)
    except BillingHalt as e:
        (SPRINT / "results" / "b3_rerun_status.json").write_text(json.dumps(
            {"status": "STOPPED", "model": B3.GEM, "model_versions": sorted(B3.gem["versions"]),
             "gemini_tried": B3.gem["tried"], "gemini_got": B3.gem["got"], "error": str(e)}, indent=2) + "\n")
        print(f"[B3-rerun] STOP (billing/quota) after {B3.gem['tried']} gemini calls ({B3.gem['got']} ok): {e}")
        print(f"[B3-rerun] meter ${B3.CLIENT.meter.data['total_usd']:.4f}")
        return 1

    versions = sorted(B3.gem["versions"])
    reg = Registry()
    base = dict(task="B3", runid="B3-2", instrument_tag="v2", corpus_tag="v1", preregistered=False, pilot=False)
    CAV = (f"B3 FULL-COVERAGE rerun — Gemini billing enabled (Tier 1, same key). Pinned pro model "
           f"'{B3.GEM}'; resolved model_version(s) {versions} (recorded per call, D-029). gpt-4.1 + Gemini "
           f"pro two-vendor panel; NO circuit-breaker, NO flash fallback; any billing/quota error STOPS the "
           f"run. Supersedes the flash best-effort B3-1 (gemini coverage was ~8%). qwen/llama still deferred "
           f"(no TOGETHER/FIREWORKS key). Cross-vendor κ over items where both vendors returned a label; "
           f"a 'modal' grade = the 2-vendor consensus.")
    for k, v in xkappa.items():
        reg.upsert(metric_id=f"b3.{k}", value=v, n=cov, caveats=[CAV, f"gemini coverage {cov}/{n} (full)",
                   "protocol reproducibility, not validity"], **base)
    reg.upsert(metric_id="b3.gpt_vs_engine_entity", value=round(ST.percent_agreement(gpt_e, eng_e), 3), n=n, caveats=[CAV], **base)
    reg.upsert(metric_id="b3.gpt_vs_engine_axis", value=round(ST.percent_agreement(gpt_a, eng_a), 3), n=n, caveats=[CAV], **base)
    reg.upsert(metric_id="b3.gemini_coverage", value=round(cov / n, 3) if n else 0.0, n=n,
               caveats=[CAV, f"{cov}/{n} claims received a Gemini-pro label (FULL coverage, billing enabled)"], **base)
    reg.upsert(metric_id="b3.grade_modal_agreement", value=modal, n=len(consensus),
               caveats=[CAV, f"panel consensus vs judge over {len(consensus)} items (gemini grade coverage {gcov}/60)"], **base)
    reg.upsert(metric_id="b3.grade_gpt_vs_judge", value=gpt_vs_judge, n=len(g_rows), caveats=[CAV], **base)
    reg.save()

    (SPRINT / "results" / "b3_rerun.json").write_text(json.dumps(
        {"model": B3.GEM, "model_versions": versions, "typing_coverage": f"{cov}/{n}",
         "grade_coverage": f"{gcov}/60", "cross_vendor_kappa": xkappa, "modal_vs_judge": modal,
         "gpt_vs_judge": gpt_vs_judge, "gemini_tried": B3.gem["tried"], "gemini_got": B3.gem["got"]},
        ensure_ascii=False, indent=2) + "\n")
    write_manifest("B3", "B3-2", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(SPRINT / "bench" / "items.json"), "bench")],
                   outputs=["results/b3_rerun.json"],
                   model_provenance=[{"role": "panel", "model": B3.GPT},
                                     {"role": "panel", "model": B3.GEM, "model_versions": versions}],
                   notes=f"B3 full-coverage rerun; Gemini pro {B3.GEM} ({versions}); typing cov {cov}/{n}, grades {gcov}/60; billing enabled")
    print(f"[B3-rerun] FULL coverage: typing {cov}/{n}, grades {gcov}/60; model {B3.GEM} {versions}")
    print(f"[B3-rerun] cross-vendor κ {xkappa}; modal-vs-judge {modal}; gpt-vs-judge {gpt_vs_judge}")
    print(f"[B3-rerun] meter ${B3.CLIENT.meter.data['total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
