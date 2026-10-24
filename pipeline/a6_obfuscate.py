#!/usr/bin/env python3
"""
pipeline/a6_obfuscate.py — A6 obfuscation application (SPEC §A6; TD4 reuses this).

Applies corpora/obfuscation_map.yaml to passage text with the owner-required guarantees (D-038):
  (b) WORD-BOUNDARY, CASE-INSENSITIVE matching (no "Lau"→"Laureys" substring hits);
  (c) DASH normalization (hyphen / en dash / em dash all matched);
  + longest-match-first (so "global neuronal workspace" is replaced before "workspace"),
  + casing-pattern preservation (UPPER→UPPER, Title→Title, lower→lower),
  + reversible de-map, + assert_clean (ZERO remaining occurrences of every source term/alias).

apply(text) -> obfuscated;  reverse(text) -> de-mapped;  assert_clean(text) raises on any leak;
selftest() validates the guarantees. Dashes are normalized to hyphen in BOTH arms (obfuscated and
clean), so the ONLY difference between arms is the obfuscation itself (v2.0.4 D2 noise-floor control).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
MAP_PATH = SPRINT / "corpora" / "obfuscation_map.yaml"
_DASH = {ord("–"): "-", ord("—"): "-", ord("‒"): "-", ord("−"): "-"}


def norm_dash(s: str) -> str:
    return s.translate(_DASH)


def _load_pairs():
    m = yaml.safe_load(MAP_PATH.read_text())
    pairs = {}
    for sec in ("theory_names", "coined_terms", "people"):
        for src, rec in (m.get(sec) or {}).items():
            tgt = rec["target"] if isinstance(rec, dict) else rec
            pairs[norm_dash(str(src).lower())] = tgt
    return pairs


_PAIRS = _load_pairs()
# longest source first (by char length) so multiword/longer terms win over their substrings
_SOURCES = sorted(_PAIRS, key=len, reverse=True)
_RX = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(s) for s in _SOURCES) + r")(?![A-Za-z0-9])",
                 re.IGNORECASE) if _SOURCES else None
# reverse: target(lower) -> source (first/canonical wins on collision, e.g. cne<-gnwt not gnw)
_REV = {}
for _s in _SOURCES[::-1]:
    _REV.setdefault(_PAIRS[_s].lower(), _s)
_REV_SRC = sorted(_REV, key=len, reverse=True)
_RX_REV = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(s) for s in _REV_SRC) + r")(?![A-Za-z0-9])",
                     re.IGNORECASE) if _REV_SRC else None


def _recase(matched: str, target: str) -> str:
    if matched.isupper():
        return target.upper()
    if matched.istitle():
        return target.title()
    if matched[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


def apply(text: str) -> str:
    """Obfuscate. Dashes normalized first (both arms get this), then word-boundary substitutions."""
    t = norm_dash(text)
    if not _RX:
        return t
    return _RX.sub(lambda mo: _recase(mo.group(1), _PAIRS[norm_dash(mo.group(1).lower())]), t)


def reverse(text: str) -> str:
    """De-map obfuscated text back toward the originals (collisions resolve to the canonical source)."""
    if not _RX_REV:
        return text
    return _RX_REV.sub(lambda mo: _recase(mo.group(1), _REV[norm_dash(mo.group(1).lower())]), text)


def remaining_sources(text: str):
    """Source terms/aliases that STILL occur after obfuscation (should be empty)."""
    t = norm_dash(text.lower())
    hits = []
    for s in _SOURCES:
        if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", t):
            hits.append(s)
    return hits


def assert_clean(text: str):
    """Owner-required post-substitution assert: ZERO remaining occurrences of every source/alias."""
    left = remaining_sources(apply(text))
    assert not left, f"A6 LEAK: source terms survived obfuscation: {left}"


def selftest():
    # (b) word-boundary: 'Lau' (person) obfuscated, 'Laureys' (substring) untouched
    assert apply("Lau and Laureys") == "Author L8 and Laureys", apply("Lau and Laureys")
    # (c) dash variants of a multiword source all match
    assert apply("cause-effect power") == apply("cause–effect power") == apply("cause—effect power")
    assert "drive-response power" in apply("the cause–effect power"), apply("the cause–effect power")
    # casing preservation
    assert apply("IIT") == "TK" and apply("iit") == "tk"
    assert apply("Global Workspace") == "Central Exchange", apply("Global Workspace")
    # longest-match-first + GNW alias family
    assert "central neuronal exchange" in apply("the global neuronal workspace").lower()
    assert apply("GNW") == "CNE"
    # zero-remaining on a compound probe
    probe = ("IIT and the Global Neuronal Workspace (GNW) differ; Tononi vs Dehaene; phi and "
             "integrated information; the workspace and workspace theory; cause–effect power.")
    assert_clean(probe)
    # reversibility (identity-family: obfuscated token maps back to a source)
    assert "workspace" in reverse(apply("neuronal workspace")).lower()
    return "A6 obfuscate selftest: PASS"


if __name__ == "__main__":
    print(selftest())
    print(f"map: {len(_PAIRS)} source terms; longest='{_SOURCES[0]}'")
    sys.exit(0)
