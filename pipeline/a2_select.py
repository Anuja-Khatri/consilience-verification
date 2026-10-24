#!/usr/bin/env python3
"""
pipeline/a2_select.py — A2 pair selection (SPEC §A2 "Pair selection, deterministic"). $0.

All A1 survivors (cap 15; overflow keeps Newman-clean + provenance-clean first, then seeded) + 15
failures stratified across the A1.4 taxonomy (≥2 per category where available), seeded fill. Target
30; floor 15 = 8+7. Each pair carries its OLD MIU tier (grade) + OLD decidability for A2.6. Freezes
results/a2_pairs.json. (Decisions were model-drafted suggestions reviewed+confirmed by Anu — D-035.)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
MIU = Path(os.path.expanduser(CFG["paths"]["miu"]))
SEED = int(CFG["seeds"]["global"])


def old_tier_index():
    idx = {}
    for rel in ("correspondences/correspondences.json", "supplementary/supplementary_matches.json",
                "engine-discovered/engine_discovered_matches.json"):
        p = MIU / rel
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        items = d if isinstance(d, list) else d.get("matches", d.get("correspondences", []))
        for it in items:
            if isinstance(it, dict) and it.get("match_id"):
                idx[it["match_id"]] = {"old_grade": it.get("grade"), "old_decidability": it.get("decidability")}
    return idx


def main() -> int:
    verdicts = json.loads((SPRINT / "results" / "a1_verdicts.json").read_text())["verdicts"]
    tiers = old_tier_index()
    survivors = [m for m, r in verdicts.items() if r["verdict"] == "PASS"]
    failures = [(m, r["first_fail"]) for m, r in verdicts.items() if r["verdict"] == "FAIL"]

    # stratify failures: >=2 per taxonomy category, then seeded fill to 15
    import random
    rng = random.Random(SEED)
    by_cat = {}
    for m, cat in failures:
        by_cat.setdefault(cat, []).append(m)
    for v in by_cat.values():
        v.sort()  # deterministic base order
        rng.shuffle(v)
    picked, seen = [], set()
    for cat, ms in sorted(by_cat.items()):
        for m in ms[:2]:                       # >=2 per category where available
            if m not in seen:
                picked.append(m); seen.add(m)
    pool = [m for m, _ in sorted(failures) if m not in seen]
    rng.shuffle(pool)
    while len(picked) < 15 and pool:
        m = pool.pop()
        if m not in seen:
            picked.append(m); seen.add(m)

    sel = survivors[:15] + picked[:15]
    pairs = []
    for m in sel:
        r = verdicts[m]
        pairs.append({"match_id": m, "a1_verdict": r["verdict"], "a1_first_fail": r["first_fail"],
                      "old_grade": tiers.get(m, {}).get("old_grade"),
                      "old_decidability": tiers.get(m, {}).get("old_decidability"),
                      "role": "survivor" if r["verdict"] == "PASS" else "failure"})
    out = {"n": len(pairs), "n_survivors": len(survivors), "n_failures_selected": len(picked[:15]),
           "stratification": {c: len(v) for c, v in by_cat.items()}, "seed": SEED, "pairs": pairs}
    (SPRINT / "results" / "a2_pairs.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"A2 pair selection: {len(pairs)} pairs = {len(survivors)} survivors + {len(picked[:15])} failures "
          f"(stratified {out['stratification']}). → results/a2_pairs.json")
    for p in pairs:
        print(f"  {p['role']:8s} {p['match_id']:14s} a1={p['a1_first_fail'] or 'PASS':20s} old_grade={p['old_grade']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
