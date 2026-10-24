# TD1B — registry metrics

| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |
|---|---|---|---|---|---|---|---|---|
| `td1b.new_claims` | 21 |  | 27 | v2 | v2b | N | N | TD1b ML-bridge corpus v2b stored for KR4 (the ML side of the homology recovery): 21 approved claims {'control_as_inference': 7, 'pc_backprop': 10, 'mbrl': 4}. Owner rules applied (no consciousness-insertion, no dup-of-engine, codebook meanings). Decisions were model-drafted suggestions (Claude) reviewed and confirmed by Anu. |
| `td1b.untypeable_rate_cai` | 0 |  | 11 | v2 | v2b | N | N | axis:none rate for source cai (control_as_inference) under the consciousness-tuned v1 vocab (DRAFT, pre-approval). >0.60 ⇒ this source's KR4 rows become `undiffable (vocabulary)` — a domain-transfer FINDING, never patched by vocab edits. This source: diffable. |
| `td1b.untypeable_rate_mbrl` | 0 |  | 4 | v2 | v2b | N | N | axis:none rate for source mbrl (mbrl) under the consciousness-tuned v1 vocab (DRAFT, pre-approval). >0.60 ⇒ this source's KR4 rows become `undiffable (vocabulary)` — a domain-transfer FINDING, never patched by vocab edits. This source: diffable. |
| `td1b.untypeable_rate_pcbp` | 0.25 |  | 12 | v2 | v2b | N | N | axis:none rate for source pcbp (pc_backprop) under the consciousness-tuned v1 vocab (DRAFT, pre-approval). >0.60 ⇒ this source's KR4 rows become `undiffable (vocabulary)` — a domain-transfer FINDING, never patched by vocab edits. This source: diffable. |
