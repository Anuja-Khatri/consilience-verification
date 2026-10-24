import sys, json
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import ss1_pid as S  # noqa


def test_ss1_enumeration_and_candidacy():
    rows = S.enumerate_rows()
    axis_matched = [r for r in rows if r[0] == 1]
    assert len(axis_matched) == 311          # candidacy pairs = VJ2 verdict count
    R = {m["metric_id"] for m in json.loads((SPRINT/"results"/"registry.json").read_text())["metrics"]}
    assert {"ss1.synergy_share_imin", "ss1.max_unique_imin", "ss1.constant_sources"} <= R
