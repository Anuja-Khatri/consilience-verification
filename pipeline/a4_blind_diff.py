#!/usr/bin/env python3
"""
pipeline/a4_blind_diff.py — A4 Leg 4 (SPEC §A4): the blind diff via KR2.

"The diff itself = KR2(f). This leg's output = results/a4_blind_diff.json + the KR2 caveat on
every table." KR2 (keys/kr2_intrepid.py) located + verified the 18-fork INTREPID register
(= intrepid_diff.json standing_predictions, verified 18/18 against current engine forks). This
script emits the sprint-side blind-diff artifact: per-register-fork the engine's recovered
side-resolution vs the held-out INTREPID prediction, with the KR2 holdout caveat stamped on the
artifact and required on every table that renders it. instrument_tag v1 (frozen forks); the v2
rerun follows the A5.3 freeze (numbers lock §0.10(9)). No API, no spend.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
from runmanifest import write_manifest, input_ref  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
SLUG_FOR_PAIR = {"IIT × NREP": ("iit", "nrep", "iitxnrep"),
                 "IIT × Active Inference": ("iit", "active-inference", "iitxactive-inference"),
                 "NREP × Active Inference": ("nrep", "active-inference", "nrepxactive-inference")}

CAVEAT = ("BLIND DIFF, instrument v1. Key transcribed from the public INTREPID review by a "
          "quarantined pre-sprint model pass (engine data/answer_keys/intrepid.yaml); the engine "
          "pipeline never accessed the review text (holdout green). Transcription is model output "
          "and may err — approved for FORMAT only, not correctness. The holdout controls the prompt, "
          "not the model's training data (see A6). The v2 rerun follows the A5.3 freeze (numbers "
          "lock §0.10(9)); these v1 numbers are provisional until then. Every table rendering this "
          "artifact MUST carry this caveat.")


def main() -> int:
    diff = json.loads((ENGINE / "results" / "intrepid_diff.json").read_text())
    ak = diff["answer_key"]
    sp = ak["standing_predictions"]
    assert len(sp) == 18, f"HALT-ASK: register is {len(sp)} forks, expected 18"

    # current forks keyed by (left_id, right_id, axis) -> full fork record (for side-resolution)
    forks = {}
    for pair, (la, ra, slug) in SLUG_FOR_PAIR.items():
        J = json.loads((ENGINE / "results" / f"{slug}_judge.json").read_text())
        for f in J["forks"]:
            forks[(f["left_ids"][0], f["right_ids"][0], f["axis"])] = f

    register = []
    verified = 0
    for p in sp:
        la, ra, _ = SLUG_FOR_PAIR[p["pair"]]
        lid, rid = f"{la}_{p['left']}", f"{ra}_{p['right']}"
        fk = forks.get((lid, rid, p["axis"]))
        present = fk is not None
        verified += present
        register.append({
            "pair": p["pair"], "axis": p["axis"],
            "left_id": lid, "right_id": rid,
            "present_in_current_forks": present,
            "left_value": fk.get("left_value") if fk else None,
            "right_value": fk.get("right_value") if fk else None,
            "type_divergence": fk.get("type_divergence") if fk else None,
            "polarity_opposed": fk.get("polarity_opposed") if fk else None,
        })

    artifact = {
        "task": "A4-Leg4", "runid": "A4-L4", "instrument_tag": "v1", "corpus_tag": "v1",
        "source_artifact": "~/consilience-demo/demo/results/intrepid_diff.json",
        "register_size": len(sp), "register_verified": verified,
        "axes": dict(Counter(p["axis"] for p in sp)),
        "pairs": dict(Counter(p["pair"] for p in sp)),
        "answer_key_summary": {
            "int_h1": "RECOVERED-as-correspondence",
            "nrep_computability": "MISSED (accepted-honest)",
            "mechanism_correspondences": len(diff.get("mechanism_correspondences", [])),
            "fault_line": diff.get("fault_line"),
        },
        "register": register,
        "v2_rerun_pending": True,
        "caveat": CAVEAT,
    }
    out = SPRINT / "results" / "a4_blind_diff.json"
    out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))

    write_manifest("A4", "A4-L4", instrument_tag="v1", corpus_tag="v1",
                   inputs=[input_ref(ENGINE / "results" / "intrepid_diff.json", "frozen-store-import")],
                   outputs=["results/a4_blind_diff.json"],
                   notes="A4 Leg 4 (= KR2(f)): blind-diff artifact; 18-fork register; v1; v2 rerun pending")
    print(f"A4 Leg 4: results/a4_blind_diff.json written — 18-fork register, verified {verified}/18; "
          f"INT_H1 RECOVERED-as-correspondence, nrep_computability MISSED (honest), "
          f"mech_corrs {len(diff.get('mechanism_correspondences', []))}. Caveat stamped. instrument_tag v1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
