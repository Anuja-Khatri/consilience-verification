#!/usr/bin/env python3
"""D4 judge — DETERMINISTIC correspondence/fork detection over typed theory graphs.
The LLM never judges; this is pure code over typed data.

Adjudication 2026-08-13 (judge-adjudication-1.md) is implemented here:
  (a) Match key is (axis, polarity, value-family). AXIS mismatch is the ONLY hard veto
      (it still kills the planted fake). entity_type no longer vetoes — a mismatch is
      recorded as `type_divergence: true`, a confidence signal, not a block.
  (b) Shared measurement space is a first-class correspondence (grade `partial`): when
      both theories carry observable_commitment/measurement claims whose observable
      spaces (axes.yaml observable_links × observables.yaml scales) intersect. The
      per-axis observable_commitment forks are STILL emitted — complementary, not either/or.
  (c) `formal` requires matching neighbor VALUES (relation ∧ endpoint axis ∧ endpoint
      value-family) ≥2, not mere typed-shape overlap; AND cross-theory grades are hard-
      capped at `partial` with a logged `capped_from`.

judge_pair(graph_a, graph_b) -> {"correspondences": [...], "forks": [...]}
Accepts Graph pydantic objects or plain dicts.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# Discriminating axes tied to observable spaces: same axis + disjoint value-family/opposed
# polarity => a FORK. Non-fork axes with a different value-family are a GENERATIVE
# correspondence (analogy), never a fork.
FORK_AXES = {"locus", "temporal_profile", "connectivity", "substrate_dependence",
             "mechanism_scale", "observable_commitment",
             # computability is the computation-vs-being fault line; after the value re-encode
             # (negation -> polarity) it forks on OPPOSED polarity (deny vs assert computability).
             "computability"}

_VOCAB = Path(__file__).resolve().parent.parent / "vocab"
_AXES = yaml.safe_load((_VOCAB / "axes.yaml").read_text())
_OBS = {o["id"]: o["scale"] for o in yaml.safe_load((_VOCAB / "observables.yaml").read_text())["observables"]}
_OBS_LINKS = _AXES.get("observable_links", {})

# ── value-family (same discriminative-stem logic as the coverage gate) ──
_STOP = {"the", "and", "of", "a", "to", "for", "per", "some", "full", "not", "with", "by", "half"}
# Non-discriminative 5-char stems: topic/scaffolding words shared across a theory's claims on
# an axis (e.g. "connectivity", "required"). Excluding them forces value-family onto the
# discriminative token (heterogeneous vs global_workspace, dependent vs independent), so genuine
# disagreements still FORK instead of being merged into a false same-family correspondence.
_GENERIC = {"subst", "corti", "corte", "cereb", "consc", "infor", "integ", "cogni",
            "proce", "neura", "brain", "syste", "struc", "cause", "effec",
            "conne", "requi",
            # axis-name structural stems (2026-08-13 sign-off): a value like `X_threshold`
            # must not match another `Y_threshold` on the vacuous axis word — the discriminative
            # tokens (X vs Y) must carry it, else it's a cross-theory echo (→ generative, per H3).
            # NOTE: `compu`/`funda` are deliberately NOT excluded — there the shared token IS the
            # commitment (both deny computability / assert fundamentality = genuine H1/H2 agreement).
            "thres", "locus", "tempo", "archi", "mecha"}


def value_family(v: str) -> frozenset:
    return frozenset(w[:5] for w in re.findall(r"[a-zΦ0-9]+", str(v).lower())
                     if len(w) >= 4 and w not in _STOP and w[:5] not in _GENERIC)


def same_family(a: str, b: str) -> bool:
    fa, fb = value_family(a), value_family(b)
    if not fa or not fb:
        return a == b            # fallback to exact match for stem-less tokens
    return bool(fa & fb)


def _norm(g):
    return g.model_dump() if hasattr(g, "model_dump") else g


def _incident_relations(edges):
    rel = {}
    for e in edges:
        rel.setdefault(e["src_claim_id"], set()).add(e["relation"])
        rel.setdefault(e["dst_claim_id"], set()).add(e["relation"])
    return rel


def _neighbor_value_sigs(g):
    """node_id -> list of (relation, neighbor_axis, neighbor_value_family). Two nodes'
    signatures 'match on values' when relation AND endpoint axis agree AND the endpoint
    value-families intersect — a real typed+valued neighbor, not just typed shape."""
    by_id = {n["claim_id"]: n for n in g["nodes"]}
    sigs = {}
    for e in g["edges"]:
        for node, other in ((e["src_claim_id"], e["dst_claim_id"]), (e["dst_claim_id"], e["src_claim_id"])):
            o = by_id.get(other)
            if o:
                sigs.setdefault(node, []).append((e["relation"], o["axis"], value_family(o["value"])))
    return sigs


def _neighbor_values_match(sa, sb) -> int:
    """count (relation, axis)-aligned neighbor pairs whose value-families intersect."""
    used, n = set(), 0
    for ra, axa, vfa in sa:
        for j, (rb, axb, vfb) in enumerate(sb):
            if j in used:
                continue
            if ra == rb and axa == axb and vfa and vfb and (vfa & vfb):
                used.add(j); n += 1; break
    return n


def _observable_spaces(node):
    """observable-space ids a measurement/observable_commitment claim commits to."""
    if node["entity_type"] != "measurement" and node["axis"] != "observable_commitment":
        return set()
    link = _OBS_LINKS.get(node["axis"], [])
    ids = link if isinstance(link, list) else link.get(node.get("theory", ""), [])
    return {i for i in ids if i in _OBS and i != "none"}


def _shared_measurement_space(A, B, pair):
    """Ruling (b): first-class `partial` correspondence over the intersecting observable
    spaces of both theories' measurement claims, if the spaces overlap at equal scale."""
    left = {n["claim_id"]: _observable_spaces(n) for n in A["nodes"] if _observable_spaces(n)}
    right = {n["claim_id"]: _observable_spaces(n) for n in B["nodes"] if _observable_spaces(n)}
    if not left or not right:
        return None
    inter = set().union(*left.values()) & set().union(*right.values())
    inter = {i for i in inter if _OBS.get(i) != "n/a"}          # keep real, scaled spaces
    if not inter:
        return None
    scales = sorted({_OBS[i] for i in inter})
    left_ids = sorted(cid for cid, s in left.items() if s & inter)
    right_ids = sorted(cid for cid, s in right.items() if s & inter)
    return {"pair": pair, "kind": "shared_measurement_space", "grade": "partial",
            "left_ids": left_ids, "right_ids": right_ids, "spaces": sorted(inter),
            "scale": scales, "type_divergence": False, "capped_from": None, "status": "draft",
            "rationale": (f"both theories commit measurements to a shared observable space "
                          f"{sorted(inter)} at {scales} scale — golden S2 (pairability spine); "
                          f"the disagreements inside it surface as the observable_commitment forks")}


def judge_pair(graph_a, graph_b):
    A, B = _norm(graph_a), _norm(graph_b)
    cross_theory = A["theory"] != B["theory"]
    rel_a, rel_b = _incident_relations(A["edges"]), _incident_relations(B["edges"])
    sig_a, sig_b = _neighbor_value_sigs(A), _neighbor_value_sigs(B)
    pair = f'{A["theory"]}x{B["theory"]}'
    corrs, forks = [], []

    # (b) shared measurement space — a first-class correspondence, emitted alongside forks
    smc = _shared_measurement_space(A, B, pair)
    if smc:
        corrs.append(smc)

    for a in A["nodes"]:
        for b in B["nodes"]:
            if a["axis"] != b["axis"]:
                continue  # (a) AXIS mismatch is the ONLY hard veto — kills the planted fake
            type_div = a["entity_type"] != b["entity_type"]   # confidence signal, not a veto
            opposed = a["polarity"] != b["polarity"]
            fam_same = same_family(a["value"], b["value"])

            if a["axis"] in FORK_AXES and ((not fam_same) or opposed):
                forks.append({"pair": pair, "axis": a["axis"], "left_ids": [a["claim_id"]],
                              "right_ids": [b["claim_id"]], "left_value": a["value"],
                              "right_value": b["value"], "type_divergence": type_div,
                              "polarity_opposed": opposed})
                continue
            if opposed:      # disagreement on a non-fork axis: neither correspondence nor fork
                continue

            shared_rel = bool(rel_a.get(a["claim_id"], set()) & rel_b.get(b["claim_id"], set()))
            nvm = _neighbor_values_match(sig_a.get(a["claim_id"], []), sig_b.get(b["claim_id"], []))
            if fam_same:
                raw = "formal" if nvm >= 2 else ("partial" if shared_rel else "generative")
            else:
                raw = "generative"           # same axis, different value-family (non-fork axis)

            grade, capped_from = raw, None
            if cross_theory and grade == "formal":
                grade, capped_from = "partial", "formal"   # (c) hard cap cross-theory grades

            corrs.append({"pair": pair, "left_ids": [a["claim_id"]], "right_ids": [b["claim_id"]],
                          "kind": "node", "grade": grade, "capped_from": capped_from,
                          "type_divergence": type_div, "status": "draft",
                          "rationale": (f'{a["axis"]}: {a["value"]} ~ {b["value"]} ({grade}'
                                        + (f', capped_from {capped_from}' if capped_from else '')
                                        + (', type_divergence' if type_div else '') + ')')})

    return {"correspondences": corrs, "forks": forks}


if __name__ == "__main__":  # smoke
    import json
    A = json.loads(Path(sys.argv[1]).read_text()); B = json.loads(Path(sys.argv[2]).read_text())
    out = judge_pair(A, B)
    print(json.dumps(out, indent=2, ensure_ascii=False))
