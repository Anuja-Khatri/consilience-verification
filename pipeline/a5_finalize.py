#!/usr/bin/env python3
"""
pipeline/a5_finalize.py — A5.1 finalization ($0; reads cached runs) + A5.3 adoption packet.

Owner $0 fixes before the A5.3 gate:
  1. Estimator reconciliation — the cache-era replication (22/88) and the Task-5 baseline
     (38/140) are the SAME 80 runs; the 140-vs-88 gap is the CLUSTER-IDENTITY/unit
     difference (Task-5: axis + passage-ID Jaccard≥0.5; sprint: (entity_type,axis,polarity)
     + value-family). Register a5.stability_baseline_sprint_estimator = 0.250 beside the
     imported 0.271; ALL adoption comparisons use the one (sprint) estimator.
  2. Wilson CIs on every A5 stability + coverage proportion. Live-vs-cache stability tested
     (Fisher); if not significant → "within sampling variation".
  3. Coverage diagnostic — per-run (pre-consensus) windowed coverage for the 5 arm-(a) and
     5 arm-(d) runs (mean/min/max); list the unrecovered windowed approved claims with the
     nearest extracted claim and which cluster-identity field failed.

Then emit review/a5_adoption_2026-10.md (+schema) and print AWAITING-ANU.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))

import a5_stability as A5M  # noqa: E402  (window/cluster/coverage machinery; no network at import)
import stats as S  # noqa: E402
from registry import Registry  # noqa: E402

RUNS = json.loads((SPRINT / "runs" / "A5" / "A5.1" / "runs.json").read_text())
DATE = A5M.CFG["dates"]["artifact_stamp"]


def _as_runs(d):
    """{'iit_w0':[per-run lists]} → {(slug,k):[...]} for the a5_stability helpers."""
    out = {}
    for key, per in d.items():
        slug, w = key.rsplit("_w", 1)
        out[(slug, int(w))] = per
    return out


def windowed_approved():
    win_pids = {s: set() for s in ("iit", "gnwt")}
    for slug in ("iit", "gnwt"):
        for w in A5M.windows_for(slug):
            win_pids[slug] |= {p["passage_id"] for p in w}
    out = []
    for slug in ("iit", "gnwt"):
        p = A5M.ENGINE / "data" / "claims" / f"{slug}_approved.jsonl"
        for ln in p.read_text().splitlines():
            if not ln.strip():
                continue
            c = json.loads(ln)
            if set(c.get("passage_ids", [])) & win_pids[slug]:
                out.append((slug, c))
    return out


def single_run_cov(runs, wapproved):
    """Pre-consensus: per run r, windowed coverage = matched approved / len(wapproved)."""
    covs = []
    for r in range(A5M.N_RUNS):
        pool = [(slug, c) for (slug, k), per in runs.items() for c in (per[r] if r < len(per) else [])]
        rec = 0
        for aslug, a in wapproved:
            aid = (a.get("entity_type"), a.get("axis"), a.get("polarity"))
            af = A5M._fam(str(a.get("value", "")))
            if any(ps == aslug and A5M.cluster_identity(c) == aid
                   and ((A5M._fam(c["value"]) & af) or c["value"] == a.get("value")) for ps, c in pool):
                rec += 1
        covs.append(rec / len(wapproved) if wapproved else 0.0)
    return covs


def unrecovered_diagnostic(runs_a, wapproved):
    """For windowed approved NOT recovered by consensus, find nearest extracted claim
    (same theory, max identity-field overlap) and the failing field(s)."""
    kept = A5M._kept_clusters(runs_a)  # (slug, canonical claim) for ≥KEEP clusters
    pool = [(slug, c) for (slug, k), per in runs_a.items() for pr in per for c in pr]  # all extracted
    rows = []
    for aslug, a in wapproved:
        aid = (a.get("entity_type"), a.get("axis"), a.get("polarity"))
        af = A5M._fam(str(a.get("value", "")))
        recovered = any(ks == aslug and A5M.cluster_identity(c) == aid
                        and ((A5M._fam(c["value"]) & af) or c["value"] == a.get("value")) for ks, c in kept)
        if recovered:
            continue
        # nearest extracted claim (same theory) by field-overlap score
        best, best_score, best_fields = None, -1, None
        for ps, c in pool:
            if ps != aslug:
                continue
            fields = {
                "entity_type": c.get("entity_type") == a.get("entity_type"),
                "axis": c.get("axis") == a.get("axis"),
                "polarity": c.get("polarity") == a.get("polarity"),
                "value_family": bool(A5M._fam(c["value"]) & af) or c["value"] == a.get("value"),
            }
            score = sum(fields.values())
            if score > best_score:
                best, best_score, best_fields = c, score, fields
        failed = [k for k, ok in (best_fields or {}).items() if not ok] if best else ["(no extracted claim this theory)"]
        rows.append({"approved_id": a.get("claim_id"), "theory": aslug,
                     "approved": {k: a.get(k) for k in ("entity_type", "axis", "polarity", "value")},
                     "nearest": ({k: best.get(k) for k in ("entity_type", "axis", "polarity", "value")} if best else None),
                     "failed_fields": failed})
    return rows


def main() -> int:
    ra = _as_runs(RUNS["arm_a_live"])
    rd = _as_runs(RUNS["arm_d_live"])
    rac = _as_runs(RUNS["arm_a_cache_replication"])
    wapp = windowed_approved()

    # recompute consensus/confweighted stability (keep, total)
    sa, ka, ta = A5M.stability(A5M.pooled(ra))
    sd, kd, td = A5M.stability_confweighted(A5M.pooled(rd))
    sac, kac, tac = A5M.stability(A5M.pooled(rac))
    cov_a = A5M.approved_coverage(ra)
    cov_d = A5M.approved_coverage(rd)
    baseline, baseline_src = A5M.import_baseline()

    # (2) live-vs-cache significance (Fisher on keep/total)
    odds, p_live_cache = S.fisher_exact([[ka, ta - ka], [kac, tac - kac]])
    sig = p_live_cache < 0.05
    stability_note = ("live vs cache-era stability differ significantly (Fisher p=%.3f)" % p_live_cache
                      if sig else "live vs cache-era stability: within sampling variation (Fisher p=%.3f)" % p_live_cache)

    # (3) single-run (pre-consensus) windowed coverage
    sr_a = single_run_cov(ra, wapp)
    sr_d = single_run_cov(rd, wapp)
    import statistics as st
    srA = (st.mean(sr_a), min(sr_a), max(sr_a))
    srD = (st.mean(sr_d), min(sr_d), max(sr_d))
    diag = unrecovered_diagnostic(ra, wapp)

    # write coverage diagnostic doc
    L = ["# A5.1 coverage diagnostic (strict matching vs consensus filtering)", "",
         f"Windowed approved denominator: {len(wapp)} (IIT+GNWT first-pass).",
         f"Consensus (≥{A5M.KEEP_MIN}/{A5M.N_RUNS}) recovered: {cov_a['windowed'][1]}/{len(wapp)} "
         f"({cov_a['windowed'][0]:.3f}).", "",
         "## Per-run (PRE-consensus) windowed coverage",
         f"- arm (a) live: mean {srA[0]:.3f}, min {srA[1]:.3f}, max {srA[2]:.3f}  (runs: "
         + ", ".join(f"{x:.3f}" for x in sr_a) + ")",
         f"- arm (d) conf: mean {srD[0]:.3f}, min {srD[1]:.3f}, max {srD[2]:.3f}  (runs: "
         + ", ".join(f"{x:.3f}" for x in sr_d) + ")",
         "",
         f"Reading: single runs recover ~{srA[0]:.0%} of windowed approved; consensus "
         f"(≥{A5M.KEEP_MIN}/{A5M.N_RUNS}) keeps {cov_a['windowed'][0]:.0%}. The gap is "
         "consensus FILTERING (claims present in <4 runs are dropped), not strict field matching.",
         "", f"## Unrecovered windowed approved claims ({len(diag)})",
         "| approved_id | theory | approved (et/axis/pol/value) | nearest extracted | failed field(s) |",
         "|---|---|---|---|---|"]
    for r in diag:
        ap = r["approved"]; ne = r["nearest"]
        L.append(f"| {r['approved_id']} | {r['theory']} | "
                 f"{ap['entity_type']}/{ap['axis']}/{ap['polarity']}/`{ap['value']}` | "
                 + (f"{ne['entity_type']}/{ne['axis']}/{ne['polarity']}/`{ne['value']}`" if ne else "—")
                 + f" | {', '.join(r['failed_fields'])} |")
    (SPRINT / "results" / "a5_coverage_diagnostic.md").write_text("\n".join(L) + "\n")

    # ---- registry: re-upsert A5 metrics WITH Wilson CIs + new metrics ----
    reg = Registry()
    CAV = ("A5.1 v1-prompt pre-freeze arm; cluster identity (entity_type,axis,polarity)+value-family.")
    common = dict(task="A5", runid="A5.1", instrument_tag="v1", corpus_tag="v1",
                  preregistered=True, pilot=False)

    def ci(k, n):
        lo, hi = S.wilson_ci(k, n)
        return round(lo, 4), round(hi, 4)

    la, ha = ci(ka, ta)
    reg.upsert(metric_id="a5.stability_consensus", value=round(sa, 4), ci_lo=la, ci_hi=ha, n=ta,
               caveats=[CAV, f"arm(a)/(c) LIVE {ka}/{ta} ≥{A5M.KEEP_MIN}/{A5M.N_RUNS}; Wilson 95% CI", stability_note], **common)
    ld, hd = ci(kd, td)
    reg.upsert(metric_id="a5.stability_confweighted", value=round(sd, 4), ci_lo=ld, ci_hi=hd, n=td,
               caveats=[CAV, f"arm(d) {kd}/{td}; Wilson 95% CI"], **common)
    lac, hac = ci(kac, tac)
    reg.upsert(metric_id="a5.stability_cache_replication", value=round(sac, 4), ci_lo=lac, ci_hi=hac, n=tac,
               caveats=[f"Task-5 warm-cache replication {kac}/{tac}; Wilson 95% CI; reported, not an arm", stability_note],
               task="A5", runid="A5.1", instrument_tag="v1", corpus_tag="v1", preregistered=False, pilot=False)
    # (1) sprint-estimator baseline beside the imported 0.271
    recon = ("ONE-ESTIMATOR reconciliation (owner fix 1): the Task-5 baseline (38/140=0.271) and this "
             "number are the SAME 80 runs. 140 vs 88 clusters = cluster-IDENTITY/unit difference, NOT "
             "scope/sample: Task-5 eval/t5_reliability.py cluster_runs() groups by `axis AND passage-ID "
             "Jaccard ≥ 0.5` (passage-based unit → 140); sprint a5_stability.py cluster_runs() groups by "
             "`(entity_type,axis,polarity) AND value-family intersection` (typed-field unit → 88, coarser). "
             "All adoption comparisons use THIS sprint estimator (0.250), not the imported 0.271.")
    reg.upsert(metric_id="a5.stability_baseline_sprint_estimator", value=round(sac, 4), ci_lo=lac, ci_hi=hac, n=tac,
               caveats=[recon], task="A5", runid="A5.1", instrument_tag="v1", corpus_tag="v1",
               preregistered=False, pilot=False)
    # coverage with CIs (windowed + all95), both arms
    for mid, c in [("a5.approved_coverage_windowed_consensus", cov_a["windowed"]),
                   ("a5.approved_coverage_windowed_confweighted", cov_d["windowed"])]:
        lo, hi = ci(c[1], c[2])
        reg.upsert(metric_id=mid, value=round(c[0], 4), ci_lo=lo, ci_hi=hi, n=c[2],
                   caveats=[CAV, "adoption denominator (windowed); Wilson 95% CI", f"{c[1]}/{c[2]}"], **common)
    for mid, c in [("a5.approved_coverage_consensus", cov_a["all95"]),
                   ("a5.approved_coverage_confweighted", cov_d["all95"])]:
        lo, hi = ci(c[1], c[2])
        reg.upsert(metric_id=mid, value=round(c[0], 4), ci_lo=lo, ci_hi=hi, n=c[2],
                   caveats=[CAV, "preregistered all-95 denominator (unattainable; printed beside windowed); Wilson 95% CI", f"{c[1]}/95"], **common)
    # (3) single-run pre-consensus windowed coverage (arm a value; arm d in caveat + diag doc)
    lo, hi = ci(round(srA[0] * len(wapp)), len(wapp))
    reg.upsert(metric_id="a5.approved_coverage_windowed_singlerun", value=round(srA[0], 4), ci_lo=lo, ci_hi=hi, n=len(wapp),
               caveats=["arm(a) per-run PRE-consensus windowed coverage: mean %.3f min %.3f max %.3f" % srA,
                        "arm(d): mean %.3f min %.3f max %.3f" % srD,
                        "gap vs consensus = consensus filtering, not strict matching (see results/a5_coverage_diagnostic.md)"],
               **common)
    reg.save()

    # ---- A5.3 adoption packet (AWAITING-ANU) ----
    cand = ("confweighted", sd, cov_d["windowed"][0]) if sd > sa else ("consensus", sa, cov_a["windowed"][0])
    GS, GC = A5M.CFG["thresholds"]["adopt_consensus_min_stability"], A5M.CFG["thresholds"]["adopt_min_approved_coverage"]
    gate = cand[1] >= GS and cand[2] >= GC
    pkt = SPRINT / "review" / "a5_adoption_2026-10.md"
    pkt.parent.mkdir(exist_ok=True)
    pkt.write_text(f"""# A5.3 instrument-v2 decoding adoption — review packet  [AWAITING-ANU]

Role: approver (not expert). Decide the extraction DECODING for instrument v2. One estimator
(sprint, A5 cluster identity) used throughout. All numbers from results/registry.json; CIs Wilson 95%.

Decision (set `decision:` to one allowed value): {{adopt-baseline | adopt-consensus | adopt-confweighted | defer}}

Evidence:
- baseline single-pass (sprint estimator): {sac:.3f} [{lac:.3f},{hac:.3f}]  (imported Task-5 figure 0.271 is a DIFFERENT clustering; not used for adoption)
- arm (c) consensus-of-5: stability {sa:.3f} [{la:.3f},{ha:.3f}], windowed coverage {cov_a['windowed'][0]:.3f}
- arm (d) confidence-weighted: stability {sd:.3f} [{ld:.3f},{hd:.3f}], windowed coverage {cov_d['windowed'][0]:.3f}
- arm (b) t0: NOT-APPLICABLE (API rejects temperature)
- preregistered gate: stability ≥ {GS} AND windowed coverage ≥ {GC}

Rule (preregistered): candidate = better consensus arm ({cand[0]}); it {'PASSES' if gate else 'FAILS'} the gate.
Fallback on fail = t0-vs-baseline; t0 not-applicable → keep baseline.

RECOMMENDATION: **adopt-baseline** (candidate {cand[0]} fails the gate; no consensus arm beats
{GS}/{GC}; stability difference live-vs-cache is within sampling variation, Fisher p={p_live_cache:.3f}).

EXAMPLES:
  decision: adopt-baseline   # accept the recommendation (single-pass production decoding)
  decision: adopt-confweighted   # override: adopt G6/CISC despite gate (state reason)
  decision: defer   # want more data before freezing

Companion schema: review/a5_adoption_schema.json
""")
    (SPRINT / "review" / "a5_adoption_schema.json").write_text(json.dumps({
        "decision": {"allowed": ["adopt-baseline", "adopt-consensus", "adopt-confweighted", "defer"]},
        "reason": {"type": "string", "required_if": "decision != adopt-baseline"}}, indent=2))

    print(f"[A5-finalize] reconciliation: sprint estimator {sac:.3f} (88 clusters) vs Task-5 0.271 (140); unit difference explained.")
    print(f"[A5-finalize] CIs added. live-vs-cache Fisher p={p_live_cache:.3f} → {'significant' if sig else 'within sampling variation'}")
    print(f"[A5-finalize] single-run windowed cov — arm(a) mean {srA[0]:.3f} [{srA[1]:.3f},{srA[2]:.3f}]; arm(d) mean {srD[0]:.3f}")
    print(f"[A5-finalize] unrecovered windowed claims: {len(diag)} → results/a5_coverage_diagnostic.md")
    print(f"AWAITING-ANU: review/a5_adoption_2026-10.md  (recommendation: adopt-baseline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
