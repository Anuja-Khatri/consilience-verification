import sys, json
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
import integrity as IG  # noqa
import proofs as PR  # noqa


def test_vj4_zero_violations():
    V, counts = IG.check()
    assert V == [], V
    assert counts["claims"] == 95 and counts["corrs"] == 221


def test_vj3_provenance_trees_present():
    jl = SPRINT / "logic" / "proofs" / "provenance.jsonl"
    assert jl.exists()
    lines = [json.loads(l) for l in jl.read_text().splitlines()]
    derived = [d for d in lines if d["verdict"] in ("fork", "corr")]
    assert derived and all(d["tree"]["rule_id"] for d in derived)  # every rule-verdict has a tree
