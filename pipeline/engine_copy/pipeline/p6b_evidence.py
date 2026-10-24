#!/usr/bin/env python3
"""E2 — evidence layer. Joins ConTraSt experiments (via the approved contrast_axis_map) to
our fork axes and emits a per-axis evidence verdict for the ledger chip column.

Chip semantics (ruling 2):
  TESTED    — mapped ConTraSt studies bear on the fork's axis (show the count).
  CONTESTED — the axis's findings are claimed on more than one side (multiple theories /
              combined-theory attributions in ConTraSt = evidence on both sides).
  UNTESTED  — zero mapped studies (a decidable-but-unstudied fork = the fundable gap).

Per-tag pro/challenge counts are NOT exposed by the ConTraSt API (the interpretation filter
returns unfiltered totals), so contestation is measured from the finding-tag THEORY-attribution
series (which includes explicit combined keys like "GWT & IIT"). Deterministic; no LLM.
Writes results/evidence.json (axis -> evidence) + the click-through payload.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

DEMO = Path(__file__).resolve().parent.parent
CONTRAST = DEMO / "data" / "sources" / "contrast"
RESULTS = DEMO / "results"
MAP_YAML = DEMO / "vocab" / "contrast_axis_map.yaml"
CONTRAST_URL = "https://contrastdb.tau.ac.il"
CITATION = "Yaron, Melloni, Pitts & Mudrik (2022), Nature Human Behaviour 6(4), 593-604"


def main() -> int:
    if not MAP_YAML.exists():
        raise SystemExit("vocab/contrast_axis_map.yaml not found — the axis-map review must be approved first.")
    amap = yaml.safe_load(MAP_YAML.read_text())["finding_tag_to_axis"]  # tag -> axis
    ft = CONTRAST / "finding_tags.json"
    if not ft.exists():   # ConTraSt data is gitignored; skip cleanly on a fresh checkout (UI is graceful)
        print("  ConTraSt data absent (data/sources/contrast/) — evidence layer skipped; UI falls back to no chips.")
        return 0
    tags = json.loads(ft.read_text())                                    # [{series_name,value,series:[{value,key}]}]
    by_tag = {t["series_name"]: t for t in tags}

    # axis -> aggregate
    axes = {}
    for tag, axis in amap.items():
        t = by_tag.get(tag)
        if not t:
            continue
        a = axes.setdefault(axis, {"axis": axis, "total": 0, "theory_counts": {}, "tags": []})
        a["total"] += t.get("value", 0)
        a["tags"].append({"tag": tag, "n": t.get("value", 0)})
        for s in t.get("series", []):
            a["theory_counts"][s["key"]] = a["theory_counts"].get(s["key"], 0) + s.get("value", 0)

    evidence = {}
    for axis, a in axes.items():
        theories = a["theory_counts"]
        distinct = {k for k in theories}                      # includes combined keys like "GWT & IIT"
        multi = len([k for k in distinct if "&" not in k]) >= 2 or any("&" in k for k in distinct)
        verdict = "UNTESTED" if a["total"] == 0 else ("CONTESTED" if multi else "TESTED")
        evidence[axis] = {
            "verdict": verdict, "n_studies": a["total"],
            "theories": dict(sorted(theories.items(), key=lambda x: -x[1])),
            "tags": sorted(a["tags"], key=lambda x: -x["n"]),
            "contrast_url": CONTRAST_URL, "citation": CITATION,
        }
    # every fork axis gets an entry; those with NO ConTraSt mapping -> UNTESTED (the fundable gap)
    for axis in ("locus", "temporal_profile", "connectivity", "observable_commitment",
                 "substrate_dependence", "mechanism_scale", "computability"):
        evidence.setdefault(axis, {"verdict": "UNTESTED", "n_studies": 0, "theories": {}, "tags": [],
                                   "contrast_url": CONTRAST_URL, "citation": CITATION})

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "evidence.json").write_text(
        json.dumps({"source": "ConTraSt snapshot taken via the ConTraSt API, 2026-08-13 (contrastdb.tau.ac.il)", "citation": CITATION,
                    "contrast_url": CONTRAST_URL, "axes": evidence}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    for axis, e in sorted(evidence.items()):
        print(f"  {axis:22} {e['verdict']:9} n={e['n_studies']:<4} theories={list(e['theories'])[:5]}")
    print("  -> results/evidence.json")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
