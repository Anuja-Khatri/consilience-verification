#!/usr/bin/env python3
"""
pipeline/a6_map.py — A6 mapping table build + Anu packet (SPEC §A6, scope v1 = IIT+GNWT).

Builds `corpora/obfuscation_map.yaml` (theory_names, coined_terms, people) as a PROPOSAL and
emits the A6-map Anu packet (approve/reject/edit). The obfuscated + clean-rerun extraction
(a6_run.py) runs ONLY after approval and both on the SAME date (v2.0.4 D2 noise-floor control).

Design rules (§A6): token-count-preserving where possible (multiword→multiword), casing-pattern
preserved at apply-time, COLLISION-checked (a target must not already occur in the corpus — else
de-map is ambiguous), reversible, map stored OUTSIDE hashed artifact dirs (corpora/), applied to
PASSAGES post-ingest never PDFs. Where a spec-given target would collide or change token count, the
deviation is recorded per-entry (e.g. ignition→"broadcast surge" collides with the existing token
"broadcast" → proposed "kindling surge" instead, flagged for Anu). No API, no spend.
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
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))

# ---- proposed mappings (source lowercased; apply-time regenerates casing variants) ----
THEORY_NAMES = {
    "integrated information theory": "theory kappa framework",   # 3→3 tokens
    "iit": "tk",                                                 # acronym → coined acronym (1→1)
    "global neuronal workspace": "central neuronal exchange",    # 3→3
    "global workspace theory": "central exchange theory",        # 3→3
    "global workspace": "central exchange",                      # 2→2 (spec)
    "gnwt": "cne",                                               # acronym (1→1)
    "gwt": "cet",                                                # acronym (1→1)
}
COINED_TERMS = {
    "integrated information": "quantified integration",  # spec "Q-information"; 2→2 token-preserving variant
    "φ": "q-measure", "phi": "q-measure",                # spec
    "ignition": "kindling surge",                        # spec target "broadcast surge" COLLIDES with token
                                                         #   "broadcast" (×38) → "kindling surge" (flagged)
    "workspace neurons": "exchange neurons",             # spec
    "maximally irreducible": "maximally indivisible",    # 2→2
    "cause-effect power": "drive-response power",         # 2→2
    "global availability": "central availability",       # 2→2
}
# K = IIT-side authors, L = GNWT-side authors (§A6 pattern Tononi→K1, Dehaene→L1, …)
PEOPLE = {
    "tononi": "Author K1", "koch": "Author K2", "albantakis": "Author K3", "oizumi": "Author K4",
    "massimini": "Author K5", "boly": "Author K6", "marshall": "Author K7", "grasso": "Author K8",
    "findlay": "Author K9", "barbosa": "Author K10", "edelman": "Author K11",
    "dehaene": "Author L1", "changeux": "Author L2", "mashour": "Author L3", "kouider": "Author L4",
    "naccache": "Author L5", "baars": "Author L6", "sergent": "Author L7", "lau": "Author L8",
}


def load_passages(slug):
    out = []
    for ln in (ENGINE / "data" / "passages" / f"{slug}.jsonl").read_text().splitlines():
        if ln.strip():
            out.append(json.loads(ln))
    return out


def main() -> int:
    text = " ".join(p["text"] for p in load_passages("iit") + load_passages("gnwt"))
    low = text.lower()

    def src_count(s):
        return len(re.findall(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", low))

    def collides(target):
        # target (lowercased) must NOT already occur as a token/phrase in the corpus
        return src_count(target.lower()) > 0

    sections = {"theory_names": THEORY_NAMES, "coined_terms": COINED_TERMS, "people": PEOPLE}
    out_map = {"_meta": {
        "scope": "v1 = IIT + GNWT", "applied_to": "passages post-ingest (never PDFs)",
        "casing": "source lowercased here; apply-time regenerates lower/Title/UPPER to match each hit",
        "reversible": True, "stored_outside_hashed_dirs": True,
        "status": "PROPOSAL — awaiting Anu approval (review/a6_map.csv); a6_run.py runs only after",
        "note": "spec target 'ignition'→'broadcast surge' replaced by 'kindling surge' (collision with "
                "existing token 'broadcast'); 'integrated information'→'quantified integration' "
                "(token-count-preserving variant of spec 'Q-information')"}}
    rows = []
    collisions = []
    targets_seen = {}
    for sec, mp in sections.items():
        out_map[sec] = {}
        for s, t in mp.items():
            sc = src_count(s)
            col = collides(t)
            tok_delta = len(t.split()) - len(s.split())
            dup = t.lower() in targets_seen and targets_seen[t.lower()] != s
            targets_seen.setdefault(t.lower(), s)
            if col:
                collisions.append((sec, s, t))
            out_map[sec][s] = {"target": t, "source_count": sc, "token_delta": tok_delta,
                               "target_collision": col, "duplicate_target": dup}
            rows.append({"section": sec, "source": s, "proposed_target": t, "source_count": sc,
                         "token_delta": tok_delta, "collision": "YES" if col else "",
                         "decision": ""})

    (SPRINT / "corpora").mkdir(exist_ok=True)
    (SPRINT / "corpora" / "obfuscation_map.yaml").write_text(
        yaml.safe_dump(out_map, sort_keys=False, allow_unicode=True))

    with open(SPRINT / "review" / "a6_map.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["section", "source", "proposed_target", "source_count",
                                           "token_delta", "collision", "decision"])
        w.writeheader(); w.writerows(rows)
    (SPRINT / "review" / "a6_map.md").write_text(
        f"""# A6 obfuscation-map review (scope v1 = IIT + GNWT)  [AWAITING-ANU]

Role: approver. Approve/reject/edit each proposed term/name/person substitution. `decision` ∈
{{approve, edit, reject}}. `edit` = change `proposed_target` in the CSV (keep it token-count- and
casing-neutral, and non-colliding). Any row with `collision=YES` MUST be edited or rejected (its
target already occurs in the corpus, so de-mapping would be ambiguous). {len(rows)} rows →
review/a6_map.csv. Collisions found: {len(collisions)} (resolved proposals shown; confirm).
Nothing is extracted until you approve; the obfuscated + clean-rerun passes then run the SAME day.
""")
    (SPRINT / "review" / "a6_map_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["approve", "edit", "reject"]}}, indent=2))

    print(f"A6 map proposal → corpora/obfuscation_map.yaml ({len(rows)} entries: "
          f"{len(THEORY_NAMES)} theory-names, {len(COINED_TERMS)} coined-terms, {len(PEOPLE)} people).")
    print(f"  collisions (target pre-exists → must edit/reject): {collisions if collisions else 'none'}")
    print(f"  AWAITING-ANU: review/a6_map.csv (a6_run.py runs after approval, obfuscated + clean same-date)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
