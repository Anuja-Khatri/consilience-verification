"""W0.6 — registry schema + numbers-lock (v2.0.2 frozen-store) tests."""
import json
import sys
from pathlib import Path

import jsonschema
import pytest

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
import validate_registry as VR  # noqa: E402

SCHEMA = json.loads((SPRINT / "results" / "registry.schema.json").read_text())


def _metric(**kw):
    base = dict(metric_id="t.x", value=0.5, ci_lo=None, ci_hi=None, n=None,
                task="T", runid="T-1", instrument_tag="v2", corpus_tag="v2",
                preregistered=True, pilot=False, caveats=[])
    base.update(kw)
    return base


# --- schema ------------------------------------------------------------- #
def test_schema_accepts_valid_metric():
    jsonschema.validate({"schema_version": "1.0", "numbers_lock": None,
                         "metrics": [_metric()]}, SCHEMA)


def test_schema_rejects_bad_instrument_tag():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"schema_version": "1.0", "metrics": [_metric(instrument_tag="v3")]},
                            SCHEMA)


def test_schema_rejects_missing_required_field():
    bad = _metric()
    del bad["caveats"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"schema_version": "1.0", "metrics": [bad]}, SCHEMA)


# --- v2.0.2 frozen-store rule (pure predicate) -------------------------- #
def test_frozen_store_predicate():
    assert VR.extraction_in_inputs({"inputs": [{"kind": "extraction", "path": "x"}]}) is True
    assert VR.extraction_in_inputs({"inputs": [{"kind": "frozen", "path": "runs/x/extract_lite.json"}]}) is True
    assert VR.extraction_in_inputs({"inputs": ["runs/KR1/KR1-2/v2_claims.json"]}) is True  # fresh extraction
    # the FROZEN approved store is NOT an extraction output (D-026)
    assert VR.extraction_in_inputs({"inputs": ["data/claims/iit_approved.jsonl"]}) is False
    assert VR.extraction_in_inputs({"inputs": [{"kind": "frozen", "path": "data/graphs/iit.json"}]}) is False
    assert VR.extraction_in_inputs({"inputs": []}) is False


def test_validate_rejects_frozen_store_with_extraction_input(tmp_path, monkeypatch):
    # craft a registry + a run manifest with an extraction input, redirect module paths
    reg = {"schema_version": "1.0", "numbers_lock": None,
           "metrics": [_metric(metric_id="ss1.synergy", task="SS1", runid="SS1-1",
                               instrument_tag="frozen-store", corpus_tag="v1")]}
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(reg))
    man = tmp_path / "runs" / "SS1" / "SS1-1" / "manifest.json"
    man.parent.mkdir(parents=True)
    man.write_text(json.dumps({"inputs": [{"kind": "extraction", "path": "runs/SS1/extract.json"}]}))
    monkeypatch.setattr(VR, "SPRINT", tmp_path)
    monkeypatch.setattr(VR, "SCHEMA", SPRINT / "results" / "registry.schema.json")
    assert VR.validate(reg_path) == 1   # frozen-store illegal with extraction input


def test_validate_allows_frozen_store_without_extraction(tmp_path, monkeypatch):
    reg = {"schema_version": "1.0", "numbers_lock": None,
           "metrics": [_metric(metric_id="f2.top10", task="F2", runid="F2-1",
                               instrument_tag="frozen-store", corpus_tag="v1")]}
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(reg))
    # no manifest at all -> no extraction input -> allowed
    monkeypatch.setattr(VR, "SPRINT", tmp_path)
    monkeypatch.setattr(VR, "SCHEMA", SPRINT / "results" / "registry.schema.json")
    assert VR.validate(reg_path) == 0
