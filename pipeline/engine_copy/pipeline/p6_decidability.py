#!/usr/bin/env python3
"""D5 decidability skeleton. Per fork axis + theory pair, emit a Verdict:
  now         — theories share an observable id at equal scale (current instruments)
  bridge      — decidable only under an authored, unproven bridge (answer_keys/bridges.yaml)
  not_current — no shared observable at current technology
Uses vocab/axes.yaml `observable_links` + vocab/observables.yaml scales. Deterministic, no LLM.
Full wiring over real Fork records lands in D5; this is the callable core + a demo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schemas import Verdict  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent
VOCAB = DEMO / "vocab"
BRIDGES = DEMO / "data" / "answer_keys" / "bridges.yaml"


def load_tables():
    axes = yaml.safe_load((VOCAB / "axes.yaml").read_text(encoding="utf-8"))
    obs = {o["id"]: o["scale"] for o in yaml.safe_load((VOCAB / "observables.yaml").read_text())["observables"]}
    bridges = yaml.safe_load(BRIDGES.read_text())["bridges"] if BRIDGES.exists() else []
    return axes.get("observable_links", {}), obs, bridges


def resolve_observables(links, axis, theory):
    entry = links.get(axis)
    if entry is None:
        return []
    if isinstance(entry, dict):        # per-theory (e.g. mechanism_scale)
        return list(entry.get(theory, []))
    return list(entry)


def theory_scale(theory, links, obs):
    """A theory's measurement scale = the scale of its mechanism_scale observables
    (IIT/GNWT -> brain_network, Orch-OR -> molecular). This is what makes IIT×Orch-OR
    forks NOT decidable at current tech even when their axis nominally links to the same
    observable id — the two theories measure in disjoint scale spaces."""
    ms = resolve_observables(links, "mechanism_scale", theory)
    scales = {obs.get(o) for o in ms if o in obs and obs.get(o) not in (None, "n/a")}
    return sorted(scales)[0] if scales else None


def decide(axis, left_theory, right_theory, tables=None):
    links, obs, bridges = tables or load_tables()
    left = set(resolve_observables(links, axis, left_theory))
    right = set(resolve_observables(links, axis, right_theory))
    shared = sorted(o for o in (left & right) if o != "none" and obs.get(o) not in (None, "n/a"))
    sl, sr = theory_scale(left_theory, links, obs), theory_scale(right_theory, links, obs)
    scale_match = sl is not None and sl == sr
    ref = f"{left_theory}x{right_theory}:{axis}"

    if shared and scale_match:
        return Verdict(fork_ref=ref, decidability="now", shared_observables=shared,
                       rationale=f"shared observable(s) {shared} at equal scale ({sl})").model_dump()
    # no shared observable at equal scale -> bridge if one is authored, else not_current
    for b in bridges:
        if b.get("applies_to_axis") == axis and set(b.get("pair", [])) == {left_theory, right_theory}:
            extra = f" (scales {sl} vs {sr} disjoint)" if not scale_match else ""
            return Verdict(fork_ref=ref, decidability="bridge", shared_observables=[],
                           bridge_note=b.get("note"),
                           rationale=f"decidable only under unproven bridge '{b.get('id')}'{extra}").model_dump()
    reason = (f"disjoint measurement scales ({sl} vs {sr})" if not scale_match
              else "no shared observable at current technology")
    return Verdict(fork_ref=ref, decidability="not_current", shared_observables=[], rationale=reason).model_dump()


def main() -> int:
    tables = load_tables()
    print("D5 decidability (demo over canonical fork axes):")
    for axis, l, r in [("locus", "IIT", "GNWT"), ("temporal_profile", "IIT", "GNWT"),
                       ("connectivity", "IIT", "GNWT"), ("substrate_dependence", "IIT", "GNWT"),
                       ("mechanism_scale", "IIT", "Orch-OR")]:
        v = decide(axis, l, r, tables)
        print(f"  {l:4} x {r:8} {axis:22} -> {v['decidability']:12} {v['shared_observables']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
