#!/usr/bin/env python3
"""
pipeline/report_costs.py — A5.5 cost reporting (SPEC §A5.5). $0.

Renders docs/tables/costs.md from results/cost_meter.json: per-task spend (calls / tokens / USD),
a budget-group rollup against config budget_usd, and the total vs the $900 hard cap. The spec's
"per verdict for A2" line is emitted once A2.6 verdicts exist (results/a2_comparison.json); until the
A2 claims packet returns it prints a pending note rather than a fabricated per-verdict figure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
BUDGETS = {k: v for k, v in CFG.get("budget_usd", {}).items()
           if isinstance(v, (int, float)) and k not in ("hard_total", "slack")}

# task_id prefix → budget-group key (grouped budgets in config)
PREFIX = [("AB", "AB_bench"), ("KR", "KR_keys"), ("SS", "SS_spectro"), ("VJ", "VJ_logic"),
          ("TD1b", "TD1b_ml"), ("TD1", "TD1_aif"), ("TD2", "TD2_variants"), ("TD4", "TD4_game"),
          ("B3", "B3"), ("B4", "B4"), ("B5", "B5"), ("B2", "B2"),
          ("A2", "A2"), ("A5", "A5"), ("A6", "A6")]


def budget_key(task: str):
    if task in BUDGETS:
        return task
    for pre, key in PREFIX:
        if task.startswith(pre) and key in BUDGETS:
            return key
    return None


def main() -> int:
    meter = json.loads((SPRINT / "results" / "cost_meter.json").read_text())
    tasks = meter.get("tasks", {})
    hard = meter.get("hard_total_usd", 900.0)
    total = meter.get("total_usd", 0.0)

    rows = sorted(tasks.items(), key=lambda kv: -kv[1]["usd"])
    lines = ["# docs/tables/costs.md — spend report (SPEC §A5.5)", "",
             f"_Generated from results/cost_meter.json (artifact_stamp {CFG['dates']['artifact_stamp']}). "
             f"Determinism via the llm.py cache; $0 to regenerate._", "",
             f"**Total spent: ${total:.4f} / ${hard:.0f} hard cap "
             f"({100*total/hard:.2f}%).**", "",
             "## Per task (meter task_id)", "",
             "| task_id | calls | in_tok | out_tok | USD |", "|---|--:|--:|--:|--:|"]
    for t, v in rows:
        lines.append(f"| {t} | {v['calls']} | {v['in_tokens']} | {v['out_tokens']} | {v['usd']:.4f} |")

    # budget-group rollup
    group = {}
    for t, v in tasks.items():
        k = budget_key(t)
        if k is None:
            group.setdefault("(no budget line — data/frozen-store)", {"usd": 0.0, "calls": 0, "budget": None})
            group["(no budget line — data/frozen-store)"]["usd"] += v["usd"]
            group["(no budget line — data/frozen-store)"]["calls"] += v["calls"]
        else:
            group.setdefault(k, {"usd": 0.0, "calls": 0, "budget": BUDGETS[k]})
            group[k]["usd"] += v["usd"]
            group[k]["calls"] += v["calls"]
    lines += ["", "## Budget-group rollup (vs config budget_usd)", "",
              "| budget group | calls | USD | budget | % of budget |", "|---|--:|--:|--:|--:|"]
    for k in sorted(group, key=lambda x: -group[x]["usd"]):
        g = group[k]
        b = g["budget"]
        pct = f"{100*g['usd']/b:.1f}%" if b else "—"
        bs = f"${b:.0f}" if b else "—"
        lines.append(f"| {k} | {g['calls']} | {g['usd']:.4f} | {bs} | {pct} |")

    # A2 per-verdict (SPEC §A5.5)
    a2cmp = SPRINT / "results" / "a2_comparison.json"
    lines += ["", "## A2 per-verdict cost (SPEC §A5.5)", ""]
    if a2cmp.exists():
        cmp = json.loads(a2cmp.read_text())
        n_v = cmp.get("n_verdicts") or cmp.get("n_pairs") or len(cmp.get("rows", cmp.get("comparison", [])))
        a2_usd = tasks.get("A2", {}).get("usd", 0.0)
        per = a2_usd / n_v if n_v else 0.0
        lines.append(f"A2 total ${a2_usd:.4f} over {n_v} pair verdicts = **${per:.4f}/verdict** "
                     f"(agreement_rate {cmp.get('agreement_rate')}, downgrade_rate {cmp.get('downgrade_rate')}).")
    else:
        a2_usd = tasks.get("A2", {}).get("usd", 0.0)
        lines.append(f"A2 extraction spent ${a2_usd:.4f} (34 side-extractions → 109 claims). "
                     f"Per-verdict figure PENDING A2.6 comparison (awaits the review/a2_claims.csv packet).")

    # pricing provenance + gaps (owner: never record $0; cite rates; flag unpriced/preview)
    lines += ["", "## Pricing provenance + gaps", "",
              "Rates in `pipeline/llm.py PRICING` (USD per 1M tokens). gemini-3.1-pro-preview: input $2 / "
              "output $12 (≤200k tier), thinking tokens billed at the output rate — "
              "https://ai.google.dev/gemini-api/docs/pricing (fetched 2026-10-23)."]
    for b in meter.get("backfills", []):
        lines.append(f"- **Backfill {b['id']}: +${b['usd']:.4f}** — {b['basis']}. GAP: {b['gap']}.")
    lines.append("- **Open-weight panel leg (qwen2.5-72b / llama-3.3-70b): DEFERRED — no TOGETHER/FIREWORKS "
                 "key.** Priced in PRICING but never called; B3 panel is two-vendor (gpt-4.1 + gemini-3.1-pro). "
                 "Stated as a limitation in B3 and the paper.")

    (SPRINT / "docs" / "tables").mkdir(parents=True, exist_ok=True)
    (SPRINT / "docs" / "tables" / "costs.md").write_text("\n".join(lines) + "\n")
    print(f"[A5.5] costs.md written — total ${total:.4f}/{hard:.0f} ({100*total/hard:.2f}%); "
          f"{len(tasks)} task ids, {len(group)} budget groups.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
