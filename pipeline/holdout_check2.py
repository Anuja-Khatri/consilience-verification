#!/usr/bin/env python3
"""
pipeline/holdout_check2.py — contamination guard (SPEC §0.5).

STAGE 1 (this file, W0.5): doc-id grep over the sprint trees
  {corpora, runs, results, probe_set, bench, logic, spectro, game, paper}
for the engine's HOLDOUT doc_ids (holdout:true in the engine manifest). A hit
anywhere OUTSIDE the sanctioned locations (pipeline/quarantine/, keys/ produced by
quarantine) is a violation → exit 1 (§0.10(6)).

STAGE 2 (n-gram MinHash vs all key texts): wired after A5.4 (ngram_guard.py). A
placeholder hook is present and prints 'stage2: deferred to A5.4'.

Run before every registry write and in `make ci`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))

SCAN_TREES = ["corpora", "runs", "results", "probe_set", "bench",
              "logic", "spectro", "game", "paper"]
# sanctioned holders of key material (§0.5): quarantine scripts and quarantine-built keys
SANCTIONED = {"pipeline/quarantine", "keys"}
TEXT_EXT = {".md", ".json", ".jsonl", ".yaml", ".yml", ".txt", ".csv", ".py",
            ".html", ".tex"}


def holdout_doc_ids() -> list:
    man = json.loads((ENGINE / "data" / "manifest.json").read_text())
    files = man.get("files", {})
    ids = sorted({v["doc_id"] for v in files.values()
                  if isinstance(v, dict) and v.get("holdout") and v.get("doc_id")})
    return ids


def scan(doc_ids):
    violations = []
    for tree in SCAN_TREES:
        root = SPRINT / tree
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
                continue
            rel = p.relative_to(SPRINT).as_posix()
            if any(rel.startswith(s + "/") or rel == s for s in SANCTIONED):
                continue
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                continue
            for did in doc_ids:
                if did in text:
                    violations.append((rel, did))
    return violations


def main() -> int:
    ids = holdout_doc_ids()
    print(f"holdout_check2 stage 1 — holdout doc_ids: {ids}")
    if len(ids) != 3:
        print(f"  WARNING: expected 3 holdout doc_ids, found {len(ids)}")
    violations = scan(ids)
    if violations:
        print("HOLDOUT CONTAMINATION (§0.10(6)):")
        for rel, did in violations:
            print(f"  - {rel} contains holdout doc_id {did}")
        return 1
    print("stage 1 clean: no holdout doc_id leaked into scanned sprint trees.")

    # STAGE 2 (A5.4, D-034): n-gram guard — flag any sprint artifact sharing an exact >=8-word run
    # with K_unique (key-unique content = key shingles − engine-corpus shingles). Rebuilt in-memory
    # from the read-only engine key PDFs each run; NO key-derived content is persisted.
    import ngram_guard as NG
    ng_viol = NG.guard_tree()
    if ng_viol:
        print("stage 2 NGRAM CONTAMINATION (§0.10(6)):")
        for rel, h in ng_viol:
            print(f"  - {rel}: shares {h} key-unique >={NG.N_GUARD}-word run(s)")
        return 1
    print(f"stage 2 clean: no key-unique >={NG.N_GUARD}-word run leaked into scanned sprint trees.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
