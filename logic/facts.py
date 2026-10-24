#!/usr/bin/env python3
"""
logic/facts.py — VJ1.1 fact extraction (SPEC §VJ1.1).

Renders every approved claim and every within-theory edge as ground facts for the logic
program, and MATERIALISES family/2 by running the ported value_family function over every
distinct value string in the corpus (the stemming logic becomes a lookup table; its hash
is recorded). Source: the engine's 6 per-theory graphs (data/graphs/*.json), READ-ONLY.

Facts:
  claim(C). theory(C,T). etype(C,E). axis(C,A). polarity(C,P). value(C,V). family(V,F).
  grounds(C1,C2). entails(C1,C2). constrains(C1,C2). predicts_obs(C1,O).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
from p5_judge import value_family  # noqa: E402  (ported; materialised into family/2)

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
GRAPHS = ENGINE / "data" / "graphs"
THEORY_SLUGS = ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]
EDGE_PREDS = {"grounds": "grounds", "entails": "entails", "constrains": "constrains",
              "predicts_observable": "predicts_obs"}


def load_graphs():
    return {slug: json.loads((GRAPHS / f"{slug}.json").read_text()) for slug in THEORY_SLUGS}


def build_facts():
    graphs = load_graphs()
    facts = []  # (pred, args-tuple)
    values = set()
    edge_counts = {}
    n_claims = 0
    for slug, g in graphs.items():
        theory = g["theory"]
        for n in g["nodes"]:
            c = n["claim_id"]
            n_claims += 1
            facts.append(("claim", (c,)))
            facts.append(("theory", (c, theory)))
            facts.append(("etype", (c, n["entity_type"])))
            facts.append(("axis", (c, n["axis"])))
            facts.append(("polarity", (c, n["polarity"])))
            facts.append(("value", (c, n["value"])))
            values.add(n["value"])
        for e in g.get("edges", []):
            pred = EDGE_PREDS.get(e["relation"])
            if pred:
                facts.append((pred, (e["src_claim_id"], e["dst_claim_id"])))
                edge_counts[e["relation"]] = edge_counts.get(e["relation"], 0) + 1
    # materialise family/2
    fam_table = {}
    for v in sorted(values):
        fams = sorted(value_family(v))
        fam_table[v] = fams
        for f in fams:
            facts.append(("family", (v, f)))
    table_hash = hashlib.sha256(
        json.dumps(fam_table, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"facts": facts, "n_claims": n_claims, "n_values": len(values),
            "edge_counts": edge_counts, "family_table": fam_table, "family_table_sha256": table_hash}


def main() -> int:
    b = build_facts()
    out = SPRINT / "logic" / "facts.json"
    out.write_text(json.dumps({"n_claims": b["n_claims"], "n_values": b["n_values"],
                               "edge_counts": b["edge_counts"],
                               "family_table_sha256": b["family_table_sha256"],
                               "n_facts": len(b["facts"])}, indent=2) + "\n")
    print(f"VJ1.1 facts: claims={b['n_claims']}, distinct values={b['n_values']}, "
          f"edges={b['edge_counts']} (total {sum(b['edge_counts'].values())}), "
          f"family_table_sha={b['family_table_sha256'][:16]}…, total facts={len(b['facts'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
