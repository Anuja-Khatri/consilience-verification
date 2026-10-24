#!/usr/bin/env python3
"""
pipeline/runmanifest.py — per-run manifest writer (SPEC §0.8).

Every task run writes runs/<task>/<runid>/manifest.json with: config snapshot,
engine_fingerprint, corpus_tag, instrument_tag, input hashes, seeds, model provenance,
outputs+hashes, start/finish (artifact_stamp — no wall clock in hashed artifacts).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

import yaml

SPRINT = Path(__file__).resolve().parent.parent


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_manifest(task: str, runid: str, *, instrument_tag: str, corpus_tag: str,
                   inputs: List[dict], outputs: Optional[List[str]] = None,
                   seeds: Optional[dict] = None, model_provenance: Optional[list] = None,
                   notes: str = "") -> Path:
    cfg = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
    fp = json.loads((SPRINT / "results" / "engine_fingerprint.json").read_text())
    out_hashes = []
    for o in (outputs or []):
        p = SPRINT / o if not Path(o).is_absolute() else Path(o)
        out_hashes.append({"path": o, "sha256": _sha(p) if p.is_file() else None,
                           "kind": "dir" if p.is_dir() else "file"})
    man = {
        "task": task, "runid": runid,
        "instrument_tag": instrument_tag, "corpus_tag": corpus_tag,
        "engine_fingerprint": fp["combined_sha256"],
        "artifact_stamp": cfg["dates"]["artifact_stamp"],
        "config_snapshot": {"models": cfg["models"], "seeds": cfg["seeds"],
                            "thresholds_ngram": cfg["thresholds"]["ngram"]},
        "inputs": inputs,
        "outputs": out_hashes,
        "seeds": seeds or {},
        "model_provenance": model_provenance or [],
        "notes": notes,
    }
    d = SPRINT / "runs" / task / runid
    d.mkdir(parents=True, exist_ok=True)
    path = d / "manifest.json"
    path.write_text(json.dumps(man, indent=2, sort_keys=False, ensure_ascii=False) + "\n")
    return path


def input_ref(path, kind: str) -> dict:
    """Build an input record {path, kind, sha256}. kind marks provenance; kind=='extraction'
    on ANY input forbids instrument_tag 'frozen-store' (v2.0.2)."""
    p = Path(path)
    sha = _sha(p) if p.exists() else None
    return {"path": str(path), "kind": kind, "sha256": sha}
