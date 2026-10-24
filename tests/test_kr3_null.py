"""tests/test_kr3_null.py — KR3 eLife key-recovery null (playbook §4; honest negative). $0."""
import json
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent

def test_kr3_null_registered_and_below_chance():
    M = {m["metric_id"]: m["value"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert "r1.key_null_p_elife" in M and "r1.key_null_z_elife" in M
    assert M["r1.key_null_p_elife"] > 0.5            # recovery does NOT beat chance (honest negative)
    d = json.loads((SPRINT / "results" / "kr3_key_nulls.json").read_text())
    assert d["real_recovered"] == 0 and d["real_recovered_plus_partial"] == 6
    assert d["null_rp_mean"] > d["real_recovered_plus_partial"]   # random keys recover MORE

def test_p1_reports_kr3_chance_rate():
    p1 = (SPRINT / "paper" / "P1.md").read_text()
    assert "at/below chance" in p1 and "no chance rate computed" not in p1
