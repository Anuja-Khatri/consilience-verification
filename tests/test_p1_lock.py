"""tests/test_p1_lock.py — NUMBERS_LOCK + P1 assembly (SPEC §0.8(iii)/§8). $0."""
import hashlib
import json
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent


def test_numbers_lock_consistent():
    lock = json.loads((SPRINT / "paper" / "NUMBERS_LOCK.json").read_text())
    reg = json.loads((SPRINT / "results" / "registry.json").read_text())
    # lock sha = sha256 of the canonical metrics array (stable regardless of the numbers_lock field)
    canon = json.dumps(sorted(reg["metrics"], key=lambda m: m["metric_id"]), sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False)
    assert lock["registry_sha256"] == hashlib.sha256(canon.encode()).hexdigest()
    assert lock["n_metrics"] == len(reg["metrics"])
    assert len(lock["preconditions_verified"]) == 13
    # registry stamped with the same lock
    assert reg["numbers_lock"]["registry_sha256"] == lock["registry_sha256"]


def test_p1_renders_locked_numbers():
    p1 = (SPRINT / "paper" / "P1.md").read_text()
    assert "NUMBERS LOCK" in p1 and json.loads((SPRINT / "paper" / "NUMBERS_LOCK.json").read_text())["registry_sha256"][:16] in p1
    # the negation headline value from the locked registry appears in the draft
    R = {m["metric_id"]: m["value"] for m in json.loads((SPRINT / "results" / "registry.json").read_text())["metrics"]}
    assert str(R["b2.negation_polarity_tracking"]) in p1   # negation headline
    assert str(R["vj1.equivalence_rate"]) in p1            # verified-judge equivalence
    assert str(R["a2.downgrade_rate"]) in p1               # A2 discovery
    assert str(R["r1.key_null_p_cogitate"]) in p1          # KR1 empirical chance rate (edit 2)
    assert (SPRINT / "review" / "p1_readthrough.md").exists()


def test_p1_readthrough_edits_applied():
    """The 10 read-through edits + the template check (no rate without n) — owner edit round."""
    import sys
    sys.path.insert(0, str(SPRINT / "pipeline"))
    import assemble_p1 as AP
    p1 = (SPRINT / "paper" / "P1.md").read_text()
    AP.template_check(p1)   # raises SystemExit on any rate-without-n or unfilled token → fails CI
    for needle in ("iit_c009 was initially rejected",                       # e1 verbatim disclosure
                   "no IIT temporal_profile claim was ever extracted",      # e1 P2 instrument
                   "does NOT reach α = 0.05",                               # e2 p governs
                   "92 asserts / 3 denies",                                 # e3 single-class polarity
                   "validated denominator of 14 carries 0 unmappable",      # e5 KR3 reconcile
                   "Decisions were model-drafted suggestions (Claude) reviewed and confirmed by Anu",  # e9
                   "no fork flagged by the scan"):                          # e9 A3/A4 caveat
        assert needle in p1, needle
