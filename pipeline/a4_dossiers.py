#!/usr/bin/env python3
"""
pipeline/a4_dossiers.py — A4 Leg 1 (SPEC §A4): validity. "A3 dossier machinery over all 18 →
results/a4_dossiers/." Reuses the A3 machinery (provenance C1 mechanical, support C2 gpt-4.1,
counter-evidence scan, decidability) over the 18-fork INTREPID register (= intrepid_diff.json
standing_predictions; IIT×NREP 8, IIT×AI 9, NREP×AI 1). Emits per-fork dossiers + the A4
counter-evidence Anu packet (review/a4_counter_evidence.csv). instrument_tag frozen-store
(v1-era forks + approved store). Spend: ~36 gpt-4.1 C2 calls (18 forks × 2 sides), cached.
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
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import a3_dossiers as A3D  # noqa: E402  (reuse c1_provenance, c2_support, counter_evidence, cap, loaders)
import llm as L  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
SLUG_FOR_PAIR = {"IIT × NREP": ("iit", "nrep", "iitxnrep"),
                 "IIT × Active Inference": ("iit", "active-inference", "iitxactive-inference"),
                 "NREP × Active Inference": ("nrep", "active-inference", "nrepxactive-inference")}
OUT = SPRINT / "results" / "a4_dossiers"
CAVEAT = ("A4 INTREPID-register dossiers (18-fork standing_predictions). instrument v1-era forks + "
          "approved store (frozen-store). The INTREPID review is a HELD-OUT answer key — never "
          "consulted here (§0.5); validity is checked against the theories' OWN corpora only.")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    idx = A3D.claims_index()
    passages = A3D.passages_by_theory()
    evidence = {}
    ev_path = ENGINE / "results" / "evidence.json"
    if ev_path.exists():
        evidence = json.loads(ev_path.read_text()).get("axes", {})

    diff = json.loads((ENGINE / "results" / "intrepid_diff.json").read_text())
    sp = diff["answer_key"]["standing_predictions"]
    assert len(sp) == 18, f"HALT-ASK: register is {len(sp)} forks, expected 18"

    # fork records keyed by (left,right,axis) for the decidability field
    fork_rec = {}
    for pair, (la, ra, slug) in SLUG_FOR_PAIR.items():
        J = json.loads((ENGINE / "results" / f"{slug}_judge.json").read_text())
        for f in J["forks"]:
            fork_rec[(f["left_ids"][0], f["right_ids"][0], f["axis"])] = f

    ce_rows, decid_worksheet = [], []
    clean = flagged = 0
    for p in sp:
        pair = p["pair"]
        la, ra, _ = SLUG_FOR_PAIR[pair]
        lid, rid = f"{la}_{p['left']}", f"{ra}_{p['right']}"
        a = idx.get(lid)
        b = idx.get(rid)
        fk = fork_rec.get((lid, rid, p["axis"]), {})
        fid = f"{pair}:{p['axis']}:{lid}x{rid}".replace(" ", "")
        ta = a["theory"] if a else pair.split(" × ")[0]
        tb = b["theory"] if b else pair.split(" × ")[1]

        sides = {}
        for lbl, c, th in (("left", a, ta), ("right", b, tb)):
            if not c:
                sides[lbl] = {"missing": True}
                continue
            sides[lbl] = {"theory": c["theory"], "value": c["value"], "polarity": c["polarity"],
                          "claim_ids": [c["claim_id"]], "quotes": [A3D.cap(c["statement"])],
                          "provenance_check": A3D.c1_provenance(c, passages.get(c["theory"], [])),
                          "support_check": A3D.c2_support(c)}
        ce = {}
        if a and b:
            ce["left"] = A3D.counter_evidence(a["theory"], b["value"], a["polarity"], passages.get(a["theory"], []))
            ce["right"] = A3D.counter_evidence(b["theory"], a["value"], b["polarity"], passages.get(b["theory"], []))
            for side, hits in ce.items():
                for h in hits:
                    ce_rows.append({"fork_id": fid, "side": side, "passage_id": h["passage_id"],
                                    "score": h["score"], "excerpt": h["excerpt"], "decision": ""})
        ev = evidence.get(p["axis"], {})
        citation_rows = [{"tag": t["tag"], "n": t["n"]} for t in ev.get("tags", [])] if ev else []
        if not citation_rows:
            decid_worksheet.append({"fork_id": fid, "axis": p["axis"],
                                    "query": f"ConTraSt finding-tag mentions bearing on axis {p['axis']}",
                                    "citation_url": "", "note": "ConTraSt-silent (web-conditional)"})
        dossier = {
            "fork_id": fid, "axis": p["axis"], "pair": pair, "register": "INTREPID-18",
            "sides": sides, "counter_evidence": ce, "anchors": [],
            "decidability": {"verdict": fk.get("decidability"),
                             "rationale": "",
                             "citation_rows": citation_rows,
                             "evidence_verdict": ev.get("verdict"),
                             "note": "ConTraSt finding-tag mentions; expert agreement deferred (never claimed); "
                                     "INTREPID review held out (§0.5)"},
            "status": "clean", "correction_note": None, "caveat": CAVEAT,
        }
        clean += 1
        (OUT / f"{fid.replace(':', '_').replace('/', '_').replace('×', 'x')}.json").write_text(
            json.dumps(dossier, ensure_ascii=False, indent=2) + "\n")

    # A4 counter-evidence packet (same schema/role as A3's)
    with open(SPRINT / "review" / "a4_counter_evidence.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["fork_id", "side", "passage_id", "score", "excerpt", "decision"])
        w.writeheader(); w.writerows(ce_rows)
    (SPRINT / "review" / "a4_counter_evidence.md").write_text(
        f"""# A4 counter-evidence review (INTREPID register)  [AWAITING-ANU]

Role: approver (never domain expert). For each candidate passage, mark whether it is a REAL
contradiction of the fork's typed value, merely rhetorical, or out-of-context.
`decision` ∈ {{real-contradiction, rhetorical, out-of-context}}. Any real-contradiction flags the
fork (→ docs/corrections.md if it defeats the typed value). The INTREPID review is NOT the source
of these passages — they are from the theories' own corpora. {len(ce_rows)} rows →
review/a4_counter_evidence.csv.
""")
    (SPRINT / "review" / "a4_counter_evidence_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["real-contradiction", "rhetorical", "out-of-context"]}}, indent=2))
    with open(SPRINT / "review" / "a4_decid_citations.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["fork_id", "axis", "query", "citation_url", "note"])
        w.writeheader(); w.writerows(decid_worksheet)

    reg = Registry()
    base = dict(task="A4", runid="A4-L1", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=False, pilot=False)
    reg.upsert(metric_id="a4.forks_dossiered", value=clean, n=len(sp),
               caveats=[CAVEAT, "18-fork INTREPID register; status clean pending the A4 "
                        "counter-evidence Anu gate (flags applied on return)"], **base)
    reg.upsert(metric_id="a4.forks_flagged", value=flagged, n=len(sp),
               caveats=["0 until Anu marks an a4_counter_evidence row real-contradiction"], **base)
    reg.save()

    write_manifest("A4", "A4-L1", instrument_tag="frozen-store", corpus_tag="v1",
                   inputs=[input_ref(ENGINE / "results" / "intrepid_diff.json", "frozen-store-import"),
                           {"path": "engine data/claims + data/passages (IIT/NREP/AI, read-only)", "kind": "corpus", "sha256": None}],
                   outputs=["results/a4_dossiers/", "review/a4_counter_evidence.csv"],
                   notes="A4 Leg 1 validity: A3-dossier machinery over the 18-fork register")
    print(f"A4 Leg 1: {clean} dossiers → results/a4_dossiers/; counter-evidence packet {len(ce_rows)} rows; "
          f"decid worksheet {len(decid_worksheet)} rows.")
    print(f"  meter ${L.default().meter.data['total_usd']:.4f}; AWAITING-ANU: review/a4_counter_evidence.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
