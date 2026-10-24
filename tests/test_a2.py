"""tests/test_a2.py — A2 slicing + extract_lite validation (SPEC §A2). All $0 (no live calls)."""
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))

import a2_adjudicate as A2  # noqa: E402


def test_window_blocks_and_clamp():
    page = ("===== PAGE 1 ===== Alpha boilerplate here. "
            "===== PAGE 2 ===== One leading sentence. The target claim sits here plainly. "
            "A following sentence. Yet another one. And a fifth.")
    blocks = A2._page_blocks(page)
    assert len(blocks) == 2
    block = A2._best_block(blocks, "the target claim sits here plainly")
    text, ratio = A2._window(block, "the target claim sits here plainly")
    assert "target claim sits here plainly" in text.lower()
    assert ratio >= 0.85                       # sentence-level locate signal
    assert 2 <= len([s for s in text.split(".") if s.strip()]) <= 6


def test_passages_artifact_well_anchored():
    """The frozen A2.1 output: 17 pairs / 34 sides, every side re-located, passage_id format."""
    d = json.loads((SPRINT / "results" / "a2_passages.json").read_text())
    assert d["n_pairs"] == 17
    sides = [(pr["match_id"], side, s) for pr in d["pairs"] for side, s in pr["sides"].items()]
    assert len(sides) == 34
    for mid, side, s in sides:
        assert s.get("passages"), f"{mid}:{side} had no passage"
        assert s["located"] is True
        assert s["passages"][0]["passage_id"] == f"mius_{mid}_{side}_1"


class _StubRec(dict):
    pass


class _StubClient:
    """Returns a fixed JSON block; records that extract_lite passed the v2 system through."""
    def __init__(self, text):
        self.text = text
        self.systems = []

    def call(self, *, system, **kw):
        self.systems.append(system)
        return {"text": self.text}


def test_extract_lite_validation():
    passages = [{"passage_id": "p1", "text": "A field grounds the global workspace broadcast."}]
    block = json.dumps([
        {"statement": "valid cited claim", "entity_type": "field", "axis": "not_an_axis",
         "value": "x", "polarity": "asserts", "passage_ids": ["p1"]},            # axis coerced → none
        {"statement": "uncited claim", "entity_type": "field", "axis": "locus",
         "value": "y", "polarity": "asserts", "passage_ids": ["pX"]},            # citation not provided → dropped
    ])
    client = _StubClient(block)
    out = A2.__dict__  # ensure module import side-effects present
    from extract_lite import extract_lite
    claims = extract_lite(passages, theory="physics", slug="mius_test_a", client=client,
                          replicate_tag="a2", task_id="A2")
    assert len(claims) == 1                                   # uncited one dropped (citation required)
    assert claims[0]["axis"] == "none"                        # coerced-to-none (closed axis list)
    assert claims[0]["claim_id"] == "mius_test_a_c001"
    assert client.systems and "DEFINITION" in client.systems[0].upper()  # v2 definitions block present
