import json
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent


def test_b4_probe_items():
    items = [json.loads(l) for l in (SPRINT / "probe_set" / "items.jsonl").read_text().splitlines() if l.strip()]
    assert 160 <= len(items) <= 220
    cells = {it["cell"] for it in items}
    assert {"true_correspondence", "equivocation", "negation"} <= cells
    for it in items:
        assert it["gold"] in ("correspond", "not_correspond")
        assert it["gold_basis"] in ("judge-after-audit", "miu-rejection-record", "constructed")
    assert (SPRINT / "probe_set" / "SHA256SUMS").exists()


def test_b4_metrics_present():
    R = {m["metric_id"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert {"b4.mpnet_acc_true_correspondence", "b4.judge_acc_true_correspondence",
            "b4.dissociation_mpnet", "b4.low_discrimination_count"} <= R
