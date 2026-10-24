"""tests/test_a2_finalize.py — A2.4-2.6 comparison (SPEC §A2). $0."""
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))

import a2_finalize as A2F  # noqa: E402


def test_classify_logic():
    assert A2F.classify("partial", "generative", False)[0] == "downgraded"
    assert A2F.classify("generative", "generative", False)[0] == "agrees"
    assert A2F.classify("generative", "partial", False)[0] == "upgraded"
    assert A2F.classify("partial", "none", False)[0] == "flipped-to-none"
    assert A2F.classify(None, "none", False)[0] == "no-baseline"      # no tier → not a flip
    assert A2F.classify(None, "generative", False)[0] == "no-baseline"
    assert A2F.classify("partial", "generative", True)[0] == "untypeable"


def test_comparison_artifact():
    d = json.loads((SPRINT / "results" / "a2_comparison.json").read_text())
    assert d["n_pairs"] == 17
    assert d["approved_claims"] == 96 and d["rejected_claims"] == 13
    assert 0.0 <= d["agreement_rate"] <= 1.0 and 0.0 <= d["downgrade_rate"] <= 1.0
    # every row has a delta in the allowed set
    allowed = {"agrees", "downgraded", "upgraded", "flipped-to-none", "untypeable", "no-baseline"}
    assert all(r["delta"] in allowed for r in d["rows"])
    m = {x["metric_id"] for x in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    for k in ("a2.agreement_rate", "a2.downgrade_rate", "a2.survivor_vs_failure_separation", "a2.untypeable_pairs"):
        assert k in m
