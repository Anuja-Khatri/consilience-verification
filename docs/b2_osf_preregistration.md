# B2 — OSF preregistration

**REGISTERED (public): https://osf.io/5n24m · DOI 10.17605/OSF.IO/5N24M · date registered 2026-10-23.**
B2 ran against this frozen preregistration; the DOI is cited in the B2 manifest, registry caveats, and
docs/briefs/negation-contract.md. (Below: the paste-ready prereg text as registered.)

**Title.** Statement-level perturbation contracts for a deterministic typed-claim judge:
invariance, negation-tracking, and a re-extraction noise-floor control.

**Design.** Confirmatory. Instrument v2 (frozen; provider-default decoding + A5.2 definitions
prompt). Reference labels are judge-after-audit (a trained annotator applying the published
codebook); the model panel measures protocol reproducibility, not validity.

## Hypotheses (per perturbation class)
Each passage is rewritten by one transformation; we extract typed claims (entity_type, axis,
polarity, value) from the rewrite and compare to the canonical claims (Level 1), then substitute
into the judge and compare verdicts (Level 2).

| class | type | preregistered expectation |
|---|---|---|
| **identity (control)** | noise floor | passage UNCHANGED, same replicate count — establishes the re-extraction noise floor; every other class is scored RELATIVE to it |
| paraphrase (near / far) | invariance | typed fields unchanged; verdict unchanged |
| casing (UPPER / tOGGLE) | invariance | unchanged |
| typos (1/12 tokens, seeded) | invariance | unchanged |
| notation swap (symbol↔name) | invariance | unchanged |
| register-formal (G4) | invariance | unchanged |
| register-popsci (G4) | invariance | unchanged |
| hedging | declared edge | field behaviour REPORTED; polarity has no hedged value → logged as a vocabulary limitation, not pass/fail |
| negation (single) | tracking | polarity flips to `denies`; L2 verdict updates |
| negation (double) | tracking | round-trip returns to `asserts` |
| entity swap (posterior↔frontal, gamma↔alpha, late↔early) | tracking | value family swaps; fork side updates |

## Preregistered analysis
- **Passages (frozen before running):** 40 passages stratified over IIT/GNWT × {locus,
  connectivity, temporal_profile, observable_commitment, substrate_dependence}; MUST include every
  passage under the 3 COGITATE-fork claims and the 6 beyond-key disagreements; seeded fill. Frozen
  to `results/b2_passages.json`.
- **Generation:** perturber at provider-default decoding, one class per call, verbatim class
  instructions; length within ±15%; double-negation chained programmatically; casing/typos/notation
  programmatic.
- **Verification:** gpt-4.1 per item ("does the rewrite implement exactly this class and nothing
  else?"); invalid → one regeneration then drop+log; 10% hand-check (min 4/class).
- **Level 1 (typing stability):** per class per field, agreement (invariance) or correct-change
  (tracking), with selection-loss reported beside every rate.
- **Level 2 (verdict tracking):** negation + entity-swap substituted into the 13 persisted pair
  graphs → judge → verdict delta.

## v2.0.4 identity-control test (the key safeguard)
Because single-pass extraction carries a measured re-extraction noise floor (A5: ~0.25 stability,
~0.39 windowed coverage per run), an invariance class is NOT evaluated against perfection — it is
evaluated against the **identity control** (the unchanged passage through the identical pipeline,
same replicate count):

> **Preregistered test.** For each invariance class, compute (class L1 field-agreement rate,
> identity-control rate, difference). An invariance class **PASSES iff it is NOT significantly
> worse than identity** — one-sided bootstrap over passages (resample passages with replacement,
> 2000×, seed 20261022), α = 0.05, testing H₀: rate_class ≥ rate_identity − δ. Every L1 number is
> reported as (rate, identity rate, difference ± 95% CI). Negation/entity-swap tracking rates are
> likewise reported beside the identity rate.

## Primary outcomes (metric_ids, bootstrap-over-passages CIs)
`b2.l1_<class>_<field>`, `b2.negation_polarity_tracking`, `b2.double_negation_restoration`,
`b2.verdict_tracking_correct`, `b2.selection_loss_<class>`, and the identity-relative differences.

## Depth arm (negation headline)
Negation at three syntactic depths (clause negation / lexical antonym / scope-ambiguous "not
only"), 10 passages each, separate rates; per-axis negation-tracking breakdown; a failure gallery
(every negation miss: quote → extraction → expected).

**Stopping rule.** Fixed 40-passage set; no optional stopping. **Analyst blinding.** The judge is
deterministic and read-only; Anu's role is approver (handcheck disagreement >15% in any class →
HALT-ASK), never label author.
