#!/usr/bin/env python3
"""
pipeline/a2_adjudicate.py — A2.1 slicing + A2.2 extract_lite + A2.3 oracle gate (SPEC §A2).

Re-adjudicates the 17 frozen A2 pairs (results/a2_pairs.json: 2 A1 survivors + 15 stratified
failures) through the production pipeline under instrument v2:

  A2.1  passage slicing — locate each side's source_sentence via the A1-C1 matcher inside the
        containing `===== PAGE n =====` block (plain .txt sources with no markers = one block),
        window ±2 sentences via the copied split_sentences (min 2 / max 6), passage_id
        `mius_<matchid>_<side>_<k>`. (No .srt sources in the 17 pairs; the ±4-line SRT corner
        is implemented for completeness.)
  A2.2  extract_lite — pipeline/extract_lite.py (p2 replica, v2 instrument) per side.  REAL spend.
  A2.3  oracle gate — review/a2_claims.csv (approve/reject/edit-value) → AWAITING-ANU.

A2.4 vocab discipline, A2.5 judge+decidability, A2.6 comparison run AFTER the packet returns
(pipeline/a2_finalize.py); a PRELIMINARY per-pair axis:none rate is reported here only.
Disclosure (D-035): decisions in the packet are model-drafted suggestions for Anu to confirm.
"""
from __future__ import annotations

import argparse
import csv
import difflib
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

import a1_audit as A1  # noqa: E402  (normalize/pagetext_for/load_claims_index/load_matches)
from split_sentences import split_sentences  # noqa: E402  (W0.4 verbatim copy of engine p1)
import llm as L  # noqa: E402

PAGE_RE = re.compile(r"=====\s*PAGE\s+\d+\s*=====")
SRT_TS_RE = re.compile(r"^\d+$|-->")


# ── A2.1 passage slicing ───────────────────────────────────────────────────
def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).quick_ratio()


def _side_fulltext(claim, cache) -> str:
    """Full normalized source text for a side: the PDF pagetext if present, else the raw
    source_file (handles .txt sources, which pagetext_for does not index)."""
    pg = A1.pagetext_for(claim, cache)
    if pg:
        return pg
    sf = claim.get("source_file", "") or ""
    for cand in ([MIU / sf] if sf else []) + list(MIU.rglob(f"{Path(sf).stem}.txt") if sf else []):
        if cand.is_file():
            return A1.normalize(cand.read_text(errors="ignore"))
    return ""


def _page_blocks(text: str):
    blocks = [b.strip() for b in PAGE_RE.split(text) if b.strip()]
    return blocks or ([text.strip()] if text.strip() else [])


def _block_best_sentence_ratio(block: str, src: str) -> float:
    sents = [s.strip() for s in split_sentences(block) if s.strip()]
    if not sents:
        return _ratio(src, block)
    return max(1.0 if (src and src in s) else _ratio(src, s) for s in sents)


def _best_block(blocks, src: str) -> str:
    for b in blocks:                      # exact-substring page wins (A1-C1 exact)
        if src and src in b:
            return b
    # else: the block whose BEST SENTENCE matches src (robust; whole-block ratio dilutes)
    return max(blocks, key=lambda b: _block_best_sentence_ratio(b, src)) if blocks else ""


def _window(block: str, src: str):
    """±2 sentences around the best-matching sentence, clamped to [2, 6].
    Returns (window_text, best_sentence_ratio) — the ratio is the genuine A1-C1 locate signal
    (short source_sentence vs its single best sentence), not diluted over the whole window."""
    sents = [s.strip() for s in split_sentences(block) if s.strip()]
    if not sents:
        return block[:1200].strip(), 0.0
    ratios = [1.0 if (src and src in s) else _ratio(src, s) for s in sents]
    j = max(range(len(sents)), key=lambda k: ratios[k])
    lo, hi = max(0, j - 2), min(len(sents), j + 3)
    while hi - lo < 2 and (lo > 0 or hi < len(sents)):
        if lo > 0:
            lo -= 1
        elif hi < len(sents):
            hi += 1
    win = sents[lo:hi][:6]                 # max 6
    return " ".join(win).strip(), ratios[j]


def _slice_srt(claim, src, cache) -> str:
    sf = claim.get("source_file", "") or ""
    raw = ""
    for cand in ([MIU / sf] if sf else []) + list(MIU.rglob(f"{Path(sf).stem}.srt") if sf else []):
        if cand.is_file():
            raw = cand.read_text(errors="ignore"); break
    lines = [A1.normalize(l) for l in raw.splitlines()
             if l.strip() and not SRT_TS_RE.search(l.strip())]
    if not lines:
        return ""
    j = max(range(len(lines)), key=lambda k: _ratio(src, lines[k]))
    return " ".join(lines[max(0, j - 4): j + 5]).strip()   # ±4 subtitle lines


def slice_side(claim, matchid, side, cache):
    src = A1.normalize(claim.get("source_sentence", "") or "")
    sf = claim.get("source_file", "") or ""
    if sf.lower().endswith(".srt"):
        text = _slice_srt(claim, src, cache)
        block_src = "srt"
        sent_ratio = 1.0
    else:
        full = _side_fulltext(claim, cache)
        if not full:
            return {"passages": [], "note": "no source text located", "block_src": "none"}
        block = _best_block(_page_blocks(full), src)
        text, sent_ratio = _window(block, src)
        block_src = "pagetext/raw"
    if not text:
        return {"passages": [], "note": "empty slice", "block_src": block_src}
    located = bool(src) and sent_ratio >= 0.85    # genuine A1-C1 sentence-level locate
    return {"passages": [{"passage_id": f"mius_{matchid}_{side}_1", "text": text}],
            "located": located, "locate_ratio": round(float(sent_ratio), 3), "block_src": block_src}


def build_passages():
    idx = A1.load_claims_index()
    matches = {m["match_id"]: m for m in A1.load_matches()}
    pairs = json.loads((OUT / "a2_pairs.json").read_text())["pairs"]
    cache = {}
    out = {"n_pairs": len(pairs), "pairs": []}
    for p in pairs:
        m = matches[p["match_id"]]
        rec = {"match_id": p["match_id"], "role": p["role"], "a1_first_fail": p["a1_first_fail"],
               "old_grade": p["old_grade"], "old_decidability": p["old_decidability"], "sides": {}}
        for side, cid in (("a", m["claim_a"]), ("b", m["claim_b"])):
            c = idx.get(cid)
            if not c:
                rec["sides"][side] = {"claim_id": cid, "missing_claim": True, "passages": []}
                continue
            s = slice_side(c, p["match_id"], side, cache)
            s.update({"claim_id": cid, "domain": c.get("domain") or c.get("_corpus") or "cross-domain",
                      "source_file": c.get("source_file"), "source_sentence": c.get("source_sentence")})
            rec["sides"][side] = s
        out["pairs"].append(rec)
    (OUT / "a2_passages.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return out


# ── A2.2 + A2.3 ─────────────────────────────────────────────────────────────
def run():
    from extract_lite import extract_lite, MAIN_V2  # noqa: E402  (deferred: triggers engine import)
    passages = build_passages()
    client = L.LLM()
    per_pair = []
    for rec in passages["pairs"]:
        pair_out = {"match_id": rec["match_id"], "role": rec["role"], "a1_first_fail": rec["a1_first_fail"],
                    "old_grade": rec["old_grade"], "old_decidability": rec["old_decidability"], "sides": {}}
        for side, s in rec["sides"].items():
            claims = []
            if s.get("passages"):
                slug = f"mius_{rec['match_id']}_{side}"
                claims = extract_lite(s["passages"], theory=s.get("domain", "cross-domain"),
                                      slug=slug, client=client, replicate_tag="a2", task_id="A2")
            pair_out["sides"][side] = {"claim_id": s.get("claim_id"), "domain": s.get("domain"),
                                       "located": s.get("located"), "source_file": s.get("source_file"),
                                       "passage": (s["passages"][0]["text"] if s.get("passages") else ""),
                                       "passage_id": (s["passages"][0]["passage_id"] if s.get("passages") else None),
                                       "claims": claims}
        per_pair.append(pair_out)

    rundir = SPRINT / "runs" / "A2" / "A2-1"
    rundir.mkdir(parents=True, exist_ok=True)
    (rundir / "v2_claims.json").write_text(json.dumps({"instrument_tag": "v2", "pairs": per_pair},
                                                      ensure_ascii=False, indent=2) + "\n")

    # A2.4 PRELIMINARY per-pair axis:none rate (final finding computed on APPROVED claims post-packet)
    prelim = []
    for pr in per_pair:
        allc = [c for s in pr["sides"].values() for c in s["claims"]]
        none_n = sum(1 for c in allc if c.get("axis") == "none")
        prelim.append({"match_id": pr["match_id"], "n_claims": len(allc), "axis_none": none_n,
                       "axis_none_frac": round(none_n / len(allc), 3) if allc else None})

    # A2.3 oracle gate packet
    rows = []
    for pr in per_pair:
        for side, s in pr["sides"].items():
            quote = s["passage"][:300]
            for c in s["claims"]:
                rows.append({"match_id": pr["match_id"], "side": side, "claim_id": c["claim_id"],
                             "statement": c["statement"][:200], "type": c["entity_type"], "axis": c["axis"],
                             "value": c["value"], "polarity": c["polarity"], "quote": quote, "decision": ""})
    REV.mkdir(exist_ok=True)
    with open(REV / "a2_claims.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["match_id", "side", "claim_id", "statement", "type", "axis",
                                          "value", "polarity", "quote", "decision"])
        w.writeheader(); w.writerows(rows)
    (REV / "a2_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["approve", "reject", "edit-value"]},
         "edit-value": {"format": "edit-value: <snake_case_token>"}}, indent=2))
    n_sides = sum(1 for pr in per_pair for _ in pr["sides"])
    n_located = sum(1 for pr in per_pair for s in pr["sides"].values() if s.get("located"))
    (REV / "a2_claims.md").write_text(
        f"""# A2 MIU re-adjudication — claim review  [AWAITING-ANU]

Role: **annotator applying the published codebook.** Instrument v2 re-extracted claims from the
source passages of {passages['n_pairs']} MIU pairs (2 A1 survivors + 15 stratified A1 failures).
For each row set `decision` ∈ {{approve, reject, edit-value}} by reading the quote against the
published entity_type/axis codebook. EXAMPLES: `approve` (typing matches the quote);
`reject` (not supported by the quote / mis-typed); `edit-value: <token>` (fix only the value).
Companion schema: review/a2_schema.json.  Disclosure (D-035): these rows are model-drafted
suggestions for your review and confirmation.

{len(rows)} claims across {n_sides} sides ({n_located} sides had their source_sentence re-located) → review/a2_claims.csv
After approval: pipeline/a2_finalize.py runs A2.4 (vocab discipline) + A2.5 (judge/decidability) + A2.6 (comparison).
""")
    # manifest
    from runmanifest import write_manifest, input_ref  # noqa: E402
    write_manifest("A2", "A2-1", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(OUT / "a2_pairs.json"), "read-only"),
                           input_ref(str(OUT / "a2_passages.json"), "read-only"),
                           input_ref(str(SPRINT / "results" / "instrument_v2_freeze.json"), "read-only")],
                   outputs=["runs/A2/A2-1/v2_claims.json", "results/a2_passages.json", "review/a2_claims.csv"],
                   seeds={"global": CFG["seeds"]["global"]},
                   model_provenance=[{"role": "extractor", "model": CFG["models"]["extractor"],
                                      "instrument": "v2", "provider_seed_honored": False}],
                   notes="A2.1 slice + A2.2 extract_lite (p2 replica, v2) + A2.3 oracle gate; A2.4-6 post-packet.")

    (OUT / "a2_prelim_vocab.json").write_text(json.dumps({"pairs": prelim}, ensure_ascii=False, indent=2) + "\n")
    print(f"[A2] pairs={passages['n_pairs']} sides={n_sides} relocated={n_located} "
          f"claims_extracted={len(rows)}")
    print(f"[A2] preliminary axis:none pairs >50%: "
          f"{[p['match_id'] for p in prelim if p['axis_none_frac'] and p['axis_none_frac'] > 0.5]}")
    print(f"[A2] meter total ${client.meter.data['total_usd']:.4f}")
    print("AWAITING-ANU: review/a2_claims.csv  (then: pipeline/a2_finalize.py)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice-only", action="store_true", help="A2.1 slicing only, no spend")
    args = ap.parse_args()
    if args.slice_only:
        out = build_passages()
        loc = sum(1 for pr in out["pairs"] for s in pr["sides"].values() if s.get("located"))
        sides = sum(1 for pr in out["pairs"] for _ in pr["sides"])
        print(f"[A2.1] sliced {out['n_pairs']} pairs / {sides} sides; relocated {loc}; "
              f"empty {sum(1 for pr in out['pairs'] for s in pr['sides'].values() if not s.get('passages'))}")
        return 0
    return run()


if __name__ == "__main__":
    sys.exit(main())
