# Falsifiability audit (TD5 / Sussex)

## 1. Her criteria ↔ the Rosas schema
| our control | Rosas-schema analogue | registry metric |
|---|---|---|
| provenance / quote-support (A1 C1/C2) | decomposition of the claim | a1.* (pending C2) |
| Newman screen (A1 C3) | — | a1.* |
| perturbation contracts (B2) | surrogate data | b2.* (pending) |
| obfuscation control (A6) | null models | a6.* (pending) |
| answer-key diffs (KR) | preregistration | kr.* |
| **surrogate nulls (this doc)** | **null models** | **r1.null_z_corr_count_\*** |

## 2. Surrogate nulls for the match rate (the new computation)
Real correspondence count over the 13 persisted pairs: **221**. Null distributions (1000 surrogates each; ported judge; node-only since the count is edge-independent):

| null model | destroys | null μ±σ | real z | p(≥real) |
|---|---|---|---|---|
| S1 axis-shuffle (marginal) | claim↔axis pairing | 206.19±6.52 | 2.271 | 0.001 |
| S1 axis-shuffle (uniform) | axis marginal too | 114.88±23.98 | 4.426 | 0.002 |
| S2 value-shuffle (within axis) | value↔axis pairing | 224.19±1.43 | -2.241 | 0.99101 |
| S3 theory-scramble | theory membership | 221.16±9.92 | -0.016 | 0.55844 |

**Honest reading (each null says something different):**
- **S1 (axis-shuffle): z=2.271 (real ABOVE null, p=0.001).** The correspondence count depends on the real claim↔axis pairing — not an artifact of the per-theory axis marginals. Marginal (S1) and uniform (S1-uniform) agree in direction.
- **S2 (value-shuffle): z=-2.241 (real BELOW null).** Shuffling values within an axis yields MORE correspondences than the real values — i.e. the real typed values are *more discriminative* than chance (they create fewer spurious family matches). A point in the engine's favour, reported as-is.
- **S3 (theory-scramble): z=-0.016 (real ≈ null).** The corr COUNT is invariant to theory membership (candidacy is axis-driven) — so count is NOT a good statistic for "theories differ"; which pairs correspond differs, not how many. Reported honestly as a scope limit of the count statistic.

### Per-axis null placement (which axes beat chance)
- beats chance (z>1.64): ['computability', 'substrate_dependence']
- does NOT beat chance: ['architecture', 'fundamentality', 'identity_relation', 'mechanism', 'unit_threshold'] (reported by name — honest)

## 3. What would falsify what
| headline claim | observation that would kill it | could this evaluation produce it? |
|---|---|---|
| correspondences are non-chance | real count inside the S1/S2 null band | YES (this test; it did not) |
| judge is deterministic | re-run hash differs | YES (CI fixture; it does not) |
| not lexical memory | obfuscated recovery = clean recovery gap ~0 (A6) | YES (A6, pending) |
| negation tracked | negation fails to flip polarity (B2) | YES (B2, pending) |

## R3 — computational closure (interpretive, NOT a result)
The typed layer behaves as a closed macro-description: B2's invariance numbers (pending) will measure how often the macro-variables are preserved under micro-rewrites. Flagged as interpretive framing, not a measured claim.

*S4 key-recovery nulls (per-key chance recovery rate) are deferred until the KR diffs land; the machinery is in place (random typed-row keys vs the ported judge).*


## S4 key-recovery nulls (now computed — KR1)
KR1 COGITATE: real recovered **2/3** vs 1000 random typed-row keys → null μ=0.531, **z=2.27**, empirical p(≥2)=0.075; recovered+partial real 2, z=1.62816017456199, p=0.155. This is the chance rate that makes the recovery interpretable (r1.key_null_z_cogitate). KR2 INTREPID recovery is qualitative → row-null N/A; KR3+ await their PDFs.
