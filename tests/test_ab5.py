"""tests/test_ab5.py — AB5 store + symbolic evaluator (SPEC §AB5). $0; no embeddings touched."""
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "bench"))
sys.path.insert(0, str(SPRINT / "logic"))

import ab5_queries as AB5  # noqa: E402


def _store():
    e = AB5.build_store()
    return e, e._index()


def test_store_has_vj1_relations():
    e, _ = _store()
    preds = {f.pred for f in e.facts}
    for p in ("claim", "theory", "axis", "polarity", "family", "grounds", "corr_any", "corresponds", "fork"):
        assert p in preds, f"missing predicate {p}"
    # symmetric corr/fork materialisation
    assert any(f.pred == "corr_any" for f in e.facts)


def _q(qid):
    return next(q for q in AB5.queries() if q["id"] == qid)


def test_symbolic_denies_computability():
    e, idx = _store()
    ans = AB5.symbolic(_q("q03"), e, idx)   # theories denying computability
    assert ans == {"IIT", "Orch-OR"}, ans


def test_symbolic_empty_calibration():
    e, idx = _store()
    assert AB5.symbolic(_q("e01"), e, idx) == set()   # no claim denies a locus
    assert AB5.symbolic(_q("e05"), e, idx) == set()   # none deny fundamentality


def test_symbolic_structural_nonempty():
    e, idx = _store()
    ans = AB5.symbolic(_q("q15"), e, idx)   # theories partial-corresponding to IIT
    assert ans and "IIT" not in ans         # cross-theory partners, not IIT itself
