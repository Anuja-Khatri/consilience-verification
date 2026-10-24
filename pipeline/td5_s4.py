#!/usr/bin/env python3
"""
pipeline/td5_s4.py — TD5 S4 key-recovery nulls (SPEC §TD5.2 S4). $0, pure compute.

"The number that makes every key diff interpretable": a 2/3 recovery means nothing without the
chance rate. For KR1 (COGITATE), generate 1000 random typed-row keys (same row count = 3, fork axes
sampled from the vocab, value families sampled from the per-theory corpus marginals) and diff each
against the REAL Anu-approved instrument-v2 IIT×GNWT forks via the ported judge + diff_engine → a null
distribution of recovery counts → z and empirical p for the real recovery (2/3). Registers
r1.key_null_z_cogitate.

KR2 (INTREPID) recovery is QUALITATIVE (register-verification / RECOVERED-as-correspondence, not a
row-count diff) → the row-recovery null does not apply in the same form; reported, not forced. KR3/KR4/KR5
nulls wait on their held-out PDFs (machinery identical once their diffs land).
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
CFG0 = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE0 = Path(os.path.expanduser(CFG0["paths"]["engine"]))
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
sys.path.insert(0, str(SPRINT / "keys"))
sys.path.append(str(ENGINE0 / "pipeline"))   # p2_extract only here; engine_copy p5_judge still wins (earlier)
import p5_judge as P5  # noqa: E402
import p2_extract as P2  # noqa: E402  (AXES vocab)
import diff_engine as DE  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
SEED = int(CFG["seeds"]["global"])
N_NULL = 1000
V2 = SPRINT / "runs" / "KR1" / "KR1-2" / "v2_claims.json"
KEY = ENGINE / "data" / "answer_keys" / "cogitate.yaml"
AXES = sorted(a for a in P2.AXES if a != "none")


def _mean_std(xs):
    n = len(xs)
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / n
    return m, (v ** 0.5)


def real_forks_and_recovery():
    v2 = json.loads(V2.read_text())
    approved = {r["v2_claim_id"] for r in csv.DictReader(open(SPRINT / "review" / "kr1_v2_claims.csv"))
                if r["decision"] == "approve"}

    def flat(b):
        return [c for grp in b.values() for c in grp if c["claim_id"] in approved]

    iit, gnwt = flat(v2["iit"]), flat(v2["gnwt"])
    forks = P5.judge_pair({"theory": "IIT", "nodes": iit, "edges": []},
                          {"theory": "GNWT", "nodes": gnwt, "edges": []})["forks"]
    key = yaml.safe_load(KEY.read_text())
    key_rows = [{"row_id": p["id"], "axis": p["fork_axis"],
                 "expected": {"value_family": [p.get("iit_value"), p.get("gnwt_value")]}}
                for p in key["predictions"]]
    real = DE.diff(key_rows, forks, caveat="")["counts"]
    # per-theory value marginals (for sampling random key families)
    iit_vals = [c["value"] for c in iit]
    gnwt_vals = [c["value"] for c in gnwt]
    return forks, key_rows, real, iit_vals, gnwt_vals


def main() -> int:
    forks, key_rows, real, iit_vals, gnwt_vals = real_forks_and_recovery()
    n_rows = len(key_rows)
    real_rec = real["recovered"]
    rng = random.Random(SEED + 400)

    rec_null, recpart_null = [], []
    for _ in range(N_NULL):
        rand_rows = [{"row_id": f"r{i}", "axis": rng.choice(AXES),
                      "expected": {"value_family": [rng.choice(iit_vals), rng.choice(gnwt_vals)]}}
                     for i in range(n_rows)]
        c = DE.diff(rand_rows, forks, caveat="")["counts"]
        rec_null.append(c["recovered"])
        recpart_null.append(c["recovered"] + c["partial"])

    m, s = _mean_std(rec_null)
    z = (real_rec - m) / s if s > 0 else float("inf") if real_rec > m else 0.0
    emp_p = sum(1 for x in rec_null if x >= real_rec) / N_NULL
    mp, sp = _mean_std(recpart_null)
    real_rp = real["recovered"] + real["partial"]
    z_rp = (real_rp - mp) / sp if sp > 0 else (float("inf") if real_rp > mp else 0.0)
    emp_p_rp = sum(1 for x in recpart_null if x >= real_rp) / N_NULL

    detail = {"key": "cogitate", "n_rows": n_rows, "n_null": N_NULL,
              "real_recovered": real_rec, "real_recovered_plus_partial": real_rp,
              "null_recovered_mean": round(m, 4), "null_recovered_std": round(s, 4),
              "z_recovered": round(z, 4) if z not in (float("inf"),) else "inf",
              "empirical_p_recovered": emp_p,
              "null_recovered_partial_mean": round(mp, 4),
              "z_recovered_partial": round(z_rp, 4) if z_rp not in (float("inf"),) else "inf",
              "empirical_p_recovered_partial": emp_p_rp,
              "axes_sampled_from": "vocab (12 axes, none excluded)",
              "families_sampled_from": "per-theory corpus value marginals"}
    (SPRINT / "results" / "td5_s4_key_nulls.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False) + "\n")

    reg = Registry()
    base = dict(task="TD5", runid="TD5-S4", instrument_tag="v2", corpus_tag="v1", preregistered=True, pilot=False)
    reg.upsert(metric_id="r1.key_null_p_cogitate", value=emp_p, n=N_NULL, caveats=[
        f"KR1 COGITATE key-recovery EMPIRICAL permutation p: fraction of {N_NULL} random typed-row keys that "
        f"recover ≥ the real {real_rec}/{n_rows} = {emp_p}. Same null as r1.key_null_z_cogitate (recovered-count "
        f"distribution, μ={m:.3f} σ={s:.3f}). p and z come from the SAME null; the normal-approx z={z:.2f} "
        f"OVERSTATES significance because the null is discrete (recovered∈{{0,1,2,3}}) and right-skewed — the "
        f"empirical p={emp_p} is the honest figure and does NOT reach α=0.05 (suggestive only)."], **base)
    reg.upsert(metric_id="r1.key_null_z_cogitate", value=round(z, 4) if z != float("inf") else "inf",
               n=N_NULL, caveats=[
                   f"KR1 COGITATE key-recovery null: real recovered {real_rec}/{n_rows} vs {N_NULL} random "
                   f"3-row keys (axes sampled from the 12-axis vocab, value-families from per-theory corpus "
                   f"marginals), diffed against the Anu-approved instrument-v2 IIT×GNWT forks. "
                   f"null recovered μ={m:.3f} σ={s:.3f}; empirical p(≥{real_rec})={emp_p:.3f}. "
                   f"Recovered+partial: real {real_rp}, null μ={mp:.3f}, z={z_rp if z_rp!=float('inf') else 'inf'}, "
                   f"p={emp_p_rp:.3f}. The chance rate that makes the 2/3 recovery interpretable.",
                   "KR2 INTREPID recovery is qualitative (register-verification) → row-recovery null N/A; "
                   "KR3/KR4/KR5 nulls await their held-out PDFs (machinery identical)."], **base)
    reg.save()

    # update the falsifiability audit's deferred note
    audit = SPRINT / "docs" / "falsifiability-audit.md"
    if audit.exists():
        txt = audit.read_text()
        s4line = (f"\n\n## S4 key-recovery nulls (now computed — KR1)\n"
                  f"KR1 COGITATE: real recovered **{real_rec}/{n_rows}** vs {N_NULL} random typed-row keys → "
                  f"null μ={m:.3f}, **z={z:.2f}**, empirical p(≥{real_rec})={emp_p:.3f}; recovered+partial "
                  f"real {real_rp}, z={z_rp if z_rp!=float('inf') else 'inf'}, p={emp_p_rp:.3f}. "
                  f"This is the chance rate that makes the recovery interpretable (r1.key_null_z_cogitate). "
                  f"KR2 INTREPID recovery is qualitative → row-null N/A; KR3+ await their PDFs.\n")
        if "S4 key-recovery nulls (now computed" not in txt:
            audit.write_text(txt + s4line)

    write_manifest("TD5", "TD5-S4", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(V2), "extraction"),
                           {"path": "engine cogitate.yaml (held-out key, cited)", "kind": "key", "sha256": None}],
                   outputs=["results/td5_s4_key_nulls.json"], seeds={"global": SEED, "offset": 400},
                   notes=f"TD5 S4 KR1 key-recovery null: real {real_rec}/{n_rows}, z={z:.3f}, p={emp_p:.3f} over {N_NULL} random keys.")
    print(f"[TD5-S4] KR1 cogitate: real recovered {real_rec}/{n_rows}; null μ={m:.3f} σ={s:.3f}; "
          f"z={z:.3f}; empirical p(≥{real_rec})={emp_p:.3f}")
    print(f"[TD5-S4] recovered+partial real {real_rp}; z={z_rp if z_rp!=float('inf') else 'inf'}; p={emp_p_rp:.3f}")
    print("[TD5-S4] → r1.key_null_z_cogitate registered; results/td5_s4_key_nulls.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
