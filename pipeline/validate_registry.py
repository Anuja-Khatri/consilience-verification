#!/usr/bin/env python3
"""
pipeline/validate_registry.py — registry schema + numbers-lock validation (SPEC §0.8,
amended v2.0.2).

1. JSON-schema validate results/registry.json against results/registry.schema.json.
2. v2.0.2 rule: REJECT instrument_tag == "frozen-store" on any metric whose run
   manifest (runs/<task>/<runid>/manifest.json) lists an extraction output among its
   inputs. An input is an extraction output if its `kind` == "extraction" or its path
   matches an extraction artifact (extract_lite / p2 / *_approved / claims extraction).
3. metric_id uniqueness.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
REGISTRY = SPRINT / "results" / "registry.json"
SCHEMA = SPRINT / "results" / "registry.schema.json"

# Extraction OUTPUTS (fresh extraction), NOT the frozen approved-claims store. The approved
# store (*_approved.jsonl) and MIU data are FROZEN inputs read by many frozen-store tasks
# (VJ1, F2, SS1/SS2) — they must NOT count as extraction (D-026 bug-fix). Prefer the explicit
# kind=="extraction" marker; this path regex is a backup for fresh-extraction artifacts.
EXTRACTION_PATH_RX = re.compile(r"extract_lite|v2_claims|_draft\.jsonl|_normalized\.jsonl", re.I)


def extraction_in_inputs(manifest: dict) -> bool:
    """Pure predicate (v2.0.2): does this run manifest list an extraction output among
    its inputs? True if any input has kind=='extraction' or an extraction-artifact path."""
    for inp in manifest.get("inputs", []):
        if isinstance(inp, dict):
            if inp.get("kind") == "extraction":
                return True
            if EXTRACTION_PATH_RX.search(str(inp.get("path", ""))):
                return True
        elif isinstance(inp, str) and EXTRACTION_PATH_RX.search(inp):
            return True
    return False


def _manifest_has_extraction_input(task: str, runid: str) -> bool:
    man = SPRINT / "runs" / task / runid / "manifest.json"
    if not man.exists():
        return False
    try:
        data = json.loads(man.read_text())
    except Exception:
        return False
    return extraction_in_inputs(data)


def validate(path: Path = REGISTRY) -> int:
    import jsonschema
    reg = json.loads(Path(path).read_text())
    schema = json.loads(SCHEMA.read_text())
    errors = []
    try:
        jsonschema.validate(reg, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"schema: {e.message} at {list(e.absolute_path)}")

    seen = set()
    for m in reg.get("metrics", []):
        mid = m.get("metric_id", "<?>")
        if mid in seen:
            errors.append(f"duplicate metric_id: {mid}")
        seen.add(mid)
        # v2.0.2 frozen-store rule
        if m.get("instrument_tag") == "frozen-store":
            if _manifest_has_extraction_input(m.get("task", ""), m.get("runid", "")):
                errors.append(
                    f"{mid}: instrument_tag 'frozen-store' illegal — run manifest "
                    f"{m.get('task')}/{m.get('runid')} lists an extraction output among "
                    f"its inputs (must be tagged 'v2').")

    if errors:
        print("REGISTRY VALIDATION FAILURES (§0.8/§0.10):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"validate_registry: OK ({len(reg.get('metrics', []))} metrics).")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
