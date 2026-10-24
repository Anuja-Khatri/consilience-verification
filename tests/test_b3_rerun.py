"""tests/test_b3_rerun.py — B3-2 full-coverage rerun + B2 hand-check (SPEC §B3/§B2). $0 (artifacts)."""
import json
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent


def _reg():
    return {m["metric_id"]: m for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}


def test_b3_rerun_full_coverage():
    d = json.loads((SPRINT / "results" / "b3_rerun.json").read_text())
    assert d["model"] == "gemini-3.1-pro-preview"
    assert d["model_versions"] == ["gemini-3.1-pro-preview"]      # resolved model_version recorded
    assert d["typing_coverage"] == "95/95" and d["grade_coverage"] == "60/60"
    assert d["gemini_got"] == d["gemini_tried"] and d["gemini_got"] > 0   # no billing/quota failures
    m = _reg()
    assert m["b3.gemini_coverage"]["value"] == 1.0                # full coverage (was ~0.084 flash)
    b32 = m["b3.panel_axis_kappa"]
    assert b32["runid"] == "B3-2" and "gemini-3.1-pro-preview" in " ".join(b32["caveats"])


def test_b2_handcheck_metric():
    m = _reg()
    assert m["b2.handcheck_agreement"]["value"] == 0.893
    cav = " ".join(m["b2.handcheck_agreement"]["caveats"])
    assert "25/28" in cav and "SINGLE-REVIEWER" in cav and "NOT changed on 3 sampled rows" in cav
