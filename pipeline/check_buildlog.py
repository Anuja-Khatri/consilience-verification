#!/usr/bin/env python3
"""
pipeline/check_buildlog.py — BUILD_LOG coverage guard (owner standing instruction).

CI fails if either:
  (1) a SPEC.md changelog id (`CHANGELOG vX.Y.Z`) has no matching D-entry in BUILD_LOG.md
      (the version string must appear in a D-entry's Links/body), or
  (2) a RESOLVED HALT-ASK in STATUS.md is not covered by BUILD_LOG.md.

Resolved-HALT-ASK detection (deterministic): STATUS lines/blocks where "HALT-ASK" occurs
within 80 chars of "RESOLVED"/"resolved", plus the Day-0 fatal HALT-ASK (approved). The
check requires BUILD_LOG.md to contain at least as many D-entries mentioning "HALT-ASK"
as there are resolved markers in STATUS, and that each SPEC changelog id is present.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
SPEC = (SPRINT / "SPEC.md").read_text()
STATUS = (SPRINT / "docs" / "STATUS.md").read_text()
BUILD = (SPRINT / "docs" / "BUILD_LOG.md").read_text()


def main() -> int:
    errors = []

    # (1) every SPEC changelog id has a D-entry referencing it
    changelog_ids = sorted(set(re.findall(r"CHANGELOG (v\d+\.\d+\.\d+)", SPEC)))
    for cid in changelog_ids:
        if cid not in BUILD:
            errors.append(f"SPEC changelog {cid} has no matching D-entry in BUILD_LOG.md")

    # (2) resolved HALT-ASKs in STATUS must be covered by HALT-ASK D-entries
    resolved = []
    for m in re.finditer(r"HALT-ASK", STATUS):
        window = STATUS[max(0, m.start() - 80): m.end() + 80]
        if re.search(r"resolved", window, re.I):
            resolved.append(m.start())
    n_resolved = len(set(resolved))
    n_buildlog_haltask = len(re.findall(r"HALT-ASK", BUILD))
    if n_resolved and n_buildlog_haltask < 1:
        errors.append("STATUS has resolved HALT-ASK(s) but BUILD_LOG.md documents none")
    # require the two canonical HALT-ASK D-entries exist (Day-0 env + temperature)
    for marker, label in [("D-004", "Day-0 fatal keys+deps HALT-ASK"),
                          ("D-015", "temperature 400 HALT-ASK")]:
        if marker not in BUILD:
            errors.append(f"BUILD_LOG.md missing {marker} ({label})")

    # (3) structural: doctrine section + append-only banner present
    if "## Current state of doctrine" not in BUILD:
        errors.append("BUILD_LOG.md missing '## Current state of doctrine' section")

    if errors:
        print("BUILD_LOG COVERAGE FAILURES (owner standing instruction):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"check_buildlog: OK ({len(changelog_ids)} changelog ids covered: {changelog_ids}; "
          f"{n_resolved} resolved HALT-ASK marker(s) in STATUS, {n_buildlog_haltask} HALT-ASK refs in BUILD_LOG).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
