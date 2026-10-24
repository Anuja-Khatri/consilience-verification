# VJ1 — registry metrics

| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |
|---|---|---|---|---|---|---|---|---|
| `vj1.equivalence_rate` | 1 |  | 213 | frozen-store | v1 | Y | N | Python judge port vs logic program (minidatalog); 213 comparisons (13 persisted pairs covering 221 corrs + 200 synthetic); per-verdict 666/666=1.0000. Primitives materialised from p5 (bounded treatment); rules transcribe the grade/fork decision tree. no divergences |
| `vj1.rule_ablation_axis` | 2801 |  | 316 | frozen-store | v1 | Y | N | verdicts changed (sym-diff) when the axis rule family is disabled, over the 13 persisted pairs (316 baseline verdicts); interventional complement to SS1's information decomposition |
| `vj1.rule_ablation_family` | 30 |  | 316 | frozen-store | v1 | Y | N | verdicts changed (sym-diff) when the family rule family is disabled, over the 13 persisted pairs (316 baseline verdicts); interventional complement to SS1's information decomposition |
| `vj1.rule_ablation_neighbour` | 0 |  | 316 | frozen-store | v1 | Y | N | verdicts changed (sym-diff) when the neighbour rule family is disabled, over the 13 persisted pairs (316 baseline verdicts); interventional complement to SS1's information decomposition |
| `vj1.rule_ablation_polarity` | 6 |  | 316 | frozen-store | v1 | Y | N | verdicts changed (sym-diff) when the polarity rule family is disabled, over the 13 persisted pairs (316 baseline verdicts); interventional complement to SS1's information decomposition |
