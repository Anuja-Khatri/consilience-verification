#!/usr/bin/env python3
"""
bench/ab_a2_posthoc.py — A2 pairs as a POST-HOC bench supplement (bench tag v0.1+a2-posthoc). $0.

Owner ruling: v0.1 (122 items) stays the preregistered headline; the A2 MIU pairs are evaluated as a
SEPARATELY LABELLED post-hoc supplement, NEVER merged into the v0.1 metrics. This runs the same rung
methods (TF-IDF, mpnet statements, typed-card, ported judge) over the A2 pairs that have approved
claims on both sides, scored against the A2.6 judge-after-audit reference, and registers them under
`ab.a2_posthoc_*` only (the frozen ab1/ab2.* v0.1 metrics are untouched).

Reference (binary, with-weak): positive iff A2.6 new_grade ∈ {formal, partial} — NONE here (0 strict
positives); weak-positive iff generative; negative iff {fork, none}. N is tiny (13) and positive-scarce
→ reported as a pilot-scale supplement with the composition stated, not a headline AUROC.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import roc_auc_score

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "bench"))
from ab2_embed import embed, cos  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

GRADE_RANK = {"formal": 3, "partial": 2, "generative": 1, "fork": 0.5, "none": 0}


def typed_str(c):
    return f"{c['entity_type']} {c['polarity']} {c['value']} on {c['axis']}".lower().replace("_", " ")


def auroc(scores, refs):
    if len(set(refs)) < 2:
        return None
    return round(float(roc_auc_score(refs, scores)), 4)


def main() -> int:
    v2 = json.loads((SPRINT / "runs" / "A2" / "A2-1" / "v2_claims.json").read_text())
    cmp = json.loads((SPRINT / "results" / "a2_comparison.json").read_text())
    grade_of = {r["match_id"]: r["new_grade"] for r in cmp["rows"]}
    import csv
    approved = {r["claim_id"] for r in csv.DictReader(open(SPRINT / "review" / "a2_claims.csv"))
                if r["decision"] == "approve"}

    items = []
    for pr in v2["pairs"]:
        a = [c for c in pr["sides"]["a"]["claims"] if c["claim_id"] in approved]
        b = [c for c in pr["sides"]["b"]["claims"] if c["claim_id"] in approved]
        if not (a and b):
            continue
        ca, cb = a[0], b[0]            # representative approved claim per side
        ng = grade_of.get(pr["match_id"], "none")
        ref = 1 if ng in ("formal", "partial", "generative") else 0   # with-weak (0 strict positives)
        strict = 1 if ng in ("formal", "partial") else 0
        items.append({"match_id": pr["match_id"], "a": ca, "b": cb, "new_grade": ng,
                      "ref_with_weak": ref, "ref_strict": strict})

    refs = [it["ref_with_weak"] for it in items]
    n_pos, n_neg = sum(refs), len(refs) - sum(refs)
    n_strict = sum(it["ref_strict"] for it in items)

    # scores
    sa = embed([it["a"]["statement"] for it in items]); sb = embed([it["b"]["statement"] for it in items])
    mpnet = [cos(x, y) for x, y in zip(sa, sb)]
    ta = embed([typed_str(it["a"]) for it in items]); tb = embed([typed_str(it["b"]) for it in items])
    typed = [cos(x, y) for x, y in zip(ta, tb)]
    tfv = TfidfVectorizer().fit([it["a"]["statement"] for it in items] + [it["b"]["statement"] for it in items])
    tfidf = []
    for it in items:
        va, vb = tfv.transform([it["a"]["statement"]]), tfv.transform([it["b"]["statement"]])
        tfidf.append(float((va @ vb.T).toarray()[0][0]))
    judge = [GRADE_RANK.get(it["new_grade"], 0) for it in items]

    au = {"mpnet": auroc(mpnet, refs), "typed": auroc(typed, refs),
          "tfidf": auroc(tfidf, refs), "judge": auroc(judge, refs)}
    detail = {"bench_tag": "v0.1+a2-posthoc", "n_items": len(items),
              "reference": {"strict_positive": n_strict, "weak_positive(generative)": n_pos - 0,
                            "with_weak_positive": n_pos, "negative(fork/none)": n_neg},
              "note": "post-hoc supplement over A2 pairs with approved claims both sides; NEVER merged "
                      "into v0.1. 0 strict positives → with-weak reference used; N tiny.",
              "auroc_with_weak": au,
              "items": [{"match_id": it["match_id"], "new_grade": it["new_grade"], "ref": it["ref_with_weak"],
                         "mpnet": round(mpnet[i], 4), "typed": round(typed[i], 4), "tfidf": round(tfidf[i], 4)}
                        for i, it in enumerate(items)]}
    (SPRINT / "results" / "ab_a2_posthoc.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n")

    reg = Registry()
    base = dict(task="AB", runid="AB-A2POSTHOC", instrument_tag="v2", corpus_tag="v1",
                preregistered=False, pilot=True)
    cav = (f"BENCH TAG v0.1+a2-posthoc — SEPARATE post-hoc supplement over the A2 MIU pairs, NEVER merged "
           f"into the frozen v0.1 bench metrics (ab1/ab2.* unchanged). N={len(items)} pairs with approved "
           f"claims both sides; reference = A2.6 judge-after-audit grade. {n_strict} strict positives "
           f"(formal/partial), {n_pos} with-weak (incl. generative), {n_neg} negative (fork/none) → "
           f"with-weak AUROC only; tiny N, positive-scarce — pilot-scale, not a headline.")
    reg.upsert(metric_id="ab.a2_posthoc_n", value=len(items), n=len(items),
               caveats=[cav, f"strict_pos={n_strict} weak_pos={n_pos} neg={n_neg}"], **base)
    for m, v in au.items():
        reg.upsert(metric_id=f"ab.a2_posthoc_auroc_{m}", value=(v if v is not None else "undefined (class scarcity)"),
                   n=len(items), caveats=[cav, f"{m} cosine vs with-weak reference"
                                          + (" (judge = circular, reference basis)" if m == "judge" else "")], **base)
    reg.save()

    write_manifest("AB", "AB-A2POSTHOC", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(SPRINT / "runs" / "A2" / "A2-1" / "v2_claims.json"), "extraction"),
                           input_ref(str(SPRINT / "results" / "a2_comparison.json"), "read-only")],
                   outputs=["results/ab_a2_posthoc.json"],
                   notes=f"A2 post-hoc bench supplement (v0.1+a2-posthoc, NOT merged); N={len(items)}, AUROC(with-weak) {au}")
    print(f"[A2-posthoc] N={len(items)} (strict_pos {n_strict}, weak_pos {n_pos}, neg {n_neg}); "
          f"with-weak AUROC {au}; bench tag v0.1+a2-posthoc (NOT merged into v0.1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
