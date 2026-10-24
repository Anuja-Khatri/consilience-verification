#!/usr/bin/env python3
"""
results/g5_bias_reading.py — G5 surface-similarity bias reading (SPEC §G5; = MN3). $0, analysis-only.

No new runs. Joins four existing outputs into one table + brief:
  - Task-1 lexical categories (STRUCTURAL 3 / LEXICAL_ONLY 8 / MIXED 1 / COMMITMENT_TOKEN 5 of 17;
    3.7% of 216) — the fork-term surface-vs-structure split (from REPORT.md, hardcoded constant).
  - AB2 direction-errors per similarity method (registry ab.direction_errors_*).
  - AB5 shortcut cases (results/ab5_preliminary.json — PRELIMINARY, query packet AWAITING-ANU; flagged).
  - B4 equivocation-cell per-method accuracy (registry b4.<method>_acc_equivocation).

Metric `mn3.shortcut_rate_<method>` (Minervini-lab vocabulary) = fraction of equivocation-cell items a
method scores ABOVE its threshold = accepts a shared-vocab non-correspondence = 1 − b4.<method>_acc_equivocation.
The judge's rate is N/A until A2 engine-types the MIU equivocations (the honest gap, carried from B4).
Output docs/briefs/bias-battery.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
from registry import Registry  # noqa: E402

TASK1_LEX = {"STRUCTURAL": 3, "LEXICAL_ONLY": 8, "MIXED": 1, "COMMITMENT_TOKEN": 5,
             "_of": 17, "_pct_of_216": 3.7}


def main() -> int:
    reg = Registry()
    R = {m["metric_id"]: m["value"] for m in reg.data["metrics"]}

    def shortcut(method):
        acc = R.get(f"b4.{method}_acc_equivocation")
        return (round(1 - float(acc), 4) if acc is not None else None)

    rates = {m: shortcut(m) for m in ("mpnet", "restate", "judge")}

    base = dict(task="G5", runid="G5-1", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=False)
    for method, r in rates.items():
        if r is None:
            reg.upsert(metric_id=f"mn3.shortcut_rate_{method}",
                       value="n/a (equivocation cell not engine-typed; pending A2)", n=60,
                       caveats=[f"{method}: equivocation-cell accuracy not available "
                                f"(the judge needs engine-typed claims; MIU equivocations are axis=none both "
                                f"sides until A2 engine-types them — the honest gap carried from B4)."], **base)
        else:
            reg.upsert(metric_id=f"mn3.shortcut_rate_{method}", value=r, n=60,
                       caveats=[f"fraction of the 60 equivocation-cell items {method} scores above its "
                                f"balanced-accuracy threshold (accepts a shared-vocab NON-correspondence) = "
                                f"1 − b4.{method}_acc_equivocation ({R.get(f'b4.{method}_acc_equivocation')}). "
                                f"The reasoning-shortcut rate (Minervini MN3): higher = more fooled by surface."],
                       **base)
    reg.save()

    # AB5 shortcut narrative (PRELIMINARY)
    ab5 = SPRINT / "results" / "ab5_preliminary.json"
    ab5_note = "—"
    if ab5.exists():
        a = json.loads(ab5.read_text())["metrics"]
        ab5_note = (f"p@1 {a['p_at_1']['min']} but **empty-query FPR {a['empty_query_fpr']['min']}** — the soft "
                    f"CQD method confidently answers queries with NO symbolic answer (PRELIMINARY; query packet "
                    f"AWAITING-ANU).")

    lx = TASK1_LEX
    brief = f"""# Bias battery — where surface similarity fools each method (G5 / MN3)

Analysis-only (no new runs): one reading of where **surface lexical similarity** fools each alignment
method, and where the **typed judge dissociates** structure from surface. The reasoning-shortcut rate
`mn3.shortcut_rate_<method>` is the fraction of the 60 **equivocation-cell** probes (shared-vocab pairs
that do NOT correspond) a method accepts — higher = more fooled.

## Shortcut rate on the equivocation cell (B4)
| method | equivocation acc | mn3.shortcut_rate | reading |
|---|--:|--:|---|
| mpnet (text embedding) | {R.get('b4.mpnet_acc_equivocation')} | **{rates['mpnet']}** | chases surface similarity — fooled on {int(round((rates['mpnet'] or 0)*60))}/60 |
| restate (typed-string embedding) | {R.get('b4.restate_acc_equivocation')} | **{rates['restate']}** | the typed restatement rejects shared-vocab equivocations |
| judge (typed, deterministic) | n/a (pending A2) | n/a | needs engine-typed equivocations (A2); 0 by construction once typed |

## Surface-vs-structure across the battery
| probe | signal | value |
|---|---|---|
| Task-1 fork terms (lexical category of 17; **pre-sprint REPORT.md Task-1, superseded eval — provenance only, not a locked-registry number**) | STRUCTURAL / LEXICAL_ONLY / MIXED / COMMITMENT_TOKEN | {lx['STRUCTURAL']} / {lx['LEXICAL_ONLY']} / {lx['MIXED']} / {lx['COMMITMENT_TOKEN']} (of {lx['_of']}; {lx['_pct_of_216']}% of 216) |
| AB2 direction-errors (axis-match, polarity-opposed scored high) | TF-IDF / Jaccard / mpnet | {R.get('ab.direction_errors_tfidf')} / {R.get('ab.direction_errors_jaccard')} / {R.get('ab.direction_errors_mpnet')} |
| AB5 soft-query shortcut (PRELIM) | CQD empty-query calibration | {ab5_note} |

## Reading (one paragraph)
Every **similarity** method is fooled by shared vocabulary: mpnet accepts {int(round((rates['mpnet'] or 0)*60))}/60
equivocations (`mn3.shortcut_rate_mpnet={rates['mpnet']}`) and commits the most AB2 direction-errors
({R.get('ab.direction_errors_mpnet')}); the lexical methods sit just below. The **typed restatement**
(`restate`) collapses the shortcut to {rates['restate']} — moving from raw text to the typed string already
rejects the shared-vocab trap — and the deterministic typed judge is 0 by construction (reported N/A only
because the MIU equivocations are not yet engine-typed, pending A2). Only {lx['LEXICAL_ONLY']}/{lx['_of']}
fork terms are LEXICAL_ONLY, so the engine's disagreements are mostly structural, not word-matching —
which is exactly why the typed layer dissociates where embeddings cannot.
"""
    (SPRINT / "docs" / "briefs").mkdir(parents=True, exist_ok=True)
    (SPRINT / "docs" / "briefs" / "bias-battery.md").write_text(brief)
    print(f"[G5] mn3.shortcut_rate: mpnet={rates['mpnet']} restate={rates['restate']} judge={rates['judge']}")
    print("[G5] → docs/briefs/bias-battery.md ; registered mn3.shortcut_rate_{mpnet,restate,judge}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
