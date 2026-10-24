# StructProbe-CSci v0.1 — datasheet (Measuring-What-Matters, honest)

Diagnostic probe set (NOT a leaderboard). 179 items; cells {'true_correspondence': 60, 'equivocation': 60, 'negation': 36, 'control_expected_flip': 5, 'control_invariant': 18}.
items.jsonl sha256 `6f216d42c7ecab71…`; v0.1; annotations CC-BY-4.0, quotes ≤25 words under source terms.

- **Composition:** true_correspondence (judge-after-audit), equivocation (MIU rejection records —
  shared vocabulary, NOT a correspondence), negation (constructed polarity-flip; B2 supersedes),
  controls (entity-swap expected-flip, casing invariant).
- **Conceded limitations:** convenience sample; one domain (consciousness theories + a MIU
  cross-field slice); single-codebook annotator (judge-after-audit, not multi-rater); contamination
  — public sources may be in training data (A6 is the related obfuscation control). Negation cell is
  constructed pending B2.
- **Intended use:** diagnosing the structure-vs-surface-similarity DISSOCIATION per method (does a
  method pass true_correspondence while rejecting equivocation?). NOT a leaderboard.
