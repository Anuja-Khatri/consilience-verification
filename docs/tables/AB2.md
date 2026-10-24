# AB2 — registry metrics

| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |
|---|---|---|---|---|---|---|---|---|
| `ab.direction_errors_mpnet` | 26 |  | 122 | frozen-store | v1 | Y | N | axis-match but polarity-opposed/family-disjoint pairs scored high by mpnet (the Hale direction-error hook — embeddings chase surface similarity) |
| `ab2.auroc_judge` | 1 |  | 122 | frozen-store | v1 | Y | N | rung 6 = ported judge (grade-mapped). NB near-circular: the reference IS judge-after-audit, so this is the ceiling by construction, reported as such |
| `ab2.auroc_mpnet` | 0.6224 |  | 122 | frozen-store | v1 | Y | N | all-mpnet-base-v2 cosine over claim statements (rung a, CPU-local) vs judge-after-audit reference; rungs (b) large / (c) reranker DEFERRED (need GPU/VRAM≥40GB or an API substitute — not run, not silently swapped) |
| `ab2.auroc_typed` | 0.8417 |  | 122 | frozen-store | v1 | Y | N | rung (d) typed-rendering embedding (mpnet over '<et> <pol> <value> on <axis>') |
