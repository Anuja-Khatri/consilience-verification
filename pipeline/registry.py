#!/usr/bin/env python3
"""
pipeline/registry.py — programmatic results registry (SPEC §0.8).

Every headline number is written here (never hand-typed into a doc). `make_tables.py`
renders this → docs/tables/*.md. Metric schema is results/registry.schema.json.

Usage:
    from registry import Registry
    reg = Registry()
    reg.upsert(metric_id="a5.stability_consensus", value=0.71, ci_lo=0.63, ci_hi=0.78,
               n=140, task="A5", runid="A5-3", instrument_tag="v2", corpus_tag="v2",
               preregistered=True, pilot=False, caveats=["..."])
    reg.save()   # runs validate_registry on the way out
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

SPRINT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = SPRINT / "results" / "registry.json"


class Registry:
    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = {"schema_version": "1.0", "numbers_lock": None, "metrics": []}
        self.data.setdefault("metrics", [])

    def get(self, metric_id: str):
        for m in self.data["metrics"]:
            if m["metric_id"] == metric_id:
                return m
        return None

    def has(self, metric_id: str) -> bool:
        return self.get(metric_id) is not None

    def upsert(self, *, metric_id: str, value, task: str, runid: str,
               instrument_tag: str, corpus_tag: str, preregistered: bool,
               pilot: bool, caveats: list, ci_lo: Optional[float] = None,
               ci_hi: Optional[float] = None, n: Optional[int] = None):
        entry = {
            "metric_id": metric_id, "value": value, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "n": n, "task": task, "runid": runid, "instrument_tag": instrument_tag,
            "corpus_tag": corpus_tag, "preregistered": bool(preregistered),
            "pilot": bool(pilot), "caveats": list(caveats),
        }
        for i, m in enumerate(self.data["metrics"]):
            if m["metric_id"] == metric_id:
                self.data["metrics"][i] = entry
                break
        else:
            self.data["metrics"].append(entry)
        return entry

    def save(self, validate: bool = True):
        self.data["metrics"].sort(key=lambda m: m["metric_id"])
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=False,
                                        ensure_ascii=False) + "\n")
        if validate:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "validate_registry", SPRINT / "pipeline" / "validate_registry.py")
            vr = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(vr)
            rc = vr.validate(self.path)
            if rc != 0:
                raise ValueError("registry failed validation after save (see output)")


if __name__ == "__main__":
    r = Registry()
    print(f"registry: {len(r.data['metrics'])} metrics, schema {r.data['schema_version']}")
