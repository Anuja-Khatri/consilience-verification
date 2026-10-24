#!/usr/bin/env python3
"""
bench/bench.py — AB0 frozen item set + AB1 lexical baselines (SPEC §5 AB0, AB1).

AB0: build the frozen bench item set (bench/items.json) from the prior Task-2 pair sheet
(reuse its stratification) + A3-audited IIT×GNWT clean corrs/forks, labelled by the
JUDGE-AFTER-AUDIT reference (positive iff persisted grade ∈ {formal,partial}; negative iff
generative…none or a fork). Positive-class scarcity (0 formal, 20 partial corpus-wide): a
weak-positive tier (generative) is recorded as a SEPARATE stratum; min N=120 → augment with
seeded cross-theory pairs the judge grades none. A2 pairs are DEFERRED (pending A1-C2) and
noted — adding them bumps the bench tag. Terminology: judge-after-audit REFERENCE labels,
never "gold standard".

AB1: TF-IDF cosine + Jaccard (A1-C3 tokenizer) over claim statements → AUROC over the frozen
reference + the Newman number (how far bag-of-words gets) + direction-errors. No API.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import roc_auc_score, f1_score
from sklearn.metrics.pairwise import cosine_similarity

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import p5_judge as P5  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
SEED = CFG["seeds"]["global"]
CAP = CFG["thresholds"]["quote_word_cap"]
BENCH = SPRINT / "bench"
_STOP = {"the", "and", "of", "a", "to", "for", "per", "some", "full", "not", "with", "by", "half",
         "that", "this", "which", "from", "into", "are", "was", "its", "can", "may"}


def claims_index():
    idx = {}
    for slug in ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]:
        for ln in (ENGINE / "data" / "claims" / f"{slug}_approved.jsonl").read_text().splitlines():
            if ln.strip():
                c = json.loads(ln); idx[c["claim_id"]] = c
    return idx


def persisted_verdicts():
    """(a,b) -> grade (node corr) or 'fork'. Judge-after-audit reference from the frozen store."""
    v = {}
    for jf in sorted(glob.glob(str(ENGINE / "results" / "*_judge.json"))):
        J = json.loads(Path(jf).read_text())
        for c in J["correspondences"]:
            if c.get("kind") == "node":
                v[(c["left_ids"][0], c["right_ids"][0])] = c["grade"]
        for f in J["forks"]:
            v.setdefault((f["left_ids"][0], f["right_ids"][0]), "fork")
    return v


def cap(t):
    w = t.split()
    return " ".join(w[:CAP]) + ("…" if len(w) > CAP else "")


def content_tokens(t):
    return {w for w in re.findall(r"[a-z]+", t.lower()) if len(w) >= 4 and w not in _STOP}


def build_items():
    idx = claims_index()
    verd = persisted_verdicts()
    items, seen = [], set()

    def add(a_id, b_id, source):
        if (a_id, b_id) in seen or a_id not in idx or b_id not in idx:
            return
        seen.add((a_id, b_id))
        a, b = idx[a_id], idx[b_id]
        grade = verd.get((a_id, b_id), "none")
        positive = grade in ("formal", "partial")
        weak = grade == "generative"
        items.append({
            "item_id": f"ab_{len(items):04d}", "left_id": a_id, "right_id": b_id,
            "text_a": cap(a["statement"]), "text_b": cap(b["statement"]),
            "typed_a": {k: a[k] for k in ("entity_type", "axis", "polarity", "value")},
            "typed_b": {k: b[k] for k in ("entity_type", "axis", "polarity", "value")},
            "grade": grade, "reference": "positive" if positive else "negative",
            "weak_positive": weak, "source": source,
            "axis_match": a["axis"] == b["axis"], "polarity_opposed": a["polarity"] != b["polarity"],
        })

    # Task-2 pair sheet (reuse stratification)
    t2 = json.loads((ENGINE / "eval_out" / "t2" / "labeling_key.json").read_text())
    for row in t2.values():
        if row.get("left_id") and row.get("right_id"):
            add(row["left_id"], row["right_id"], "task2")
    # A3-audited IIT×GNWT clean corrs/forks
    for f in glob.glob(str(SPRINT / "results" / "a3_dossiers" / "*.json")):
        d = json.loads(Path(f).read_text())
        if d.get("status") == "clean":
            la = d["sides"].get("left", {}).get("claim_ids", [None])[0]
            rb = d["sides"].get("right", {}).get("claim_ids", [None])[0]
            if la and rb:
                add(la, rb, "a3")
    # augment negatives to reach N>=120 (seeded cross-theory pairs the judge grades none/neg)
    rng = random.Random(SEED)
    ids = list(idx.keys())
    tries = 0
    while len(items) < 120 and tries < 20000:
        tries += 1
        a_id, b_id = rng.choice(ids), rng.choice(ids)
        if idx[a_id]["theory"] == idx[b_id]["theory"] or (a_id, b_id) in seen:
            continue
        if verd.get((a_id, b_id), "none") in ("formal", "partial"):
            continue
        before = len(items)
        add(a_id, b_id, "augmented")
        if len(items) > before:
            items[-1]["augmented"] = True
    return items


def auroc(scores, refs):
    y = [1 if r == "positive" else 0 for r in refs]
    if len(set(y)) < 2:
        return None
    return float(roc_auc_score(y, scores))


def main() -> int:
    BENCH.mkdir(exist_ok=True)
    items = build_items()
    n_pos = sum(1 for it in items if it["reference"] == "positive")
    n_weak = sum(1 for it in items if it["weak_positive"])
    sha = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    (BENCH / "items.json").write_text(json.dumps(
        {"bench_version": "v0.1", "n": len(items), "n_positive": n_pos, "n_weak_positive": n_weak,
         "reference": "judge-after-audit", "items_sha256": sha,
         "note": "A2 pairs DEFERRED (pending A1-C2); adding them bumps the bench tag to v0.2",
         "items": items}, ensure_ascii=False, indent=2) + "\n")

    # AB1 lexical baselines
    texts = [it["text_a"] for it in items] + [it["text_b"] for it in items]
    tfidf = TfidfVectorizer().fit(texts)
    cos, jac, refs = [], [], []
    for it in items:
        va, vb = tfidf.transform([it["text_a"]]), tfidf.transform([it["text_b"]])
        cos.append(float(cosine_similarity(va, vb)[0][0]))
        ta, tb = content_tokens(it["text_a"]), content_tokens(it["text_b"])
        jac.append(len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0)
        refs.append(it["reference"])
    au_tfidf, au_jac = auroc(cos, refs), auroc(jac, refs)

    # direction-errors: axis matches but polarity opposed or families disjoint, scored high
    def direction_errors(scores):
        thr = sorted(scores)[int(0.7 * len(scores))] if scores else 1.0
        n = 0
        for it, s in zip(items, scores):
            if it["axis_match"] and (it["polarity_opposed"] or not P5.same_family(
                    it["typed_a"]["value"], it["typed_b"]["value"])) and s >= thr:
                n += 1
        return n

    reg = Registry()
    base = dict(task="AB1", runid="AB-1", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=False)
    reg.upsert(metric_id="ab0.n_items", value=len(items), n=len(items),
               caveats=[f"frozen bench v0.1; {n_pos} positive (judge-after-audit formal/partial), "
                        f"{n_weak} weak-positive (generative, separate stratum); A2 deferred. "
                        "judge-after-audit REFERENCE labels (not a leaderboard)."],
               task="AB0", runid="AB-0", instrument_tag="frozen-store", corpus_tag="v1",
               preregistered=True, pilot=False)
    reg.upsert(metric_id="ab1.auroc_tfidf", value=(round(au_tfidf, 4) if au_tfidf is not None else "n/a"),
               n=len(items), caveats=["TF-IDF cosine over claim statements vs judge-after-audit reference; "
                                      "the Newman floor (how far bag-of-words gets)"], **base)
    reg.upsert(metric_id="ab1.auroc_jaccard", value=(round(au_jac, 4) if au_jac is not None else "n/a"),
               n=len(items), caveats=["Jaccard over A1-C3 content tokens vs reference"], **base)
    reg.upsert(metric_id="ab.direction_errors_tfidf", value=direction_errors(cos), n=len(items),
               caveats=["axis-match but polarity-opposed/family-disjoint pairs scored above the 70th "
                        "percentile by TF-IDF (the Hale direction-error hook)"], **base)
    reg.upsert(metric_id="ab.direction_errors_jaccard", value=direction_errors(jac), n=len(items),
               caveats=["axis-match but polarity-opposed/family-disjoint pairs scored high by Jaccard"], **base)
    reg.save()
    print(f"AB0: {len(items)} items ({n_pos} pos, {n_weak} weak-pos); items_sha {sha[:16]}…")
    print(f"AB1 lexical: AUROC tfidf={au_tfidf}, jaccard={au_jac}; "
          f"direction-errors tfidf={direction_errors(cos)} jaccard={direction_errors(jac)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
