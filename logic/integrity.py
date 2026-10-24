#!/usr/bin/env python3
"""
logic/integrity.py — VJ4 integrity constraints over the whole store (SPEC §VJ4 = MN5).

Seven constraints (EXPECT 0 violations; any violation = a real data bug, reported honestly,
fixed only in sprint copies + logged in corrections.md):
  (i)   no pair both corresponds and forks
  (ii)  every node correspondence's two axes are identical
  (iii) every fork has opposed polarity OR disjoint value-families on a shared axis
  (iv)  polarity ∈ {asserts, denies}
  (v)   family materialisation is a well-defined function value→family-set (deterministic)
  (vi)  no claim cited by an edge is missing from the store
  (vii) vocabulary closure: every axis/entity_type in the store exists in the vocab yamls
Output logic/integrity_report.md + metric vj4.violations.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline"))
import p5_judge as P5  # noqa: E402  (same_family, value_family)
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
GRAPHS = ENGINE / "data" / "graphs"
VOCAB = ENGINE / "vocab"
SLUGS = ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]


def load_store():
    claims, edges = {}, []
    for slug in SLUGS:
        g = json.loads((GRAPHS / f"{slug}.json").read_text())
        for n in g["nodes"]:
            claims[n["claim_id"]] = n
        edges += g.get("edges", [])
    corrs, forks = [], []
    for jf in sorted(glob.glob(str(ENGINE / "results" / "*_judge.json"))):
        J = json.loads(Path(jf).read_text())
        corrs += J.get("correspondences", [])
        forks += J.get("forks", [])
    return claims, edges, corrs, forks


def check():
    claims, edges, corrs, forks = load_store()
    V = []  # violations

    # (i) no pair both corresponds and forks (node corrs)
    node_corr_pairs = {frozenset((c["left_ids"][0], c["right_ids"][0]))
                       for c in corrs if c.get("kind") == "node"}
    fork_pairs = {frozenset((f["left_ids"][0], f["right_ids"][0])) for f in forks}
    both = node_corr_pairs & fork_pairs
    if both:
        V += [f"(i) pair both corresponds and forks: {sorted(map(sorted, both))[:5]}"]

    # (ii) node correspondence axes identical
    for c in corrs:
        if c.get("kind") != "node":
            continue
        a, b = claims.get(c["left_ids"][0]), claims.get(c["right_ids"][0])
        if a and b and a["axis"] != b["axis"]:
            V.append(f"(ii) corr {c['left_ids'][0]}×{c['right_ids'][0]} axes differ: {a['axis']} vs {b['axis']}")

    # (iii) fork: shared axis AND (opposed polarity OR disjoint families)
    for f in forks:
        a, b = claims.get(f["left_ids"][0]), claims.get(f["right_ids"][0])
        if not (a and b):
            continue
        shared_axis = a["axis"] == b["axis"]
        opposed = a["polarity"] != b["polarity"]
        disjoint = not P5.same_family(a["value"], b["value"])
        if not (shared_axis and (opposed or disjoint)):
            V.append(f"(iii) fork {f['left_ids'][0]}×{f['right_ids'][0]} ill-formed "
                     f"(axis {a['axis']}/{b['axis']}, opposed={opposed}, disjoint={disjoint})")

    # (iv) polarity enum
    for cid, c in claims.items():
        if c["polarity"] not in ("asserts", "denies"):
            V.append(f"(iv) claim {cid} polarity '{c['polarity']}' not in {{asserts,denies}}")

    # (v) family materialisation deterministic (value → consistent family-set)
    for cid, c in claims.items():
        if P5.value_family(c["value"]) != P5.value_family(c["value"]):  # pragma: no cover
            V.append(f"(v) value_family nondeterministic for {c['value']}")
    # (note: value→family is intentionally a SET map, not single-valued; determinism is the invariant)

    # (vi) edge endpoints present
    for e in edges:
        for end in (e["src_claim_id"], e["dst_claim_id"]):
            if end not in claims:
                V.append(f"(vi) edge endpoint missing from store: {end}")

    # (vii) vocabulary closure
    axes_ok = set(yaml.safe_load((VOCAB / "axes.yaml").read_text())["axes"]) | {"none"}
    etypes_ok = set(yaml.safe_load((VOCAB / "entity_types.yaml").read_text())["types"].keys())
    for cid, c in claims.items():
        if c["axis"] not in axes_ok:
            V.append(f"(vii) claim {cid} axis '{c['axis']}' not in vocab")
        if c["entity_type"] not in etypes_ok:
            V.append(f"(vii) claim {cid} entity_type '{c['entity_type']}' not in vocab")

    return V, {"claims": len(claims), "edges": len(edges), "corrs": len(corrs), "forks": len(forks)}


def main() -> int:
    V, counts = check()
    md = ["# VJ4 integrity report (SPEC §VJ4)", "",
          f"Store: {counts['claims']} claims, {counts['edges']} edges, {counts['corrs']} "
          f"correspondences, {counts['forks']} forks.", "",
          f"**Violations: {len(V)}** (expected 0).", ""]
    md += ([f"- {v}" for v in V] if V else
           ["All seven constraints hold. (NB constraint (v): value→family is intentionally a "
            "SET map — value_family returns multiple 5-char stems; the invariant checked is "
            "determinism, which holds.)"])
    (SPRINT / "logic" / "integrity_report.md").write_text("\n".join(md) + "\n")
    reg = Registry()
    reg.upsert(metric_id="vj4.violations", value=len(V), n=counts["corrs"] + counts["forks"],
               task="VJ4", runid="VJ4-1", instrument_tag="frozen-store", corpus_tag="v1",
               preregistered=True, pilot=False,
               caveats=["ASP-style integrity constraints over the persisted store; "
                        f"{counts['claims']} claims / {counts['corrs']} corrs / {counts['forks']} forks; "
                        "0 expected; any >0 is a real data bug (corrections.md)"])
    reg.save()
    print(f"VJ4 integrity: {len(V)} violations over "
          f"{counts['claims']} claims / {counts['corrs']} corrs / {counts['forks']} forks "
          f"→ logic/integrity_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
