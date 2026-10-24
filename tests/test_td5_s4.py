"""tests/test_td5_s4.py — TD5 S4 key-recovery null (SPEC §TD5.2 S4). $0, pure compute."""
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))

import td5_s4 as S4  # noqa: E402


def test_real_recovery_rebuilds():
    forks, key_rows, real, iit_vals, gnwt_vals = S4.real_forks_and_recovery()
    assert len(key_rows) == 3                       # COGITATE has 3 predictions
    assert real["recovered"] == 2                   # matches kr.cogitate.recovered (v2)
    assert iit_vals and gnwt_vals                   # per-theory marginals non-empty


def test_artifact_and_metric():
    d = json.loads((SPRINT / "results" / "td5_s4_key_nulls.json").read_text())
    assert d["key"] == "cogitate" and d["n_null"] == 1000 and d["real_recovered"] == 2
    assert 0.0 <= d["empirical_p_recovered"] <= 1.0
    assert d["null_recovered_mean"] < 2            # real recovery beats the chance mean
    m = {x["metric_id"]: x for x in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert "r1.key_null_z_cogitate" in m
