#!/usr/bin/env python3
"""
pipeline/check_readonly.py — read-only-tree guard (SPEC §0.1).

CI fails if any sprint .py contains a WRITE-MODE open (or obvious write call)
TARGETING the read-only trees (~/consilience-demo, ~/miu-demo, the prior eval
workspace). Reuse of those trees is by copy only; never by in-place write.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent

# read-only path markers (match literal strings appearing in code)
RO_MARKERS = ["consilience-demo", "miu-demo", "eval_out", "/eval/"]
# write-mode open or write call on the same line as a read-only marker
WRITE_RX = re.compile(
    r"""open\([^)]*['"](?:w|a|x|wb|ab|xb|w\+|a\+|r\+)['"]"""
    r"""|\.write_text\(|\.write_bytes\(|\.write\(|shutil\.(copy|move)\([^)]*,|os\.remove\(|os\.rename\(""",
    re.I,
)


def main() -> int:
    violations = []
    for p in SPRINT.rglob("*.py"):
        rel = p.relative_to(SPRINT).as_posix()
        if rel.startswith(".venv/") or "/engine_copy/" in ("/" + rel):
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if "check_readonly" in line:   # this guard's own doc lines
                continue
            if any(m in line for m in RO_MARKERS) and WRITE_RX.search(line):
                violations.append((rel, i, line.strip()[:100]))
    if violations:
        print("READ-ONLY-TREE WRITE VIOLATIONS (§0.1/§0.10(5)):")
        for rel, i, snip in violations:
            print(f"  {rel}:{i}  {snip}")
        return 1
    print("check_readonly: clean (no write-mode open targets a read-only tree).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
