"""VJ1 — logic program ≡ Python judge (SPEC §VJ1.3). Fast subset for CI."""
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import judge_program as JP  # noqa: E402
import equiv as EQ  # noqa: E402
import yaml, os  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))


def test_equiv_iitxgnwt():
    A = json.loads((ENGINE / "data/graphs/iit.json").read_text())
    B = json.loads((ENGINE / "data/graphs/gnwt.json").read_text())
    lp, gt = JP.run_pair(A, B), JP.judge_truth(A, B)
    assert lp["forks"] == gt["forks"]
    assert lp["corrs"] == gt["corrs"]


def test_equiv_all_persisted_pairs():
    for name, A, B in EQ.persisted_pairs():
        lp, gt = JP.run_pair(A, B), JP.judge_truth(A, B)
        assert lp["forks"] == gt["forks"], name
        assert lp["corrs"] == gt["corrs"], name


def test_equiv_synthetic_sample():
    for i in range(40):
        A, B = EQ.synthetic(i)
        lp, gt = JP.run_pair(A, B), JP.judge_truth(A, B)
        assert lp["forks"] == gt["forks"], f"synthetic {i} forks"
        assert lp["corrs"] == gt["corrs"], f"synthetic {i} corrs"
