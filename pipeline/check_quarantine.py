#!/usr/bin/env python3
"""
pipeline/check_quarantine.py — quarantine-reader guard (SPEC §0.4).

Quarantined cache records may be read ONLY by scripts under pipeline/quarantine/.
CI fails if any sprint .py OUTSIDE pipeline/quarantine/ references quarantined-record
reading (the llm.py quarantine read API or the `quarantined` cache flag). The one
allowed definition site is pipeline/llm.py (which implements the restriction).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
ALLOWED_PREFIXES = ("pipeline/quarantine/",
                    "tests/")  # tests exercise the enforcement; they process no real key text
ALLOWED_FILES = ("pipeline/llm.py",            # defines the restriction
                 "pipeline/check_quarantine.py")  # this guard
# signals that a script is READING quarantined material
READ_RX = re.compile(r"quarantine\s*=\s*True|['\"]quarantined['\"]|read_cache\([^)]*quarantin", re.I)


def main() -> int:
    violations = []
    for p in SPRINT.rglob("*.py"):
        rel = p.relative_to(SPRINT).as_posix()
        if rel.startswith(".venv/"):
            continue
        if rel in ALLOWED_FILES or any(rel.startswith(a) for a in ALLOWED_PREFIXES):
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if READ_RX.search(line):
                violations.append((rel, i, line.strip()[:100]))
    if violations:
        print("QUARANTINE-READER VIOLATIONS (§0.4): quarantined records are readable")
        print("only by pipeline/quarantine/ scripts.")
        for rel, i, snip in violations:
            print(f"  {rel}:{i}  {snip}")
        return 1
    print("check_quarantine: clean (no quarantined-record reader outside pipeline/quarantine/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
