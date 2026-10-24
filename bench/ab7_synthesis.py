#!/usr/bin/env python3
"""bench/ab7_synthesis.py — AB7 bench synthesis (SPEC §5 AB7). One table across the rungs
(AB1 lexical, AB2 embedding ladder, AB3 Procrustes, AB4 GWOT) rendered from results/registry.json;
the discovery-instrument brief docs/briefs/alignment-bench.md (Hale/Goldstein/Monash). AB5/AB6
appended later (query packet / spend)."""
import json, sys
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
R = {m["metric_id"]: m["value"] for m in json.loads((SPRINT/"results"/"registry.json").read_text())["metrics"]}
def v(k): return R.get(k, "—")
items = json.loads((SPRINT/"bench"/"items.json").read_text())
# AB5 is PRELIMINARY (query packet AWAITING-ANU) — read from the preliminary file, mark it so.
_ab5p = SPRINT/"results"/"ab5_preliminary.json"
AB5 = json.loads(_ab5p.read_text())["metrics"] if _ab5p.exists() else None
def ab5(k, tn="min"): return (AB5[k][tn] if AB5 else "—")
brief = f"""# Alignment bench — six ways to align claim structures (AB7)

The point (fixed): several ways of aligning claim structures across theories, from lexical to
unsupervised-geometric, ALL scored against the same **judge-after-audit reference** — the typed
judge is rung 6, not the assumption. Frozen item set: **{items['n']} pairs** (bench {items['bench_version']},
{items['n_positive']} positive + {items['n_weak_positive']} weak-positive; A2 pairs deferred,
pending A1-C2). Reference labels are judge-after-audit (the banned leaderboard term is avoided).

| rung | method | metric | direction-errors |
|---|---|---|---|
| 0 | TF-IDF cosine (AB1) | AUROC {v('ab1.auroc_tfidf')} | {v('ab.direction_errors_tfidf')} |
| 0 | Jaccard content tokens (AB1) | AUROC {v('ab1.auroc_jaccard')} | {v('ab.direction_errors_jaccard')} |
| 1 | mpnet statements (AB2a) | AUROC {v('ab2.auroc_mpnet')} | {v('ab.direction_errors_mpnet')} |
| 1d | mpnet typed-card (AB2d) | AUROC {v('ab2.auroc_typed')} | — |
| 5a | Procrustes abstraction ladder (AB3) | top1 L0/L1/L2 = {v('ab3.top1_L0')}/{v('ab3.top1_L1')}/{v('ab3.top1_L2')} (null {v('ab3.null_top1')}) | — |
| 5b | GWOT unsupervised (AB4) | typed {v('ab4.top1_typed')}; embedding {v('ab4.top1_embedding')} | — |
| 5c | soft CQD queries vs symbolic (AB5, PRELIM) | p@1 {ab5('p_at_1')} (min)/{ab5('p_at_1','product')} (prod); empty-query FPR {ab5('empty_query_fpr')} | shortcut: q12 |
| 5d | structured-abstraction (AB6) | abstract-then-judge {v('ab6.acc_abstracted')} vs direct {v('ab6.acc_direct')} | — |
| 6 | ported judge (AB2, comparison) | AUROC {v('ab2.auroc_judge')} (circular — reference IS judge) | — |

## Reading (the discovery-instrument story)
- **The ladder lifts with abstraction:** TF-IDF/mpnet on raw statements sit at ~0.62 AUROC;
  the **typed-card rendering jumps to {v('ab2.auroc_typed')}** — the typed abstraction, not the
  surface text, carries the alignment signal (Goldstein's abstraction-induces-alignment).
- **Direction-errors rise with embeddings** ({v('ab.direction_errors_mpnet')} vs TF-IDF's
  {v('ab.direction_errors_tfidf')}): similarity methods score axis-matched-but-opposed/disjoint
  pairs highly — they chase surface similarity where the typed judge dissociates (the Hale hook).
- **The geometric rungs are honest pilot negatives at this N:** anchored Procrustes (AB3) does
  not beat chance on 22 mostly-weak-positive anchors; unsupervised GWOT (AB4) yields no
  non-degenerate coupling at 24×19 — both are feasibility pilots (Monash scale-up), reported as-is.

- **Compositional soft vs symbolic (AB5, 5c — PRELIMINARY, query packet AWAITING-ANU):** on the
  drafted query set the soft CQD method matches the exact Datalog answer at p@1 {ab5('p_at_1')}, but
  its **empty-query FPR is {ab5('empty_query_fpr')}** — it confidently answers queries that have NO
  symbolic answer (poorly calibrated to absence), and the one p@1 miss (q12) is a lexical shortcut
  (computable ∧ free-energy → only Active Inference symbolically; the soft arm picks IIT by surface
  similarity). Numbers finalise at bench/ab5_finalize.py after the query packet returns.
- **Structured abstraction helps (AB6, 5d):** abstract-then-judge {v('ab6.acc_abstracted')} beats
  direct quote→judgment {v('ab6.acc_direct')} — explicit typed abstraction before the judgment lifts
  accuracy (Freitas QuaSAR), driven by positive recall; both arms over-reject (strong on negatives).

G5's bias-battery table draws on these direction-error + AB5 shortcut cells.
"""
(SPRINT/"docs"/"briefs"/"alignment-bench.md").write_text(brief)
print("AB7 -> docs/briefs/alignment-bench.md")
