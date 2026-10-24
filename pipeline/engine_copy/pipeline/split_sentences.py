#!/usr/bin/env python3
"""split_sentences — EXTRACTED VERBATIM from the engine's p1_ingest.py (W0.4).

Source: ~/consilience-demo/demo/pipeline/p1_ingest.py (lines 33-87). Only the
sentence-splitter + its constants are copied (A2.1 passage slicing needs it).
p1_ingest.py is NOT fingerprinted; this is a function extraction, not a byte copy.
"""
from __future__ import annotations

import re

TARGET_SENTENCES = 3
MIN_S, MAX_S = 2, 6
_ABBREV = {"e.g", "i.e", "cf", "et al", "vs", "Fig", "eq", "Eq", "approx",
           "ca", "p", "pp", "Dr", "no", "No"}


def split_sentences(text: str):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    # re-merge fragments that split on a known abbreviation
    out, buf = [], ""
    for p in parts:
        buf = (buf + " " + p).strip() if buf else p
        last = buf.rsplit(" ", 1)[-1].rstrip(".").strip()
        if last in _ABBREV:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return [s for s in out if s.strip()]


def window(sentences):
    """Group sentences into ~TARGET spans, clamped to [MIN_S, MAX_S]."""
    spans, i, n = [], 0, len(sentences)
    while i < n:
        take = min(TARGET_SENTENCES, n - i)
        # avoid a trailing 1-sentence orphan
        if n - (i + take) == 1 and take < MAX_S:
            take += 1
        chunk = sentences[i:i + take]
        if len(chunk) < MIN_S and spans:  # merge a too-small tail into previous
            spans[-1] = spans[-1] + " " + " ".join(chunk)
        else:
            spans.append(" ".join(chunk))
        i += take
    return spans
