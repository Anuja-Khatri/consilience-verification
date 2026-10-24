# AB1 — registry metrics

| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |
|---|---|---|---|---|---|---|---|---|
| `ab.direction_errors_jaccard` | 21 |  | 122 | frozen-store | v1 | Y | N | axis-match but polarity-opposed/family-disjoint pairs scored high by Jaccard |
| `ab.direction_errors_tfidf` | 22 |  | 122 | frozen-store | v1 | Y | N | axis-match but polarity-opposed/family-disjoint pairs scored above the 70th percentile by TF-IDF (the Hale direction-error hook) |
| `ab1.auroc_jaccard` | 0.7044 |  | 122 | frozen-store | v1 | Y | N | Jaccard over A1-C3 content tokens vs reference |
| `ab1.auroc_tfidf` | 0.6218 |  | 122 | frozen-store | v1 | Y | N | TF-IDF cosine over claim statements vs judge-after-audit reference; the Newman floor (how far bag-of-words gets) |
