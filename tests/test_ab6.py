"""tests/test_ab6.py — AB6 subsample determinism + accuracy helper (SPEC §AB6). $0; no live calls."""
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "bench"))
sys.path.insert(0, str(SPRINT / "pipeline"))

import ab6_abstraction as AB6  # noqa: E402


def _items():
    d = json.loads((SPRINT / "bench" / "items.json").read_text())
    return d if isinstance(d, list) else d["items"]


def test_subsample_deterministic_and_keeps_positives():
    items = _items()
    s1 = AB6.subsample(items)
    s2 = AB6.subsample(items)
    assert [x["item_id"] for x in s1] == [x["item_id"] for x in s2]   # seeded, deterministic
    assert len(s1) == AB6.N_SUB
    n_pos_total = sum(1 for it in items if it["reference"] == "positive")
    n_pos_sub = sum(1 for it in s1 if it["reference"] == "positive")
    assert n_pos_sub == n_pos_total   # all positives retained (scarce class)


def test_accuracy_helper():
    toy = [{"reference": "positive"}, {"reference": "negative"}, {"reference": "negative"}]
    acc, n = AB6.accuracy([True, False, True], toy)   # 2/3 correct
    assert n == 3 and abs(acc - 2 / 3) < 1e-9
    acc2, n2 = AB6.accuracy([True, None, False], toy)  # malformed skipped → 2/2
    assert n2 == 2 and acc2 == 1.0
