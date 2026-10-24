"""tests/test_td_kr_finalize.py — TD1/TD1b/TD2 reruns + KR3/KR4 finalize (SPEC §TD/§KR3/§KR4). $0."""
import json
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent


def _reg():
    return {m["metric_id"]: m["value"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}


def test_td_finalize_metrics():
    m = _reg()
    assert m["td1.new_claims"] == 11
    assert m["td1b.new_claims"] == 21
    assert m["td2.within_family_corrs"] == 19 and m["td2.within_family_forks"] == 7
    ml = json.loads((SPRINT / "corpora" / "td1b" / "claims.json").read_text())
    assert ml["n"] == 21 and ml["corpus_tag"] == "v2b"


def test_kr3_final():
    d = json.loads((SPRINT / "keys" / "elife_key_final.json").read_text())
    assert sorted(d["dropped"]) == ["elife_14", "elife_16"] and d["n_valid"] == 14
    assert d["counts"]["recovered"] + d["counts"]["partial"] + d["counts"]["missed"] == d["n_mappable"]
    assert _reg()["kr.elife.missed"] == d["counts"]["missed"]


def test_kr4_recovery_and_finding():
    d = json.loads((SPRINT / "keys" / "buckley_diff.json").read_text())
    assert sorted(d["dropped"]) == ["buckley_05", "buckley_07", "buckley_10", "buckley_12"]
    assert d["counts"]["RECOVERED"] + d["counts"]["PARTIAL"] + d["counts"]["MISSED"] + d["counts"]["UNDIFFABLE"] == 8
    # owner finding: no AIF↔MBRL among validated rows
    assert all("mbrl" not in r["frameworks"].lower() for r in d["rows"])
    m = _reg()
    assert m["kr.buckley.recovered"] == d["counts"]["RECOVERED"]
    assert m["kr.buckley.undiffable"] == d["counts"]["UNDIFFABLE"]
