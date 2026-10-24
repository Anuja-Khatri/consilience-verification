#!/usr/bin/env python3
"""
bench/ab5_finalize.py — AB5 finalize after the query packet (SPEC §AB5). $0.

Reads the Anu-approved review/ab5_queries.csv (23 approve / 3 reject: e01,e02,e05 rejected) and
recomputes the metrics over the APPROVED query set from results/ab5_preliminary.json (per-query
symbolic truth + soft top-5/top-1 were already computed there; no re-embedding needed).

Owner note (verbatim rationale): e01/e02/e05's emptiness is a POLARITY-ENCODING ARTIFACT — every stored
claim has polarity "asserts" with negation folded into the value (e.g. GNWT "not posterior-only"), so a
"denying X" query can have a true answer in MEANING. Those three are dropped; ab5.empty_query_fpr is
recomputed over the remaining genuine empty-calibration queries {e03,e04,e06}, with the old 6-query
0.833 reported ALONGSIDE under this caveat.
Disclosure (D-035): decisions were model-drafted suggestions reviewed and confirmed by Anu.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
from registry import Registry  # noqa: E402

TAU = 0.50


def main() -> int:
    approved = {r["id"] for r in csv.DictReader(open(SPRINT / "review" / "ab5_queries.csv"))
                if r["decision"] == "approve"}
    rejected = {r["id"] for r in csv.DictReader(open(SPRINT / "review" / "ab5_queries.csv"))
                if r["decision"] == "reject"}
    prelim = json.loads((SPRINT / "results" / "ab5_preliminary.json").read_text())
    qs = [q for q in prelim["queries"] if q["id"] in approved]

    hits = {"min": {"p1": 0, "p5": 0}, "product": {"p1": 0, "p5": 0}}
    empty_fp = {"min": 0, "product": 0}
    n_nonempty = n_empty = 0
    empty_ids = []
    for q in qs:
        truth = set(q["symbolic"])
        is_empty = (q["n_symbolic"] == 0)
        if is_empty:
            n_empty += 1; empty_ids.append(q["id"])
        else:
            n_nonempty += 1
        for tn in ("min", "product"):
            s = q["soft"][tn]
            if is_empty:
                if s["top1_score"] >= TAU:
                    empty_fp[tn] += 1
            else:
                top = s["top5"]
                if top and top[0] in truth:
                    hits[tn]["p1"] += 1
                if set(top) & truth:
                    hits[tn]["p5"] += 1

    p1 = {tn: round(hits[tn]["p1"] / n_nonempty, 4) for tn in hits}
    p5 = {tn: round(hits[tn]["p5"] / n_nonempty, 4) for tn in hits}
    efpr = {tn: round(empty_fp[tn] / n_empty, 4) if n_empty else None for tn in empty_fp}

    final = {"n_approved": len(approved), "n_rejected": len(rejected), "rejected": sorted(rejected),
             "n_nonempty": n_nonempty, "n_empty": n_empty, "empty_ids": sorted(empty_ids),
             "p_at_1": p1, "p_at_5": p5, "empty_query_fpr": efpr,
             "empty_query_fpr_preliminary_6q": prelim["metrics"]["empty_query_fpr"]}
    (SPRINT / "results" / "ab5_final.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n")

    DISC = "Decisions were model-drafted suggestions (Claude) reviewed and confirmed by Anu."
    cav = (f"AB5 FINAL over the Anu-approved query set ({len(approved)} approve / {len(rejected)} reject: "
           f"{sorted(rejected)} rejected). {DISC} CQD soft vs exact Datalog over VJ1's program; t-norms "
           f"min/product. {n_nonempty} non-empty + {n_empty} empty-calibration ({sorted(empty_ids)}).")
    efpr_cav = (f"empty-query false-positive rate recomputed over {sorted(empty_ids)} (n={n_empty}) = {efpr}. "
                f"OWNER RULING: e01/e02/e05 were REJECTED because their emptiness is a POLARITY-ENCODING "
                f"ARTIFACT — every stored claim is polarity 'asserts' with negation folded into the value "
                f"(e.g. 'not posterior-only'), so a 'denying X' query can have a true answer in meaning. "
                f"Old 6-query preliminary FPR (incl. the 3 artifact queries) = {prelim['metrics']['empty_query_fpr']}, "
                f"reported ALONGSIDE under this caveat. {DISC}")
    reg = Registry()
    base = dict(task="AB5", runid="AB5-FINAL", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=False)
    reg.upsert(metric_id="ab5.p_at_1", value=p1["min"], n=n_nonempty,
               caveats=[cav, f"top-1 soft answer in the exact symbolic set; min-tnorm {p1['min']}, product {p1['product']}"], **base)
    reg.upsert(metric_id="ab5.p_at_5", value=p5["min"], n=n_nonempty,
               caveats=[cav, f"a correct symbolic answer in soft top-5; min {p5['min']}, product {p5['product']}"], **base)
    reg.upsert(metric_id="ab5.empty_query_fpr", value=efpr["min"], n=n_empty,
               caveats=[cav, efpr_cav], **base)
    reg.save()
    print(f"[AB5-final] approved {len(approved)} (rej {sorted(rejected)}); non-empty {n_nonempty}, empty {sorted(empty_ids)}")
    print(f"[AB5-final] p@1 {p1} | p@5 {p5} | empty_query_fpr {efpr} (old 6q {prelim['metrics']['empty_query_fpr']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
