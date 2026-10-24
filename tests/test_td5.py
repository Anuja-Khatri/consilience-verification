import sys, json, random
from collections import Counter
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import td5_surrogates as T  # noqa


def test_real_count_and_shuffles():
    graphs, pairs = T.load()
    assert T.count_corrs(graphs, pairs) == 221          # real baseline
    rng = random.Random(1)
    s1 = T.shuffle_s1(graphs, rng)                      # marginal: axis multiset per theory preserved
    for th in graphs:
        assert Counter(n["axis"] for n in s1[th]) == Counter(n["axis"] for n in graphs[th])
    s3 = T.shuffle_s3(graphs, random.Random(1))         # theory-scramble preserves total claim count
    assert sum(len(v) for v in s3.values()) == sum(len(v) for v in graphs.values()) == 95


def test_td5_metrics_present():
    R = {m["metric_id"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert {"r1.null_z_corr_count_s1", "r1.null_z_corr_count_s2", "r1.null_z_corr_count_s3"} <= R
