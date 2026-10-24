#!/usr/bin/env python3
"""
logic/fol.py — VJ2.1 sorted-FOL / SMT rendering of the judge decision (SPEC §VJ2.1).

Per cross-theory candidate pair the judge verdict is a function of six ground primitives
(materialised from p5, bounded treatment, as in VJ1): SF=same_family, OP=opposed,
SR=shared_rel, NV=nvm>=2, FA=fork_axis, CT=cross_theory. The decision axioms below mirror
VJ1.2's rules (which transcribe p5_judge.judge_pair); here they are Z3 boolean expressions
so every verdict becomes a theorem checked by the SMT solver (VJ2.2).
"""
from __future__ import annotations

import sys
from pathlib import Path

import z3

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import p5_judge as P5  # noqa: E402

PRIM = ["SF", "OP", "SR", "NV", "FA", "CT"]


def primitives(A, B):
    """{(a_id,b_id): {SF,OP,SR,NV,FA,CT}} over same-axis candidate pairs (p5 ground truth)."""
    A, B = P5._norm(A), P5._norm(B)
    rel_a, rel_b = P5._incident_relations(A["edges"]), P5._incident_relations(B["edges"])
    sig_a, sig_b = P5._neighbor_value_sigs(A), P5._neighbor_value_sigs(B)
    ct = A["theory"] != B["theory"]
    out = {}
    for a in A["nodes"]:
        for b in B["nodes"]:
            if a["axis"] != b["axis"]:
                continue
            out[(a["claim_id"], b["claim_id"])] = {
                "SF": P5.same_family(a["value"], b["value"]),
                "OP": a["polarity"] != b["polarity"],
                "SR": bool(rel_a.get(a["claim_id"], set()) & rel_b.get(b["claim_id"], set())),
                "NV": P5._neighbor_values_match(sig_a.get(a["claim_id"], []), sig_b.get(b["claim_id"], [])) >= 2,
                "FA": a["axis"] in P5.FORK_AXES,
                "CT": ct,
            }
    return out


def decision(SF, OP, SR, NV, FA, CT):
    """Judge decision as Z3 boolean expressions (mirrors p5:155-186 / VJ1.2 rules).
    Returns dict of verdict literals: fork, grade_formal, grade_partial, grade_generative, none."""
    And, Or, Not = z3.And, z3.Or, z3.Not
    fork = And(FA, Or(Not(SF), OP))                         # p5:161
    skip = Or(fork, OP)                                     # p5:166-168
    formalraw = And(Not(skip), SF, NV)                      # p5:173 formal if nvm>=2
    haspartial = And(Not(skip), SF, SR)                     # p5:173 partial if shared_rel
    g_formal = And(formalraw, Not(CT))                      # p5:177
    g_partial = Or(And(formalraw, CT), And(haspartial, Not(formalraw)))   # p5:173,178-179 (cap)
    g_generative = And(Not(skip), Not(formalraw), Not(haspartial))        # p5:173,175
    g_none = And(Not(fork), skip)                           # opposed non-fork → neither (p5:167)
    return {"fork": fork, "formal": g_formal, "partial": g_partial,
            "generative": g_generative, "none": g_none}


def lits(vals):
    """Z3 BoolVal literals for a primitive dict."""
    return {k: z3.BoolVal(bool(vals[k])) for k in PRIM}


def entailed(verdict_key, vals):
    """Is `verdict_key` entailed by the decision axioms under ground primitives `vals`?
    UNSAT(axioms ∧ facts ∧ ¬verdict) ⇒ entailed. Returns (entailed_bool, z3_result)."""
    L = lits(vals)
    d = decision(L["SF"], L["OP"], L["SR"], L["NV"], L["FA"], L["CT"])
    s = z3.Solver()
    s.add(z3.Not(d[verdict_key]))
    r = s.check()
    return (r == z3.unsat), str(r)


def symbolic_vars():
    return {k: z3.Bool(k) for k in PRIM}
