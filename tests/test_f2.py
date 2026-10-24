import sys, json
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import f2_unification as F  # noqa


def test_f2_ranks_and_mo3_deterministic():
    # re-run load + a couple invariants (deterministic, frozen-store)
    claims, ebt, corrs, forks = F.load()
    node = [c for c in corrs if c.get("kind") == "node"]
    assert len(node) == 216  # 221 - 5 smc
    top = json.loads((SPRINT / "results" / "f2_top10.json").read_text())
    assert top["n_ranked"] == 216 and len(top["top10"]) == 10
    assert top["top10"][0]["u"] >= top["top10"][-1]["u"]  # sorted desc
