#!/usr/bin/env python3
"""
pipeline/b3_panel.py — B3 reliability battery, expert-free (SPEC §4 B3). Multi-vendor panel
with the spec's "panel reduction + printed limitation" latitude when a vendor leg is unavailable.

Vendors: gpt-4.1 (always) + gemini-flash-latest (best-effort). The §4.2 fallback chain
gemini-2.5-pro → gemini-2.0-pro → any ≥1.5-pro is UNREACHABLE for this key (2.5-pro retired/404,
D-028; every pro/≥1.5-pro tier returns 429 RESOURCE_EXHAUSTED, verified 2026-10-23). The only
reachable Gemini is gemini-flash-latest (→ gemini-3.8-flash) and even it is rate/quota limited,
so the Gemini leg is run BEST-EFFORT: a liveness probe, paced calls, and a circuit-breaker on
repeated failures. κ is computed over the items where BOTH vendors returned a label; Gemini
COVERAGE is reported honestly; if Gemini is exhausted the run degrades to PANEL=1 and the
cross-vendor κ is recorded `not-applicable` (NEVER faked). Open-weight (qwen/llama) deferred
pending a TOGETHER/FIREWORKS key.

B3.1 per-claim typing {entity_type, axis, polarity} from source passages, instrument-v2 defs.
B3.2 grade 60 seeded bench items ∈ {formal,partial,generative,none} vs the judge (fork→none).
B3.3 republish the adopted A5 stability as the standing self-consistency score.
Gemini model_version captured per D-029. Budget B3 $90.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
sys.path.insert(0, str(ENGINE / "pipeline"))
sys.path.insert(0, str(ENGINE / "eval"))

import p2_extract as P2  # noqa: E402
import a5_freeze as FRZ  # noqa: E402
import a3_dossiers as A3D  # noqa: E402
import stats as ST  # noqa: E402
import llm as L  # noqa: E402
from llm import HaltAsk  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

GPT = "gpt-4.1"
GEM = "gemini-flash-latest"
GEM_TARGET = "gemini-2.5-pro (spec); all pro/≥1.5-pro tiers 404/429 → gemini-flash-latest fallback"
GEM_PACE_S = 2.0          # pace Gemini to respect its low RPM
GEM_RETRY = [2, 3]        # SHORT backoff: fail fast on transient 429/503 (free-tier is flaky)
GEM_BREAKER = 8           # consecutive Gemini failures → trip the breaker, finish PANEL=1
DEFS = FRZ.definitions_block()
SEED = CFG["seeds"]["global"]
CLIENT = L.LLM()

gem = {"ok": True, "consec_fail": 0, "got": 0, "tried": 0, "versions": set()}

PANEL_LIMITATION = ("PANEL: gpt-4.1 always; gemini-flash-latest best-effort (a smaller tier than the "
                    "spec's ≥1.5-pro target — every pro/≥1.5-pro Gemini tier is 404/429 for this key, "
                    "affects κ interpretation). Open-weight (qwen2.5-72b/llama-3.3-70b) deferred "
                    "pending a TOGETHER/FIREWORKS key. Cross-vendor κ is over items where BOTH vendors "
                    "returned a label; Gemini coverage is reported. A 'modal' grade = the 2-vendor "
                    "consensus (ties = no consensus).")

TYPE_SYS = ("Derive the (entity_type, axis, polarity) of the theory's claim from ONLY the passages "
            f"below. entity_type must be one of {sorted(P2.ENTITY_TYPES)}; axis one of "
            f"{sorted(P2.AXES)} (use 'none' if it commits to no axis); polarity is asserts or denies.\n"
            + DEFS + "\nOutput ONLY JSON {\"entity_type\": ..., \"axis\": ..., \"polarity\": ...}.")

GRADE_SYS = (
    "Grade the correspondence between two typed theory-claims. Definitions:\n"
    "- formal: same axis and polarity AND matching typed-neighbour values on >=2 of "
    "(relation, endpoint axis, endpoint value-family). (Cross-theory pairs are capped at partial.)\n"
    "- partial: a shared measurement space / same axis with a shared relation, but fewer than two "
    "matching neighbour values.\n"
    "- generative: the same axis but different value-families (an analogy, not an alignment).\n"
    "- none: no correspondence — different axes, or the two claims oppose (a disagreement).\n"
    "Judge from the quoted claims alone. Output ONLY JSON {\"grade\": \"formal|partial|generative|none\"}.")


def _gpt(system, user, max_tokens):
    rec = CLIENT.call_json(task_id="B3", model=GPT, system=system,
                           messages=[{"role": "user", "content": user}], replicate_tag="b3",
                           temperature=0, max_tokens=max_tokens)
    return rec.get("parsed") or {}


def _gemini(system, user, max_tokens):
    """Best-effort Gemini call. Returns parsed dict or None (unavailable). Trips the breaker on
    repeated failures. A genuine empty/truncated-but-200 response still raises HaltAsk (D-029)."""
    if not gem["ok"]:
        return None
    time.sleep(GEM_PACE_S)
    gem["tried"] += 1
    rec = CLIENT.call_json(task_id="B3", model=GEM, system=system,
                           messages=[{"role": "user", "content": user}], replicate_tag="b3",
                           temperature=0, max_tokens=max(max_tokens, 400), retry_delays=GEM_RETRY)
    mv = (rec.get("provenance") or {}).get("model_version")
    if mv:
        gem["versions"].add(mv)
    parsed = rec.get("parsed")
    if parsed:
        gem["consec_fail"] = 0
        gem["got"] += 1
        return parsed
    # parsed is None/empty → a 429-exhausted FAILED placeholder (not a HaltAsk). Count + maybe break.
    gem["consec_fail"] += 1
    if gem["consec_fail"] >= GEM_BREAKER:
        gem["ok"] = False
        print(f"  [gemini circuit-breaker tripped after {gem['consec_fail']} consecutive failures "
              f"at call {gem['tried']}; finishing PANEL=1 for the remainder]")
    return None


def probe_gemini():
    try:
        p = _gemini("Output ONLY JSON {\"ok\": true}.", "reply ok", 400)
        if p is None:
            gem["ok"] = False
        print(f"  [gemini liveness probe: {'OK' if gem['ok'] else 'UNAVAILABLE (429) → PANEL=1'}]")
    except HaltAsk as e:
        gem["ok"] = False
        print(f"  [gemini liveness probe HaltAsk → PANEL=1: {str(e)[:80]}]")


def b31_panel(claims, passages_by_id):
    rows = []
    for c in claims:
        excerpt = "\n".join(f'[{i}] {A3D.cap(passages_by_id[i]["text"], 120)}'
                            for i in c.get("passage_ids", []) if i in passages_by_id)
        if not excerpt:
            continue
        user = f"Theory: {c['theory']}\nClaim: {c['statement']}\nPassages:\n{excerpt}"
        g = _gpt(TYPE_SYS, user, 150)
        gm = _gemini(TYPE_SYS, user, 150)
        rows.append({"claim_id": c["claim_id"],
                     "engine": {k: c[k] for k in ("entity_type", "axis", "polarity")},
                     GPT: {k: g.get(k) for k in ("entity_type", "axis", "polarity")},
                     GEM: ({k: gm.get(k) for k in ("entity_type", "axis", "polarity")} if gm else None)})
    return rows


def _paired(rows, field):
    """(gpt, gemini) label columns over rows where BOTH present."""
    a, b = [], []
    for r in rows:
        if r[GEM] is not None:
            a.append(str(r[GPT].get(field)))
            b.append(str(r[GEM].get(field)))
    return a, b


def b32_grades(items):
    rows = []
    for it in items:
        user = (f"Claim A ({it['typed_a'].get('axis')}/{it['typed_a'].get('polarity')}): "
                f"{A3D.cap(it['text_a'], 90)}\n"
                f"Claim B ({it['typed_b'].get('axis')}/{it['typed_b'].get('polarity')}): "
                f"{A3D.cap(it['text_b'], 90)}")
        judge = "none" if it["grade"] == "fork" else it["grade"]
        g = _gpt(GRADE_SYS, user, 120)
        gm = _gemini(GRADE_SYS, user, 120)
        okset = {"formal", "partial", "generative", "none"}
        rows.append({"item_id": it["item_id"], "judge": judge,
                     GPT: (g.get("grade") if g.get("grade") in okset else None),
                     GEM: (gm.get("grade") if (gm and gm.get("grade") in okset) else None)})
    return rows


def main() -> int:
    idx = A3D.claims_index()
    passages_by_id = {p["passage_id"]: p for ps in A3D.passages_by_theory().values() for p in ps}
    claims = [idx[k] for k in sorted(idx)]
    reg = Registry()
    base = dict(task="B3", runid="B3-1", instrument_tag="v2", corpus_tag="v1",
                preregistered=False, pilot=False)
    NA = "not-applicable"
    probe_gemini()

    # ---- B3.1 ----
    p_rows = b31_panel(claims, passages_by_id)
    n = len(p_rows)
    cov = sum(1 for r in p_rows if r[GEM] is not None)
    gpt_e, eng_e = [str(r[GPT].get("entity_type")) for r in p_rows], [str(r["engine"]["entity_type"]) for r in p_rows]
    gpt_a, eng_a = [str(r[GPT].get("axis")) for r in p_rows], [str(r["engine"]["axis"]) for r in p_rows]
    panel_ok = cov >= 2
    if panel_ok:
        ge, me = _paired(p_rows, "entity_type")
        ga, ma = _paired(p_rows, "axis")
        gp, mp = _paired(p_rows, "polarity")
        xkappa = {"panel_entity_kappa": round(ST.cohen_kappa(ge, me), 3),
                  "panel_axis_kappa": round(ST.cohen_kappa(ga, ma), 3),
                  "panel_polarity_pabak": round(ST.pabak(gp, mp), 3)}
    else:
        xkappa = {"panel_entity_kappa": NA, "panel_axis_kappa": NA, "panel_polarity_pabak": NA}
    cov_cav = f"gemini coverage {cov}/{n}" + ("" if panel_ok else " → cross-vendor κ not-applicable (PANEL=1)")
    for k, v in xkappa.items():
        reg.upsert(metric_id=f"b3.{k}", value=v, n=(cov if panel_ok else 0),
                   caveats=[PANEL_LIMITATION, cov_cav, "protocol reproducibility, not validity"], **base)
    reg.upsert(metric_id="b3.gpt_vs_engine_entity", value=round(ST.percent_agreement(gpt_e, eng_e), 3), n=n,
               caveats=[PANEL_LIMITATION, "gpt-4.1 typing vs the engine's approved labels"], **base)
    reg.upsert(metric_id="b3.gpt_vs_engine_axis", value=round(ST.percent_agreement(gpt_a, eng_a), 3), n=n,
               caveats=[PANEL_LIMITATION], **base)
    reg.upsert(metric_id="b3.gemini_coverage", value=round(cov / n, 3) if n else 0.0, n=n,
               caveats=[PANEL_LIMITATION, f"{cov}/{n} claims received a gemini-flash label before quota limits"], **base)
    (SPRINT / "results" / "b3_panel_typing.json").write_text(
        json.dumps({"n": n, "vendors": [GPT, GEM], "gemini_coverage": cov, "panel2": panel_ok,
                    "metrics": xkappa, "rows": p_rows, "limitation": PANEL_LIMITATION}, ensure_ascii=False, indent=2))

    # ---- B3.2 ----
    items_all = json.loads((SPRINT / "bench" / "items.json").read_text())["items"]
    rank = sorted(range(len(items_all)),
                  key=lambda i: hashlib.sha256(f"{SEED}:{items_all[i]['item_id']}".encode()).hexdigest())
    sub = [items_all[i] for i in sorted(rank[:60])]
    g_rows = b32_grades(sub)
    gcov = sum(1 for r in g_rows if r[GEM] is not None)
    consensus = [(r[GPT], r["judge"]) for r in g_rows if r[GEM] is not None and r[GPT] is not None and r[GPT] == r[GEM]]
    modal_agree = round(sum(1 for m, j in consensus if m == j) / len(consensus), 3) if consensus else NA
    gpt_vs_judge = round(ST.percent_agreement([str(r[GPT]) for r in g_rows], [str(r["judge"]) for r in g_rows]), 3)
    dist = {"judge": dict(Counter(r["judge"] for r in g_rows)),
            GPT: dict(Counter(str(r[GPT]) for r in g_rows)),
            GEM: dict(Counter(str(r[GEM]) for r in g_rows))}
    reg.upsert(metric_id="b3.grade_modal_agreement", value=modal_agree, n=len(consensus),
               caveats=[PANEL_LIMITATION, f"panel consensus vs judge over {len(consensus)} items where both "
                        f"vendors agree (gemini coverage {gcov}/60); judge `fork`→`none`"], **base)
    reg.upsert(metric_id="b3.grade_gpt_vs_judge", value=gpt_vs_judge, n=len(g_rows),
               caveats=[PANEL_LIMITATION, "gpt-4.1 grade vs the judge's grade (fork→none)"], **base)
    (SPRINT / "results" / "b3_grade_distribution.json").write_text(
        json.dumps({"n": len(g_rows), "gemini_coverage": gcov, "distribution": dist,
                    "modal_agreement": modal_agree, "gpt_vs_judge": gpt_vs_judge,
                    "rows": g_rows, "limitation": PANEL_LIMITATION}, ensure_ascii=False, indent=2))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        cats = ["formal", "partial", "generative", "none"]
        who = ["judge", GPT] + ([GEM] if gcov else [])
        x = np.arange(len(cats)); w = 0.8 / len(who)
        fig, ax = plt.subplots(figsize=(7, 4))
        for j, wname in enumerate(who):
            ax.bar(x + (j - (len(who) - 1) / 2) * w, [dist[wname].get(c, 0) for c in cats], w, label=wname)
        ax.set_xticks(x); ax.set_xticklabels(cats); ax.set_ylabel("count (of 60)")
        ax.set_title(f"B3.2 grade distribution vs judge (gemini cov {gcov}/60)"); ax.legend()
        fig.tight_layout(); fig.savefig(SPRINT / "results" / "b3_grade_distribution.png", dpi=110)
        plt.close(fig)
    except Exception as e:
        print(f"  (plot skipped: {e})")

    # ---- B3.3 ----
    a5 = {m["metric_id"]: m for m in reg.data["metrics"] if m["metric_id"].startswith("a5.stability")}
    adopted = next((v for k, v in a5.items() if "baseline" in k or "consensus" in k or "adopt" in k), None)
    if adopted is None and a5:
        adopted = list(a5.values())[0]
    if adopted is not None:
        reg.upsert(metric_id="b3.self_consistency_standing", value=adopted["value"], n=adopted.get("n", 0),
                   caveats=["B3.3 republishes the adopted A5 stability (" + adopted["metric_id"] +
                            ") as the standing self-consistency score; per-theory breakdown in a5.*"], **base)

    reg.save()
    write_manifest("B3", "B3-1", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(SPRINT / "bench" / "items.json", "bench"),
                           {"path": "engine approved claims + passages (read-only)", "kind": "corpus", "sha256": None}],
                   outputs=["results/b3_panel_typing.json", "results/b3_grade_distribution.json",
                            "results/b3_grade_distribution.png"],
                   notes=f"B3 panel; gpt-4.1 + gemini-flash best-effort [{GEM_TARGET}]; gemini coverage "
                         f"typing {cov}/{n}, grades {gcov}/60; model_versions={sorted(gem['versions'])}; "
                         "open-weight deferred")
    print(f"B3.1 (n={n}, gemini cov {cov}): cross-vendor {xkappa}; "
          f"gpt-vs-engine axis={round(ST.percent_agreement(gpt_a, eng_a), 3)}.")
    print(f"B3.2 (60, gemini cov {gcov}): modal-vs-judge={modal_agree} (on {len(consensus)} consensus); "
          f"gpt-vs-judge={gpt_vs_judge}; dist judge={dist['judge']}.")
    print(f"  gemini model_version(s): {sorted(gem['versions'])}")
    print(f"  meter ${CLIENT.meter.data['total_usd']:.4f} (B3 budget ${CFG['budget_usd']['B3']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
