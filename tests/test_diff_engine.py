"""KR0 — keys/diff_engine.py semantics (SPEC §KR0). Synthetic fixtures lock
RECOVERED / PARTIAL / MISSED / BEYOND-KEY + the caveats and corpus-overlap guard.
KR1's 2/1/0/6 is validated separately by the import assert in keys/kr1_import.py."""
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "keys"))
import diff_engine as DE  # noqa: E402

ENGINE_ITEMS = [
    {"axis": "locus", "left_value": "posterior_hot_zone", "right_value": "prefrontal_cortex"},
    {"axis": "temporal_profile", "left_value": "sustained", "right_value": "early_onset"},
    {"axis": "substrate_dependence", "left_value": "substrate_dependent", "right_value": "grounded"},
    {"axis": "observable_commitment", "left_value": "ignition_signature", "right_value": "phi_metric"},
]
KEY_ROWS = [
    {"row_id": "P1", "axis": "locus", "expected": {"value_family": ["posterior", "prefrontal"]}},
    {"row_id": "P2", "axis": "temporal_profile", "expected": {"value_family": "offset_component"}},
    {"row_id": "P3", "axis": "connectivity", "expected": {"value_family": "integrated"}},
]


def test_diff_counts():
    out = DE.diff(KEY_ROWS, ENGINE_ITEMS, caveat="KEY CAVEAT")
    c = out["counts"]
    assert c["recovered"] == 1   # P1 locus: posterior/prefrontal family present
    assert c["partial"] == 1     # P2 temporal_profile: axis present, family 'offset' absent
    assert c["missed"] == 1      # P3 connectivity: no engine item on axis
    assert c["beyond"] == 2      # substrate_dependence + observable_commitment (not key axes)


def test_caveats_auto_appended():
    out = DE.diff(KEY_ROWS, ENGINE_ITEMS, caveat="KEY CAVEAT")
    assert out["caveats"][0] == "KEY CAVEAT"
    assert DE.TRAINING_DATA_CAVEAT in out["caveats"]


def test_row_status_detail():
    rows = {r["row_id"]: r for r in [DE.classify_row(r, ENGINE_ITEMS) for r in KEY_ROWS]}
    assert rows["P1"]["status"] == "RECOVERED"
    assert rows["P2"]["status"] == "PARTIAL"
    assert rows["P3"]["status"] == "MISSED"


def test_corpus_overlap_guard():
    assert DE.corpus_overlap_ok(["10.1234/elife.xyz"], ["no doi here", "other text"]) is True
    assert DE.corpus_overlap_ok(["10.1234/elife.xyz"], ["cites 10.1234/elife.xyz inline"]) is False
