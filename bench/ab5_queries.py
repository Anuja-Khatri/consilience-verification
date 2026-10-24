#!/usr/bin/env python3
"""
bench/ab5_queries.py — AB5 Rung 5c: compositional soft queries vs symbolic answers (= MN2).
SPEC §AB5.  $0 (local mpnet embeddings, cached under cache/emb/; symbolic is pure Python).

~26 conjunctive 2–3-hop queries over the claim store, template-authored here and emitted as an
Anu QUERY PACKET (review/ab5_queries.csv — approve/edit; a reading task). Two answer engines:

  SYMBOLIC (exact): minidatalog queries over the VJ1 program's materialised relations —
    base facts (claim/theory/axis/polarity/value/family + grounds/entails/constrains) from
    logic/facts.py, PLUS corr/corresponds/fork derived by logic/judge_program.run_pair over the
    13 persisted theory pairs (VJ1's logic program). Family constraints that OR several tokens
    are evaluated as a UNION of conjunctive Datalog bodies. This is the ground truth.

  SOFT (CQD-style): the compositional SKELETON (variables + structural joins: theory membership,
    grounds/corr/fork edges) is shared by both arms; the soft arm's ONLY approximation is CLAIM
    CONTENT — each content-descriptor atom is scored by embedding cosine (AB2-a mpnet over claim
    statements) between the atom's rendered text and each claim, NOT by its typed fields. Existential
    claim vars are resolved by a top-k=5 beam (CQD's method); the conjunction is a t-norm, both
    {min, product} reported. So a soft binding can pick a lexically-similar but WRONGLY-TYPED claim
    (the direction/shortcut error) — exactly the failure analysis AB5 feeds to G5.

Metrics (PRELIMINARY here — final land at bench/ab5_finalize.py after the query packet returns, per
the A2/kr1 packet discipline): ab5.p_at_1 / ab5.p_at_5 per t-norm vs symbolic truth; ab5.empty_query_fpr
(empty-symbolic queries are KEPT as a calibration corner — the soft method should score them low).
"""
from __future__ import annotations

import csv
import json
import sys
from itertools import product
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
sys.path.insert(0, str(SPRINT / "bench"))

import minidatalog as M  # noqa: E402
import facts as F  # noqa: E402
import equiv as EQ  # noqa: E402
import judge_program as JP  # noqa: E402
from ab2_embed import embed, cos  # noqa: E402

REV = SPRINT / "review"
OUT = SPRINT / "results"
TAU = 0.50  # calibration threshold for empty_query_fpr (cosine-scale min-tnorm top-1)
BEAM_K = 5


# ── store (base facts + VJ1-program corr/fork) ───────────────────────────────
def build_store():
    e = M.Engine()
    b = F.build_facts()
    for pred, args in b["facts"]:
        e.add_fact(pred, *args)
    for _name, A, B in EQ.persisted_pairs():
        o = JP.run_pair(A, B)
        for (a, bb, g) in o["corrs"]:
            if g == "smc":
                continue
            for x, y in ((a, bb), (bb, a)):          # relation is symmetric for querying
                e.add_fact("corr_any", x, y)
                e.add_fact("corr_grade", x, y, g)
                if g in ("formal", "partial"):
                    e.add_fact("corresponds", x, y)
        for (a, bb) in o["forks"]:
            e.add_fact("fork", a, bb); e.add_fact("fork", bb, a)
    return e


def claim_statements():
    g = F.load_graphs()
    return {n["claim_id"]: n["statement"] for s in g.values() for n in s["nodes"]}


THEORIES = ["Active Inference", "CEMI", "GNWT", "IIT", "NREP", "Orch-OR"]


# ── query set (authored; grounded in the real store) ─────────────────────────
# var tokens are "?"-prefixed; theory/grade constants are bare. descs carry BOTH an NL `text`
# (soft) and typed fields axis/pol/families/etype (symbolic). answer = projected variable.
def queries():
    Q = []

    def q(id, nl, answer, answer_kind, descs, rels, tag):
        Q.append({"id": id, "nl": nl, "answer": answer, "answer_kind": answer_kind,
                  "descs": descs, "rels": rels, "tag": tag})

    # ---- content-descriptor, answer = theory (2-hop: desc + theory join) ----
    q("q01", "theories with a claim asserting a prefrontal/parietal cortical locus of consciousness",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness is localised to prefrontal and parietal cortex", "axis": "locus",
        "pol": "asserts", "families": ["prefr", "parie"]}],
      [["theory", "?C", "?T"]], "content")
    q("q02", "theories with a claim asserting a single maximal/irreducible complex as the locus",
      "?T", "theory",
      [{"var": "?C", "text": "the physical substrate is a single maximally irreducible complex", "axis": "locus",
        "pol": "asserts", "families": ["compl", "maxim", "irred"]}],
      [["theory", "?C", "?T"]], "content")
    q("q03", "theories with a claim denying that consciousness is computable",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness is not computable / not a form of computation", "axis": "computability",
        "pol": "denies", "families": ["compu"]}],
      [["theory", "?C", "?T"]], "content")
    q("q04", "theories with a claim asserting consciousness is fundamental (not emergent)",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness is fundamental, a basic feature of reality, not emergent",
        "axis": "fundamentality", "pol": "asserts", "families": ["funda"]}],
      [["theory", "?C", "?T"]], "content")
    q("q05", "theories with a claim asserting substrate dependence",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness depends on a specific physical substrate", "axis": "substrate_dependence",
        "pol": "asserts", "families": ["depen"]}],
      [["theory", "?C", "?T"]], "content")
    q("q06", "theories with a claim asserting free-energy / surprise minimization as the mechanism",
      "?T", "theory",
      [{"var": "?C", "text": "the brain minimises variational free energy and prediction surprise",
        "axis": "mechanism", "pol": "asserts", "families": ["energ", "free", "minim", "surpr"]}],
      [["theory", "?C", "?T"]], "content")
    q("q07", "theories with a claim asserting neural synchrony as the mechanism or connectivity",
      "?T", "theory",
      [{"var": "?C", "text": "conscious binding is realised by synchronous neural oscillations",
        "axis": None, "pol": "asserts", "families": ["synch"]}],
      [["theory", "?C", "?T"]], "content")
    q("q08", "theories with a claim asserting an electromagnetic field as the physical locus",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness is an electromagnetic field in the brain", "axis": "locus",
        "pol": "asserts", "families": ["field"]}],
      [["theory", "?C", "?T"]], "content")
    q("q09", "theories with a claim asserting access consciousness / global broadcast as the observable commitment",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness is access/global broadcast, measurable as reportability",
        "axis": "observable_commitment", "pol": "asserts", "families": ["acces", "broad"]}],
      [["theory", "?C", "?T"]], "content")
    q("q10", "theories with a claim asserting identity between experience and physical structure",
      "?T", "theory",
      [{"var": "?C", "text": "experience is identical to an integrated cause-effect structure",
        "axis": "identity_relation", "pol": "asserts", "families": ["ident", "equal", "exper"]}],
      [["theory", "?C", "?T"]], "content")

    # ---- two-descriptor, answer = theory (the spec's 2-hop template) ----
    q("q11", "theories asserting a cortical locus AND asserting substrate dependence",
      "?T", "theory",
      [{"var": "?C1", "text": "consciousness is localised in cortical regions", "axis": "locus", "pol": "asserts",
        "families": None},
       {"var": "?C2", "text": "consciousness depends on a specific neural substrate",
        "axis": "substrate_dependence", "pol": "asserts", "families": ["depen", "neuro", "groun"]}],
      [["theory", "?C1", "?T"], ["theory", "?C2", "?T"]], "content")
    q("q12", "theories asserting computability-related mechanism AND asserting a free-energy mechanism",
      "?T", "theory",
      [{"var": "?C1", "text": "consciousness or inference is computable", "axis": "computability", "pol": "asserts",
        "families": ["compu"]},
       {"var": "?C2", "text": "the system minimises free energy", "axis": "mechanism", "pol": "asserts",
        "families": ["energ", "free", "minim"]}],
      [["theory", "?C1", "?T"], ["theory", "?C2", "?T"]], "content")
    q("q13", "theories denying computability AND asserting fundamentality",
      "?T", "theory",
      [{"var": "?C1", "text": "consciousness is not computable", "axis": "computability", "pol": "denies",
        "families": ["compu"]},
       {"var": "?C2", "text": "consciousness is fundamental", "axis": "fundamentality", "pol": "asserts",
        "families": ["funda"]}],
      [["theory", "?C1", "?T"], ["theory", "?C2", "?T"]], "content")

    # ---- structural / relational (3-hop over corr / grounds / fork) ----
    q("q14", "claims that ground a claim which corresponds to an Active Inference claim",
      "?C1", "claim",
      [], [["grounds", "?C1", "?C2"], ["corr_any", "?C2", "?C3"], ["theory", "?C3", "Active Inference"]],
      "structural")
    q("q15", "theories having a claim in a partial correspondence with an IIT claim",
      "?T", "theory",
      [], [["corresponds", "?C1", "?C2"], ["theory", "?C2", "IIT"], ["theory", "?C1", "?T"]], "structural")
    q("q16", "claims that are in a fork with an IIT claim on the locus axis",
      "?C1", "claim",
      [{"var": "?C1", "text": "a claim about where consciousness is located", "axis": "locus", "pol": None,
        "families": None}],
      [["fork", "?C1", "?C2"], ["theory", "?C2", "IIT"]], "mixed")
    q("q17", "GNWT claims that ground another GNWT claim about global access",
      "?C1", "claim",
      [{"var": "?C2", "text": "global workspace access broadcast of information", "axis": None, "pol": "asserts",
        "families": ["globa", "acces", "works", "broad"]}],
      [["theory", "?C1", "GNWT"], ["grounds", "?C1", "?C2"], ["theory", "?C2", "GNWT"]], "mixed")
    q("q18", "claims corresponding to a CEMI claim that asserts an electromagnetic field",
      "?C1", "claim",
      [{"var": "?C2", "text": "consciousness is an electromagnetic field", "axis": None, "pol": "asserts",
        "families": ["field"]}],
      [["corr_any", "?C1", "?C2"], ["theory", "?C2", "CEMI"]], "mixed")
    q("q19", "theories with a claim that corresponds to a claim asserting a free-energy mechanism",
      "?T", "theory",
      [{"var": "?C2", "text": "the brain minimises free energy", "axis": "mechanism", "pol": "asserts",
        "families": ["energ", "free", "minim"]}],
      [["corr_any", "?C1", "?C2"], ["theory", "?C1", "?T"]], "mixed")
    q("q20", "claims that ground a claim asserting a free-energy / surprise-minimization mechanism",
      "?C1", "claim",
      [{"var": "?C2", "text": "the brain minimises variational free energy and prediction surprise",
        "axis": "mechanism", "pol": "asserts", "families": ["energ", "free", "minim", "surpr"]}],
      [["grounds", "?C1", "?C2"]], "mixed")

    # ---- empty-symbolic calibration corner (soft SHOULD score low) ----
    q("e01", "theories with a claim DENYING a posterior/cortical locus of consciousness",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness is not located in posterior cortex", "axis": "locus", "pol": "denies",
        "families": None}],
      [["theory", "?C", "?T"]], "empty")
    q("e02", "theories with a claim DENYING substrate dependence",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness does not depend on any physical substrate",
        "axis": "substrate_dependence", "pol": "denies", "families": None}],
      [["theory", "?C", "?T"]], "empty")
    q("e03", "theories with a claim DENYING a free-energy mechanism",
      "?T", "theory",
      [{"var": "?C", "text": "the brain does not minimise free energy", "axis": "mechanism", "pol": "denies",
        "families": ["energ", "free", "minim"]}],
      [["theory", "?C", "?T"]], "empty")
    q("e04", "theories asserting computability AND denying a cortical locus (no such pairing exists)",
      "?T", "theory",
      [{"var": "?C1", "text": "inference is computable", "axis": "computability", "pol": "asserts",
        "families": ["compu"]},
       {"var": "?C2", "text": "consciousness is not cortical", "axis": "locus", "pol": "denies", "families": None}],
      [["theory", "?C1", "?T"], ["theory", "?C2", "?T"]], "empty")
    q("e05", "theories with a claim DENYING that consciousness is fundamental",
      "?T", "theory",
      [{"var": "?C", "text": "consciousness is emergent, not fundamental", "axis": "fundamentality", "pol": "denies",
        "families": ["funda", "emerg"]}],
      [["theory", "?C", "?T"]], "empty")
    q("e06", "claims that are in a fork with an NREP claim on the computability axis",
      "?C1", "claim",
      [{"var": "?C1", "text": "a claim about whether consciousness is computable", "axis": "computability",
        "pol": None, "families": None}],
      [["fork", "?C1", "?C2"], ["theory", "?C2", "NREP"]], "empty")
    return Q


# ── symbolic answers (exact, minidatalog) ────────────────────────────────────
def _term(x):
    return M.Var(x[1:]) if isinstance(x, str) and x.startswith("?") else x


def _desc_body(d, fam):
    C = M.Var(d["var"][1:])
    body = [M.Atom("claim", (C,))]
    if d.get("axis"):
        body.append(M.Atom("axis", (C, d["axis"])))
    if d.get("pol"):
        body.append(M.Atom("polarity", (C, d["pol"])))
    if d.get("etype"):
        body.append(M.Atom("etype", (C, d["etype"])))
    if fam:
        Vv = M.Var(d["var"][1:] + "_v")
        body += [M.Atom("value", (C, Vv)), M.Atom("family", (Vv, fam))]
    return body


def symbolic(q, e, idx):
    ans_var = q["answer"][1:]
    fam_opts = [d.get("families") or [None] for d in q["descs"]]
    answers = set()
    for combo in product(*fam_opts):
        body = []
        for d, fam in zip(q["descs"], combo):
            body += _desc_body(d, fam)
        for r in q["rels"]:
            body.append(M.Atom(r[0], tuple(_term(x) for x in r[1:])))
        for s in e._match_body(body, idx):
            if ans_var in s:
                answers.add(s[ans_var])
    return answers


# ── soft answers (CQD-style: structure exact, content by embedding) ──────────
def soft(q, e, idx, claims, vecs_claim, vecs_desc, tnorm):
    """Rank answer bindings by t-norm of descriptor cosines over the best structural grounding.
    Structural rels (theory/grounds/corr/fork) enforced EXACTLY; typed fields of descs IGNORED
    (content judged only by embedding — where lexical shortcuts occur)."""
    desc_vars = {d["var"][1:]: d for d in q["descs"]}
    # beams: content vars → top-k claims by cosine; others filled during the structural join
    beams = {}
    for v, d in desc_vars.items():
        scored = sorted(((cos(vecs_desc[q["id"] + v], vecs_claim[c]), c) for c in claims), reverse=True)
        beams[v] = scored[:BEAM_K]
    # variables and domains
    rel_vars = []
    for r in q["rels"]:
        for x in r[1:]:
            if isinstance(x, str) and x.startswith("?"):
                rel_vars.append(x[1:])
    allvars = list(dict.fromkeys(list(desc_vars) + rel_vars))
    theory_vars = {v for r in q["rels"] if r[0] == "theory" for v in [r[2][1:]] if r[2].startswith("?")}

    def domain(v):
        if v in beams:
            return [(sc, c) for sc, c in beams[v]]
        if v in theory_vars:
            return [(1.0, t) for t in THEORIES]
        return [(1.0, c) for c in claims]

    best = {}  # answer binding -> best score
    order = sorted(allvars, key=lambda v: (v not in beams, v not in theory_vars))
    doms = [domain(v) for v in order]

    def rels_ok(assign):
        for r in q["rels"]:
            args = []
            ok = True
            for x in r[1:]:
                if isinstance(x, str) and x.startswith("?"):
                    if x[1:] not in assign:
                        ok = False; break
                    args.append(assign[x[1:]])
                else:
                    args.append(x)
            if not ok:
                continue
            if M.Atom(r[0], tuple(args)) not in e.facts:
                return False
        return True

    ans_var = q["answer"][1:]
    for combo in product(*doms):
        assign = {v: c for v, (_sc, c) in zip(order, combo)}
        if not rels_ok(assign):
            continue
        dsc = [sc for v, (sc, _c) in zip(order, combo) if v in beams]
        score = 1.0
        if dsc:
            score = min(dsc) if tnorm == "min" else _prod(dsc)
        a = assign.get(ans_var)
        if a is not None and score > best.get(a, -1):
            best[a] = score
    return sorted(best.items(), key=lambda kv: -kv[1])


def _prod(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p


# ── run ──────────────────────────────────────────────────────────────────────
def main() -> int:
    e = build_store()
    idx = e._index()
    stmts = claim_statements()
    claims = sorted(stmts)
    Q = queries()

    # embed claim statements (AB2-a) + descriptor texts, keyed stably
    desc_texts, desc_keys = [], []
    for q in Q:
        for d in q["descs"]:
            desc_keys.append(q["id"] + d["var"][1:]); desc_texts.append(d["text"])
    cvecs = embed([stmts[c] for c in claims])
    dvecs = embed(desc_texts)
    vecs_claim = {c: v for c, v in zip(claims, cvecs)}
    vecs_desc = {k: v for k, v in zip(desc_keys, dvecs)}

    rows, per_query = [], []
    hits = {"min": {"p1": 0, "p5": 0}, "product": {"p1": 0, "p5": 0}}
    n_nonempty = 0
    empty_fp = {"min": 0, "product": 0}
    n_empty = 0
    for q in Q:
        truth = symbolic(q, e, idx)
        rec = {"id": q["id"], "nl": q["nl"], "tag": q["tag"], "n_symbolic": len(truth),
               "symbolic": sorted(map(str, truth))[:12], "soft": {}}
        is_empty = (len(truth) == 0)
        if is_empty:
            n_empty += 1
        else:
            n_nonempty += 1
        for tn in ("min", "product"):
            ranked = soft(q, e, idx, claims, vecs_claim, vecs_desc, tn)
            top = [str(a) for a, _s in ranked[:5]]
            top1_score = ranked[0][1] if ranked else 0.0
            rec["soft"][tn] = {"top5": top, "top1_score": round(float(top1_score), 3)}
            if is_empty:
                if top1_score >= TAU:
                    empty_fp[tn] += 1
            else:
                if top and top[0] in {str(x) for x in truth}:
                    hits[tn]["p1"] += 1
                if set(top) & {str(x) for x in truth}:
                    hits[tn]["p5"] += 1
        rows.append({"id": q["id"], "nl": q["nl"], "tag": q["tag"], "answer_kind": q["answer_kind"],
                     "n_symbolic_answers": len(truth), "decision": ""})
        per_query.append(rec)

    metrics = {"n_queries": len(Q), "n_nonempty": n_nonempty, "n_empty": n_empty, "tau": TAU, "beam_k": BEAM_K,
               "p_at_1": {tn: round(hits[tn]["p1"] / n_nonempty, 3) for tn in hits},
               "p_at_5": {tn: round(hits[tn]["p5"] / n_nonempty, 3) for tn in hits},
               "empty_query_fpr": {tn: round(empty_fp[tn] / n_empty, 3) if n_empty else None for tn in empty_fp}}
    OUT.mkdir(exist_ok=True)
    (OUT / "ab5_preliminary.json").write_text(json.dumps({"metrics": metrics, "queries": per_query},
                                                         ensure_ascii=False, indent=2) + "\n")

    # ── query packet (AWAITING-ANU) ──
    REV.mkdir(exist_ok=True)
    with open(REV / "ab5_queries.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "nl", "tag", "answer_kind", "n_symbolic_answers", "decision"])
        w.writeheader(); w.writerows(rows)
    (REV / "ab5_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["approve", "reject", "edit"]},
         "edit": {"format": "edit: <revised natural-language query>"}}, indent=2))
    (REV / "ab5_queries.md").write_text(
        f"""# AB5 compositional-query set — review  [AWAITING-ANU]

Role: **approver by reading** (query-set approval, not domain judgment). {len(Q)} template-authored
conjunctive 2–3-hop queries over the claim store. For each set `decision` ∈ {{approve, reject, edit}}.
`edit: <text>` to reword a query; `reject` to drop one. The `tag` is the query family
(content / structural / mixed / empty-calibration — `empty` rows have an intentionally empty symbolic
answer set, kept to measure soft-method calibration). `n_symbolic_answers` is the exact Datalog answer
count (0 for empty-calibration by design). Companion schema: review/ab5_schema.json.

{len(rows)} queries → review/ab5_queries.csv
After approval: bench/ab5_finalize.py recomputes + registers ab5.p_at_1 / ab5.p_at_5 / ab5.empty_query_fpr.
""")
    print(f"[AB5] queries={len(Q)} (nonempty {n_nonempty}, empty-calibration {n_empty})")
    print(f"[AB5] PRELIMINARY p@1 {metrics['p_at_1']} | p@5 {metrics['p_at_5']} | "
          f"empty_query_fpr {metrics['empty_query_fpr']} (τ={TAU}, beam k={BEAM_K})")
    print("AWAITING-ANU: review/ab5_queries.csv  (then: bench/ab5_finalize.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
