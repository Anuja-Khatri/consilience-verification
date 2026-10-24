#!/usr/bin/env python3
"""
probe_set/build_probe.py — B4 diagnostic probe set "StructProbe-CSci v0.1" (SPEC §4 B4).

Builds probe_set/items.jsonl (schema probe_set/schema.json) across cells:
  true_correspondence : persisted IIT×GNWT (+cross-theory) node corrs, gold=correspond,
                        basis=judge-after-audit
  equivocation        : MIU rejection-record pairs (shared vocabulary but NOT a correspondence),
                        gold=not_correspond, basis=miu-rejection-record (each carries its reason)
  negation            : constructed canonical-vs-polarity-flipped (B2 pending → basis=constructed)
  control_expected_flip / control_invariant : constructed entity-swap / casing
Quotes ≤25 words with doc/loc; CC-BY-4.0 annotations. Name: "diagnostic probe set" (never
"benchmark"; linter-enforced). Datasheet + SHA256SUMS written. Harness: probe_set/run_probe.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
MIU = Path(os.path.expanduser(CFG["paths"]["miu"]))
SEED = CFG["seeds"]["global"]
CAP = CFG["thresholds"]["quote_word_cap"]
PS = SPRINT / "probe_set"
ENTITY_SWAP = {"posterior": "frontal", "frontal": "posterior", "gamma": "alpha", "alpha": "gamma",
               "late": "early", "early": "late"}


def cap(t):
    w = str(t).split()
    return " ".join(w[:CAP]) + ("…" if len(w) > CAP else "")


def eng_claims():
    idx = {}
    for slug in ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]:
        for ln in (ENGINE / "data" / "claims" / f"{slug}_approved.jsonl").read_text().splitlines():
            if ln.strip():
                c = json.loads(ln); idx[c["claim_id"]] = c
    return idx


def miu_index():
    idx = {}
    for p in [MIU / "correspondences" / "_index" / "all_claims.json",
              MIU / "correspondences" / "supplementary" / "new_claims_index.json",
              MIU / "correspondences" / "engine-discovered" / "ed_claims_index.json"]:
        if p.exists():
            data = json.loads(p.read_text())
            for c in (data if isinstance(data, list) else data.get("claims", [])):
                if isinstance(c, dict) and c.get("claim_id"):
                    idx.setdefault(c["claim_id"], c)
    return idx


def typed(c):
    return {"entity_type": c.get("entity_type", "process"), "axis": c.get("axis", "none"),
            "polarity": c.get("polarity", "asserts"), "value": c.get("value", "")}


def main() -> int:
    PS.mkdir(exist_ok=True)
    rng = random.Random(SEED)
    eng = eng_claims()
    miu = miu_index()
    items = []

    def add(cell, a_text, b_text, ta, tb, gold, basis, src_a, src_b, extra=None):
        it = {"item_id": f"sp_{len(items):04d}", "cell": cell, "text_a": cap(a_text),
              "text_b": cap(b_text), "typed_a": ta, "typed_b": tb, "gold": gold,
              "gold_basis": basis, "source_a": src_a, "source_b": src_b,
              "license_note": "annotations CC-BY-4.0; quotes ≤25 words under source terms",
              "provenance": {"created_by_task": "B4", "runid": "B4-1"}}
        if extra:
            it.update(extra)
        items.append(it)

    # true_correspondence (persisted node corrs)
    import glob
    corrs = []
    for jf in glob.glob(str(ENGINE / "results" / "*_judge.json")):
        for c in json.loads(Path(jf).read_text()).get("correspondences", []):
            if c.get("kind") == "node" and c["left_ids"][0] in eng and c["right_ids"][0] in eng:
                corrs.append(c)
    rng.shuffle(corrs)
    for c in corrs[:60]:
        a, b = eng[c["left_ids"][0]], eng[c["right_ids"][0]]
        add("true_correspondence", a["statement"], b["statement"], typed(a), typed(b),
            "correspond", "judge-after-audit",
            {"doc": a["theory"], "loc": a["claim_id"], "sha": hashlib.sha256(a["statement"].encode()).hexdigest()[:12]},
            {"doc": b["theory"], "loc": b["claim_id"], "sha": hashlib.sha256(b["statement"].encode()).hexdigest()[:12]},
            {"grade": c["grade"]})

    # equivocation (MIU rejection records — shared vocab, not a correspondence)
    rej = json.loads((MIU / "correspondences" / "rejections.json").read_text())
    rng.shuffle(rej)
    for r in rej[:60]:
        a, b = miu.get(r["claim_a"]), miu.get(r["claim_b"])
        if not (a and b):
            continue
        add("equivocation", a.get("claim_text", ""), b.get("claim_text", ""),
            typed({"axis": "none", "polarity": "asserts", "value": a.get("claim_text", "")[:20]}),
            typed({"axis": "none", "polarity": "asserts", "value": b.get("claim_text", "")[:20]}),
            "not_correspond", "miu-rejection-record",
            {"doc": a.get("source_file", "miu"), "loc": r["claim_a"], "sha": ""},
            {"doc": b.get("source_file", "miu"), "loc": r["claim_b"], "sha": ""},
            {"rejection_reason": cap(r.get("reason", ""))})

    # negation (constructed: claim vs polarity-flipped self) — B2 canonical-vs-negated pending
    pool = [c for c in eng.values() if c["axis"] != "none"]
    rng.shuffle(pool)
    for c in pool[:36]:
        flip = "denies" if c["polarity"] == "asserts" else "asserts"
        tb = typed(c); tb["polarity"] = flip; tb["value"] = "not_" + c["value"]
        add("negation", c["statement"], "NOT: " + c["statement"], typed(c), tb,
            "not_correspond", "constructed",
            {"doc": c["theory"], "loc": c["claim_id"], "sha": ""}, {"doc": c["theory"], "loc": "constructed", "sha": ""},
            {"note": "constructed polarity flip; B2 canonical-vs-negated supersedes when B2 runs"})

    # controls: expected-flip (entity swap) + invariant (casing)
    swap_pool = [c for c in eng.values() if any(k in c["value"] for k in ENTITY_SWAP)]
    rng.shuffle(swap_pool)
    for c in swap_pool[:18]:
        sv = c["value"]
        for k, v in ENTITY_SWAP.items():
            if k in sv:
                sv = sv.replace(k, v); break
        tb = typed(c); tb["value"] = sv
        add("control_expected_flip", c["statement"], c["statement"].replace(
            next(k for k in ENTITY_SWAP if k in c["value"]), ENTITY_SWAP[next(k for k in ENTITY_SWAP if k in c["value"])]),
            typed(c), tb, "not_correspond", "constructed",
            {"doc": c["theory"], "loc": c["claim_id"], "sha": ""}, {"doc": c["theory"], "loc": "entity-swap", "sha": ""})
    inv_pool = list(eng.values()); rng.shuffle(inv_pool)
    for c in inv_pool[:18]:
        add("control_invariant", c["statement"], c["statement"].upper(), typed(c), typed(c),
            "correspond", "constructed",
            {"doc": c["theory"], "loc": c["claim_id"], "sha": ""}, {"doc": c["theory"], "loc": "casing", "sha": ""})

    (PS / "items.jsonl").write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items))
    (PS / "schema.json").write_text(json.dumps({
        "fields": ["item_id", "cell", "text_a", "text_b", "typed_a", "typed_b", "gold",
                   "gold_basis", "source_a", "source_b", "license_note", "provenance"],
        "cell": ["true_correspondence", "equivocation", "negation", "control_expected_flip", "control_invariant"],
        "gold": ["correspond", "not_correspond"]}, indent=2) + "\n")
    import collections
    cells = collections.Counter(it["cell"] for it in items)
    sha = hashlib.sha256((PS / "items.jsonl").read_bytes()).hexdigest()
    (PS / "SHA256SUMS").write_text(f"{sha}  items.jsonl\n")
    (PS / "DATASHEET.md").write_text(f"""# StructProbe-CSci v0.1 — datasheet (Measuring-What-Matters, honest)

Diagnostic probe set (NOT a leaderboard). {len(items)} items; cells {dict(cells)}.
items.jsonl sha256 `{sha[:16]}…`; v0.1; annotations CC-BY-4.0, quotes ≤25 words under source terms.

- **Composition:** true_correspondence (judge-after-audit), equivocation (MIU rejection records —
  shared vocabulary, NOT a correspondence), negation (constructed polarity-flip; B2 supersedes),
  controls (entity-swap expected-flip, casing invariant).
- **Conceded limitations:** convenience sample; one domain (consciousness theories + a MIU
  cross-field slice); single-codebook annotator (judge-after-audit, not multi-rater); contamination
  — public sources may be in training data (A6 is the related obfuscation control). Negation cell is
  constructed pending B2.
- **Intended use:** diagnosing the structure-vs-surface-similarity DISSOCIATION per method (does a
  method pass true_correspondence while rejecting equivocation?). NOT a leaderboard.
""")
    print(f"B4 probe set: {len(items)} items, cells {dict(cells)}; items.jsonl sha {sha[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
