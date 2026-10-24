"""tests/test_kr34.py — KR3 eLife + KR4 Buckley key builds (SPEC §KR3/§KR4). $0 (artifact checks)."""
import csv
import json
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent


def _reg():
    return {m["metric_id"]: m["value"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}


def test_kr3_elife_key_and_metrics():
    d = json.loads((SPRINT / "keys" / "elife_key.json").read_text())
    assert d["class"] == "public" and d["n_rows"] >= 8
    assert d["n_mappable"] + d["n_unmappable"] == d["n_rows"]
    assert all(r["axis"] in ("locus", "connectivity", "mechanism_scale", "observable_commitment", "unmappable")
               for r in d["rows"])
    m = _reg()
    for k in ("kr.elife.recovered", "kr.elife.partial", "kr.elife.missed", "kr.elife.beyond", "kr.elife.unmappable_rows"):
        assert k in m, k
    rows = list(csv.DictReader(open(SPRINT / "review" / "kr3_elife.csv")))
    assert rows and all(r["decision"] in ("valid", "invalid") for r in rows)   # format packet RETURNED
    assert sum(1 for r in rows if r["decision"] == "valid") == 14


def test_kr4_buckley_key_and_deferred_diff():
    d = json.loads((SPRINT / "keys" / "buckley_key.json").read_text())
    assert d["n_rows"] >= 4
    assert all(r["axis"] == "mechanism" for r in d["rows"])   # homologies typed as mechanism family
    m = _reg()
    assert "kr.buckley.rows_built" in m
    assert "kr.buckley.recovered" in m        # recovery diff now RUN (TD1b approved, corpus v2b)
    rows = list(csv.DictReader(open(SPRINT / "review" / "kr4_buckley.csv")))
    assert rows and all(r["decision"] in ("valid", "invalid") for r in rows)
    assert sum(1 for r in rows if r["decision"] == "valid") == 8
