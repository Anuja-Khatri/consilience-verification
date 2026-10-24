#!/usr/bin/env python3
"""
pipeline/lint_claims.py — banned-phrase linter v2 (SPEC §0.6).

Scans docs/, results/*.md, probe_set/, bench/, paper/, review/ for case-insensitive
banned patterns; CI fails on any match. Legitimate mentions are exempted via
pipeline/lint_allowlist.txt (one allowed substring per line; a finding on a line
containing an allowlisted substring is suppressed) or an inline `lint-allow` pragma.

SPEC.md (repo root) is the source of truth and is NOT scanned.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
ALLOWLIST = SPRINT / "pipeline" / "lint_allowlist.txt"

SCAN_DIRS = ["docs", "probe_set", "bench", "paper", "review"]
SCAN_GLOBS = ["results/*.md"]
TEXT_EXT = {".md", ".txt", ".csv", ".html", ".tex", ".json"}
# Internal WHY-logs legitimately QUOTE banned phrases to explain the bans (like SPEC.md,
# which is unscanned). The §0.6 linter guards application-facing OUTPUT, not process logs.
# Internal process/continuity logs are exempt (they quote banned terms to document decisions,
# like SPEC.md which is unscanned). Application-facing outputs stay scanned: docs/briefs/,
# docs/tables/, instrument_v2.md, corrections.md, falsifiability-audit.md, probe_set/, bench/,
# paper/, review/. (D-022, extended D-027.)
EXCLUDE_FILES = {"docs/BUILD_LOG.md", "docs/DECISIONS.md", "docs/STATUS.md",
                 "docs/EVAL_LOG.md", "docs/ENV.md", "docs/judge_port.md",
                 "docs/SPRINT_REPORT.md"}


def _wd(n):  # up to n words of gap
    return r"(?:\W+\w+){0,%d}\W+" % n


# (name, compiled regex, scope_predicate(relpath) or None for all-scanned)
def _monash(rel):
    r = rel.lower()
    return any(k in r for k in ("monash", "anesthesia", "gwot", "td3", "mo2", "mo3", "tsuchiya", "kuhlmann"))


def _probeset(rel):
    return rel.startswith("probe_set/")


PATTERNS = [
    # carried from v1.0
    ("VF2", re.compile(r"\bVF2\b"), None),
    ("graph isomorphism", re.compile(r"\bgraph\s+isomorphism\b", re.I), None),
    ("subgraph isomorphism", re.compile(r"\bsubgraph\s+isomorphism\b", re.I), None),
    ("independent~Haiku", re.compile(r"\bindependent\b" + _wd(6) + r"Haiku\b|Haiku\b" + _wd(6) + r"\bindependent\b", re.I), None),
    ("9 to 2 / 9->2 / nine to two", re.compile(r"\b9\s*(?:to|→|->)\s*2\b|\bnine\s+to\s+two\b", re.I), None),
    ("prevents memori", re.compile(r"prevents\s+memori", re.I), None),
    ("15 judged pairs", re.compile(r"\b15\s+judged\s+pairs\b", re.I), None),
    ("ConTraSt experiments", re.compile(r"\bConTraSt\s+experiments\b", re.I), None),
    ("INTREPID result/showed/confirms", re.compile(r"\bINTREPID\s+(result|showed|confirms)\b", re.I), None),
    ("coverage~prediction maps + %", re.compile(r"coverage" + _wd(6) + r"prediction\s+maps.*%|prediction\s+maps" + _wd(6) + r"coverage.*%", re.I), None),
    ("human ceiling", re.compile(r"\bhuman\s+ceiling\b", re.I), None),
    ("benchmark (in probe_set/)", re.compile(r"\bbenchmark\b", re.I), _probeset),
    # new — domain guardrails
    ("Phi = / computed Phi / compute integrated information",
     re.compile(r"\bPhi\s*=|\bΦ\s*=|computed\s+Phi|compute\s+integrated\s+information", re.I), None),
    ("measure qualia / qualia measurement",
     re.compile(r"\bmeasure\s+qualia\b|\bqualia\s+measurement\b", re.I), None),
    ("causal emergence ~ we/engine/computed",
     re.compile(r"causal\s+emergence" + _wd(6) + r"(we|engine|computed)|(we|engine|computed)" + _wd(6) + r"causal\s+emergence", re.I), None),
    ("quantum ~ consciousness (Monash doc)",
     re.compile(r"\bquantum\b" + _wd(6) + r"consciousness|consciousness" + _wd(6) + r"\bquantum\b", re.I), _monash),
    ("functor (not candidate/toward/counts)",
     re.compile(r"\bfunctor\b", re.I), None),  # exemption handled in code via FUNCTOR_OK
    ("proves ~ emergence", re.compile(r"\bproves\b" + _wd(4) + r"emergence", re.I), None),
    ("solves autoformalisation", re.compile(r"\bsolves\s+autoformali[sz]ation\b", re.I), None),
    # status honesty
    ("gold standard", re.compile(r"\bgold\s+standard\b", re.I), None),
]

# functor exemption: the simple negative-lookahead above is brittle; handle in code.
FUNCTOR_OK = re.compile(r"\bfunctor\b(?:\W+\w+){0,3}\W+(candidate|toward|counts)"
                        r"|(candidate|toward|counts)(?:\W+\w+){0,3}\W+functor\b", re.I)


def load_allowlist():
    if not ALLOWLIST.exists():
        return []
    return [ln.strip() for ln in ALLOWLIST.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def iter_files():
    seen = set()
    for d in SCAN_DIRS:
        root = SPRINT / d
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in TEXT_EXT:
                    seen.add(p)
    for g in SCAN_GLOBS:
        for p in SPRINT.glob(g):
            if p.is_file():
                seen.add(p)
    return sorted(seen)


def main() -> int:
    allow = load_allowlist()
    findings = []
    for p in iter_files():
        rel = p.relative_to(SPRINT).as_posix()
        if rel in EXCLUDE_FILES:
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if "lint-allow" in line:
                continue
            if any(a in line for a in allow):
                continue
            for name, rx, scope in PATTERNS:
                if scope is not None and not scope(rel):
                    continue
                if name.startswith("functor"):
                    if re.search(r"\bfunctor\b", line, re.I) and not FUNCTOR_OK.search(line):
                        findings.append((rel, i, name, line.strip()[:100]))
                    continue
                if rx.search(line):
                    findings.append((rel, i, name, line.strip()[:100]))
    if findings:
        print("BANNED-PHRASE LINT FAILURES (§0.6):")
        for rel, i, name, snippet in findings:
            print(f"  {rel}:{i}  [{name}]  {snippet}")
        return 1
    print(f"lint_claims: clean ({len(iter_files())} files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
