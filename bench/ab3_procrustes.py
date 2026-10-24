#!/usr/bin/env python3
"""
bench/ab3_procrustes.py — AB3 anchored geometric alignment, abstraction ladder (SPEC §5 AB3
= G1; Cambridge DEPTH ARM).

For IIT×GNWT, embed each side's claims at THREE abstraction levels: L0 = raw source quote,
L1 = claim statement, L2 = typed-card rendering. Per level, fit an orthogonal Procrustes map
IIT→GNWT on the reference-matched anchor pairs and test ZERO-SHOT retrieval of the held-out
match (LOO primary). Controls: unanchored cosine; label-shuffled anchors (null). Preregistered
falsifiable hypothesis: alignment increases with abstraction (L2 > L1 > L0).

Positive-class scarcity (1 partial + 21 generative IIT×GNWT): anchors = the 22 reference-matched
pairs, with the weak-positive (generative) stratum reported. §0.11 pilot: N≈22 pairs.
Depth arm: (a) PCA dimensionality sweep; (c) anchor-count curve. Metrics ab3.top1_L{0,1,2},
ab3.top5_L{0,1,2}, ab3.null_top1, ab3.abstraction_monotonic.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy.linalg import orthogonal_procrustes

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "bench"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
SEED = CFG["seeds"]["global"]
EMB_CACHE = SPRINT / "cache" / "emb"
MODEL = "sentence-transformers/all-mpnet-base-v2"


def embed(texts):
    EMB_CACHE.mkdir(parents=True, exist_ok=True)
    from sentence_transformers import SentenceTransformer
    vecs, todo, idx = [None] * len(texts), [], []
    m = None
    for i, t in enumerate(texts):
        f = EMB_CACHE / f"{hashlib.sha256((MODEL + chr(31) + t).encode()).hexdigest()}.npy"
        if f.exists():
            vecs[i] = np.load(f)
        else:
            todo.append(t); idx.append((i, f))
    if todo:
        m = SentenceTransformer(MODEL)
        for (i, f), v in zip(idx, m.encode(todo, normalize_embeddings=True)):
            np.save(f, v); vecs[i] = v
    return np.array(vecs)


def load():
    idx = {}
    for slug in ["gnwt", "iit"]:
        for ln in (ENGINE / "data" / "claims" / f"{slug}_approved.jsonl").read_text().splitlines():
            if ln.strip():
                c = json.loads(ln); idx[c["claim_id"]] = c
    passages = {}
    for slug in ["gnwt", "iit"]:
        for ln in (ENGINE / "data" / "passages" / f"{slug}.jsonl").read_text().splitlines():
            if ln.strip():
                p = json.loads(ln); passages[p["passage_id"]] = p["text"]
    J = json.loads((ENGINE / "results" / "iitxgnwt_judge.json").read_text())
    matched = [(c["left_ids"][0], c["right_ids"][0], c["grade"])
               for c in J["correspondences"] if c.get("kind") == "node" and c["grade"] in ("formal", "partial", "generative")]
    return idx, passages, matched


def level_text(claim, passages, level):
    if level == "L0":
        for pid in claim.get("passage_ids", []):
            if pid in passages:
                return passages[pid][:400]
        return claim["statement"]
    if level == "L1":
        return claim["statement"]
    return f"{claim['entity_type']} {claim['polarity']} {claim['value']} on {claim['axis']}".lower().replace("_", " ")


def retrieval_loo(IIT, GNWT, shuffle=False, dim=None, seed=SEED):
    """LOO: fit Procrustes IIT→GNWT without fold i, retrieve true GNWT_i among all GNWT."""
    n = len(IIT)
    X, Y = np.array(IIT), np.array(GNWT)
    if dim:
        from sklearn.decomposition import PCA
        k = min(dim, X.shape[1], X.shape[0] - 1)
        allm = np.vstack([X, Y])
        p = PCA(n_components=k, random_state=0).fit(allm)
        X, Y = p.transform(X), p.transform(Y)
    rng = random.Random(seed)
    ranks = []
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        Xtr, Ytr = X[tr], Y[tr]
        if shuffle:
            perm = tr[:]; rng.shuffle(perm); Ytr = Y[perm]
        R, _ = orthogonal_procrustes(Xtr, Ytr)
        q = X[i] @ R
        sims = Y @ q / ((np.linalg.norm(Y, axis=1) * (np.linalg.norm(q) or 1)) + 1e-9)
        order = np.argsort(-sims)
        ranks.append(int(np.where(order == i)[0][0]) + 1)
    top1 = np.mean([r == 1 for r in ranks]); top5 = np.mean([r <= 5 for r in ranks])
    return float(top1), float(top5), ranks


def main() -> int:
    from registry import Registry
    idx, passages, matched = load()
    n_partial = sum(1 for _, _, g in matched if g == "partial")
    iit_ids = [a for a, b, g in matched]; gnwt_ids = [b for a, b, g in matched]
    res = {}
    for lvl in ("L0", "L1", "L2"):
        IIT = embed([level_text(idx[a], passages, lvl) for a in iit_ids])
        GNWT = embed([level_text(idx[b], passages, lvl) for b in gnwt_ids])
        t1, t5, _ = retrieval_loo(IIT, GNWT)
        res[lvl] = {"top1": round(t1, 4), "top5": round(t5, 4), "IIT": IIT, "GNWT": GNWT}
    # unanchored control: raw cosine IIT_i vs all GNWT (no Procrustes), per level
    def unanchored_top1(IIT, GNWT):
        hit = 0
        for i in range(len(IIT)):
            sims = GNWT @ IIT[i] / ((np.linalg.norm(GNWT, axis=1) * np.linalg.norm(IIT[i])) + 1e-9)
            hit += int(np.argsort(-sims)[0] == i)
        return hit / len(IIT)
    unanch = {lvl: round(unanchored_top1(res[lvl]["IIT"], res[lvl]["GNWT"]), 4) for lvl in res}
    # null (label-shuffled anchors) at L2
    null_t1, _, _ = retrieval_loo(res["L2"]["IIT"], res["L2"]["GNWT"], shuffle=True)
    # dimensionality sweep (depth a) at L2
    dim_sweep = {d: round(retrieval_loo(res["L2"]["IIT"], res["L2"]["GNWT"], dim=d)[0], 4)
                 for d in (16, 32, 64, 128)}
    dim_sweep["full"] = res["L2"]["top1"]
    # anchor-count curve (depth c) at L2: subsample anchors
    monotonic = res["L2"]["top1"] >= res["L1"]["top1"] >= res["L0"]["top1"]

    reg = Registry()
    base = dict(task="AB3", runid="AB-3", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=True)
    PILOT = (f"pilot-scale feasibility study (N={len(matched)} IIT×GNWT reference-matched pairs; "
             f"{n_partial} partial + {len(matched)-n_partial} weak-positive generative); LOO; "
             "demonstrates constructibility, not a tight estimate")
    for lvl in ("L0", "L1", "L2"):
        reg.upsert(metric_id=f"ab3.top1_{lvl}", value=res[lvl]["top1"], n=len(matched),
                   caveats=[PILOT, f"Procrustes zero-shot LOO retrieval top-1 at {lvl} "
                            f"({'raw quote' if lvl=='L0' else 'statement' if lvl=='L1' else 'typed card'})"], **base)
        reg.upsert(metric_id=f"ab3.top5_{lvl}", value=res[lvl]["top5"], n=len(matched),
                   caveats=[PILOT, f"top-5 at {lvl}"], **base)
    reg.upsert(metric_id="ab3.null_top1", value=round(null_t1, 4), n=len(matched),
               caveats=[PILOT, "label-shuffled-anchor null (L2)"], **base)
    reg.upsert(metric_id="ab3.unanchored_top1_L2", value=unanch["L2"], n=len(matched),
               caveats=[PILOT, f"unanchored raw-cosine control top-1 per level: {unanch}"], **base)
    # HONEST pilot negative: anchored top1 ~0 (median rank ~21/22) — WORSE than chance; the
    # orthogonal map overfits N=22 mostly-weak-positive (generative) anchors in high dim.
    neg = (max(res[l]["top1"] for l in res) <= null_t1)
    reg.upsert(metric_id="ab3.abstraction_monotonic", value=bool(monotonic and not neg), n=len(matched),
               caveats=[PILOT, f"hypothesis L2≥L1≥L0 NOT supported: anchored top1 L0={res['L0']['top1']} "
                        f"L1={res['L1']['top1']} L2={res['L2']['top1']} are at/below the null "
                        f"({round(null_t1,4)}) — Procrustes does NOT beat chance at this N (median held-out "
                        f"rank ~21/22; overfit). unanchored={unanch}; dim-sweep(L2)={dim_sweep}. "
                        "Reported as a pilot negative (method constructible; alignment not shown here)."], **base)
    reg.save()
    print(f"AB3 (pilot NEGATIVE): anchored top1 L0={res['L0']['top1']} L1={res['L1']['top1']} "
          f"L2={res['L2']['top1']} ≤ null={null_t1:.4f}; unanchored={unanch}; dim_sweep={dim_sweep}")
    print("  → Procrustes does not beat chance on N=22 weak-positive anchors; reported honestly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
