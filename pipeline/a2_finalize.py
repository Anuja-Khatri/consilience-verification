#!/usr/bin/env python3
"""
pipeline/a2_finalize.py — A2.4 + A2.5 + A2.6 (SPEC §A2), post-packet. $0 (judge/decidability port).

Consumes the Anu-approved review/a2_claims.csv (96 approve / 13 reject) and runs:
  A2.4  Vocabulary discipline — per pair, fraction of APPROVED claims with axis:none; >50% ⇒
        `untypeable-under-v1-vocab` (a REPORTED finding). Only if ≥8 pairs are untypeable does the
        ≤6-new-axis PROPOSAL protocol trigger (A2.4); otherwise untypeability is simply measured.
  A2.5  Judge + decidability — per-pair mini-graph from approved claims (side a vs side b) via the
        W0.4 judge port; the two sides are forced cross-"theory" (SIDE_A/SIDE_B) so the judge treats
        the match as cross-domain. new_grade = best correspondence grade (formal>partial>generative),
        else `fork`, else `none`. Decidability via the ported p6 (MIU domains aren't in the engine's
        observable tables → expected `not_current`; reported honestly).
  A2.6  Comparison — results/a2_comparison.json + docs/tables/A2.md: pair | old MIU tier | old
        decidability | new grade | flags | new decidability | delta | reason. Metrics
        a2.agreement_rate, a2.downgrade_rate, a2.survivor_vs_failure_separation (A1-survivors graded
        above A1-failures? 2×2 + Fisher exact — tiny N, reported honestly).

DISCLOSURE (D-035): the claim decisions were model-drafted suggestions reviewed and confirmed by Anu.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))

import p5_judge as P5  # noqa: E402
import p6_decidability as P6  # noqa: E402
import stats as S  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

ENGINE_RANK = {"formal": 3, "partial": 2, "generative": 1, "fork": 0.5, "none": 0}
MIU_RANK = {"isomorphism": 3, "partial": 2, "generative": 1, "thematic": 1, "conditional": 1}


def new_grade(forks, corrs):
    if corrs:
        best = max(corrs, key=lambda g: ENGINE_RANK.get(g, 0))
        return best
    if forks:
        return "fork"
    return "none"


def classify(old_grade, ng, untypeable):
    if untypeable:
        return "untypeable", "pair is >50% axis:none under v1 vocab (A2.4)"
    if not old_grade or old_grade not in MIU_RANK:
        # no MIU tier to compare against — flip-to-none is only meaningful WITH a baseline
        return "no-baseline", f"no MIU tier recorded for this match (old_grade={old_grade}); new grade={ng}"
    if ng == "none":
        return "flipped-to-none", f"had old tier {old_grade}; re-adjudicated sides no longer correspond under v2"
    nr, orr = ENGINE_RANK[ng], MIU_RANK[old_grade]
    if nr == orr:
        return "agrees", f"new {ng} == old {old_grade} (rank {nr})"
    if nr < orr:
        return "downgraded", f"new {ng} (rank {nr}) < old {old_grade} (rank {orr})"
    return "upgraded", f"new {ng} (rank {nr}) > old {old_grade} (rank {orr})"


def main() -> int:
    approved = {r["claim_id"] for r in csv.DictReader(open(SPRINT / "review" / "a2_claims.csv"))
                if r["decision"] == "approve"}
    rejected = {r["claim_id"] for r in csv.DictReader(open(SPRINT / "review" / "a2_claims.csv"))
                if r["decision"] == "reject"}
    v2 = json.loads((SPRINT / "runs" / "A2" / "A2-1" / "v2_claims.json").read_text())

    rows, vocab_rows = [], []
    untypeable_pairs = []
    for pr in v2["pairs"]:
        a = [c for c in pr["sides"]["a"]["claims"] if c["claim_id"] in approved]
        b = [c for c in pr["sides"]["b"]["claims"] if c["claim_id"] in approved]
        allc = a + b
        none_n = sum(1 for c in allc if c.get("axis") == "none")
        frac_none = (none_n / len(allc)) if allc else 0.0
        untypeable = len(allc) > 0 and frac_none > 0.5
        if untypeable:
            untypeable_pairs.append(pr["match_id"])
        vocab_rows.append({"match_id": pr["match_id"], "n_approved": len(allc), "axis_none": none_n,
                           "frac_none": round(frac_none, 3), "untypeable": untypeable})

        # A2.5 judge mini-graph (force cross-"theory")
        ga = {"theory": "SIDE_A", "nodes": [{**c, "theory": "SIDE_A"} for c in a], "edges": []}
        gb = {"theory": "SIDE_B", "nodes": [{**c, "theory": "SIDE_B"} for c in b], "edges": []}
        out = P5.judge_pair(ga, gb) if (a and b) else {"forks": [], "correspondences": []}
        corr_grades = [c.get("grade") for c in out["correspondences"] if c.get("kind") != "shared_measurement_space"]
        fork_axes = sorted({f["axis"] for f in out["forks"]})
        axis_of = {c["claim_id"]: c.get("axis") for c in allc}
        corr_axes = sorted({axis_of.get(c["left_ids"][0]) for c in out["correspondences"]
                            if c.get("kind") != "shared_measurement_space" and axis_of.get(c["left_ids"][0])})
        ng = new_grade(fork_axes, corr_grades)
        flags = []
        if out["forks"]:
            flags.append(f"fork@{','.join(fork_axes)}")
        if any(c.get("kind") == "shared_measurement_space" for c in out["correspondences"]):
            flags.append("smc")

        # A2.5 decidability on the primary contested axis (domains aren't engine theories → not_current)
        prim_axis = (fork_axes or corr_axes or [None])[0]
        dom_a, dom_b = pr["sides"]["a"].get("domain"), pr["sides"]["b"].get("domain")
        new_decid = "n/a (no shared axis)"
        if prim_axis:
            try:
                v = P6.decide(prim_axis, dom_a or "A", dom_b or "B")
                new_decid = v.get("decidability", "not_current")
            except Exception as e:  # noqa: BLE001
                new_decid = f"not_current ({type(e).__name__})"

        delta, reason = classify(pr.get("old_grade"), ng, untypeable)
        rows.append({"match_id": pr["match_id"], "role": pr["role"], "a1_first_fail": pr["a1_first_fail"],
                     "old_grade": pr.get("old_grade"), "old_decidability": pr.get("old_decidability"),
                     "n_approved_a": len(a), "n_approved_b": len(b), "new_grade": ng,
                     "new_flags": "|".join(flags), "new_decidability": new_decid,
                     "frac_axis_none": round(frac_none, 3), "delta": delta, "reason": reason})

    # ── A2.6 metrics ──
    baselined = [r for r in rows if r["delta"] not in ("no-baseline", "untypeable")]
    agrees = sum(1 for r in rows if r["delta"] == "agrees")
    downgr = sum(1 for r in rows if r["delta"] in ("downgraded", "flipped-to-none"))
    n_base = len(baselined)
    agreement_rate = round(agrees / n_base, 4) if n_base else 0.0
    downgrade_rate = round(downgr / n_base, 4) if n_base else 0.0

    # survivor vs failure separation: corresponds (formal/partial/generative) vs not (fork/none)
    def corresponds(r):
        return r["new_grade"] in ("formal", "partial", "generative")
    surv = [r for r in rows if r["role"] == "survivor"]
    fail = [r for r in rows if r["role"] == "failure"]
    a11 = sum(1 for r in surv if corresponds(r)); a10 = len(surv) - a11
    a01 = sum(1 for r in fail if corresponds(r)); a00 = len(fail) - a01
    try:
        _, fisher_p = S.fisher_exact([[a11, a10], [a01, a00]])
    except Exception:  # noqa: BLE001
        fisher_p = None

    from collections import Counter
    delta_dist = dict(Counter(r["delta"] for r in rows))
    comparison = {"n_pairs": len(rows), "approved_claims": len(approved), "rejected_claims": len(rejected),
                  "delta_distribution": delta_dist, "n_baselined": n_base,
                  "agreement_rate": agreement_rate, "downgrade_rate": downgrade_rate,
                  "untypeable_pairs": untypeable_pairs,
                  "survivor_vs_failure": {"table_[[surv_corr,surv_not],[fail_corr,fail_not]]": [[a11, a10], [a01, a00]],
                                          "fisher_p": fisher_p},
                  "vocab": vocab_rows, "rows": rows}
    (SPRINT / "results" / "a2_comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n")

    DISCLOSURE = "Decisions were model-drafted suggestions (Claude) reviewed and confirmed by Anu."
    cav = (f"A2 MIU re-adjudication through instrument v2 (96 approve / 13 reject of 109 re-extracted). "
           f"new_grade from the ported judge on per-pair mini-graphs (sides forced cross-theory). {DISCLOSURE} "
           f"Baseline = the OLD MIU tier where recorded ({n_base}/{len(rows)} pairs had one; "
           f"{delta_dist.get('no-baseline',0)} matches carried no MIU grade and are excluded from the rates). "
           f"axis:none rows deliberately APPROVED so A2.4 untypeability is measured, not filtered.")
    reg = Registry()
    base = dict(task="A2", runid="A2-1", instrument_tag="v2", corpus_tag="v1", preregistered=True, pilot=False)
    reg.upsert(metric_id="a2.agreement_rate", value=agreement_rate, n=n_base,
               caveats=[cav, f"{agrees}/{n_base} baselined pairs where new grade == old MIU tier; "
                             f"delta distribution {delta_dist}"], **base)
    reg.upsert(metric_id="a2.downgrade_rate", value=downgrade_rate, n=n_base,
               caveats=[cav, f"{downgr}/{n_base} baselined pairs downgraded or flipped-to-none"], **base)
    reg.upsert(metric_id="a2.survivor_vs_failure_separation",
               value=(round(fisher_p, 4) if isinstance(fisher_p, float) else "n/a"), n=len(rows),
               caveats=[cav, f"2×2 survivor/failure × corresponds/not = [[{a11},{a10}],[{a01},{a00}]]; "
                             f"Fisher exact p={fisher_p}. Only {len(surv)} A1-survivors → severely "
                             f"underpowered; reported as-is (not a significance claim)."], **base)
    reg.upsert(metric_id="a2.untypeable_pairs", value=len(untypeable_pairs), n=len(rows),
               caveats=[f"pairs >50% axis:none under v1 vocab (A2.4 untypeability, MEASURED not filtered): "
                        f"{untypeable_pairs or 'none'}. The ≤6-new-axis PROPOSAL protocol triggers only at "
                        f"≥8 untypeable pairs ({len(untypeable_pairs)} here → {'TRIGGERED' if len(untypeable_pairs)>=8 else 'not triggered'})."],
               **base)
    reg.save()

    # table
    lines = ["# docs/tables/A2.md — MIU re-adjudication through instrument v2 (A2.6)", "",
             f"96 approve / 13 reject of 109 re-extracted claims. {DISCLOSURE}", "",
             f"agreement_rate **{agreement_rate}** · downgrade_rate **{downgrade_rate}** "
             f"(over {n_base} baselined pairs) · untypeable {len(untypeable_pairs)} · "
             f"survivor-vs-failure Fisher p={fisher_p}", "",
             "| pair | role | a1_fail | old tier | new grade | flags | new decid | axis:none | delta |",
             "|---|---|---|---|---|---|---|--:|---|"]
    for r in rows:
        lines.append(f"| {r['match_id']} | {r['role']} | {r['a1_first_fail'] or '—'} | {r['old_grade'] or '—'} | "
                     f"{r['new_grade']} | {r['new_flags'] or '—'} | {r['new_decidability']} | "
                     f"{r['frac_axis_none']} | {r['delta']} |")
    (SPRINT / "docs" / "tables").mkdir(parents=True, exist_ok=True)
    (SPRINT / "docs" / "tables" / "A2.md").write_text("\n".join(lines) + "\n")

    write_manifest("A2", "A2-6", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(SPRINT / "runs" / "A2" / "A2-1" / "v2_claims.json"), "extraction"),
                           {"path": "review/a2_claims.csv (Anu decisions)", "kind": "packet", "sha256": None},
                           input_ref(str(SPRINT / "results" / "a2_pairs.json"), "read-only")],
                   outputs=["results/a2_comparison.json", "docs/tables/A2.md"],
                   notes=f"A2.4-2.6: agreement {agreement_rate}, downgrade {downgrade_rate}, untypeable {len(untypeable_pairs)}; "
                         f"survivor/failure fisher p={fisher_p}")

    print(f"[A2.4] untypeable pairs ({len(untypeable_pairs)}): {untypeable_pairs or 'none'} "
          f"→ vocab-extension {'TRIGGERED (≥8)' if len(untypeable_pairs)>=8 else 'not triggered'}")
    print(f"[A2.6] delta distribution: {delta_dist}")
    print(f"[A2.6] agreement_rate={agreement_rate} downgrade_rate={downgrade_rate} (n_baselined={n_base})")
    print(f"[A2.6] survivor/failure 2×2 [[{a11},{a10}],[{a01},{a00}]] Fisher p={fisher_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
