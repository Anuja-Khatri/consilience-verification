#!/usr/bin/env python3
"""pipeline/ss3_synthesis.py — SS3 spectrometer synthesis (SPEC §6 SS3). One brief joining
VJ1.4 rule-ablation (interventional) + SS1 PID atoms (information) + SS2 O-info signs
(systemic). G5 bias table + mn3.shortcut_rate_* are appended later (need AB2/AB5/B4)."""
import json, sys
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
R = {m["metric_id"]: m for m in json.loads((SPRINT/"results"/"registry.json").read_text())["metrics"]}
def v(k): return R.get(k, {}).get("value")
brief = f"""# Structure spectrometer — one build, three instruments (SS3)

Three independent readings of the SAME deterministic verdict, from the frozen store:

1. **Interventional (VJ1.4 rule-ablation).** Disabling each rule family changes verdicts by:
   axis veto **{v('vj1.rule_ablation_axis')}**, value-family **{v('vj1.rule_ablation_family')}**,
   polarity **{v('vj1.rule_ablation_polarity')}**, neighbour **{v('vj1.rule_ablation_neighbour')}**.
   The axis veto + family match carry the judgment.
2. **Information (SS1 PID of the verdict).** Over the axis-matched candidacy pairs (X1 dropped
   as the constant veto), synergy share ≈ **{v('ss1.synergy_share_imin')}** (I_min) /
   **{v('ss1.synergy_share_mmi')}** (MMI) — NOT synergy-dominated; the verdict is dominated by
   the UNIQUE contribution of value-family match (max unique ≈ {v('ss1.max_unique_imin')}).
   Measure-robust across I_min and MMI.
3. **Systemic (SS2 O-information).** The typed fields are **redundancy-dominated**: whole-corpus
   O-info **{v('ss2.o_info_corpus')}** (z {v('ss2.null_z_corpus')}), cross-theory
   **{v('ss2.o_info_crosstheory')}** (z {v('ss2.null_z_crosstheory')}); polarity excluded
   (single-class). Both significant vs 1000 field-shuffle surrogates.

**One story.** Interventional, information-theoretic, and systemic instruments agree: the
engine's verdict is carried by a small set of near-necessary typed conditions (axis veto +
value-family), not by an irreducible high-order synergy. The honest negative on the
synergy hypothesis is itself the finding; it says the gate is *legible*, not *entangled*.

*Pending (appended when AB2/AB5/B4 land): G5 surface-similarity bias table and the
mn3.shortcut_rate_<method> reasoning-shortcut rates per method.*
"""
(SPRINT/"docs"/"briefs"/"structure-spectrometer.md").write_text(brief)
print("SS3 → docs/briefs/structure-spectrometer.md")
