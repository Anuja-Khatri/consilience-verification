#!/usr/bin/env python3
"""
pipeline/make_tables.py — render results/registry.json → docs/tables/*.md (SPEC §0.8).

One table per task (metrics grouped by `task`) + an index. These renders are the ONLY
path a number may take into a paper/essay/brief/email. Deterministic; no wall clock in
the body (artifact_stamp from config).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
REGISTRY = SPRINT / "results" / "registry.json"
TABLES = SPRINT / "docs" / "tables"


def fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def ci(m):
    if m.get("ci_lo") is None or m.get("ci_hi") is None:
        return ""
    return f"[{fmt(m['ci_lo'])}, {fmt(m['ci_hi'])}]"


def main() -> int:
    reg = json.loads(REGISTRY.read_text())
    metrics = reg.get("metrics", [])
    TABLES.mkdir(parents=True, exist_ok=True)

    by_task = {}
    for m in metrics:
        by_task.setdefault(m["task"], []).append(m)

    # per-task tables
    for task, ms in sorted(by_task.items()):
        lines = [f"# {task} — registry metrics", "",
                 "| metric_id | value | 95% CI | n | instrument | corpus | prereg | pilot | caveats |",
                 "|---|---|---|---|---|---|---|---|---|"]
        for m in sorted(ms, key=lambda x: x["metric_id"]):
            lines.append(
                f"| `{m['metric_id']}` | {fmt(m['value'])} | {ci(m)} | "
                f"{m.get('n') if m.get('n') is not None else ''} | {m['instrument_tag']} | "
                f"{m['corpus_tag']} | {'Y' if m['preregistered'] else 'N'} | "
                f"{'Y' if m['pilot'] else 'N'} | {'; '.join(m.get('caveats', []))} |")
        (TABLES / f"{task}.md").write_text("\n".join(lines) + "\n")

    # index
    idx = ["# docs/tables — registry render index", "",
           f"Rendered from `results/registry.json` (schema {reg.get('schema_version')}).",
           f"Total metrics: **{len(metrics)}**.", ""]
    if by_task:
        idx.append("| task | metrics | file |")
        idx.append("|---|---|---|")
        for task, ms in sorted(by_task.items()):
            idx.append(f"| {task} | {len(ms)} | [{task}.md]({task}.md) |")
    else:
        idx.append("_No metrics in the registry yet (scaffold stage W0.6)._")
    lock = reg.get("numbers_lock")
    idx += ["", f"NUMBERS_LOCK: {'set' if lock else 'not set'}."]
    (TABLES / "index.md").write_text("\n".join(idx) + "\n")

    print(f"make_tables: rendered {len(by_task)} task table(s) + index "
          f"({len(metrics)} metrics) → {TABLES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
