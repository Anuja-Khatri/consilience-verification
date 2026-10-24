#!/usr/bin/env python3
"""
logic/judge_program.py — VJ1.2 judge decision logic as a stratified logic program.

The judge's GRADE-ASSIGNMENT + FORK-DETECTION decision tree (p5_judge.judge_pair) is
transcribed into minidatalog rules (each rule cites the p5 line it transcribes). The
PRIMITIVE relations the decision consumes — value-family match, opposed polarity, shared
incident relation, neighbour-value-support ≥2, shared-measurement-space — are MATERIALISED
from the ported p5 functions (the sanctioned bounded treatment, §VJ1.2/§VJ2.1); the logic
program then derives the verdicts from them. `logic/judge.lp` ships the same rules in ASP
(clingo) syntax with the same comments.

run_pair(graph_a, graph_b) -> {"forks": set((a,b,axis)), "corrs": set((a,b,grade_or_kind))}
reproducing judge_pair's forks + node/smc correspondences.
"""
from __future__ import annotations

import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
sys.path.insert(0, str(SPRINT / "logic"))
import p5_judge as P5  # noqa: E402  (authoritative judge — primitives + ground truth)
import minidatalog as M  # noqa: E402

V = M.Var


def _materialise(A, B, ablate=None):
    """Primitive facts from p5's own functions (bounded treatment).
    ablate ∈ {None,'axis','polarity','family','neighbour'} disables a rule family (VJ1.4c):
      axis     — drop the axis veto (every node pair becomes a candidate)
      polarity — drop opposed facts (polarity ignored)
      family   — drop samefam facts (value-family match ignored)
      neighbour— drop nvm2 facts (no formal via neighbour support)."""
    A, B = P5._norm(A), P5._norm(B)
    rel_a, rel_b = P5._incident_relations(A["edges"]), P5._incident_relations(B["edges"])
    sig_a, sig_b = P5._neighbor_value_sigs(A), P5._neighbor_value_sigs(B)
    cross = A["theory"] != B["theory"]
    facts = []
    for a in A["nodes"]:
        for b in B["nodes"]:
            if a["axis"] != b["axis"] and ablate != "axis":
                continue  # p5:155 — axis mismatch is the ONLY hard veto
            ai, bi = a["claim_id"], b["claim_id"]
            facts.append(("cand", (ai, bi)))
            if ablate != "family" and P5.same_family(a["value"], b["value"]):
                facts.append(("samefam", (ai, bi)))          # p5:159,64-68
            if ablate != "polarity" and a["polarity"] != b["polarity"]:
                facts.append(("opposed", (ai, bi)))          # p5:158
            if rel_a.get(ai, set()) & rel_b.get(bi, set()):
                facts.append(("sharedrel", (ai, bi)))        # p5:170
            if ablate != "neighbour" and P5._neighbor_values_match(sig_a.get(ai, []), sig_b.get(bi, [])) >= 2:
                facts.append(("nvm2", (ai, bi)))             # p5:171,173 (formal needs >=2)
            if a["axis"] in P5.FORK_AXES:
                facts.append(("forkaxis", (ai,)))            # p5:31-36,161
    if cross:
        facts.append(("crosstheory", ()))                   # p5:142,178
    # shared_measurement_space correspondence (p5:148-151) — materialised, kind-level
    smc = P5._shared_measurement_space(A, B, f'{A["theory"]}x{B["theory"]}')
    return facts, smc


def _rules():
    a, b = V("A"), V("B")
    At = M.Atom
    # stratum groups (evaluated in order for sound stratified negation)
    g0 = [
        M.Rule(At("notsamefam", (a, b)), [At("cand", (a, b))], neg=[At("samefam", (a, b))],
               rule_id="notsamefam", comment="p5:159 fam_same = same_family(...)"),
        M.Rule(At("fork", (a, b)), [At("cand", (a, b)), At("forkaxis", (a,)), At("notsamefam", (a, b))],
               rule_id="fork_fam", comment="p5:161 axis in FORK_AXES and not fam_same"),
        M.Rule(At("fork", (a, b)), [At("cand", (a, b)), At("forkaxis", (a,)), At("opposed", (a, b))],
               rule_id="fork_pol", comment="p5:161 axis in FORK_AXES and opposed"),
        M.Rule(At("skipcorr", (a, b)), [At("fork", (a, b))],
               rule_id="skip_fork", comment="p5:166 continue after fork"),
        M.Rule(At("skipcorr", (a, b)), [At("cand", (a, b)), At("opposed", (a, b))],
               rule_id="skip_opp", comment="p5:167-168 if opposed: continue"),
    ]
    g1 = [
        M.Rule(At("formalraw", (a, b)), [At("cand", (a, b)), At("samefam", (a, b)), At("nvm2", (a, b))],
               neg=[At("skipcorr", (a, b))],
               rule_id="formal", comment="p5:173 formal if nvm>=2 (same_family, not skipped)"),
        M.Rule(At("haspartial", (a, b)), [At("cand", (a, b)), At("samefam", (a, b)), At("sharedrel", (a, b))],
               neg=[At("skipcorr", (a, b))],
               rule_id="partial_cand", comment="p5:173 partial if shared_rel"),
    ]
    g2 = [
        M.Rule(At("partialonly", (a, b)), [At("haspartial", (a, b))], neg=[At("formalraw", (a, b))],
               rule_id="partial_only", comment="p5:173 partial only when not formal"),
        M.Rule(At("generative", (a, b)), [At("cand", (a, b))],
               neg=[At("skipcorr", (a, b)), At("formalraw", (a, b)), At("haspartial", (a, b))],
               rule_id="generative", comment="p5:173,175 generative otherwise (incl. not fam_same)"),
    ]
    g3 = [
        M.Rule(At("corr", (a, b, "partial")), [At("formalraw", (a, b)), At("crosstheory", ())],
               rule_id="cap", comment="p5:178-179 cross-theory formal hard-capped to partial"),
        M.Rule(At("corr", (a, b, "formal")), [At("formalraw", (a, b))], neg=[At("crosstheory", ())],
               rule_id="formal_final", comment="p5:177 within-theory formal stands"),
        M.Rule(At("corr", (a, b, "partial")), [At("partialonly", (a, b))],
               rule_id="partial_final", comment="p5:173 partial"),
        M.Rule(At("corr", (a, b, "generative")), [At("generative", (a, b))],
               rule_id="generative_final", comment="p5:173,175 generative"),
    ]
    return [g0, g1, g2, g3]


def run_pair(A, B, ablate=None):
    facts, smc = _materialise(A, B, ablate=ablate)
    e = M.Engine()
    for pred, args in facts:
        e.add_fact(pred, *args)
    for group in _rules():
        for r in group:
            e.add_rule(r)
        e.run()
    forks, corrs = set(), set()
    for f in e.query("fork", V("A"), V("B")):
        a, b = f.args
        # axis of a (from the graph) — look up
        forks.add((a, b))
    for f in e.query("corr", V("A"), V("B"), V("G")):
        a, b, g = f.args
        corrs.add((a, b, g))
    if smc:
        corrs.add((tuple(smc["left_ids"]), tuple(smc["right_ids"]), "smc"))
    return {"forks": forks, "corrs": corrs, "engine": e}


def judge_truth(A, B):
    """Ground truth from judge_pair: forks as (a,b); corrs as (a,b,grade) or smc tuple."""
    out = P5.judge_pair(A, B)
    forks = set()
    for f in out["forks"]:
        forks.add((f["left_ids"][0], f["right_ids"][0]))
    corrs = set()
    for c in out["correspondences"]:
        if c.get("kind") == "shared_measurement_space":
            corrs.add((tuple(c["left_ids"]), tuple(c["right_ids"]), "smc"))
        else:
            corrs.add((c["left_ids"][0], c["right_ids"][0], c["grade"]))
    return {"forks": forks, "corrs": corrs}
