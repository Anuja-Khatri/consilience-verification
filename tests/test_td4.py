"""tests/test_td4.py — TD4 setup artifacts (SPEC §TD4). $0; no game run (post-approval)."""
import csv
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))

import td4_setup as TD4  # noqa: E402


def test_map_b_no_collisions_no_overlap_with_map_a():
    rows, collisions, overlaps = TD4.build_map_b()
    assert collisions == [], collisions           # no target already in corpus (de-map must be unambiguous)
    assert overlaps == [], overlaps               # map-B targets must not equal any map-A target (firewall)
    assert len(rows) == 34


def test_items_well_formed():
    d = json.loads((SPRINT / "results" / "td4_items.json").read_text())
    items = d["items"]
    assert d["n"] == 30 and len(items) == 30
    for it in items:
        assert len(it["candidates"]) == 6, it["item_id"]
        if it["reference_match"] != "none":
            assert it["reference_match"] in it["candidates"], it["item_id"]
        # A and B are different theories
        assert it["a_theory"] != it["b_theory"]


def test_card_schema_fields():
    s = TD4.CARD_SCHEMA
    assert set(s["required"]) == {"entity_type", "axis", "polarity", "value_description", "question"}
    assert s["properties"]["value_description"]["maxWords"] == 12
    assert s["properties"]["polarity"]["enum"] == ["asserts", "denies"]
