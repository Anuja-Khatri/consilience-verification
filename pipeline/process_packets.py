#!/usr/bin/env python3
"""
pipeline/process_packets.py — apply the returned Anu decisions for the packets processable now
(a3_counter_evidence, a4_counter_evidence, a4_outcomes). kr1_v2_claims + a1_c2_relation arrived
EMPTY in the working tree (decisions absent) → NOT processed here (HALT-ASK reported separately).

DISCLOSURE (owner, verbatim, recorded once in BUILD_LOG + each packet's provenance): "Decisions
were model-drafted suggestions (Claude) reviewed and confirmed by Anu." Draft-vs-confirmed
agreement is reported wherever a model draft existed.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
import yaml  # noqa: E402
from registry import Registry  # noqa: E402

DISCLOSURE = "Decisions were model-drafted suggestions (Claude) reviewed and confirmed by Anu."


def rows(name):
    return list(csv.DictReader(open(SPRINT / "review" / f"{name}.csv")))


def main() -> int:
    reg = Registry()

    # ---- a3_counter_evidence (tally from owner; file empty but only 'real-contradiction' matters) ----
    # owner: 0 real-contradiction / 73 rhetorical / 56 out-of-context → NO FORK FLAGGED BY THE SCAN.
    a3base = dict(task="A3", runid="A3-1", instrument_tag="frozen-store", corpus_tag="v1",
                  preregistered=True, pilot=False)
    reg.upsert(metric_id="a3.forks_flagged", value=0, n=129,
               caveats=[DISCLOSURE, "Anu counter-evidence gate returned 0 real-contradiction "
                        "(73 rhetorical / 56 out-of-context), judged at EXCERPT level (truncated "
                        "excerpts, no fork-side claim text in packet) → 'no fork flagged by the scan', "
                        "NOT 'forks validated'. No model-draft decision existed (scan drafted candidates "
                        "only) → no draft-vs-confirmed metric."], **a3base)
    reg.upsert(metric_id="a3.corrections_count", value=0, n=129,
               caveats=[DISCLOSURE, "0 real-contradiction → 0 corrections (docs/corrections.md)"], **a3base)

    # ---- a4_counter_evidence (file FILLED: 0 real / 76 rhetorical / 43 out-of-context) ----
    a4c = rows("a4_counter_evidence")
    a4c_dist = Counter(r["decision"] for r in a4c)
    assert a4c_dist.get("real-contradiction", 0) == 0, "HALT-ASK: a4 real-contradiction present — fork flag needed"
    a4base = dict(task="A4", runid="A4-L1", instrument_tag="frozen-store", corpus_tag="v1",
                  preregistered=False, pilot=False)
    reg.upsert(metric_id="a4.forks_flagged", value=0, n=len(a4c),
               caveats=[DISCLOSURE, f"Anu counter-evidence gate: 0 real-contradiction "
                        f"({a4c_dist.get('rhetorical',0)} rhetorical / {a4c_dist.get('out-of-context',0)} "
                        "out-of-context), judged at EXCERPT level (no fork-side claim text in packet) → "
                        "'no fork flagged by the scan', NOT 'forks validated'."], **a4base)

    # ---- a4_outcomes (file FILLED: 15 approve / 3 reject→demote-vacuous) ----
    a4o = rows("a4_outcomes")
    approve = [r for r in a4o if r["decision"] == "approve"]
    reject = [r for r in a4o if r["decision"] == "reject"]
    demoted_fids = [r["fork_id"] for r in reject]
    (SPRINT / "results" / "a4_demoted.json").write_text(json.dumps(
        {"demoted": demoted_fids, "reason": "observable is a validation-method question, not a "
         "measurement pattern (Anu, A4 Leg-2 gate)"}, indent=2))
    # flip the 3 YAMLs to vacuous
    for fid in demoted_fids:
        yp = SPRINT / "results" / "a4_outcomes" / (fid.replace(":", "_").replace("×", "x") + ".yaml")
        if yp.exists():
            y = yaml.safe_load(yp.read_text())
            y["vacuous"] = True
            y["vacuity_rationale"] = ("DEMOTED by Anu (A4 Leg-2 gate): observable is a validation-method "
                                      "question, not a measurement pattern. " + DISCLOSURE)
            yp.write_text(yaml.safe_dump(y, sort_keys=False, allow_unicode=True))
    a4l2 = dict(task="A4", runid="A4-L2", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=False, pilot=False)
    agree = round(len(approve) / len(a4o), 3)
    reg.upsert(metric_id="a4.predictions_strong", value=len(approve), n=len(a4o),
               caveats=[DISCLOSURE, "Anu-CONFIRMED non-vacuous discriminating observables (was 18 draft); "
                        "reviewed observable text only (outcome spaces/favors not in packet)"], **a4l2)
    reg.upsert(metric_id="a4.predictions_demoted", value=len(reject), n=len(a4o),
               caveats=[DISCLOSURE, "demoted to docs/prediction_register.md: " + ", ".join(demoted_fids) +
                        " — observable is a validation-method question, not a measurement pattern"], **a4l2)
    reg.upsert(metric_id="a4.outcomes_draft_confirmed_agreement", value=agree, n=len(a4o),
               caveats=[DISCLOSURE, f"{len(approve)}/{len(a4o)} model-drafted observables confirmed by Anu "
                        f"(3 rejected as validation-method, not measurement patterns)"], **a4l2)
    reg.save()

    # prediction_register.md demotions section
    regmd = SPRINT / "docs" / "prediction_register.md"
    demo = ["\n\n## Demotions (A4 Leg-2 Anu gate — vacuous)\n",
            f"> {DISCLOSURE}\n\n",
            "These forks' observables are validation-method questions, not measurement patterns, so "
            "they make no discriminating prediction and are DEMOTED (excluded from Leg 3):\n"]
    for fid in demoted_fids:
        demo.append(f"- `{fid}`\n")
    with open(regmd, "a") as fh:
        fh.write("".join(demo))

    print(f"a3_counter: 0 real-contradiction → a3.forks_flagged=0 (no fork flagged by the scan).")
    print(f"a4_counter: {dict(a4c_dist)} → a4.forks_flagged=0 (no fork flagged by the scan).")
    print(f"a4_outcomes: {len(approve)} approve / {len(reject)} reject → a4.predictions_strong={len(approve)}, "
          f"demoted={len(reject)} ({demoted_fids}); draft-confirmed agreement={agree}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
