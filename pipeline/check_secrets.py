#!/usr/bin/env python3
"""
pipeline/check_secrets.py — secret-string guard (owner W0.5 CI TODO).

Fails CI if a key-SHAPED secret appears anywhere in the git-tracked tree. Matches
the FULL secret shape (prefix + >=20-char tail), NOT a bare prefix, so prose that
merely names a pattern does not trip. An allowlist (pipeline/lint_allowlist.txt,
shared) exempts lines that name the pattern. Key values are NEVER echoed — only the
file:line and the matched pattern NAME are printed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
ALLOWLIST = SPRINT / "pipeline" / "lint_allowlist.txt"

PATTERNS = [
    ("openai/anthropic sk-", re.compile(r"sk-(?:ant-)?[A-Za-z0-9_\-]{20,}")),
    ("google AIza", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
]


def load_allow():
    if not ALLOWLIST.exists():
        return []
    return [ln.strip() for ln in ALLOWLIST.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=SPRINT,
                             capture_output=True, text=True, check=True).stdout
        return [SPRINT / f for f in out.splitlines() if f]
    except Exception:
        return list(SPRINT.rglob("*"))


def main() -> int:
    allow = load_allow()
    hits = []
    for p in tracked_files():
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if any(a in line for a in allow) or "check_secrets" in line:
                continue
            for name, rx in PATTERNS:
                if rx.search(line):
                    hits.append((p.relative_to(SPRINT).as_posix(), i, name))
    if hits:
        print("SECRET-SHAPED STRINGS in tracked tree (values NOT shown):")
        for rel, i, name in hits:
            print(f"  {rel}:{i}  [{name}]")
        return 1
    print("check_secrets: clean (no key-shaped secret in the tracked tree).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
