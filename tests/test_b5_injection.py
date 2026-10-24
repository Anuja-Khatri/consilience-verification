"""tests/test_b5_injection.py — B5.2 injection battery artifact + Wilson helper (SPEC §B5.2). $0."""
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))

import b5_injection as B5  # noqa: E402


def test_wilson():
    lo, hi = B5.wilson(45, 50)
    assert lo is not None and 0 <= lo < hi <= 1
    assert B5.wilson(0, 0) == (None, None)


def test_battery_artifact_and_asymmetry():
    d = json.loads((SPRINT / "runs" / "B5" / "B5-2" / "injection_battery.json").read_text())
    assert d["n_passages"] == 30
    cls = d["classes"]
    assert set(cls) == {"direct", "indirect_quoted", "field_steering", "polite_contextual"}
    for c, v in cls.items():
        for k in ("obedience_rate", "clean_baseline", "delta", "ci", "target"):
            assert k in v, (c, k)
    # the measured asymmetry: polite-contextual polarity flip obeyed far more than the direct axis override
    assert cls["polite_contextual"]["obedience_rate"] > cls["direct"]["obedience_rate"]
    assert 0.0 <= d["overall"]["obedience_rate"] <= 1.0
