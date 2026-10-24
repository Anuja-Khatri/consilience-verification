# SS1 — registry metrics

| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |
|---|---|---|---|---|---|---|---|---|
| `ss1.constant_sources` | X1_axis |  | 1 | frozen-store | v1 | Y | Y | sources constant over the enumerated population (dropped from PID); candidacy structure described in prose |
| `ss1.max_unique_imin` | 0.226 |  | 311 | frozen-store | v1 | Y | Y | largest unique atom under imin |
| `ss1.max_unique_mmi` | 0.226 |  | 311 | frozen-store | v1 | Y | Y | largest unique atom under mmi |
| `ss1.synergy_share_4way` | 0.0024 |  | 311 | frozen-store | v1 | Y | Y | 4-way grade target (none/generative/partial/formal), I_min |
| `ss1.synergy_share_imin` | 0.0024 |  | 311 | frozen-store | v1 | Y | Y | synergy atom / I(sources:Y) under Williams–Beer I_min; sources=['X2_polcompat', 'X3_family', 'X4_neighbour']; exact enumeration N=311 pairs; constant (dropped): ['X1_axis']; true 4-source BROJA unavailable (measure-sensitivity pair) |
| `ss1.synergy_share_mmi` | 0.0024 |  | 311 | frozen-store | v1 | Y | Y | synergy atom / I(sources:Y) under MMI; sources=['X2_polcompat', 'X3_family', 'X4_neighbour']; exact enumeration N=311 pairs; constant (dropped): ['X1_axis']; true 4-source BROJA unavailable (measure-sensitivity pair) |
