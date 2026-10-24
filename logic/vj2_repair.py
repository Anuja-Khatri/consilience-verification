#!/usr/bin/env python3
"""
logic/vj2_repair.py — VJ2.4 repair-loop demonstration (F3, PEIRCE-style) (SPEC §VJ2.4).

A3's `flagged` real-contradiction forks are not yet available, so (per spec) the conjecture
→ criticism → correction → re-check loop is shown on ONE clearly-labelled SYNTHETIC planted
error: a fork that exists only because a value was mis-typed; correcting the value (the
"counter-evidence") makes the families agree and the Z3-checked verdict flips fork→corr.
Writes docs/briefs/repair-loop.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import fol  # noqa: E402
import p5_judge as P5  # noqa: E402


def mkpair(val_a, val_b, axis="locus", pol="asserts"):
    A = {"theory": "T1", "edges": [], "nodes": [{"claim_id": "T1_x", "theory": "T1",
         "entity_type": "process", "axis": axis, "polarity": pol, "value": val_a}]}
    B = {"theory": "T2", "edges": [], "nodes": [{"claim_id": "T2_y", "theory": "T2",
         "entity_type": "process", "axis": axis, "polarity": pol, "value": val_b}]}
    return A, B


def verdict(A, B):
    out = P5.judge_pair(A, B)
    if out["forks"]:
        return "fork"
    if out["correspondences"]:
        return out["correspondences"][0]["grade"]
    return "none"


def main() -> int:
    # CONJECTURE: a fork on `locus`, but side A's value was mis-typed ("preforntal" typo)
    A, B = mkpair("preforntal_cortex", "prefrontal_cortex")   # planted typo breaks same_family
    v0 = verdict(A, B)
    prims0 = fol.primitives(A, B)[("T1_x", "T2_y")]
    ent_fork, _ = fol.entailed("fork", prims0)
    # CRITICISM / COUNTER-EVIDENCE (synthetic): the quote actually says "prefrontal cortex"
    # CORRECTION: fix the typed value
    A2, _ = mkpair("prefrontal_cortex", "prefrontal_cortex")
    v1 = verdict(A2, B)
    prims1 = fol.primitives(A2, B)[("T1_x", "T2_y")]
    ent_corr, _ = fol.entailed("generative", prims1)

    brief = f"""# Repair loop — conjecture → criticism → correction → Z3 re-check (VJ2.4 / F3)

**⚠ SYNTHETIC example (clearly labelled).** A3 produced no real-contradiction `flagged`
forks at the time of writing, so — per the spec — the Peirce-style repair loop is shown on
one planted error, never a fabricated real one.

1. **Conjecture.** Two claims on axis `locus`, side A mis-typed `preforntal_cortex` (a typo),
   side B `prefrontal_cortex`. The judge emits a **{v0}** (the typo breaks the value-family
   match → `locus` is a fork axis → fork). Z3: `fork` entailed = **{ent_fork}**
   (primitives SF={prims0['SF']}, OP={prims0['OP']}, FA={prims0['FA']}).
2. **Criticism / counter-evidence.** Reading the source quote shows the claim is about the
   *prefrontal cortex* — the fork exists only because of the typo, not a real disagreement.
3. **Correction.** Fix the typed value to `prefrontal_cortex`.
4. **Z3 re-check.** The families now agree; the verdict flips to **{v1}** (Z3: `generative`
   entailed = **{ent_corr}**, SF={prims1['SF']}). The fork is gone — the correction is
   verified by the SMT solver, not asserted by hand.

This is the conjecture–criticism loop operating over typed claims with a machine-checked
disposition: soft reading proposes the fix; the hard, autoformalised judge disposes.
"""
    (SPRINT / "docs" / "briefs").mkdir(parents=True, exist_ok=True)
    (SPRINT / "docs" / "briefs" / "repair-loop.md").write_text(brief)
    print(f"VJ2.4 repair loop: {v0} (fork entailed {ent_fork}) → corrected → {v1} "
          f"(generative entailed {ent_corr}) → docs/briefs/repair-loop.md")
    assert v0 == "fork" and v1 != "fork", "repair-loop demo did not flip the verdict"
    return 0


if __name__ == "__main__":
    sys.exit(main())
