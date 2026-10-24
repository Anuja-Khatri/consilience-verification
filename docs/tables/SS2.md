# SS2 — registry metrics

| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |
|---|---|---|---|---|---|---|---|---|
| `ss2.excluded_vars` | polarity |  | 1 | frozen-store | v1 | Y | Y | polarity excluded from Arm 1 — single-class (95 asserts, 0 denies), zero entropy; the single-class fact is itself a finding (see B3 PABAK note) |
| `ss2.null_z_corpus` | 11.98 |  | 1000 | frozen-store | v1 | Y | Y | z vs 1000 per-column field-shuffle surrogates; null μ=0.7882 σ=0.0743 (n=1000) |
| `ss2.null_z_crosstheory` | 13.57 |  | 1000 | frozen-store | v1 | Y | Y | z vs 1000 field-shuffle surrogates; null μ=-0.1043 σ=0.0271 (n=1000) |
| `ss2.o_info_active-inference` | 1.406 |  | 16 | frozen-store | v1 | Y | Y | per-theory pilot (Active Inference, n=16); sign redundancy-dominated; null μ=1.2848 σ=0.1410 (n=1000) |
| `ss2.o_info_cemi` | 1.883 |  | 15 | frozen-store | v1 | Y | Y | per-theory pilot (CEMI, n=15); sign redundancy-dominated; null μ=1.4269 σ=0.1459 (n=1000) |
| `ss2.o_info_corpus` | 1.678 |  | 95 | frozen-store | v1 | Y | Y | whole-corpus O-info over (entity_type,axis,family); sign redundancy-dominated; null μ=0.7882 σ=0.0743 (n=1000); polarity EXCLUDED (single-class 95 asserts/0 denies, zero entropy) |
| `ss2.o_info_crosstheory` | 0.2629 |  | 216 | frozen-store | v1 | Y | Y | cross-theory O-info over (axisA_family,axisB_family,grade); sign redundancy-dominated; null μ=-0.1043 σ=0.0271 (n=1000) |
| `ss2.o_info_gnwt` | 1.904 |  | 19 | frozen-store | v1 | Y | Y | per-theory pilot (GNWT, n=19); sign redundancy-dominated; null μ=1.6916 σ=0.1181 (n=1000) |
| `ss2.o_info_iit` | 2.392 |  | 24 | frozen-store | v1 | Y | Y | per-theory pilot (IIT, n=24); sign redundancy-dominated; null μ=2.0804 σ=0.0947 (n=1000) |
| `ss2.o_info_nrep` | 2.046 |  | 10 | frozen-store | v1 | Y | Y | per-theory pilot (NREP, n=10); sign redundancy-dominated; null μ=1.5079 σ=0.1428 (n=1000) |
| `ss2.o_info_orch-or` | 2.05 |  | 11 | frozen-store | v1 | Y | Y | per-theory pilot (Orch-OR, n=11); sign redundancy-dominated; null μ=2.1188 σ=0.0981 (n=1000) |
