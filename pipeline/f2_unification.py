#!/usr/bin/env python3
"""
pipeline/f2_unification.py — F2 unification index + MO3 functoriality counts (SPEC §5 F2).

Preregistered (Kitcher-flavoured): for each persisted correspondence c on axis A between
theories T1,T2:
  u(c) = w1·forks_touched(c) + w2·support_cone(c) + w3·axis_reach(c),   w=(1,1,1)
  forks_touched = persisted forks on axis A involving T1 or T2
  support_cone  = within-theory edges (grounds/entails/constrains) incident to either claim
  axis_reach    = count of OTHER theory pairs with a persisted corr on the same axis+family
Sensitivity: Kendall τ of the ranking over the weight-simplex grid {0.2..0.8} (normalised) →
f2.rank_stability_tau_min. Generative corrs INCLUDED but flagged (201/221); a partial-only
ranking is reported beside. Top-10 → results/f2_top10.json + docs/briefs/unification-index.md.

MO3: over pairs of reference-matched pairs (m1:a1↔b1, m2:a2↔b2, same theories), does a
within-theory edge a1→a2 have a matching edge b1→b2 (same type)? Raw counts only —
"candidate functorial structure: counts" (never claims established functoriality).
"""
from __future__ import annotations

import glob
import itertools
import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import p5_judge as P5  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
GRAPHS = ENGINE / "data" / "graphs"
SLUGS = ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]
WITHIN_EDGES = {"grounds", "entails", "constrains"}


def load():
    claims, edges_by_theory = {}, {}
    for slug in SLUGS:
        g = json.loads((GRAPHS / f"{slug}.json").read_text())
        th = g["theory"]
        for n in g["nodes"]:
            claims[n["claim_id"]] = n
        edges_by_theory[th] = [e for e in g.get("edges", []) if e["relation"] in WITHIN_EDGES]
    corrs, forks = [], []
    for jf in sorted(glob.glob(str(ENGINE / "results" / "*_judge.json"))):
        J = json.loads(Path(jf).read_text())
        for c in J.get("correspondences", []):
            corrs.append(c)
        for f in J.get("forks", []):
            forks.append(f)
    return claims, edges_by_theory, corrs, forks


def corr_axis_family(c, claims):
    a = claims.get(c["left_ids"][0]); b = claims.get(c["right_ids"][0])
    if not (a and b):
        return None, frozenset()
    fam = P5.value_family(a["value"]) & P5.value_family(b["value"])
    if not fam:
        fam = P5.value_family(a["value"]) or P5.value_family(b["value"])
    return a["axis"], fam


def main() -> int:
    claims, edges_by_theory, corrs, forks = load()
    node_corrs = [c for c in corrs if c.get("kind") == "node"]

    # incidence count per claim (within-theory edges)
    incid = {}
    for th, edges in edges_by_theory.items():
        for e in edges:
            incid[e["src_claim_id"]] = incid.get(e["src_claim_id"], 0) + 1
            incid[e["dst_claim_id"]] = incid.get(e["dst_claim_id"], 0) + 1

    # forks indexed by axis -> set of theories
    fork_axis_theories = {}
    for f in forks:
        a = claims.get(f["left_ids"][0]); b = claims.get(f["right_ids"][0])
        if not (a and b):
            continue
        fork_axis_theories.setdefault(a["axis"], []).append((a["theory"], b["theory"]))

    # axis -> list of (pair_frozenset, familyset) for axis_reach
    axis_index = {}
    corr_meta = []
    for c in node_corrs:
        a = claims.get(c["left_ids"][0]); b = claims.get(c["right_ids"][0])
        if not (a and b):
            corr_meta.append(None); continue
        axis, fam = corr_axis_family(c, claims)
        pair = frozenset((a["theory"], b["theory"]))
        axis_index.setdefault(axis, []).append((pair, fam))
        corr_meta.append({"axis": axis, "fam": fam, "pair": pair, "T1": a["theory"], "T2": b["theory"]})

    def forks_touched(m):
        n = 0
        for (ta, tb) in fork_axis_theories.get(m["axis"], []):
            if m["T1"] in (ta, tb) or m["T2"] in (ta, tb):
                n += 1
        return n

    def support_cone(c):
        return incid.get(c["left_ids"][0], 0) + incid.get(c["right_ids"][0], 0)

    def axis_reach(m):
        pairs = set()
        for (pair, fam) in axis_index.get(m["axis"], []):
            if pair != m["pair"] and (fam & m["fam"]):
                pairs.add(pair)
        return len(pairs)

    def u_of(c, m, w):
        return w[0] * forks_touched(m) + w[1] * support_cone(c) + w[2] * axis_reach(m)

    def ranking(w):
        scored = []
        for c, m in zip(node_corrs, corr_meta):
            if m is None:
                continue
            scored.append((u_of(c, m, w), c["left_ids"][0] + "×" + c["right_ids"][0], c["grade"]))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored

    base = ranking((1, 1, 1))
    # sensitivity: Kendall tau over the weight-simplex grid {0.2..0.8}, normalised
    from scipy.stats import kendalltau
    base_order = [x[1] for x in base]
    base_rankpos = {k: i for i, k in enumerate(base_order)}
    taus = []
    grid = [0.2, 0.4, 0.6, 0.8]
    for w1, w2, w3 in itertools.product(grid, grid, grid):
        s = w1 + w2 + w3
        w = (w1 / s, w2 / s, w3 / s)
        r = ranking(w)
        order = [x[1] for x in r]
        pos = {k: i for i, k in enumerate(order)}
        a = [base_rankpos[k] for k in base_order]
        b = [pos[k] for k in base_order]
        tau, _ = kendalltau(a, b)
        taus.append(tau)
    tau_min = min(taus)

    partial_only = [x for x in base if x[2] == "partial"]
    top10 = base[:10]
    (SPRINT / "results" / "f2_top10.json").write_text(json.dumps(
        {"weights": [1, 1, 1], "top10": [{"u": u, "pair": p, "grade": g} for u, p, g in top10],
         "n_ranked": len(base), "generative_flagged": sum(1 for x in base if x[2] == "generative"),
         "partial_only_top10": [{"u": u, "pair": p} for u, p, g in partial_only[:10]]},
        indent=2) + "\n")

    # MO3 functoriality counts
    # reference-matched pairs = node corrs (a↔b). For pairs sharing theories, check squares.
    edgeset = {}  # theory -> {(src,dst,rel)}
    for th, edges in edges_by_theory.items():
        edgeset[th] = {(e["src_claim_id"], e["dst_claim_id"], e["relation"]) for e in edges}
    matches = [(c["left_ids"][0], c["right_ids"][0], claims[c["left_ids"][0]]["theory"],
                claims[c["right_ids"][0]]["theory"]) for c in node_corrs
               if c["left_ids"][0] in claims and c["right_ids"][0] in claims]
    squares_checked = squares_commuting = 0
    by_type = {}
    for (a1, b1, ta1, tb1), (a2, b2, ta2, tb2) in itertools.permutations(matches, 2):
        if ta1 != ta2 or tb1 != tb2:
            continue
        for rel in WITHIN_EDGES:
            if (a1, a2, rel) in edgeset.get(ta1, set()):
                squares_checked += 1
                by_type.setdefault(rel, [0, 0])
                by_type[rel][0] += 1
                if (b1, b2, rel) in edgeset.get(tb1, set()):
                    squares_commuting += 1
                    by_type[rel][1] += 1

    reg = Registry()
    b = dict(task="F2", runid="F2-1", instrument_tag="frozen-store", corpus_tag="v1",
             preregistered=True, pilot=False)
    reg.upsert(metric_id="f2.rank_stability_tau_min", value=round(tau_min, 4), n=len(base),
               ci_lo=None, ci_hi=None,
               caveats=[f"min Kendall τ of the top ranking vs w=(1,1,1) over the weight-simplex "
                        f"grid {{0.2..0.8}} ({len(taus)} weight combos); generative corrs included "
                        f"(201/221) and flagged; partial-only ranking beside it"], **b)
    reg.upsert(metric_id="f2.top1_unification", value=top10[0][0], n=len(base),
               caveats=[f"max u(c) = {top10[0][1]} ({top10[0][2]}); full top-10 in results/f2_top10.json"], **b)
    reg.upsert(metric_id="mo3.squares_checked", value=squares_checked, n=len(matches),
               caveats=["candidate functorial structure: counts (never established functoriality). "
                        f"per edge type: {{{', '.join(f'{k}:{v[0]}' for k,v in by_type.items())}}}"], **b)
    reg.upsert(metric_id="mo3.squares_commuting", value=squares_commuting, n=squares_checked,
               caveats=[f"of {squares_checked} within-theory edge squares checked; per type: "
                        f"{{{', '.join(f'{k}:{v[1]}/{v[0]}' for k,v in by_type.items())}}}. "
                        "candidate functorial structure: counts."], **b)
    reg.save()

    # brief
    L = ["# Unification index (F2) — Kitcher-flavoured, operationalised", "",
         f"u(c) = forks_touched + support_cone + axis_reach (w=1,1,1 preregistered). "
         f"{len(base)} node correspondences ranked; generative flagged ({sum(1 for x in base if x[2]=='generative')}/{len(node_corrs)}).",
         f"Rank stability (Kendall τ) over the weight grid: **min τ = {tau_min:.3f}**.", "",
         "## Top 10 (full ranking)", "", "| rank | u | pair | grade |", "|---|---|---|---|"]
    for i, (u, p, g) in enumerate(top10, 1):
        L.append(f"| {i} | {u} | {p} | {g} |")
    L += ["", "## Top 10 — partial-grade only (beside the full ranking)", "",
          "| rank | u | pair |", "|---|---|---|"]
    for i, (u, p, g) in enumerate(partial_only[:10], 1):
        L.append(f"| {i} | {u} | {p} |")
    L += ["", "## MO3 — candidate functorial structure: counts",
          f"- within-theory edge squares checked: **{squares_checked}**; commuting (matching "
          f"edge on the other side): **{squares_commuting}**.",
          f"- per edge type: {{{', '.join(f'{k}: {v[1]}/{v[0]}' for k,v in by_type.items())}}}.",
          "- Reported as counts only; small is honest; this is NOT a claim of established functoriality."]
    (SPRINT / "docs" / "briefs" / "unification-index.md").write_text("\n".join(L) + "\n")
    print(f"F2: ranked {len(base)} corrs; top u={top10[0][0]} ({top10[0][1]}); tau_min={tau_min:.3f}")
    print(f"MO3: squares_checked={squares_checked}, commuting={squares_commuting} {dict(by_type)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
