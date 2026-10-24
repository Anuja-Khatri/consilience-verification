#!/usr/bin/env python3
"""
pipeline/extract_lite.py — A2.2 extract_lite (SPEC §A2.2). Real spend (A2 budget $40).

Replicates production p2 EXACTLY — verbatim v2 SYSTEM prompt (production p2 system +
A5.2 definitions block; = frozen v2_system 2fc0035d), same FEWSHOT and same vocab
injection (both carried by p2's extract_system()), CLAIMS_PER_WINDOW=4, WINDOW=8,
max_tokens=1500 — but takes an EXPLICIT passage list (not candidates(load_passages)).

Validation identical to p2 (SPEC §A2.2):
  - citation required: a claim's passage_ids must intersect the window's provided ids;
  - entity_type closed, axis coerced-to-none if outside the list, polarity ∈ {asserts,denies}
    — all enforced by P2.to_claim via the engine Claim model (invalid → dropped).

All calls go through pipeline/llm.py. Reused by A2 (pipeline/a2_adjudicate.py); the module
is theory-agnostic so it can serve any explicit-passage extraction need.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
sys.path.insert(0, str(ENGINE / "pipeline"))
sys.path.insert(0, str(ENGINE / "eval"))

import p2_extract as P2  # noqa: E402  (extract_system/FEWSHOT/vocab/WINDOW/to_claim/dedup/_json_block)
import a5_stability as A5M  # noqa: E402  (extract_system — production main prompt w/ FEWSHOT + vocab)
import a5_freeze as FRZ  # noqa: E402  (definitions_block — the A5.2 definitions)

SONNET = P2.SONNET
WINDOW = P2.WINDOW
MAX_TOKENS = int(CFG.get("models", {}).get("extract_max_tokens", 1500))
DEFS = FRZ.definitions_block()
MAIN_V2 = A5M.extract_system() + "\n" + DEFS  # = frozen v2_system (2fc0035d)


def _windows(passages):
    return [passages[i:i + WINDOW] for i in range(0, len(passages), WINDOW)]


def extract_lite(passages, theory, slug, client, *, replicate_tag="a2", task_id="A2",
                 system=None, max_tokens=None):
    """Run the v2 instrument over an explicit passage list; return validated claim dicts.

    passages : [{"passage_id","text"}, ...]
    theory   : the field/domain label passed to the prompt (production p2 passes the theory).
    slug     : claim_id namespace (P2.to_claim builds f"{slug}_c{idx:03d}").
    """
    system = system or MAIN_V2
    max_tokens = max_tokens or MAX_TOKENS
    raw = []
    for win in _windows(passages):
        user = "Theory: %s\nPassages:\n%s" % (
            theory, "\n".join(f'[{p["passage_id"]}] {p["text"]}' for p in win))
        rec = client.call(task_id=task_id, model=SONNET, system=system,
                          messages=[{"role": "user", "content": user}],
                          replicate_tag=replicate_tag, temperature=None, max_tokens=max_tokens)
        ids = {p["passage_id"] for p in win}
        for c in P2._json_block(rec.get("text") or ""):
            pids = [i for i in c.get("passage_ids", []) if i in ids]  # citation required from provided ids
            if not pids:
                continue
            c["passage_ids"] = pids
            raw.append(c)
    deduped = P2.dedup(raw)
    claims = [c for c in (P2.to_claim(theory, slug, i + 1, c) for i, c in enumerate(deduped)) if c]
    return [c.model_dump() for c in claims]
