import sys, json
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import ss2_oinformation as S  # noqa


def test_o_info_deterministic_and_signed():
    cl = S.claims()
    assert len(cl) == 95
    corpus = [(c["entity_type"], c["axis"], c["family"]) for c in cl]
    oi1 = S.o_info(corpus); oi2 = S.o_info(corpus)
    assert oi1 == oi2 and oi1 is not None          # deterministic
    # polarity is single-class across the corpus (the excluded-var finding)
    assert len({c["polarity"] for c in cl}) == 1


def test_ss2_registry_metrics_present():
    R = {m["metric_id"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert {"ss2.o_info_corpus", "ss2.null_z_corpus", "ss2.o_info_crosstheory", "ss2.excluded_vars"} <= R
