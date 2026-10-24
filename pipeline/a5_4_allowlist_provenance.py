#!/usr/bin/env python3
"""
pipeline/a5_4_allowlist_provenance.py — owner-requested provenance for the 7 A5.4 allowlisted runs.

For each allowlisted ≥8-word run, report: (a) the extraction OUTPUT + source passage it came from,
(b) the KEY location (which key doc contains it), (c) whether the same wording appears in any
engine-corpus passage in NON-EXACT form. The allowlist is held PROVISIONAL until the owner confirms;
if any run cannot be traced to engine-passage content → HALT-ASK (exit 2).

Writes docs/a5_4_allowlist_provenance.md (docs/ is non-scanned; the runs are public IIT doctrine).
Key text read in-memory only (which key contains the run is reported as a source label, not a
holdout doc_id).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
import ngram_guard as G  # noqa: E402


def _norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def walk_claims(obj, out):
    if isinstance(obj, dict):
        if "statement" in obj and isinstance(obj["statement"], str):
            out.append(obj)
        for v in obj.values():
            walk_claims(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_claims(v, out)


def main() -> int:
    runs = sorted(ALLOW for ALLOW in G._allowlist())
    # extraction outputs → claim dicts
    claims = []
    srcmap = {}
    for f in ["runs/A5/A5.1/runs.json", "runs/KR1/KR1-2/v2_claims.json"]:
        cl = []
        walk_claims(json.loads((SPRINT / f).read_text()), cl)
        for c in cl:
            srcmap[id(c)] = f
        claims += cl
    # engine passages
    eng = {}
    for txt, did, yr in G.engine_passages():
        eng[len(eng)] = (txt, did)
    # key texts (in-memory) + source labels
    keys = G.load_key_texts_year()

    def contig_subrun_in_engine(run_words):
        """longest contiguous subsequence of run_words that appears (as a phrase) in some engine passage."""
        best, best_pid = 0, None
        for _, (txt, did) in eng.items():
            nt = _norm(txt)
            for L in range(len(run_words), 2, -1):
                hit = False
                for i in range(len(run_words) - L + 1):
                    if " ".join(run_words[i:i + L]) in nt:
                        if L > best:
                            best, best_pid, hit = L, did, True
                        break
                if hit:
                    break
        return best, best_pid

    def words_in_single_passage(run_words):
        best = 0
        for _, (txt, did) in eng.items():
            pw = set(re.findall(r"[a-z0-9]+", txt.lower()))
            n = sum(1 for w in run_words if w in pw)
            best = max(best, n)
        return best

    lines = ["# A5.4 allowlist provenance — the 7 acknowledged-benign key-unique runs (PROVISIONAL)\n",
             "Owner-requested trace. The allowlist (`pipeline/ngram_allowlist.txt`) is **PROVISIONAL** "
             "until the owner confirms; reported in the KR1 v2 caveat meanwhile. Each run is convergent "
             "canonical IIT doctrine. (a) extraction output + source passage; (b) key location; "
             "(c) non-exact engine-passage presence.\n"]
    halt = []
    for r in runs:
        rw = r.split()
        # (a) extraction output(s) + passage(s)
        hits = [(c, srcmap[id(c)]) for c in claims if r in _norm(c["statement"])]
        a_out = []
        for c, f in hits[:3]:
            pids = c.get("passage_ids", [])
            a_out.append(f"`{f}` claim `{c.get('claim_id', c.get('value', '?'))}` (passages {pids})")
        # (b) key location
        in_keys = [src for _kid, (txt, _yr, src) in keys.items() if r in _norm(txt)]
        # (c) non-exact engine presence
        subrun, pid = contig_subrun_in_engine(rw)
        nwords = words_in_single_passage(rw)
        traceable = (nwords >= 6) or (subrun >= 4)
        if not traceable:
            halt.append(r)
        lines += [f"\n## \"{r}\"\n",
                  f"- (a) extraction output(s): {'; '.join(a_out) if a_out else 'NOT FOUND in A5.1/KR1 outputs'}\n",
                  f"- (b) key location: {sorted(set(in_keys)) if in_keys else 'NOT in key texts (unexpected)'}\n",
                  f"- (c) engine non-exact: longest contiguous subrun in an engine passage = **{subrun} words** "
                  f"(e.g. {pid}); {nwords}/{len(rw)} run words present in a single engine passage → "
                  f"**{'TRACEABLE' if traceable else 'UNTRACEABLE'}**\n"]
    (SPRINT / "docs" / "a5_4_allowlist_provenance.md").write_text("".join(lines))
    print(f"A5.4 allowlist provenance → docs/a5_4_allowlist_provenance.md ({len(runs)} runs).")
    print(f"  traceable: {len(runs) - len(halt)}/{len(runs)}; untraceable: {halt}")
    if halt:
        print(f"HALT-ASK: {len(halt)} allowlisted run(s) NOT traceable to engine-passage content.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
