# docs/instrument_v2.md — Instrument v2 (FROZEN 2026-10, A5.3)

FROZEN per owner decision on `review/a5_adoption_2026-10.md`: **adopt-baseline**. Decision
logged as D1 (`docs/DECISIONS.md`); machine record `results/instrument_v2_freeze.json`
(v2_system_sha `2fc0035d…`). `instrument_tag: v2` is now mandatory in extraction manifests.

## Determinism (owner ruling v2.0.3 — stated once, here)
**Determinism of all downstream artifacts rests on the `pipeline/llm.py` cache, NOT on
decoding.** The Anthropic API (SDK 2.1.0) exposes no temperature/sampling knob for the
the models (`claude-sonnet-4-6` returns HTTP 400 "temperature: Extra inputs are not
permitted"), so decoding is the provider default throughout — identical to production. What
makes every rerun byte-identical is the cache key = sha256 of the FULL request (model,
system, messages, max_tokens, every param sent, `replicate_tag`): a cache hit returns the
exact stored response. Reproducibility is a property of the cache + replicate_tag discipline,
not of a temperature setting.

## Models
- extractor: `claude-sonnet-4-6` (== production p2_extract.py SONNET; parity asserted, W0.2).
- checker (same-family cross-check, never "independent"): `claude-haiku-4-5-20251001`.
- max_tokens 1500 (extract) / 200 (haiku); CLAIMS_PER_WINDOW 4.

## Prompt version
- v1 = production p2 system prompt (byte-identical reconstruction; system-prompt sha
  `a6dc88a2…`).
- v2 = v1 + a `Definitions:` block after the vocab lists (A5.2), built verbatim from
  `vocab/entity_types.yaml` + `axes.yaml` (Task-3b condition B; 14 entity + 12 axis defs).
  Definitions adopted on Task-3b's standing result (+0.105 entity-κ directional, CIs cross 0,
  fixes 73 vs stretch-fits 35); the ablation is NOT rerun. Shas: v1_system `758e5943…`,
  definitions_block `a0a88d9c…`, **v2_system `2fc0035d…`** (= the frozen extraction prompt,
  `results/instrument_v2_prompt.txt`).

## Decoding
- Provider default (no temperature); `temperature_applied: false` for all Anthropic calls
  (v2.0.3). A t0 arm is not-applicable (no temperature knob).

## Adopted decoding arm (A5.1 → A5.3)
One estimator throughout (the A5 cluster identity: (entity_type,axis,polarity)+value-family).
All figures Wilson 95% CI, from `results/registry.json`:
- baseline single-pass (single-pass estimator): **0.250** [0.171, 0.350]  *(the imported Task-5
  0.271 is a different clustering — passage-based — and is NOT used for adoption)*
- arm (c) consensus-of-5: **0.170** [0.106, 0.262], windowed coverage 0.258
- arm (d) confidence-weighted: **0.346** [0.250, 0.457], windowed coverage 0.258
- arm (b) t0: not-applicable
- preregistered gate: stability ≥0.70 AND windowed coverage ≥0.85 — **no arm passes**.
- live-vs-cache stability difference: within sampling variation (Fisher p=0.267).

**DECISION (D1, owner-approved): adopt single-pass baseline decoding** — the candidate
consensus arm (confweighted) failed the gate, and t0 (the only arm that could otherwise change
the instrument) is not-applicable. Consensus does not rescue stability here; the human
approval gate remains the reliability mechanism.

## Vocab / judge
- vocab: engine `vocab/axes.yaml`, `entity_types.yaml` (frozen; in engine fingerprint).
- judge hash: engine_fingerprint combined `09b90e8d…`; ported judge reproduces all 221
  persisted correspondences (W0.4).

## Freeze status — FROZEN 2026-10 (A5.3)
`instrument_tag: v2` is now mandatory in extraction manifests. A5.1 arms remain tagged `v1`
(they measured the v1 prompt pre-freeze). Machine record: `results/instrument_v2_freeze.json`.
A key diff or measurement run after ANY change to this instrument bumps the tag and
invalidates/reruns per the numbers lock (§0.8).
