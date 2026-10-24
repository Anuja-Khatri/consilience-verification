"""tests/test_td.py — TD1/TD1b/TD2 extraction-to-packet artifacts (SPEC §TD1/§TD1b/§TD2). $0."""
import csv
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent


def _claims(task, runid):
    return json.loads((SPRINT / "runs" / task / runid / "claims.json").read_text())


def test_td_packets_and_claims():
    for task, runid, key, n in (("TD1", "TD1-1", "td1", 24), ("TD1B", "TD1b-1", "td1b", 27),
                                ("TD2", "TD2-1", "td2", 19)):
        d = _claims(task, runid)
        assert len(d["claims"]) == n, (key, len(d["claims"]))
        rows = list(csv.DictReader(open(SPRINT / "review" / f"{key}_claims.csv")))
        assert len(rows) == n
        assert all(r["decision"] in ("approve", "reject") for r in rows)   # packet RETURNED
        assert all(r["type"] and r["polarity"] in ("asserts", "denies") for r in rows)
    # returned approve counts (owner decisions)
    appr = lambda k: sum(1 for r in csv.DictReader(open(SPRINT / "review" / f"{k}_claims.csv")) if r["decision"] == "approve")
    assert appr("td1") == 11 and appr("td1b") == 21 and appr("td2") == 11


def test_td1b_untypeable_registered_and_diffable():
    m = {x["metric_id"]: x["value"] for x in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    for doc in ("cai", "pcbp", "mbrl"):
        k = f"td1b.untypeable_rate_{doc}"
        assert k in m, k
        assert m[k] <= 0.60   # all three sources diffable (none >0.60 → undiffable)


def test_td_corpus_tags():
    assert _claims("TD1", "TD1-1")["corpus_tag"] == "v2"
    assert _claims("TD1B", "TD1b-1")["corpus_tag"] == "v2b"
    assert _claims("TD2", "TD2-1")["corpus_tag"] == "v2c"
