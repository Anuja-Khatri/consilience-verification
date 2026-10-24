# VJ2 — registry metrics

| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |
|---|---|---|---|---|---|---|---|---|
| `vj2.congruence_rate` | 1 |  | 311 | frozen-store | v1 | Y | N | 311/311 persisted verdicts entailed by the Z3-autoformalised judge (decision axioms mirror VJ1.2/p5); 0 undecided-by-solver (10s timeout). Primitives materialised from p5 (bounded treatment). |
| `vj2.f5_agreement` | 1 |  | 25 | frozen-store | v1 | Y | N | F5 logic-parametric: 25/25 pairs agree 3/3 across Python port, Datalog (VJ1), Z3-FOL |
| `vj2.flip_distance_min` | 1 |  | 25 | frozen-store | v1 | Y | N | counterfactual minimality: min primitive flips to change a verdict (dist mean 1, max 1) over 25 sampled verdicts |
