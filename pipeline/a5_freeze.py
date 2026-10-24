#!/usr/bin/env python3
"""
pipeline/a5_freeze.py — A5.3 FREEZE (SPEC §A5.3). $0; no model calls.

Owner decision (A5.3 packet): adopt-baseline. Instrument v2 = production decoding
(provider-default; no temperature per v2.0.3) + A5.2 definitions prompt. This script
builds the v2 system prompt (production p2 system + verbatim definitions block from the
vocab yamls, exactly as Task-3b condition B), logs the freeze hash, finalizes
docs/instrument_v2.md, and records the adopted decoding in the registry.

After this, instrument_tag `v2` is the frozen instrument; extraction tasks tag v2.
"""
from __future__ import annotations

import hashlib
import json
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

import a5_stability as A5M  # noqa: E402  (extract_system — production prompt reconstruction)
import t4_annotation as t4  # noqa: E402  (entity_defs/axis_defs — vocab definitions)
from registry import Registry  # noqa: E402


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def definitions_block() -> str:
    """Verbatim Task-3b condition-B definitions block (deterministic, sorted)."""
    ed, ad = t4.entity_defs(), t4.axis_defs()
    lines = ["", "Definitions of the controlled vocabulary (use them; do not stretch a claim to fit):",
             "entity_type:"]
    for k in sorted(ed):
        lines.append(f"- {k}: {ed[k]}")
    lines.append("axis:")
    for k in sorted(ad):
        lines.append(f"- {k}: {ad[k]}")
    lines.append("- none: the claim commits to no axis in the controlled list.")
    return "\n".join(lines)


def main() -> int:
    v1_system = A5M.extract_system()           # production p2 system prompt (parity-asserted)
    defs = definitions_block()
    v2_system = v1_system + "\n" + defs         # A5.2: p2 prompt + definitions block
    v1_sha, defs_sha, v2_sha = _sha(v1_system), _sha(defs), _sha(v2_system)
    fp = json.loads((SPRINT / "results" / "engine_fingerprint.json").read_text())["combined_sha256"]

    freeze = {
        "instrument_tag": "v2",
        "adopted_decoding": "baseline (single-pass, provider-default; no temperature per v2.0.3)",
        "adoption_decision": "adopt-baseline",
        "adoption_packet": "review/a5_adoption_2026-10.md",
        "adoption_rule": "preregistered gate stability≥0.70 AND windowed coverage≥0.85; candidate "
                         "confweighted failed (0.346/0.258); t0 not-applicable → baseline.",
        "prompt": {"v1_system_sha256": v1_sha, "definitions_block_sha256": defs_sha,
                   "v2_system_sha256": v2_sha, "definitions_source": "vocab/entity_types.yaml + axes.yaml "
                   "(Task-3b condition B; ablation NOT rerun — +0.105 entity-κ directional, CIs cross 0)"},
        "models": {"extractor": CFG["models"]["extractor"], "checker": CFG["models"]["checker"],
                   "extract_max_tokens": 1500, "haiku_max_tokens": 200},
        "engine_fingerprint": fp,
        "date": CFG["dates"]["artifact_stamp"],
        "determinism": "rests on the pipeline/llm.py cache (sha256 full request + replicate_tag), "
                       "not on decoding (Anthropic exposes no temperature knob).",
    }
    (SPRINT / "results" / "instrument_v2_freeze.json").write_text(
        json.dumps(freeze, indent=2, ensure_ascii=False) + "\n")
    (SPRINT / "results" / "instrument_v2_prompt.txt").write_text(v2_system + "\n")

    # register the adopted decoding (string metric, frozen-store — pure decision, no extraction input)
    reg = Registry()
    reg.upsert(metric_id="a5.adopted_decoding", value="baseline-single-pass",
               task="A5", runid="A5.3", instrument_tag="frozen-store", corpus_tag="v1",
               preregistered=True, pilot=False,
               caveats=["A5.3 FREEZE (adopt-baseline); candidate confweighted failed the "
                        "preregistered gate (0.346/0.258 vs ≥0.70/≥0.85); t0 not-applicable.",
                        f"v2_system_sha256 {v2_sha[:16]}…; determinism via llm.py cache, not decoding."])
    reg.save()

    print(f"[A5.3 FREEZE] instrument v2 frozen. adopt-baseline.")
    print(f"  v1_system_sha {v1_sha[:16]}…  defs_sha {defs_sha[:16]}…  v2_system_sha {v2_sha[:16]}…")
    print(f"  → results/instrument_v2_freeze.json + instrument_v2_prompt.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
