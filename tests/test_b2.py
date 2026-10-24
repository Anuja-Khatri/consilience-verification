"""tests/test_b2.py — B2 perturbation suite (SPEC §B2, OSF-preregistered). $0 (artifact checks)."""
import json
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent


def _reg():
    return {m["metric_id"]: m for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}


def test_b2_passages_frozen_40():
    d = json.loads((SPRINT / "results" / "b2_passages.json").read_text())
    assert d["n"] == 40
    assert all(p["primary_axis"] in d["target_axes"] for p in d["passages"])


def test_b2_run_and_osf_doi():
    d = json.loads((SPRINT / "runs" / "B2" / "B2-1" / "b2_run.json").read_text())
    assert d["osf"]["doi"] == "10.17605/OSF.IO/5N24M"
    assert d["osf"]["url"] == "https://osf.io/5n24m"
    # identity polarity is the stable floor; negation flip is a genuinely lower rate
    assert d["identity_rates"]["polarity"] >= 0.9
    assert 0.0 <= d["negation_polarity_tracking"] <= 1.0
    m = _reg()
    for k in ("b2.negation_polarity_tracking", "b2.double_negation_restoration", "b2.verdict_tracking_correct",
              "b2.l1_register_formal_axis", "b2.selection_loss_negation"):
        assert k in m, k
    # OSF DOI cited in registry caveats
    assert any("10.17605/OSF.IO/5N24M" in " ".join(m[k]["caveats"]) for k in m if k.startswith("b2."))


def test_b2_identity_control_present():
    # every invariance L1 metric reports an identity-relative PASS flag in its caveat
    m = _reg()
    # invariance classes (NOT identity, which is the control itself) carry the identity-relative PASS flag
    inv = [k for k in m if k.startswith("b2.l1_") and k.endswith("_axis") and "_identity_" not in k]
    assert inv
    assert all("PASS(not-worse-than-identity)" in " ".join(m[k]["caveats"]) for k in inv)
