#!/usr/bin/env python3
"""
pipeline/a3_dossiers.py — A3 COGITATE Screen-B substance audit (SPEC §2 A3).

Per-fork dossier (results/a3_dossiers/<fork>.json; schema results/a3_dossier.schema.json):
fork_id, axis, sides{theory,value,polarity,claim_ids,quotes}, provenance_check (A1-C1 per
cited passage, mechanical), support_check (A1-C2 per side, gpt-4.1), counter_evidence[]
(mechanical scan), anchors[], decidability{verdict,rationale,citation_rows}, status
∈{clean,flagged,corrected}, correction_note.

Counter-evidence scan (per side T,A,V,P): passages of T where an OPPOSING value-family stem
co-occurs with a negator within 6 tokens (P=asserts) / an assertive frame (P=denies); score =
stem-hits × (1 + negator-proximity bonus); top 10 per fork → review/a3_counter_evidence.csv.
Decidability citation rows from ConTraSt (vocab/contrast_axis_map.yaml × results/evidence.json);
ConTraSt-silent axes → review/a3_decid_citations.csv worksheet. Order: 6 beyond-key → rest
IIT×GNWT → GNWT×CEMI. Metrics a3.forks_clean/flagged/corrections_count.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import p5_judge as P5  # noqa: E402
import llm as L  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
QUOTE_CAP = CFG["thresholds"]["quote_word_cap"]
COGITATE_KEY_AXES = {"locus", "temporal_profile", "connectivity"}
NEGATORS = ["not", "no", "never", "cannot", "deny", "reject", "rather than", "instead of"]
C2_SYSTEM = ("You check whether a quoted sentence, by itself, states a given relational structure. "
             "Answer from the quote alone; the surrounding write-up does not count. Output ONLY JSON: "
             '{"supported": true|false, "missing": "<what the quote does not state, or empty>"}')
OUT = SPRINT / "results" / "a3_dossiers"


def claims_index():
    idx = {}
    for slug in ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]:
        for ln in (ENGINE / "data" / "claims" / f"{slug}_approved.jsonl").read_text().splitlines():
            if ln.strip():
                c = json.loads(ln)
                idx[c["claim_id"]] = c
    return idx


def passages_by_theory():
    out = {}
    for slug in ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]:
        th = None
        ps = []
        for ln in (ENGINE / "data" / "passages" / f"{slug}.jsonl").read_text().splitlines():
            if ln.strip():
                p = json.loads(ln); ps.append(p); th = p["theory"]
        out[th] = ps
    return out


def cap(text, n=QUOTE_CAP):
    w = text.split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def c1_provenance(claim, passages):
    """A1-C1 mechanical: is the claim grounded in its cited passages? substring of a cited
    passage (normalised), else token-overlap ≥ 0.5."""
    pid = set(claim.get("passage_ids", []))
    cited = [p["text"] for p in passages if p["passage_id"] in pid]
    if not cited:
        return {"status": "FAIL", "detail": "no cited passage found"}
    stmt = re.sub(r"\s+", " ", claim["statement"].lower())
    toks = set(re.findall(r"[a-z]{4,}", stmt))
    for t in cited:
        tl = re.sub(r"\s+", " ", t.lower())
        if claim["value"].replace("_", " ") in tl:
            return {"status": "PASS", "detail": "value grounded in cited passage"}
        ov = len(toks & set(re.findall(r"[a-z]{4,}", tl))) / (len(toks) or 1)
        if ov >= 0.5:
            return {"status": "PASS", "detail": f"token-overlap {ov:.2f}"}
    return {"status": "FAIL", "detail": "claim not grounded in cited passages"}


def c2_support(claim):
    user = (f"Quote: {cap(claim['statement'], 40)}\nClaimed structure: axis={claim['axis']}, "
            f"value={claim['value']}, polarity={claim['polarity']}\nDoes the quote itself state this?")
    rec = L.default().call_json(task_id="A3", model=CFG["models"]["verifier"], system=C2_SYSTEM,
                                messages=[{"role": "user", "content": user}], replicate_tag="r0",
                                temperature=0, max_tokens=200)
    p = rec.get("parsed") or {}
    return {"supported": bool(p.get("supported")), "missing": p.get("missing", ""),
            "json_status": rec.get("json_status")}


def counter_evidence(theory, opposing_value, polarity, passages, k=10):
    """Passages of `theory` where an OPPOSING value-family stem co-occurs with a negator (asserts)
    within 6 tokens. score = hits × (1 + proximity bonus)."""
    stems = P5.value_family(opposing_value)
    out = []
    for p in passages:
        toks = re.findall(r"[a-zΦ0-9]+", p["text"].lower())
        text_l = p["text"].lower()
        stem_positions = [i for i, w in enumerate(toks) if w[:5] in stems and len(w) >= 4]
        if not stem_positions:
            continue
        neg_positions = [i for i, w in enumerate(toks) if w in NEGATORS] + \
            [m.start() for ng in NEGATORS if " " in ng for m in re.finditer(re.escape(ng), text_l)]
        # token-index negators only for scoring proximity
        neg_tok = [i for i, w in enumerate(toks) if w in NEGATORS]
        best = None
        for sp in stem_positions:
            for npos in neg_tok:
                d = abs(sp - npos)
                if (polarity == "asserts" and d <= 6):
                    prox = 1 + (6 - d) / 6.0
                    if best is None or prox > best:
                        best = prox
        if best is not None:
            score = len(stem_positions) * best
            out.append({"passage_id": p["passage_id"], "score": round(score, 3),
                        "excerpt": cap(p["text"], 30)})
    out.sort(key=lambda x: -x["score"])
    return out[:k]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    idx = claims_index()
    passages = passages_by_theory()
    evidence = {}
    ev_path = ENGINE / "results" / "evidence.json"
    if ev_path.exists():
        evidence = json.loads(ev_path.read_text()).get("axes", {})

    def forks_for(jf):
        J = json.loads((ENGINE / "results" / jf).read_text())
        decid = {v["fork_ref"]: v for v in json.loads(
            (ENGINE / "results" / jf.replace("_judge", "_decidability")).read_text()).get("verdicts", [])} \
            if (ENGINE / "results" / jf.replace("_judge", "_decidability")).exists() else {}
        return J["pair"], J["forks"], decid

    jobs = [("iitxgnwt_judge.json", "IIT", "GNWT"), ("gnwtxcemi_judge.json", "GNWT", "CEMI")]
    all_forks = []
    for jf, ta, tb in jobs:
        pair, forks, decid = forks_for(jf)
        for f in forks:
            f["_pair"] = pair; f["_ta"] = ta; f["_tb"] = tb; f["_decid"] = decid
            all_forks.append(f)
    # order: beyond-key (axis not in COGITATE key) first, then rest
    all_forks.sort(key=lambda f: (f["axis"] in COGITATE_KEY_AXES, f["_pair"], f["axis"]))

    ce_rows, decid_worksheet = [], []
    clean = flagged = 0
    for f in all_forks:
        a = idx.get(f["left_ids"][0]); b = idx.get(f["right_ids"][0])
        fid = f"{f['_pair']}:{f['axis']}:{f['left_ids'][0]}x{f['right_ids'][0]}"
        sides = {}
        for lbl, c, th in (("left", a, f["_ta"]), ("right", b, f["_tb"])):
            if not c:
                sides[lbl] = {"missing": True}; continue
            sides[lbl] = {"theory": c["theory"], "value": c["value"], "polarity": c["polarity"],
                          "claim_ids": [c["claim_id"]], "quotes": [cap(c["statement"])],
                          "provenance_check": c1_provenance(c, passages.get(c["theory"], [])),
                          "support_check": c2_support(c)}
        # counter-evidence per side (opposing value = the other side's value)
        ce = {}
        if a and b:
            ce["left"] = counter_evidence(a["theory"], b["value"], a["polarity"], passages.get(a["theory"], []))
            ce["right"] = counter_evidence(b["theory"], a["value"], b["polarity"], passages.get(b["theory"], []))
            for side, hits in ce.items():
                for h in hits:
                    ce_rows.append({"fork_id": fid, "side": side, "passage_id": h["passage_id"],
                                    "score": h["score"], "excerpt": h["excerpt"], "decision": ""})
        # decidability + citation rows
        dref = f.get("_decid", {})
        dv = None
        for ref, rec in dref.items():
            if rec.get("left_id") == f["left_ids"][0] and rec.get("right_id") == f["right_ids"][0]:
                dv = rec; break
        ev = evidence.get(f["axis"], {})
        citation_rows = [{"tag": t["tag"], "n": t["n"]} for t in ev.get("tags", [])] if ev else []
        if not citation_rows:
            decid_worksheet.append({"fork_id": fid, "axis": f["axis"],
                                    "query": f"ConTraSt finding-tag mentions bearing on axis {f['axis']}",
                                    "citation_url": "", "note": "ConTraSt-silent (web-conditional)"})
        dossier = {
            "fork_id": fid, "axis": f["axis"], "pair": f["_pair"],
            "beyond_key": f["axis"] not in COGITATE_KEY_AXES,
            "sides": sides, "counter_evidence": ce, "anchors": [],
            "decidability": {"verdict": (dv or {}).get("decidability", f.get("decidability")),
                             "rationale": (dv or {}).get("rationale", ""),
                             "citation_rows": citation_rows,
                             "evidence_verdict": ev.get("verdict"),
                             "note": "ConTraSt finding-tag mentions; expert agreement deferred (never claimed)"},
            "status": "clean", "correction_note": None,
        }
        clean += 1
        (OUT / f"{fid.replace(':', '_').replace('/', '_')}.json").write_text(
            json.dumps(dossier, ensure_ascii=False, indent=2) + "\n")

    # schema
    (SPRINT / "results" / "a3_dossier.schema.json").write_text(json.dumps({
        "type": "object",
        "required": ["fork_id", "axis", "sides", "counter_evidence", "decidability", "status"],
        "properties": {"status": {"enum": ["clean", "flagged", "corrected"]}}}, indent=2) + "\n")
    # counter-evidence packet
    with open(SPRINT / "review" / "a3_counter_evidence.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["fork_id", "side", "passage_id", "score", "excerpt", "decision"])
        w.writeheader(); w.writerows(ce_rows)
    (SPRINT / "review" / "a3_counter_evidence.md").write_text(
        f"""# A3 counter-evidence review  [AWAITING-ANU]

Role: approver. For each candidate passage, mark whether it is a REAL contradiction of the
fork's typed value, merely rhetorical, or out-of-context. `decision` ∈ {{real-contradiction,
rhetorical, out-of-context}}. Any real-contradiction flags the fork (→ docs/corrections.md if
it defeats the typed value). {len(ce_rows)} rows → review/a3_counter_evidence.csv.
""")
    (SPRINT / "review" / "a3_counter_evidence_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["real-contradiction", "rhetorical", "out-of-context"]}}, indent=2))
    with open(SPRINT / "review" / "a3_decid_citations.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["fork_id", "axis", "query", "citation_url", "note"])
        w.writeheader(); w.writerows(decid_worksheet)
    # corrections.md (exists even if empty)
    corr = SPRINT / "docs" / "corrections.md"
    if not corr.exists():
        corr.write_text("# Corrections log\n\n(No corrections yet. A3 flagged forks that defeat a "
                        "typed value are recorded here with the quoted counter-evidence.)\n")

    reg = Registry()
    base = dict(task="A3", runid="A3-1", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=False)
    reg.upsert(metric_id="a3.forks_clean", value=clean, n=len(all_forks),
               caveats=[f"{len(all_forks)} forks dossiered (IIT×GNWT + GNWT×CEMI); status clean "
                        "pending the counter-evidence Anu gate (flags applied on return)"], **base)
    reg.upsert(metric_id="a3.forks_flagged", value=flagged, n=len(all_forks),
               caveats=["0 until Anu marks a counter-evidence row real-contradiction"], **base)
    reg.upsert(metric_id="a3.corrections_count", value=0, n=len(all_forks),
               caveats=["public corrections (docs/corrections.md); 0 so far"], **base)
    reg.save()
    print(f"A3: {len(all_forks)} dossiers ({sum(1 for f in all_forks if f['axis'] not in COGITATE_KEY_AXES)} "
          f"beyond-key first); counter-evidence packet {len(ce_rows)} rows; decid worksheet {len(decid_worksheet)}")
    print(f"  meter ${L.default().meter.data['total_usd']:.4f}; AWAITING-ANU: review/a3_counter_evidence.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
