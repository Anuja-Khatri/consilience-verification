"""tests/test_finalize_ab5_b5.py — AB5 + B5 finalize after returned packets (SPEC §AB5/§B5.2). $0."""
import json
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent


def _reg():
    return {m["metric_id"]: m["value"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}


def test_ab5_final():
    d = json.loads((SPRINT / "results" / "ab5_final.json").read_text())
    assert sorted(d["rejected"]) == ["e01", "e02", "e05"]
    assert d["n_approved"] == 23 and d["n_nonempty"] == 20 and d["n_empty"] == 3
    assert d["p_at_1"]["min"] == 0.95
    assert d["empty_query_fpr"]["min"] == round(2 / 3, 4)           # 2/3 over e03/e04/e06
    assert d["empty_query_fpr_preliminary_6q"]["min"] == 0.833      # old reported alongside
    assert _reg()["ab5.p_at_1"] == 0.95


def test_b5_catchability():
    d = json.loads((SPRINT / "runs" / "B5" / "B5-2" / "catchability.json").read_text())
    assert d["n_sample"] == 20 and d["caught_y"] == 8 and d["gate_catchability"] == 0.4
    # owner hypothesis: uncaught obedience is largely coincidental correct typing
    assert d["obedient_correct_typing"] == d["of_which_caught"] + d["of_which_uncaught"]
    m = _reg()
    assert m["b5.gate_catchability"] == 0.4
    assert "b5.obedient_correct_typing_rate" in m
