"""W0.4 — judge/decidability port validation (SPEC §1 W0.4).

(1) byte-hash-assert: the copied p5/p6/p6b + axes/entity_types vocab are byte-identical
    to results/engine_fingerprint.json (import ONLY from the copy).
(2) fixture: re-judge the 221 persisted correspondences from stored inputs via the COPY;
    the re-judged correspondences must equal the stored outputs EXACTLY (determinism +
    port correctness in one test). port_validated: reproduced-stored-correspondences.
(3) decidability + split_sentences smoke on the copy.
"""
import glob
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

SPRINT = Path(__file__).resolve().parent.parent
EC = SPRINT / "pipeline" / "engine_copy"
sys.path.insert(0, str(EC / "pipeline"))   # import ONLY from the copy

import p5_judge          # noqa: E402  (engine_copy/pipeline/p5_judge.py)
import p6_decidability   # noqa: E402
import split_sentences as ss  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
FP = json.loads((SPRINT / "results" / "engine_fingerprint.json").read_text())["files"]


def _sha(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


# --- (1) byte-hash-assert vs fingerprint --------------------------------- #
@pytest.mark.parametrize("label,relpath", [
    ("p5_judge.py", "pipeline/p5_judge.py"),
    ("p6_decidability.py", "pipeline/p6_decidability.py"),
    ("p6b_evidence.py", "pipeline/p6b_evidence.py"),
    ("axes.yaml", "vocab/axes.yaml"),
    ("entity_types.yaml", "vocab/entity_types.yaml"),
])
def test_engine_copy_byte_identical(label, relpath):
    assert _sha(EC / relpath) == FP[label], f"{relpath} drifted from engine fingerprint"


def test_import_is_from_copy_not_engine():
    assert str(EC) in p5_judge.__file__
    assert str(ENGINE) not in p5_judge.__file__


# --- (2) fixture: re-judge the 221 from stored inputs -------------------- #
def test_rejudge_reproduces_221_correspondences():
    judge_files = sorted(glob.glob(str(ENGINE / "results" / "*_judge.json")))
    assert len(judge_files) == 13, "expected 13 persisted pairs"
    total = 0
    mismatches = []
    for jf in judge_files:
        J = json.loads(Path(jf).read_text())
        ga = {"theory": J["left"]["theory"], "nodes": J["left"]["nodes"],
              "edges": J["left"]["edges"]}
        gb = {"theory": J["right"]["theory"], "nodes": J["right"]["nodes"],
              "edges": J["right"]["edges"]}
        out = p5_judge.judge_pair(ga, gb)
        total += len(out["correspondences"])
        stored = json.dumps(J["correspondences"], sort_keys=True, ensure_ascii=False)
        rejud = json.dumps(out["correspondences"], sort_keys=True, ensure_ascii=False)
        if stored != rejud:
            mismatches.append(os.path.basename(jf))
    assert total == 221, f"re-judged correspondence total {total} != 221"
    assert mismatches == [], f"correspondence mismatch in: {mismatches}"


# --- (3) decidability + split_sentences smoke ---------------------------- #
def test_decidability_smoke():
    tables = p6_decidability.load_tables()
    v = p6_decidability.decide("locus", "IIT", "GNWT", tables)
    assert v["decidability"] in {"now", "bridge", "not_current"}
    assert "fork_ref" in v and v["fork_ref"] == "IITxGNWT:locus"


def test_split_sentences():
    out = ss.split_sentences("First sentence here. Second one follows! A third? Yes.")
    assert len(out) >= 3
    assert ss.split_sentences("") == []
