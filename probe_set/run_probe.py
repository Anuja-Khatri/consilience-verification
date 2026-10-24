#!/usr/bin/env python3
"""
probe_set/run_probe.py — B4 diagnostic-probe harness (SPEC §4 B4).

--method {mpnet,restate,judge} (large/rerank need GPU/API → deferred). Per-cell accuracy +
the structure-vs-surface dissociation: a method that passes true_correspondence while REJECTING
equivocation is dissociating; one fooled by equivocation is not. Per-item point-biserial
discrimination; |r|<0.05 flagged low-discrimination (documented, not pruned in v0.1).
Metrics b4.<method>_acc_<cell>, b4.dissociation_<method>, b4.low_discrimination_count.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import p5_judge as P5  # noqa: E402
import stats as S  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
PS = SPRINT / "probe_set"
EMB_CACHE = SPRINT / "cache" / "emb"
MODEL = "sentence-transformers/all-mpnet-base-v2"
CELLS = ["true_correspondence", "equivocation", "negation", "control_expected_flip", "control_invariant"]


def embed(texts):
    EMB_CACHE.mkdir(parents=True, exist_ok=True)
    from sentence_transformers import SentenceTransformer
    vecs, todo, idx = [None] * len(texts), [], []
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


def typed_str(t):
    return f"{t['entity_type']} {t['polarity']} {t['value']} on {t['axis']}".lower().replace("_", " ")


def judge_predict(it):
    # the judge needs ENGINE-typed claims. MIU-sourced equivocations are not engine-typed
    # (placeholder axis=none both sides) → N/A until A2 engine-types them. Return None to skip.
    if it["gold_basis"] == "miu-rejection-record" or (
            it["typed_a"].get("axis") == "none" and it["typed_b"].get("axis") == "none"):
        return None
    a = {"claim_id": "a", "theory": "A", **it["typed_a"]}
    b = {"claim_id": "b", "theory": "B", **it["typed_b"]}
    out = P5.judge_pair({"theory": "A", "nodes": [a], "edges": []},
                        {"theory": "B", "nodes": [b], "edges": []})
    return 1 if out["correspondences"] else 0   # 1 = predicts correspond


def main() -> int:
    items = [json.loads(l) for l in (PS / "items.jsonl").read_text().splitlines() if l.strip()]
    gold = np.array([1 if it["gold"] == "correspond" else 0 for it in items])

    scores = {}
    A = embed([it["text_a"] for it in items]); B = embed([it["text_b"] for it in items])
    scores["mpnet"] = np.array([float(np.dot(a, b)) for a, b in zip(A, B)])
    yA = embed([typed_str(it["typed_a"]) for it in items]); yB = embed([typed_str(it["typed_b"]) for it in items])
    scores["restate"] = np.array([float(np.dot(a, b)) for a, b in zip(yA, yB)])
    judge_preds = [judge_predict(it) for it in items]   # None = N/A (not engine-typed)
    scores["judge"] = np.array([-1 if p is None else p for p in judge_preds], float)

    reg = Registry()
    reg.data["metrics"] = [m for m in reg.data["metrics"] if not m["metric_id"].startswith("b4.")]  # clean re-run
    base = dict(task="B4", runid="B4-1", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=False)
    low_disc = 0
    for method, sc in scores.items():
        # judge preds are 0/1 or N/A (-1); score methods get a balanced-accuracy threshold
        if method == "judge":
            pred = sc.astype(int)
            na_mask = np.array([p is None for p in judge_preds])
        else:
            na_mask = np.zeros(len(items), bool)
            # BALANCED-accuracy threshold (mean of sensitivity+specificity) — avoids the
            # all-negative trivial optimum on this imbalanced probe set.
            ths = sorted(set(sc))
            best_t, best_b = float(np.median(sc)), -1.0
            for t in ths:
                p = (sc >= t).astype(int)
                tpr = ((p == 1) & (gold == 1)).sum() / max((gold == 1).sum(), 1)
                tnr = ((p == 0) & (gold == 0)).sum() / max((gold == 0).sum(), 1)
                bal = 0.5 * (tpr + tnr)
                if bal > best_b:
                    best_b, best_t = bal, t
            pred = (sc >= best_t).astype(int)
        # per-cell accuracy (skip N/A items, e.g. judge on non-engine-typed MIU equivocations)
        bycell = defaultdict(list)
        for i, (it, p, g) in enumerate(zip(items, pred, gold)):
            if na_mask[i]:
                continue
            bycell[it["cell"]].append(int(p == g))
        for cell in CELLS:
            if bycell[cell]:
                reg.upsert(metric_id=f"b4.{method}_acc_{cell}", value=round(float(np.mean(bycell[cell])), 4),
                           n=len(bycell[cell]), caveats=[f"{method} accuracy on the {cell} cell"], **base)
        tc = np.mean(bycell["true_correspondence"]) if bycell["true_correspondence"] else None
        eq = np.mean(bycell["equivocation"]) if bycell["equivocation"] else None
        if tc is None or eq is None:
            reg.upsert(metric_id=f"b4.dissociation_{method}", value="n/a", n=len(items),
                       caveats=[f"dissociation N/A for {method}: "
                                + ("equivocation cell not engine-typed (pending A2) — the judge needs "
                                   "engine typing; mpnet/restate use text and are scored"
                                   if method == "judge" else "a cell was empty")], **base)
        else:
            reg.upsert(metric_id=f"b4.dissociation_{method}", value=round(float(min(tc, eq)), 4), n=len(items),
                       caveats=[f"min(acc true_correspondence {tc:.2f}, acc equivocation {eq:.2f}) — does "
                                f"{method} accept real correspondences while REJECTING shared-vocab equivocations?"], **base)
        # point-biserial discrimination
        if method != "judge":
            r, _ = S.point_biserial(list(gold), list(sc))
            if abs(r) < 0.05:
                low_disc += 1
    reg.upsert(metric_id="b4.low_discrimination_count", value=low_disc, n=len(scores),
               caveats=["methods with |point-biserial r|<0.05 (documented, not pruned in v0.1)"], **base)
    reg.save()
    print("B4 run_probe:")
    for m in scores:
        print(f"  {m}: dissociation(min tc,eq) = {reg.get(f'b4.dissociation_{m}')['value']}; "
              f"equivocation acc = {reg.get(f'b4.{m}_acc_equivocation') and reg.get(f'b4.{m}_acc_equivocation')['value']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
