#!/usr/bin/env python3
"""
bench/ab2_embed.py — AB2 embedding ladder (SPEC §5 AB2 = B1 of v1.0).

Rung (a) all-mpnet-base-v2 cosine over claim statements (CPU, local).
Rung (d) typed-rendering embedding: mpnet over "<ENTITY_TYPE> <POLARITY> <VALUE> on <AXIS>"
         lowercased, underscores→spaces.
Rung 6 (comparison) = the ported judge, grade-mapped {formal:3,partial:2,generative:1,none:0}.
Rungs (b) large/distilled + (c) reranker need GPU/VRAM≥40GB or an API substitute — DEFERRED
with a printed caveat (never silent). AUROC over the frozen judge-after-audit reference +
direction-errors. Embeddings cached under cache/emb/.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import yaml
from sklearn.metrics import roc_auc_score

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import p5_judge as P5  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
EMB_CACHE = SPRINT / "cache" / "emb"
MODEL = "sentence-transformers/all-mpnet-base-v2"


def embed(texts):
    EMB_CACHE.mkdir(parents=True, exist_ok=True)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(MODEL)
    out = []
    todo, todo_idx = [], []
    vecs = [None] * len(texts)
    for i, t in enumerate(texts):
        key = hashlib.sha256((MODEL + "\x1f" + t).encode()).hexdigest()
        f = EMB_CACHE / f"{key}.npy"
        if f.exists():
            vecs[i] = np.load(f)
        else:
            todo.append(t); todo_idx.append((i, f))
    if todo:
        enc = m.encode(todo, normalize_embeddings=True)
        for (i, f), v in zip(todo_idx, enc):
            np.save(f, v); vecs[i] = v
    return vecs


def cos(a, b):
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) or 1.0))


def typed_str(t):
    return f"{t['entity_type']} {t['polarity']} {t['value']} on {t['axis']}".lower().replace("_", " ")


def auroc(scores, refs):
    y = [1 if r == "positive" else 0 for r in refs]
    return float(roc_auc_score(y, scores)) if len(set(y)) > 1 else None


def main() -> int:
    items = json.loads((SPRINT / "bench" / "items.json").read_text())["items"]
    refs = [it["reference"] for it in items]
    # rung (a) statements
    tA = embed([it["text_a"] for it in items]); tB = embed([it["text_b"] for it in items])
    mpnet = [cos(a, b) for a, b in zip(tA, tB)]
    # rung (d) typed rendering
    yA = embed([typed_str(it["typed_a"]) for it in items]); yB = embed([typed_str(it["typed_b"]) for it in items])
    typed = [cos(a, b) for a, b in zip(yA, yB)]
    # rung 6 judge grade map
    gmap = {"formal": 3, "partial": 2, "generative": 1, "none": 0, "fork": 0}
    judge = [gmap.get(it["grade"], 0) for it in items]

    def direction_errors(scores):
        thr = sorted(scores)[int(0.7 * len(scores))]
        return sum(1 for it, s in zip(items, scores)
                   if it["axis_match"] and (it["polarity_opposed"] or not P5.same_family(
                       it["typed_a"]["value"], it["typed_b"]["value"])) and s >= thr)

    reg = Registry()
    base = dict(task="AB2", runid="AB-2", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=False)
    reg.upsert(metric_id="ab2.auroc_mpnet", value=round(auroc(mpnet, refs), 4), n=len(items),
               caveats=["all-mpnet-base-v2 cosine over claim statements (rung a, CPU-local) vs "
                        "judge-after-audit reference; rungs (b) large / (c) reranker DEFERRED "
                        "(need GPU/VRAM≥40GB or an API substitute — not run, not silently swapped)"], **base)
    reg.upsert(metric_id="ab2.auroc_typed", value=round(auroc(typed, refs), 4), n=len(items),
               caveats=["rung (d) typed-rendering embedding (mpnet over '<et> <pol> <value> on <axis>')"], **base)
    reg.upsert(metric_id="ab2.auroc_judge", value=round(auroc([float(x) for x in judge], refs), 4), n=len(items),
               caveats=["rung 6 = ported judge (grade-mapped). NB near-circular: the reference IS "
                        "judge-after-audit, so this is the ceiling by construction, reported as such"], **base)
    reg.upsert(metric_id="ab.direction_errors_mpnet", value=direction_errors(mpnet), n=len(items),
               caveats=["axis-match but polarity-opposed/family-disjoint pairs scored high by mpnet "
                        "(the Hale direction-error hook — embeddings chase surface similarity)"], **base)
    reg.save()
    print(f"AB2: AUROC mpnet={auroc(mpnet,refs):.4f}, typed={auroc(typed,refs):.4f}, "
          f"judge(rung6)={auroc([float(x) for x in judge],refs):.4f}; "
          f"direction-errors mpnet={direction_errors(mpnet)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
