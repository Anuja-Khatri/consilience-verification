#!/usr/bin/env python3
"""
pipeline/kr1_v2_extract.py — KR1 v2 full-fidelity re-extraction (D-024, owner Option 1).

Re-extracts IIT + GNWT under instrument v2 across the three passes that produced the
canonical claims, with the A5.2 definitions block injected into every vocab-injecting
EXTRACTION prompt (main + _TARGET_SYSTEM). All else production. All calls via llm.py.

Passes (reconstructed from claim provenance, D-024):
  - first-pass  : extract_window(v2) over candidates(all theory passages)      → c-claims
  - new-sources : extract_window(v2) over candidates(doc) [IIT iit_nrn_2016,    → n-claims
                  GNWT gnwt_science_2017], deduped vs canonical
  - targeted    : extract_window_targeted(v2 _TARGET_SYSTEM) over _TARGET_RE    → t-claims (IIT only)
FORKS depend only on nodes, so no edge pass is needed for the diff.

Output: runs/KR1/KR1-2/v2_claims.json + an ORACLE-LIGHT review packet (review/kr1_v2_claims.*):
rows are only the v2 claims whose typed fields differ from the nearest canonical claim
(full packet if >30% differ, per A6). Then AWAITING-ANU; kr1_v2_diff.py runs on approval.
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
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
sys.path.insert(0, str(ENGINE / "pipeline"))
sys.path.insert(0, str(ENGINE / "eval"))

import p2_extract as P2  # noqa: E402  (candidates/load_passages/dedup/_json_block/to_claim/_TARGET_* etc.)
from p5_judge import value_family  # noqa: E402
import llm as L  # noqa: E402
import a5_stability as A5M  # noqa: E402  (extract_system — production main prompt)
import a5_freeze as FRZ  # noqa: E402  (definitions_block)

SONNET, HAIKU = P2.SONNET, P2.HAIKU
DEFS = FRZ.definitions_block()
MAIN_V2 = A5M.extract_system() + "\n" + DEFS                 # = frozen v2_system (2fc0035d)
TARGET_V2 = P2._TARGET_SYSTEM + "\n" + DEFS                  # _TARGET_SYSTEM + definitions (v2.0.4 / D-024)
HAIKU_SYS = ("Independently derive the (entity_type, axis, polarity) of the theory's claim from ONLY these "
             f"passages. entity_type in {sorted(P2.ENTITY_TYPES)}; axis in {sorted(P2.AXES)} or 'none'; polarity "
             "asserts|denies. Output ONLY JSON {\"entity_type\",\"axis\",\"polarity\"}.")  # production checker (no defs)

NEW_DOC = {"IIT": "iit_nrn_2016", "GNWT": "gnwt_science_2017"}
TARGETED = {"IIT": "iit_nrn_2016"}  # GNWT has no targeted pass
THEORIES = [("IIT", "iit"), ("GNWT", "gnwt")]
CLIENT = L.LLM()


def _extract(system, theory, window, max_tokens, targeted=False):
    user = "Theory: %s\nPassages:\n%s" % (theory, "\n".join(f'[{p["passage_id"]}] {p["text"]}' for p in window))
    rec = CLIENT.call(task_id="KR1", model=SONNET, system=system,
                      messages=[{"role": "user", "content": user}], replicate_tag="kr1",
                      temperature=None, max_tokens=max_tokens)
    ids = {p["passage_id"] for p in window}
    out = []
    for c in P2._json_block(rec.get("text") or ""):
        pids = [i for i in c.get("passage_ids", []) if i in ids]
        if not pids:
            continue
        if targeted and c.get("axis") not in P2._TARGET_AXES:
            continue
        c["passage_ids"] = pids
        out.append(c)
    return out


def _haiku(theory, claim, by_id):
    """Same-family Haiku cross-check (production parity; checker prompt, no definitions).
    Returns True if Haiku's (entity_type, axis, polarity) matches the Sonnet claim."""
    excerpt = "\n".join(f'[{i}] {by_id[i]["text"]}' for i in claim["passage_ids"] if i in by_id)
    rec = CLIENT.call(task_id="KR1", model=HAIKU, system=HAIKU_SYS,
                      messages=[{"role": "user", "content": f"Theory: {theory}\nClaim: {claim['statement']}\nPassages:\n{excerpt}"}],
                      replicate_tag="kr1", temperature=None, max_tokens=200)
    try:
        t = rec.get("text") or ""
        import re as _re
        t = _re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=_re.M)
        h = json.loads(t)
        return (h.get("entity_type") == claim["entity_type"] and h.get("axis") == claim["axis"]
                and h.get("polarity") == claim["polarity"])
    except Exception:
        return False


def _windows(passages):
    cands = P2.candidates(passages)
    return [cands[i:i + P2.WINDOW] for i in range(0, len(cands), P2.WINDOW)]


def _targeted_windows(passages):
    scored = sorted(((len(P2._TARGET_RE.findall(p["text"])), p) for p in passages
                     if not P2.REFLIKE.search(p["text"]) and len(p["text"]) >= 60 and P2._TARGET_RE.search(p["text"])),
                    key=lambda x: (-x[0], x[1]["passage_id"]))
    cands = [p for _, p in scored[:48]]
    return [cands[i:i + P2.WINDOW] for i in range(0, len(cands), P2.WINDOW)]


def run_theory(theory, slug):
    passages = P2.load_passages(slug)
    by_id = {p["passage_id"]: p for p in passages}
    raw = []
    for win in _windows(passages):
        raw += _extract(MAIN_V2, theory, win, 1500)
    # new-sources (main prompt), deduped vs canonical approved keys
    ndoc = NEW_DOC[theory]
    npass = [p for p in passages if p["passage_id"].startswith(ndoc)]
    nraw = []
    for win in _windows(npass):
        nraw += _extract(MAIN_V2, theory, win, 1500)
    # targeted (IIT only)
    traw = []
    if theory in TARGETED:
        tpass = [p for p in passages if p["passage_id"].startswith(TARGETED[theory])]
        for win in _targeted_windows(tpass):
            traw += _extract(TARGET_V2, theory, win, 1400, targeted=True)
    # dedup within each stream, then to_claim (validates vocab), assign ids
    def mk(stream, prefix, dedup_vs_approved):
        deduped = P2.dedup(stream)
        if dedup_vs_approved:
            seen = P2.approved_keys(slug)
            deduped = [c for c in deduped
                       if (c["entity_type"], c["axis"], str(c.get("value", "")), c["polarity"]) not in seen]
        claims = [c for c in (P2.to_claim(theory, slug, i + 1, c) for i, c in enumerate(deduped)) if c]
        for i, c in enumerate(claims, 1):
            c.claim_id = f"{slug}_{prefix}{i:03d}"
        dumped = []
        for c in claims:
            d = c.model_dump()
            d["agreement"] = _haiku(theory, d, by_id)  # same-family Haiku cross-check (parity)
            dumped.append(d)
        return dumped
    cc = mk(raw, "c", False)
    nn = mk(nraw, "n", True)
    tt = mk(traw, "t", True)
    return {"c": cc, "n": nn, "t": tt}


# ---- oracle-light gate ---- #
def _fam(v):
    return value_family(str(v))


def canonical(slug):
    p = ENGINE / "data" / "claims" / f"{slug}_approved.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def nearest_canonical(claim, canon):
    """best canonical match by field-overlap; returns (match, differing_fields)."""
    best, best_score, best_diff = None, -1, None
    cf = _fam(claim["value"])
    for a in canon:
        fields = {"entity_type": a.get("entity_type") == claim["entity_type"],
                  "axis": a.get("axis") == claim["axis"],
                  "polarity": a.get("polarity") == claim["polarity"],
                  "value_family": bool(_fam(a.get("value")) & cf) or a.get("value") == claim["value"]}
        score = sum(fields.values())
        if score > best_score:
            best, best_score, best_diff = a, score, [k for k, ok in fields.items() if not ok]
    return best, best_diff


def main() -> int:
    out = {}
    for theory, slug in THEORIES:
        print(f"[KR1-v2] extracting {theory} …")
        out[slug] = run_theory(theory, slug)
        print(f"  {theory}: c={len(out[slug]['c'])} n={len(out[slug]['n'])} t={len(out[slug]['t'])}")

    d = SPRINT / "runs" / "KR1" / "KR1-2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "v2_claims.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))

    # oracle-light: rows = v2 claims whose fields differ from nearest canonical
    rows, total = [], 0
    for theory, slug in THEORIES:
        canon = canonical(slug)
        for cls in ("c", "n", "t"):
            for c in out[slug][cls]:
                total += 1
                match, diff = nearest_canonical(c, canon)
                if diff:  # differs from nearest canonical on >=1 field
                    rows.append({"theory": theory, "v2_claim_id": c["claim_id"], "entity_type": c["entity_type"],
                                 "axis": c["axis"], "polarity": c["polarity"], "value": c["value"],
                                 "statement": c["statement"][:160],
                                 "nearest_canonical": match["claim_id"] if match else "",
                                 "differing_fields": "|".join(diff), "haiku_agree": c.get("agreement"), "decision": ""})
    frac = len(rows) / total if total else 0.0
    full = frac > 0.30
    if full:  # >30% differ → full packet (all v2 claims)
        rows = []
        for theory, slug in THEORIES:
            canon = canonical(slug)
            for cls in ("c", "n", "t"):
                for c in out[slug][cls]:
                    match, diff = nearest_canonical(c, canon)
                    rows.append({"theory": theory, "v2_claim_id": c["claim_id"], "entity_type": c["entity_type"],
                                 "axis": c["axis"], "polarity": c["polarity"], "value": c["value"],
                                 "statement": c["statement"][:160],
                                 "nearest_canonical": match["claim_id"] if match else "",
                                 "differing_fields": "|".join(diff) or "(matches canonical)", "haiku_agree": c.get("agreement"), "decision": ""})

    rev = SPRINT / "review"
    rev.mkdir(exist_ok=True)
    with open(rev / "kr1_v2_claims.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["theory", "v2_claim_id", "entity_type", "axis", "polarity",
                                          "value", "statement", "nearest_canonical", "differing_fields", "haiku_agree", "decision"])
        w.writeheader()
        w.writerows(rows)
    (rev / "kr1_v2_claims.md").write_text(
        f"""# KR1 v2 re-extraction — oracle-light review  [AWAITING-ANU]

Role: approver applying the published codebook. instrument v2 re-extracted IIT+GNWT
({total} claims). Oracle-light: {'FULL packet (>30% differ from canonical)' if full else f'{len(rows)}/{total} claims DIFFER from nearest canonical'}.
Set `decision` per row ∈ {{approve, reject, edit-value}}. Unlisted claims match a canonical
claim and are carried as approved. EXAMPLES: `approve` (typing is correct); `reject` (not
supported / mis-typed); `edit-value: <token>` (fix the value). Companion schema: review/kr1_v2_schema.json.

{len(rows)} rows → review/kr1_v2_claims.csv
""")
    (rev / "kr1_v2_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["approve", "reject", "edit-value"]},
         "edit-value": {"format": "edit-value: <snake_case_token>"}}, indent=2))

    print(f"[KR1-v2] total v2 claims {total}; differ-from-canonical {sum(1 for r in rows if r['differing_fields'] not in ('', '(matches canonical)'))}; "
          f"packet {'FULL' if full else 'oracle-light'} {len(rows)} rows")
    print(f"[KR1-v2] meter spent ${CLIENT.meter.data['total_usd']:.4f}")
    print(f"AWAITING-ANU: review/kr1_v2_claims.csv  (then: pipeline/kr1_v2_diff.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
