#!/usr/bin/env python3
"""
pipeline/a4_outcomes.py — A4 Leg 2 (SPEC §A4): discriminativeness. Per fork
`results/a4_outcomes/<fork>.yaml`: {fork_id, observable, outcome_space [2–4 mutually exclusive
measurement patterns], favors {outcome: IIT|NREP|ActInf|neither|both}, vacuous, vacuity_rationale}.

Outcomes are phrased as MEASUREMENT PATTERNS, never experiment/paradigm names from any key; the
INTREPID review is NOT consulted (§0.5) — we condition ONLY on the two sides' typed values. Emits
the A4 outcomes Anu packet (reading task: approve/edit). Demotions (vacuous) → docs/prediction_register.md.
Metrics a4.predictions_strong / a4.predictions_demoted are DRAFT here (final counts applied on the
Anu packet's return). Spend: 18 gpt-4.1 calls.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
import llm as L  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
THEORY_TOKEN = {"IIT": "IIT", "NREP": "NREP", "Active Inference": "ActInf"}
OUT = SPRINT / "results" / "a4_outcomes"

SYSTEM = (
    "You are a measurement designer for consciousness science. You are given one DISAGREEMENT "
    "between two theories on a single typed axis: each side is {theory, value, polarity}. Your job: "
    "design the observable that would discriminate the two typed values, and enumerate the mutually "
    "exclusive measurement patterns it could show.\n"
    "HARD RULES:\n"
    "- Phrase everything as MEASUREMENT PATTERNS (what a measurement could show), NOT experiment "
    "names, paradigm names, study names, dataset names, or citations. No proper nouns for studies.\n"
    "- Condition ONLY on the two typed values given. Do NOT invoke any specific published prediction, "
    "review, or adversarial collaboration.\n"
    "- outcome_space: 2 to 4 patterns, mutually exclusive and jointly plausible.\n"
    "- favors: for each pattern, which theory it supports — one of IIT, NREP, ActInf, neither, both. "
    "Use ONLY the two theories named in this fork (plus neither/both).\n"
    "- vacuous=true iff no feasible measurement could distinguish the two typed values (they are "
    "empirically indistinguishable, or one/both values are not empirically contentful on this axis).\n"
    'Output ONLY JSON: {"observable": "<one measurable contrast>", "outcome_space": '
    '[{"pattern": "<measurement pattern>", "favors": "IIT|NREP|ActInf|neither|both"}, ...], '
    '"vacuous": true|false, "vacuity_rationale": "<one sentence>"}'
)


def draft(fork_id, axis, left, right):
    allowed = {THEORY_TOKEN.get(left["theory"], left["theory"]),
               THEORY_TOKEN.get(right["theory"], right["theory"]), "neither", "both"}
    user = (f"Axis: {axis}\n"
            f"Side A: theory={left['theory']} ({THEORY_TOKEN.get(left['theory'])}), "
            f"value={left['value']}, polarity={left['polarity']}\n"
            f"Side B: theory={right['theory']} ({THEORY_TOKEN.get(right['theory'])}), "
            f"value={right['value']}, polarity={right['polarity']}\n"
            f"Design the discriminating observable and its mutually exclusive measurement patterns.")
    rec = L.default().call_json(task_id="A4", model=CFG["models"]["verifier"], system=SYSTEM,
                                messages=[{"role": "user", "content": user}], replicate_tag="r0",
                                temperature=0, max_tokens=700)
    p = rec.get("parsed") or {}
    os_ = []
    for o in (p.get("outcome_space") or []):
        fav = o.get("favors")
        if fav not in allowed:
            fav = "neither"  # out-of-vocab favors token → neither (conservative; flagged in packet)
        os_.append({"pattern": str(o.get("pattern", "")).strip(), "favors": fav})
    return {"observable": str(p.get("observable", "")).strip(),
            "outcome_space": os_,
            "favors": {o["pattern"]: o["favors"] for o in os_},
            "vacuous": bool(p.get("vacuous")),
            "vacuity_rationale": str(p.get("vacuity_rationale", "")).strip(),
            "json_status": rec.get("json_status")}, allowed


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    diff = json.loads((ENGINE / "results" / "intrepid_diff.json").read_text())
    sp = diff["answer_key"]["standing_predictions"]
    assert len(sp) == 18, f"HALT-ASK: register is {len(sp)} forks, expected 18"

    SLUG = {"IIT × NREP": ("iit", "nrep"), "IIT × Active Inference": ("iit", "active-inference"),
            "NREP × Active Inference": ("nrep", "active-inference")}
    import a3_dossiers as A3D  # reuse the claims index
    idx = A3D.claims_index()

    strong = demoted = 0
    packet_rows = []
    for p in sp:
        la, ra = SLUG[p["pair"]]
        lid, rid = f"{la}_{p['left']}", f"{ra}_{p['right']}"
        a, b = idx.get(lid), idx.get(rid)
        if not (a and b):
            continue
        fid = f"{p['pair']}:{p['axis']}:{lid}x{rid}".replace(" ", "")
        d, allowed = draft(fid, p["axis"], a, b)
        if 2 <= len(d["outcome_space"]) <= 4 and not d["vacuous"]:
            strong += 1
        if d["vacuous"]:
            demoted += 1
        rec = {"fork_id": fid, "axis": p["axis"], "pair": p["pair"],
               "sides": {"left": {"theory": a["theory"], "value": a["value"], "polarity": a["polarity"]},
                         "right": {"theory": b["theory"], "value": b["value"], "polarity": b["polarity"]}},
               }
        rec.update({k: d[k] for k in ("observable", "outcome_space", "favors", "vacuous", "vacuity_rationale")})
        (OUT / f"{fid.replace(':', '_').replace('×', 'x')}.yaml").write_text(
            yaml.safe_dump(rec, sort_keys=False, allow_unicode=True))
        packet_rows.append({"fork_id": fid, "axis": p["axis"], "observable": d["observable"],
                            "n_outcomes": len(d["outcome_space"]), "vacuous": d["vacuous"],
                            "decision": ""})

    # Anu packet (reading task: approve / edit the drafted outcome YAMLs)
    with open(SPRINT / "review" / "a4_outcomes.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["fork_id", "axis", "observable", "n_outcomes", "vacuous", "decision"])
        w.writeheader(); w.writerows(packet_rows)
    (SPRINT / "review" / "a4_outcomes.md").write_text(
        f"""# A4 outcomes review (INTREPID register, Leg 2 discriminativeness)  [AWAITING-ANU]

Role: approver (reading task). Open each `results/a4_outcomes/<fork>.yaml` and judge, from the
typed values alone, whether the drafted observable + outcome_space discriminate the two sides.
`decision` ∈ {{approve, edit, demote-vacuous}}. `approve` = the observable and 2–4 mutually
exclusive measurement patterns stand. `edit` = fix the YAML in place (then mark edit). `demote-vacuous`
= the fork makes no discriminating prediction (→ demoted to docs/prediction_register.md).
Outcomes are measurement patterns only — no experiment names; the INTREPID review is NOT the source.
{len(packet_rows)} forks → review/a4_outcomes.csv. DRAFT counts (pending your return): strong={strong},
vacuous/demoted={demoted}.
""")
    (SPRINT / "review" / "a4_outcomes_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["approve", "edit", "demote-vacuous"]}}, indent=2))

    reg = Registry()
    base = dict(task="A4", runid="A4-L2", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=False, pilot=False)
    reg.upsert(metric_id="a4.predictions_strong", value=strong, n=len(packet_rows),
               caveats=["DRAFT (pre-Anu): forks with a non-vacuous 2–4-pattern discriminating observable; "
                        "final count set when review/a4_outcomes.csv returns"], **base)
    reg.upsert(metric_id="a4.predictions_demoted", value=demoted, n=len(packet_rows),
               caveats=["DRAFT (pre-Anu): forks drafted vacuous (→ docs/prediction_register.md on approval)"], **base)
    reg.save()

    write_manifest("A4", "A4-L2", instrument_tag="frozen-store", corpus_tag="v1",
                   inputs=[input_ref(ENGINE / "results" / "intrepid_diff.json", "frozen-store-import")],
                   outputs=["results/a4_outcomes/", "review/a4_outcomes.csv"],
                   notes="A4 Leg 2 discriminativeness: outcome-space drafts + Anu packet (DRAFT metrics)")
    print(f"A4 Leg 2: {len(packet_rows)} outcome YAMLs → results/a4_outcomes/; "
          f"DRAFT strong={strong} vacuous={demoted}.")
    print(f"  meter ${L.default().meter.data['total_usd']:.4f}; AWAITING-ANU: review/a4_outcomes.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
