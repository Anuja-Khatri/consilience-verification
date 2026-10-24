import sys, json, glob, os
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import fol, judge_program as JP  # noqa
import yaml
CFG = yaml.safe_load((SPRINT/"pipeline"/"config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))

def test_vj2_congruence_iitxgnwt():
    import p5_judge as P5
    A = json.loads((ENGINE/"data/graphs/iit.json").read_text())
    B = json.loads((ENGINE/"data/graphs/gnwt.json").read_text())
    prims = fol.primitives(A, B)
    J = json.loads((ENGINE/"results/iitxgnwt_judge.json").read_text())
    checked = 0
    for c in J["correspondences"]:
        if c.get("kind") == "shared_measurement_space": continue
        vals = prims.get((c["left_ids"][0], c["right_ids"][0]))
        if vals is None: continue
        ent, _ = fol.entailed(c["grade"], vals); assert ent; checked += 1
    for f in J["forks"]:
        vals = prims.get((f["left_ids"][0], f["right_ids"][0]))
        if vals is None: continue
        ent, _ = fol.entailed("fork", vals); assert ent; checked += 1
    assert checked > 20
