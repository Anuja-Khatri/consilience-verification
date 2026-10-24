"""tests/test_td4_run.py — TD4 protocol-game run (SPEC §TD4 = G2). $0 (artifact + obfuscator checks)."""
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "logic"))
import td4_run as T  # noqa: E402


def test_maps_firewall_distinct_and_clean():
    # map-A and map-B targets disjoint (firewall), word-boundary + dash-norm substitution works
    assert not (set(T.OBF_A.targets) & set(T.OBF_B.targets))
    assert T.OBF_A.apply("IIT") != T.OBF_B.apply("IIT")
    assert T.OBF_A.remaining_sources(T.OBF_A.apply("the Global Neuronal Workspace (GNW) and PSC and MICS")) == []


def test_game_artifact_and_metrics():
    d = json.loads((SPRINT / "runs" / "TD4" / "TD4-1" / "game.json").read_text())
    for arm in ("free", "typed"):
        a = d["agg"][arm]
        assert a["n"] == 30 and 0.0 <= a["task_acc"] <= 1.0 and a["turns_mean"] <= 6.0
    assert "identity NOT guaranteed hidden" in d["firewall_verdict"] or "firewall holds" in d["firewall_verdict"]
    m = {x["metric_id"]: x["value"] for x in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    for k in ("g2.task_acc_free", "g2.task_acc_typed", "g2.turns_mean_free", "g2.tokens_mean_typed",
              "g2.firewall_leaks", "g2.value_field_leak_rate", "g2.deobf_leaks"):
        assert k in m, k
