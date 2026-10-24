import json
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent


def test_ab0_frozen_items():
    d = json.loads((SPRINT / "bench" / "items.json").read_text())
    assert d["n"] >= 120 and d["bench_version"] == "v0.1"
    assert d["reference"] == "judge-after-audit"      # never "gold standard"
    assert len(d["items_sha256"]) == 64
    # every item has a reference label and typed fields both sides
    for it in d["items"]:
        assert it["reference"] in ("positive", "negative")
        assert "axis" in it["typed_a"] and "axis" in it["typed_b"]


def test_ab1_metrics_present():
    R = {m["metric_id"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert {"ab0.n_items", "ab1.auroc_tfidf", "ab1.auroc_jaccard", "ab.direction_errors_tfidf"} <= R


def test_ab2_metrics_present():
    import json
    R = {m["metric_id"]: m for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert {"ab2.auroc_mpnet", "ab2.auroc_typed", "ab2.auroc_judge"} <= set(R)
    assert R["ab2.auroc_judge"]["value"] == 1.0            # rung-6 ceiling (circular, documented)
    assert R["ab2.auroc_typed"]["value"] >= R["ab2.auroc_mpnet"]["value"]  # typed rendering lifts alignment


def test_ab3_pilot_negative_reported_honestly():
    import json
    R = {m["metric_id"]: m for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert {"ab3.top1_L0", "ab3.top1_L1", "ab3.top1_L2", "ab3.null_top1", "ab3.abstraction_monotonic"} <= set(R)
    # honest: anchored top1 at/below null -> hypothesis not supported
    assert R["ab3.abstraction_monotonic"]["value"] is False


def test_ab4_degeneracy_reported():
    import json
    R = {m["metric_id"]: m for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert {"ab4.top1_typed", "ab4.top1_embedding", "ab4.degenerate_cells", "ab4.restart_dispersion"} <= set(R)
    # honest degeneracy finding (string sentinel, not a faked number)
    assert R["ab4.top1_typed"]["value"] == "no-nondegenerate-alignment"
