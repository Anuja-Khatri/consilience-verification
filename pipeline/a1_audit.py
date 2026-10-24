#!/usr/bin/env python3
"""
pipeline/a1_audit.py — A1 rule-based audit of the MIU discoveries (SPEC §A1).

MIU-data-only; no engine instrument, no rebuild (A1 ∥ A5). READ-ONLY on ~/miu-demo.

Implemented: A1.1 discovery resolution; A1.2 match sample (30); A1.3 criteria
  C1 provenance (mechanical), C3 Newman screen (mechanical), C5 scale (mechanical),
  C2 relation-support (gpt-4.1 drafts → oracle packet), C4 testability (worksheet,
  PASS-PENDING-C4). A1.4 verdicts are computed PROVISIONALLY on C1/C3/C5 and finalized
  after the C2 packet returns (pipeline/a1_finalize.py). Emits the C2 packet (AWAITING-ANU).
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
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
MIU = Path(os.path.expanduser(CFG["paths"]["miu"]))
OUT = SPRINT / "results"
REV = SPRINT / "review"

import llm as L  # noqa: E402
from p5_judge import _GENERIC, _STOP  # noqa: E402  (ported Newman stems)

DEMO_DATA = MIU / "demo" / "demo_data.json"
ALL_CLAIMS = MIU / "correspondences" / "_index" / "all_claims.json"
MATCH_FILES = {
    "correspondences": MIU / "correspondences" / "correspondences.json",
    "supplementary": MIU / "correspondences" / "supplementary" / "supplementary_matches.json",
    "engine-discovered": MIU / "correspondences" / "engine-discovered" / "engine_discovered_matches.json",
}
SEED = CFG["seeds"]["global"]
SCALE_ORDER = ["planck", "quantum", "molecular", "cellular", "neural", "organism", "social", "cosmological"]
STOPWORDS = {"the", "and", "that", "this", "with", "from", "which", "into", "than", "then",
             "they", "them", "their", "there", "when", "what", "where", "whom", "whose",
             "have", "has", "been", "being", "are", "was", "were", "for", "not", "but",
             "its", "it's", "one", "two", "more", "most", "such", "both", "each", "any",
             "all", "can", "may", "will", "would", "could", "should", "between", "within"}
NAMES = {"tononi", "hagelin", "maharishi", "koch", "dehaene", "friston", "beggs", "plenz",
         "casali", "massimini", "samkhya", "vedanta", "bohm"}


# ── normalization (C1) ──
_LIG = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}


def normalize(t: str) -> str:
    for k, v in _LIG.items():
        t = t.replace(k, v)
    t = t.replace("­", "")  # soft hyphen
    t = re.sub(r"[‘’‛′]", "'", t)
    t = re.sub(r"[“”″]", '"', t)
    t = re.sub(r"[‐-―]", "-", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ── loaders ──
def load_claims_index():
    """Merge the main + supplementary + engine-discovered claim indexes (§A1.2)."""
    idx = {}
    paths = [ALL_CLAIMS,
             MIU / "correspondences" / "supplementary" / "new_claims_index.json",
             MIU / "correspondences" / "engine-discovered" / "ed_claims_index.json"]
    for p in paths:
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        items = data if isinstance(data, list) else data.get("claims", [])
        for c in items:
            if isinstance(c, dict) and c.get("claim_id"):
                idx.setdefault(c["claim_id"], c)
    return idx


def load_matches():
    out = []
    for src, p in MATCH_FILES.items():
        if not p.exists():
            continue
        for m in json.loads(p.read_text()):
            m = dict(m)
            m["_src"] = src
            out.append(m)
    return out


def resolve_discoveries() -> dict:
    d = json.loads(DEMO_DATA.read_text())
    rows, halts = [], []
    for x in d["discoveries"]:
        ca, cb = x.get("claim_a") or {}, x.get("claim_b") or {}
        if not ca.get("id") or not cb.get("id"):
            halts.append(x.get("id")); continue
        rows.append({"id": x.get("id"), "title": x.get("title"), "grade": x.get("grade"),
                     "provenance": x.get("provenance"), "match_ref": f"{ca['id']}__{cb['id']}",
                     "side_a": {"claim_id": ca["id"]}, "side_b": {"claim_id": cb["id"]}})
    if halts:
        raise SystemExit(f"HALT-ASK (§A1.1): discoveries lacking claim ids: {halts}")
    return {"n_discoveries": len(rows), "discoveries": rows}


# ── A1.2 match sample ──
def pick_sample(matches, discoveries, n=30):
    import random
    rng = random.Random(SEED)
    bypair = {}
    for m in matches:
        bypair[frozenset((m["claim_a"], m["claim_b"]))] = m
    chosen, seen_ids = [], set()
    # discovery-underlying first
    for disc in discoveries:
        key = frozenset((disc["side_a"]["claim_id"], disc["side_b"]["claim_id"]))
        m = bypair.get(key)
        if m and m["match_id"] not in seen_ids:
            chosen.append({**m, "_discovery": disc["id"]}); seen_ids.add(m["match_id"])
    # forced minima: ≥5 engine-discovered, ≥3 supplementary
    def fill_from(src, k):
        pool = [m for m in matches if m["_src"] == src and m["match_id"] not in seen_ids]
        rng.shuffle(pool)
        for m in pool[:k]:
            chosen.append({**m, "_discovery": None}); seen_ids.add(m["match_id"])
    have_ed = sum(1 for m in chosen if m["_src"] == "engine-discovered")
    have_sp = sum(1 for m in chosen if m["_src"] == "supplementary")
    fill_from("engine-discovered", max(0, 5 - have_ed))
    fill_from("supplementary", max(0, 3 - have_sp))
    # proportional random fill to n across the three files
    rest = [m for m in matches if m["match_id"] not in seen_ids]
    rng.shuffle(rest)
    for m in rest:
        if len(chosen) >= n:
            break
        chosen.append({**m, "_discovery": None}); seen_ids.add(m["match_id"])
    return chosen[:n]


# ── A1.3 criteria ──
def pagetext_for(claim, idx_cache):
    sf = claim.get("source_file", "")
    stem = Path(sf).stem
    if stem in idx_cache:
        return idx_cache[stem]
    hits = list((MIU / "extraction_text").rglob(f"{stem}.pagetext.txt"))
    txt = normalize(hits[0].read_text(errors="ignore")) if hits else ""
    idx_cache[stem] = txt
    return txt


def c1_provenance(claim, idx_cache):
    src = normalize(claim.get("source_sentence", ""))
    page = pagetext_for(claim, idx_cache)
    if not src:
        return {"status": "FAIL", "provenance": "no source_sentence"}
    if not page:
        return {"status": "FAIL", "provenance": "no pagetext for source_file"}
    if src in page:
        return {"status": "PASS", "provenance": "exact"}
    # fuzzy sliding window (difflib)
    import difflib
    best = 0.0
    L_ = len(src)
    sm = difflib.SequenceMatcher(None, src, "")
    sm.set_seq1(src)
    step = max(1, L_ // 2)
    for i in range(0, max(1, len(page) - L_), step):
        sm.set_seq2(page[i:i + L_ + 20])
        r = sm.quick_ratio()
        if r > best:
            best = r
    status = "PASS" if best >= 0.93 else "FAIL"
    return {"status": status, "provenance": f"fuzzy({best:.2f})"}


def content_stems(text):
    toks = [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4]
    stems = set()
    for w in toks:
        if w in _STOP or w in STOPWORDS or w in NAMES:
            continue
        s = w[:5]
        if s in _GENERIC:
            continue
        stems.add(s)
    return stems


def c3_newman(ca, cb):
    """FAIL iff the two claim_texts share ≥2 non-generic content stems that also co-occur
    in both source quotes."""
    sa, sb = content_stems(ca.get("claim_text", "")), content_stems(cb.get("claim_text", ""))
    shared = sa & sb
    qa, qb = content_stems(ca.get("source_sentence", "")), content_stems(cb.get("source_sentence", ""))
    in_both_quotes = {s for s in shared if s in qa and s in qb}
    status = "FAIL" if len(in_both_quotes) >= 2 else "PASS"
    return {"status": status, "shared_stems": sorted(in_both_quotes), "n": len(in_both_quotes)}


def c5_scale(ca, cb):
    sa, sb = ca.get("scale"), cb.get("scale")
    if sa == "metaphysical" or sb == "metaphysical":
        return {"status": "PASS", "note": "metaphysical wildcard", "scales": [sa, sb]}
    if sa not in SCALE_ORDER or sb not in SCALE_ORDER:
        return {"status": "FAIL", "note": f"scale not in enum ({sa},{sb})", "scales": [sa, sb]}
    dist = abs(SCALE_ORDER.index(sa) - SCALE_ORDER.index(sb))
    status = "PASS" if dist <= 1 else "FAIL"
    return {"status": status, "distance": dist, "scales": [sa, sb]}


C2_SYSTEM = ("You check whether a quoted sentence, by itself, states a given relational structure. "
             "Answer from the quote alone; the surrounding write-up does not count. Output ONLY JSON: "
             '{"supported": true|false, "missing": "<what the quote does not state, or empty>"}')


def c2_relation(claim):
    user = (f"Quote: {claim.get('source_sentence','')}\n"
            f"Claimed structure: {claim.get('claim_text','')}\n"
            "Does the quote itself state this structure?")
    rec = L.default().call_json(task_id="A1", model=CFG["models"]["verifier"], system=C2_SYSTEM,
                                messages=[{"role": "user", "content": user}], replicate_tag="r0",
                                temperature=0, max_tokens=300)
    p = rec.get("parsed") or {}
    return {"supported": bool(p.get("supported")), "missing": p.get("missing", ""),
            "json_status": rec.get("json_status")}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True); REV.mkdir(exist_ok=True)
    idx = load_claims_index()
    matches = load_matches()
    dmap = resolve_discoveries()
    (OUT / "a1_discovery_map.json").write_text(json.dumps(dmap, ensure_ascii=False, indent=2) + "\n")
    sample = pick_sample(matches, dmap["discoveries"])
    print(f"A1.1: {dmap['n_discoveries']}/9 discoveries. A1.2: {len(sample)} matches "
          f"(ED={sum(1 for m in sample if m['_src']=='engine-discovered')}, "
          f"supp={sum(1 for m in sample if m['_src']=='supplementary')}, "
          f"disc-underlying={sum(1 for m in sample if m.get('_discovery'))})")

    idx_cache = {}
    rows, c2_packet, c4_worksheet = [], [], []
    import random
    rng = random.Random(SEED)
    for m in sample:
        ca, cb = idx.get(m["claim_a"]), idx.get(m["claim_b"])
        rec = {"match_id": m["match_id"], "src": m["_src"], "discovery": m.get("_discovery"),
               "claim_a": m["claim_a"], "claim_b": m["claim_b"], "sides": {}}
        # C3/C5 are per-match (symmetric); SKIP if a claim is missing from the indexes
        c5 = c5_scale(ca, cb) if (ca and cb) else {"status": "SKIP", "note": "missing claim"}
        rec["C3"] = c3_newman(ca, cb) if (ca and cb) else {"status": "SKIP", "note": "missing claim"}
        rec["C5"] = c5
        for side, c in (("a", ca), ("b", cb)):
            if not c:
                rec["sides"][side] = {"missing_claim": True}; continue
            c1 = c1_provenance(c, idx_cache)
            c2 = c2_relation(c)
            rec["sides"][side] = {"C1": c1, "C5": c5, "C2": c2}
            # C2 packet: all supported:false + 20% of true (spot-check)
            if not c2["supported"] or rng.random() < 0.20:
                c2_packet.append({"match_id": m["match_id"], "side": side, "claim_id": c["claim_id"],
                                  "quote": (c.get("source_sentence") or "")[:300],
                                  "claimed_structure": (c.get("claim_text") or "")[:300],
                                  "model_supported": c2["supported"], "model_missing": c2["missing"],
                                  "decision": ""})
            # C4 worksheet for measurable_with assertions
            if c.get("measurable") and c.get("measurable_with"):
                c4_worksheet.append({"match_id": m["match_id"], "side": side, "claim_id": c["claim_id"],
                                     "instrument": c.get("measurable_with"),
                                     "query": f"does {c.get('measurable_with')} measure {c.get('claim_text','')[:80]}",
                                     "citation_url": "", "citation_title": "", "verdict": "PASS-PENDING-C4"})
        rows.append(rec)

    (OUT / "a1_match_sample.json").write_text(json.dumps({"n": len(rows), "matches": rows}, ensure_ascii=False, indent=2) + "\n")

    # C2 oracle packet
    with open(REV / "a1_c2_relation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["match_id", "side", "claim_id", "quote", "claimed_structure",
                                          "model_supported", "model_missing", "decision"])
        w.writeheader(); w.writerows(c2_packet)
    (REV / "a1_c2_relation.md").write_text(
        f"""# A1-C2 relation-support review  [AWAITING-ANU]

Role: approver by READING the quote alone. For each row, does the QUOTE (by itself) state the
claimed relational structure? `decision` ∈ {{supported, not-supported}}. All model `supported:false`
rows are here, plus a 20% spot-check of `true`. EXAMPLES: `supported` (quote states it);
`not-supported` (quote does not state the structure). Schema: review/a1_c2_schema.json.

{len(c2_packet)} rows → review/a1_c2_relation.csv
""")
    (REV / "a1_c2_schema.json").write_text(json.dumps({"decision": {"allowed": ["supported", "not-supported"]}}, indent=2))
    # C4 worksheet
    with open(REV / "a1_c4_citations.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["match_id", "side", "claim_id", "instrument", "query",
                                          "citation_url", "citation_title", "verdict"])
        w.writeheader(); w.writerows(c4_worksheet)

    # provisional mechanical summary
    def pf(k):
        return sum(1 for r in rows for s in r["sides"].values() if isinstance(s, dict) and s.get(k, {}).get("status") == "PASS")
    print(f"A1.3 mechanical (provisional): C1 PASS sides={pf('C1')}; "
          f"C3 PASS matches={sum(1 for r in rows if r.get('C3',{}).get('status')=='PASS')}/{len(rows)}; "
          f"C5 PASS sides={pf('C5')}")
    print(f"C2 packet: {len(c2_packet)} rows (AWAITING-ANU: review/a1_c2_relation.csv); "
          f"C4 worksheet: {len(c4_worksheet)} rows")
    print(f"meter spent ${L.default().meter.data['total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
