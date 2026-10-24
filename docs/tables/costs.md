# docs/tables/costs.md — spend report (SPEC §A5.5)

_Generated from results/cost_meter.json (artifact_stamp 2026-10). Determinism via the llm.py cache; $0 to regenerate._

**Total spent: $12.5954 / $900 hard cap (1.40%).**

## Per task (meter task_id)

| task_id | calls | in_tok | out_tok | USD |
|---|--:|--:|--:|--:|
| B2 | 903 | 504173 | 162127 | 3.7782 |
| A5 | 242 | 421255 | 131527 | 3.2367 |
| KR1 | 343 | 372658 | 57689 | 1.5154 |
| TD4_game | 420 | 235841 | 38100 | 1.2790 |
| B5 | 150 | 166150 | 49295 | 1.2379 |
| B3 | 338 | 292839 | 5967 | 0.6177 |
| A2 | 34 | 38942 | 11816 | 0.2941 |
| AB_bench | 120 | 21926 | 6703 | 0.1663 |
| TD1_aif | 8 | 21956 | 3740 | 0.1220 |
| TD2_variants | 8 | 17207 | 3735 | 0.1076 |
| TD1b_ml | 7 | 13342 | 2968 | 0.0845 |
| KR_keys | 3 | 20620 | 2523 | 0.0614 |
| A4 | 18 | 6677 | 4285 | 0.0476 |
| A1 | 55 | 7064 | 2511 | 0.0342 |
| A3 | 33 | 4341 | 330 | 0.0113 |
| B3-smoke | 2 | 607 | 18 | 0.0014 |
| B3-precond | 1 | 18 | 1 | 0.0000 |
| B3-dbg | 1 | 0 | 0 | 0.0000 |

## Budget-group rollup (vs config budget_usd)

| budget group | calls | USD | budget | % of budget |
|---|--:|--:|--:|--:|
| B2 | 903 | 3.7782 | $170 | 2.2% |
| A5 | 242 | 3.2367 | $120 | 2.7% |
| KR_keys | 346 | 1.5768 | $20 | 7.9% |
| TD4_game | 420 | 1.2790 | $60 | 2.1% |
| B5 | 150 | 1.2379 | $30 | 4.1% |
| B3 | 342 | 0.6191 | $90 | 0.7% |
| A2 | 34 | 0.2941 | $40 | 0.7% |
| AB_bench | 120 | 0.1663 | $50 | 0.3% |
| TD1_aif | 8 | 0.1220 | $40 | 0.3% |
| TD2_variants | 8 | 0.1076 | $30 | 0.4% |
| (no budget line — data/frozen-store) | 106 | 0.0932 | — | — |
| TD1b_ml | 7 | 0.0845 | $15 | 0.6% |

## A2 per-verdict cost (SPEC §A5.5)

A2 total $0.2941 over 17 pair verdicts = **$0.0173/verdict** (agreement_rate 0.1429, downgrade_rate 0.8571).

## Pricing provenance + gaps

Rates in `pipeline/llm.py PRICING` (USD per 1M tokens). gemini-3.1-pro-preview: input $2 / output $12 (≤200k tier), thinking tokens billed at the output rate — https://ai.google.dev/gemini-api/docs/pricing (fetched 2026-10-23).
- **Backfill gemini-3.1-pro-preview-B3-2: +$0.3223** — 156 calls, recorded input 141661 + output(candidates) 3250 tokens @ $2/$12 per M (ai.google.dev/gemini-api/docs/pricing, 2026-10-23). GAP: thoughts_token_count NOT captured at run time (billed at output rate) -> this backfill EXCLUDES thinking tokens (lower bound); adapter now folds thoughts into output.
- **Open-weight panel leg (qwen2.5-72b / llama-3.3-70b): DEFERRED — no TOGETHER/FIREWORKS key.** Priced in PRICING but never called; B3 panel is two-vendor (gpt-4.1 + gemini-3.1-pro). Stated as a limitation in B3 and the paper.
