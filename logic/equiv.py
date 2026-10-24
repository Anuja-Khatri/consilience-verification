#!/usr/bin/env python3
"""
logic/equiv.py — VJ1.3 equivalence harness (SPEC §VJ1.3).

Runs BOTH the Python port (p5_judge.judge_pair) and the logic program
(judge_program.run_pair) over:
  (i)  all cross-theory candidate pairs within the 13 persisted theory pairs,
  (ii) the 221 persisted correspondences (= the union of (i)'s corr outputs),
  (iii) 200 seeded synthetic claim graphs probing edge cases (empty, self/within-theory,
       axis none, multi-edge chains depth 3, denies-denies, identical values different
       families, unicode).
Compares verdict sets EXACTLY (forks + corrs incl. grade/kind). Metric vj1.equivalence_rate
(target 1.0); any mismatch itemised in logic/divergences.md. Also emits logic/judge.lp.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import judge_program as JP  # noqa: E402
import p5_judge as P5  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
SEED = CFG["seeds"]["global"]
THEORY_SLUGS = ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]


def persisted_pairs():
    """The 13 persisted pairs, as (graph_a, graph_b) from the stored judge files."""
    out = []
    import glob
    for jf in sorted(glob.glob(str(ENGINE / "results" / "*_judge.json"))):
        J = json.loads(Path(jf).read_text())
        ga = {"theory": J["left"]["theory"], "nodes": J["left"]["nodes"], "edges": J["left"]["edges"]}
        gb = {"theory": J["right"]["theory"], "nodes": J["right"]["nodes"], "edges": J["right"]["edges"]}
        out.append((Path(jf).name, ga, gb))
    return out


# ---- synthetic graph generator (VJ1.3 edge cases) ---- #
AXES = ["locus", "temporal_profile", "connectivity", "mechanism_scale", "observable_commitment",
        "substrate_dependence", "computability", "identity_relation", "none"]
ETYPES = ["invariant", "process", "constraint", "measurement", "field", "state", "system"]
POLS = ["asserts", "denies"]
VALUES = ["posterior_hot_zone", "prefrontal_cortex", "sustained", "ignition_onset",
          "integrated_information", "global_workspace", "Φ_structure", "quantum_coherence",
          "αβ_oscillation", "x", "value_one", "value_two"]  # incl. unicode + stem-less
RELS = ["grounds", "entails", "constrains", "predicts_observable"]


def _mkclaim(theory, i, rng):
    return {"claim_id": f"{theory}_s{i}", "theory": theory,
            "entity_type": rng.choice(ETYPES), "axis": rng.choice(AXES),
            "polarity": rng.choice(POLS), "value": rng.choice(VALUES), "status": "approved"}


def synthetic(i):
    rng = random.Random(SEED + i)
    bucket = i % 8
    if bucket == 0:  # empty graph A
        return ({"theory": "T1", "nodes": [], "edges": []},
                {"theory": "T2", "nodes": [_mkclaim("T2", 0, rng)], "edges": []})
    within = (bucket == 1)  # within-theory pair (tests the non-cap formal branch)
    ta, tb = ("T1", "T1") if within else ("T1", "T2")
    na = rng.randint(1, 5); nb = rng.randint(1, 5)
    A = {"theory": ta, "nodes": [_mkclaim(ta, k, rng) for k in range(na)], "edges": []}
    B = {"theory": tb, "nodes": [_mkclaim(tb, k, rng) for k in range(nb)], "edges": []}
    if bucket == 2:  # denies-denies on a shared axis/value
        for n in A["nodes"] + B["nodes"]:
            n["polarity"] = "denies"; n["axis"] = "locus"; n["value"] = "posterior_hot_zone"
    if bucket == 3:  # identical values (stem-less 'x') different nominal
        for n in A["nodes"]:
            n["value"] = "x"
        for n in B["nodes"]:
            n["value"] = "x"
    if bucket == 4 and len(A["nodes"]) >= 3:  # multi-edge chain depth 3 within A
        ids = [n["claim_id"] for n in A["nodes"]]
        A["edges"] = [{"src_claim_id": ids[0], "dst_claim_id": ids[1], "relation": "grounds", "source": "rule"},
                      {"src_claim_id": ids[1], "dst_claim_id": ids[2], "relation": "grounds", "source": "rule"}]
    if bucket == 5:  # random edges both sides
        for G in (A, B):
            ids = [n["claim_id"] for n in G["nodes"]]
            if len(ids) >= 2:
                G["edges"] = [{"src_claim_id": ids[0], "dst_claim_id": ids[1],
                               "relation": rng.choice(RELS), "source": "rule"}]
    return A, B


def compare(name, A, B, diverg):
    lp = JP.run_pair(A, B)
    gt = JP.judge_truth(A, B)
    ok = lp["forks"] == gt["forks"] and lp["corrs"] == gt["corrs"]
    if not ok:
        diverg.append({"case": name,
                       "forks_only_logic": sorted(map(str, lp["forks"] - gt["forks"])),
                       "forks_only_truth": sorted(map(str, gt["forks"] - lp["forks"])),
                       "corrs_only_logic": sorted(map(str, lp["corrs"] - gt["corrs"])),
                       "corrs_only_truth": sorted(map(str, gt["corrs"] - lp["corrs"]))})
    # per-verdict tallies
    nv = len(gt["forks"]) + len(gt["corrs"])
    matched = len(lp["forks"] & gt["forks"]) + len(lp["corrs"] & gt["corrs"])
    return ok, nv, matched


def emit_judge_lp():
    lines = ["% logic/judge.lp — judge decision logic in ASP (clingo); mirrors",
             "% logic/judge_program.py minidatalog rules. Each rule cites the p5_judge.py line.",
             "% Primitives (cand, samefam, opposed, sharedrel, nvm2, forkaxis, crosstheory) are",
             "% materialised from the ported p5 functions (bounded treatment, VJ1.2).", ""]
    for group in JP._rules():
        for r in group:
            head = f"{r.head.pred}({','.join(_lp(t) for t in r.head.args)})"
            body = [f"{b.pred}({','.join(_lp(t) for t in b.args)})" for b in r.body]
            body += [f"not {n.pred}({','.join(_lp(t) for t in n.args)})" for n in r.neg]
            lines.append(f"% {r.comment}")
            lines.append(f"{head} :- {', '.join(body)}." if body else f"{head}.")
    (SPRINT / "logic" / "judge.lp").write_text("\n".join(lines) + "\n")


def _lp(t):
    import minidatalog as M
    if isinstance(t, M.Var):
        return t.name
    return f'"{t}"'


def main() -> int:
    emit_judge_lp()
    diverg = []
    total_cmp = matched_cmp = 0
    tot_v = tot_m = 0
    # (i)+(ii) 13 persisted pairs (covers the 221 correspondences)
    corr_total = 0
    for name, A, B in persisted_pairs():
        ok, nv, mt = compare(f"persisted:{name}", A, B, diverg)
        total_cmp += 1; matched_cmp += int(ok); tot_v += nv; tot_m += mt
        corr_total += len([1 for c in P5.judge_pair(A, B)["correspondences"]])
    # (iii) 200 synthetic
    for i in range(200):
        A, B = synthetic(i)
        ok, nv, mt = compare(f"synthetic:{i}", A, B, diverg)
        total_cmp += 1; matched_cmp += int(ok); tot_v += nv; tot_m += mt

    rate = matched_cmp / total_cmp if total_cmp else 0.0
    vrate = tot_m / tot_v if tot_v else 1.0
    # divergences.md
    md = ["# VJ1.3 equivalence divergences", "",
          f"Pair-level exact-match: {matched_cmp}/{total_cmp} ({rate:.4f}). "
          f"Per-verdict match: {tot_m}/{tot_v} ({vrate:.4f}).",
          f"Persisted correspondences covered: {corr_total} (= 221 expected).", ""]
    if not diverg:
        md.append("**No divergences — logic program ≡ Python judge over all cases.**")
    else:
        md.append(f"## {len(diverg)} divergent case(s)")
        for d in diverg:
            md.append(f"- **{d['case']}**: {json.dumps({k: v for k, v in d.items() if k != 'case' and v})}")
    (SPRINT / "logic" / "divergences.md").write_text("\n".join(md) + "\n")

    reg = Registry()
    reg.upsert(metric_id="vj1.equivalence_rate", value=round(rate, 4), n=total_cmp,
               ci_lo=None, ci_hi=None, task="VJ1", runid="VJ1-1",
               instrument_tag="frozen-store", corpus_tag="v1", preregistered=True, pilot=False,
               caveats=[f"Python judge port vs logic program (minidatalog); {total_cmp} comparisons "
                        f"(13 persisted pairs covering {corr_total} corrs + 200 synthetic); "
                        f"per-verdict {tot_m}/{tot_v}={vrate:.4f}. Primitives materialised from p5 "
                        "(bounded treatment); rules transcribe the grade/fork decision tree. "
                        f"{'no divergences' if not diverg else str(len(diverg))+' divergences — see logic/divergences.md'}"])
    reg.save()
    print(f"VJ1.3 equivalence: pair-level {matched_cmp}/{total_cmp}={rate:.4f}; "
          f"per-verdict {tot_m}/{tot_v}={vrate:.4f}; corrs covered {corr_total}; "
          f"divergences {len(diverg)}")
    print("  → logic/judge.lp, logic/divergences.md; vj1.equivalence_rate registered")
    return 0 if rate == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
