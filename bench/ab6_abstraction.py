#!/usr/bin/env python3
"""
bench/ab6_abstraction.py — AB6 Rung 5d: structured-abstraction arm (= F4, QuaSAR-style).
SPEC §AB6.  Live spend, billed to the AB_bench budget ($50).

Per bench pair, two arms with ONE model (the extractor, provider-default decoding = Anthropic has
no temperature knob, D-015):
  - ABSTRACTED (abstract-then-judge): the model first emits the typed fields (entity_type, axis,
    polarity, value) of EACH claim, THEN a correspondence judgment — a chain.
  - DIRECT (quote→judgment): the model judges correspondence straight from the two quotes, no
    abstraction step.
60-pair seeded subsample of the frozen AB0 bench (all positives + direction-error negatives first,
then seeded fill). Metric: ab6.acc_abstracted vs ab6.acc_direct vs the judge-after-audit reference
(binary). Does explicit structural abstraction improve model judgment (Freitas QuaSAR finding, on
claims)? Per-class + direction-error (axis-match & polarity-opposed) accuracies reported beside.
Corner: a refusal / unparseable JSON gets 2 schema-nudge retries (llm.py) then the item is
`malformed`, counted per arm (never silently dropped).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "bench"))

import llm as L  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
EXTRACTOR = CFG["models"]["extractor"]
SEED = int(CFG["seeds"]["global"])
N_SUB = 60
TASK = "AB_bench"

DIRECT_SYS = (
    "You decide whether two claims about consciousness describe a CORRESPONDING typed structure: "
    "the SAME entity on the SAME axis (dimension of disagreement) with COMPATIBLE polarity and the "
    "same value-family. Opposed-polarity pairs and different-axis pairs do NOT correspond even when "
    "they share vocabulary. Output ONLY JSON: {\"corresponds\": true|false}.")
ABSTRACT_SYS = (
    "First EXTRACT the typed fields of EACH claim, THEN decide correspondence. For each claim give "
    "entity_type, axis (the dimension of disagreement), polarity (asserts|denies), value. Two claims "
    "correspond iff SAME axis, COMPATIBLE polarity, and same value-family; opposed polarity or "
    "different axis ⇒ no correspondence even with shared words. Output ONLY JSON: "
    "{\"a\":{\"entity_type\":\"\",\"axis\":\"\",\"polarity\":\"\",\"value\":\"\"},"
    "\"b\":{\"entity_type\":\"\",\"axis\":\"\",\"polarity\":\"\",\"value\":\"\"},\"corresponds\":true|false}.")


def subsample(items):
    """Deterministic 60-pair subsample: all positives + all direction-error negatives first,
    then seeded fill from remaining negatives."""
    rng = random.Random(SEED)
    pos = [it for it in items if it["reference"] == "positive"]
    neg = [it for it in items if it["reference"] != "positive"]
    dir_err = [it for it in neg if it.get("axis_match") and it.get("polarity_opposed")]
    rest = [it for it in neg if not (it.get("axis_match") and it.get("polarity_opposed"))]
    dir_err.sort(key=lambda it: it["item_id"]); rest.sort(key=lambda it: it["item_id"])
    rng.shuffle(rest)
    chosen = list(pos) + list(dir_err)
    for it in rest:
        if len(chosen) >= N_SUB:
            break
        chosen.append(it)
    chosen.sort(key=lambda it: it["item_id"])
    return chosen[:N_SUB]


def judge(client, system, item, max_tokens):
    user = f"Claim A: {item['text_a']}\nClaim B: {item['text_b']}"
    rec = client.call_json(task_id=TASK, model=EXTRACTOR, system=system,
                           messages=[{"role": "user", "content": user}],
                           replicate_tag="ab6", temperature=None, max_tokens=max_tokens)
    if rec.get("json_status") != "OK" or not isinstance(rec.get("parsed"), dict):
        return None  # malformed (after llm.py's schema-nudge retries)
    return bool(rec["parsed"].get("corresponds"))


def accuracy(preds, items):
    ok = tot = 0
    for p, it in zip(preds, items):
        if p is None:
            continue
        tot += 1
        if p == (it["reference"] == "positive"):
            ok += 1
    return (ok / tot if tot else 0.0), tot


def main() -> int:
    data = json.loads((SPRINT / "bench" / "items.json").read_text())
    items = data if isinstance(data, list) else data["items"]
    sub = subsample(items)
    client = L.LLM()

    direct, abstr = [], []
    for it in sub:
        direct.append(judge(client, DIRECT_SYS, it, 150))
        abstr.append(judge(client, ABSTRACT_SYS, it, 400))

    acc_d, n_d = accuracy(direct, sub)
    acc_a, n_a = accuracy(abstr, sub)
    mal_d = sum(1 for p in direct if p is None)
    mal_a = sum(1 for p in abstr if p is None)

    def class_acc(preds, want_positive):
        ok = tot = 0
        for p, it in zip(preds, sub):
            if p is None or (it["reference"] == "positive") != want_positive:
                continue
            tot += 1
            if p == want_positive:
                ok += 1
        return round(ok / tot, 3) if tot else None, tot

    def direrr_acc(preds):  # axis-match & polarity-opposed negatives: should be rejected (False)
        ok = tot = 0
        for p, it in zip(preds, sub):
            if p is None or not (it.get("axis_match") and it.get("polarity_opposed")):
                continue
            tot += 1
            if p is False:
                ok += 1
        return round(ok / tot, 3) if tot else None, tot

    pos_a, npos = class_acc(abstr, True); neg_a, nneg = class_acc(abstr, False)
    pos_d, _ = class_acc(direct, True); neg_d, _ = class_acc(direct, False)
    de_a, nde = direrr_acc(abstr); de_d, _ = direrr_acc(direct)

    rundir = SPRINT / "runs" / "AB6" / "AB6-1"
    rundir.mkdir(parents=True, exist_ok=True)
    detail = {"n_subsample": len(sub), "extractor": EXTRACTOR, "seed": SEED,
              "acc_abstracted": round(acc_a, 4), "acc_direct": round(acc_d, 4),
              "malformed_abstracted": mal_a, "malformed_direct": mal_d,
              "per_class": {"abstracted": {"pos": pos_a, "neg": neg_a}, "direct": {"pos": pos_d, "neg": neg_d}},
              "n_pos": npos, "n_neg": nneg,
              "direction_error_reject_acc": {"abstracted": de_a, "direct": de_d, "n": nde},
              "items": [{"item_id": it["item_id"], "reference": it["reference"],
                         "abstracted": abstr[i], "direct": direct[i]} for i, it in enumerate(sub)]}
    (rundir / "ab6_detail.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n")

    reg = Registry()
    base = dict(task="AB6", runid="AB6-1", instrument_tag="v2", corpus_tag="v1",
                preregistered=True, pilot=False)
    cav = (f"QuaSAR-style abstract-then-judge vs direct-judge, one model ({EXTRACTOR}), provider-default "
           f"decoding (Anthropic has no temperature knob, D-015). 60-pair seeded subsample of frozen bench "
           f"v0.1 (all {npos} positives + direction-error negatives first, seeded fill). Reference = binary "
           f"judge-after-audit (NOT a leaderboard/gold). Imbalanced ({npos} pos / {nneg} neg) → per-class + "
           f"direction-error reject accuracies in runs/AB6/AB6-1/ab6_detail.json.")
    reg.upsert(metric_id="ab6.acc_abstracted", value=round(acc_a, 4), n=n_a,
               caveats=[cav, f"abstract-then-judge; per-class pos={pos_a} neg={neg_a}; "
                             f"direction-error reject acc={de_a} (n={nde}); malformed {mal_a}"], **base)
    reg.upsert(metric_id="ab6.acc_direct", value=round(acc_d, 4), n=n_d,
               caveats=[cav, f"direct quote→judgment; per-class pos={pos_d} neg={neg_d}; "
                             f"direction-error reject acc={de_d} (n={nde}); malformed {mal_d}"], **base)
    reg.save()

    write_manifest("AB6", "AB6-1", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(SPRINT / "bench" / "items.json"), "read-only")],
                   outputs=["runs/AB6/AB6-1/ab6_detail.json"], seeds={"global": SEED},
                   model_provenance=[{"role": "extractor", "model": EXTRACTOR, "instrument": "v2",
                                      "provider_seed_honored": False}],
                   notes="AB6 structured-abstraction (abstract-then-judge) vs direct-judgment over 60-pair bench subsample.")

    print(f"[AB6] n={len(sub)} (pos {npos}/neg {nneg}); acc_abstracted={acc_a:.4f} (mal {mal_a}) "
          f"vs acc_direct={acc_d:.4f} (mal {mal_d})")
    print(f"[AB6] direction-error reject acc abstracted={de_a} direct={de_d} (n={nde}); "
          f"per-class abstracted pos={pos_a}/neg={neg_a}, direct pos={pos_d}/neg={neg_d}")
    print(f"[AB6] meter total ${client.meter.data['total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
