"""VJ1 — minidatalog evaluator + fact materialisation tests (SPEC §VJ1.1)."""
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
import minidatalog as M  # noqa: E402
import facts as F  # noqa: E402


def test_transitive_closure_and_provenance():
    e = M.Engine()
    for a, b in [("a", "b"), ("b", "c"), ("c", "d")]:
        e.add_fact("edge", a, b)
    X, Y, Z = M.Var("X"), M.Var("Y"), M.Var("Z")
    e.add_rule(M.Rule(M.Atom("path", (X, Y)), [M.Atom("edge", (X, Y))], rule_id="base"))
    e.add_rule(M.Rule(M.Atom("path", (X, Z)), [M.Atom("edge", (X, Y)), M.Atom("path", (Y, Z))], rule_id="rec"))
    e.run()
    paths = {f.args for f in e.query("path", M.Var("A"), M.Var("B"))}
    assert ("a", "d") in paths and ("a", "c") in paths
    # provenance tree for a transitively-derived fact
    tree = e.explain(M.Atom("path", ("a", "d")))
    assert tree["rule_id"] in ("rec", "base")
    assert tree["premises"]  # derived, has premises


def test_stratified_negation():
    e = M.Engine()
    e.add_fact("node", "x"); e.add_fact("node", "y"); e.add_fact("red", "x")
    X = M.Var("X")
    e.add_rule(M.Rule(M.Atom("notred", (X,)), [M.Atom("node", (X,))], neg=[M.Atom("red", (X,))], rule_id="n"))
    e.run()
    notred = {f.args for f in e.query("notred", M.Var("A"))}
    assert ("y",) in notred and ("x",) not in notred


def test_vj1_1_fact_counts():
    b = F.build_facts()
    assert b["n_claims"] == 95
    assert b["edge_counts"] == {"grounds": 84, "entails": 21, "constrains": 15, "predicts_observable": 32}
    # family/2 materialised for every distinct value
    fam_vals = {a[0] for p, a in b["facts"] if p == "family"}
    assert fam_vals.issubset(set(b["family_table"].keys()))
    assert len(b["family_table_sha256"]) == 64
