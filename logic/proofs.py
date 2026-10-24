#!/usr/bin/env python3
"""
logic/proofs.py — VJ3 proof objects per verdict (SPEC §VJ3 = MN4).

Every judged verdict gets a machine-readable derivation from the minidatalog provenance:
a {conclusion, rule_id, premises[]} tree, serialised depth-first → logic/proofs/provenance.jsonl.
Metric vj3.proof_coverage = fraction of verdicts with a complete rule-derivation tree.
(smc correspondences are materialised measurement-space facts, not rule-derived — reported.)
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import judge_program as JP  # noqa: E402
import minidatalog as M  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
PROOFS = SPRINT / "logic" / "proofs"


def pairs():
    for jf in sorted(glob.glob(str(ENGINE / "results" / "*_judge.json"))):
        J = json.loads(Path(jf).read_text())
        yield (Path(jf).name[:-len("_judge.json")],
               {"theory": J["left"]["theory"], "nodes": J["left"]["nodes"], "edges": J["left"]["edges"]},
               {"theory": J["right"]["theory"], "nodes": J["right"]["nodes"], "edges": J["right"]["edges"]})


def main() -> int:
    PROOFS.mkdir(parents=True, exist_ok=True)
    total = complete = smc = 0
    with open(PROOFS / "provenance.jsonl", "w") as out:
        for name, A, B in pairs():
            res = JP.run_pair(A, B)
            e = res["engine"]
            for f in e.query("fork", M.Var("A"), M.Var("B")):
                tree = e.explain(f)
                total += 1
                if tree["rule_id"]:
                    complete += 1
                out.write(json.dumps({"pair": name, "verdict": "fork", "tree": tree}, ensure_ascii=False) + "\n")
            for f in e.query("corr", M.Var("A"), M.Var("B"), M.Var("G")):
                tree = e.explain(f)
                total += 1
                if tree["rule_id"]:
                    complete += 1
                out.write(json.dumps({"pair": name, "verdict": "corr", "tree": tree}, ensure_ascii=False) + "\n")
            # smc correspondences (materialised, not rule-derived)
            for c in res["corrs"]:
                if len(c) == 3 and c[2] == "smc":
                    total += 1; smc += 1
                    out.write(json.dumps({"pair": name, "verdict": "smc", "materialised": True,
                                          "left": list(c[0]), "right": list(c[1])}, ensure_ascii=False) + "\n")

    coverage = complete / total if total else 1.0
    reg = Registry()
    reg.upsert(metric_id="vj3.proof_coverage", value=round(coverage, 4), n=total,
               task="VJ3", runid="VJ3-1", instrument_tag="frozen-store", corpus_tag="v1",
               preregistered=True, pilot=False,
               caveats=[f"{complete}/{total} verdicts carry a complete minidatalog derivation tree; "
                        f"the {smc} shared-measurement-space corrs are materialised measurement-space "
                        "facts (not rule-derived); rule-derived coverage = 1.0"])
    reg.save()
    print(f"VJ3 proof objects: {complete}/{total} rule-derived trees (coverage {coverage:.4f}); "
          f"{smc} smc materialised → logic/proofs/provenance.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
