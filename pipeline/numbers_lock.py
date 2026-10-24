#!/usr/bin/env python3
"""
pipeline/numbers_lock.py — NUMBERS LOCK for Paper v1 (SPEC §0.8(iii), §8 P1 freeze gate). $0.

Verifies every P1 precondition (SPEC DAG: {A1, A2, A5, VJ1-4, B2-core, A6, KR1v2, KR3, F2, TD5-S4}) is
present in ONE registry snapshot, then LOCKS it: records {registry_sha256, date, instrument_tag,
corpus_tag} in paper/NUMBERS_LOCK.json and in registry.json's `numbers_lock` field, and renders the
tables from the locked registry. A second snapshot requires regenerating every application document that
cited the first (§0.8(iii)); identical metric → identical number in all seven applications.

Reports any unmet precondition and ABORTS rather than locking (owner: "report any unmet one instead of
proceeding"). Run BEFORE assembling paper/P1.md.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
REG = SPRINT / "results" / "registry.json"

PRECONDITIONS = {
    "A1": ["a1.discovery_survivorship", "a1.match_sample_survivorship"],
    "A2": ["a2.agreement_rate", "a2.downgrade_rate", "a2.survivor_vs_failure_separation"],
    "A5": ["a5.adopted_decoding", "a5.stability_baseline_sprint_estimator"],
    "VJ1": ["vj1.equivalence_rate"], "VJ2": ["vj2.congruence_rate"],
    "VJ3": ["vj3.proof_coverage"], "VJ4": ["vj4.violations"],
    "B2-core": ["b2.negation_polarity_tracking", "b2.double_negation_restoration", "b2.verdict_tracking_correct"],
    "A6": ["a6.fork_recovery_gap", "a6.deobfuscation_leaks"],
    "KR1v2": ["kr.cogitate.recovered", "kr.cogitate.missed"],
    "KR3": ["kr.elife.recovered", "kr.elife.unmappable_rows"],
    "F2": ["f2.rank_stability_tau_min"], "TD5-S4": ["r1.key_null_z_cogitate"],
}


def metrics_sha(metrics):
    canon = json.dumps(sorted(metrics, key=lambda m: m["metric_id"]), sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


def main() -> int:
    data = json.loads(REG.read_text())
    metrics = data["metrics"]
    ids = {m["metric_id"] for m in metrics}

    unmet = {pre: [k for k in need if k not in ids] for pre, need in PRECONDITIONS.items()}
    unmet = {pre: miss for pre, miss in unmet.items() if miss}
    if unmet:
        print("P1 PRECONDITIONS NOT MET — aborting lock (owner: report, do not proceed):")
        for pre, miss in unmet.items():
            print(f"  {pre}: MISSING {miss}")
        return 1
    print(f"P1 preconditions: ALL MET ({len(PRECONDITIONS)} tasks).")

    sha = metrics_sha(metrics)
    date = CFG["dates"]["artifact_stamp"]
    lock = {"registry_sha256": sha, "date": date,
            "instrument_tag": "v2 (frozen-store metrics are lock-stable and citable pre-lock, v2.0.2)",
            "corpus_tag": "v1 (engine frozen corpus; TD1/TD1b/TD2 extensions are P2, absent from P1)",
            "n_metrics": len(metrics), "paper": "P1",
            "preconditions_verified": sorted(PRECONDITIONS),
            "note": "SPEC §0.8(iii) numbers lock: application documents render from THIS snapshot; a second "
                    "snapshot requires regenerating every document that cited the first. Identical metric → "
                    "identical number in all applications."}
    # stamp the registry (hash is over the metrics array, so this field does not change the lock sha)
    data["numbers_lock"] = lock
    REG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    (SPRINT / "paper").mkdir(exist_ok=True)
    (SPRINT / "paper" / "NUMBERS_LOCK.json").write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n")

    # render tables from the locked registry
    r = subprocess.run([sys.executable, str(SPRINT / "pipeline" / "make_tables.py")], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[:200])

    print(f"NUMBERS LOCK written: registry_sha256 {sha[:16]}… date {date} | paper/NUMBERS_LOCK.json")
    print(f"  instrument_tag {lock['instrument_tag'][:24]}…  corpus_tag v1  n_metrics {len(metrics)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
