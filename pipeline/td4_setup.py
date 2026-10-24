#!/usr/bin/env python3
"""
pipeline/td4_setup.py — TD4 (= G2) protocol-game SETUP → Anu packet (SPEC §TD4). $0.

Builds everything the TD4 run needs, as PROPOSALS for Anu to approve (the game run, td4_run.py,
happens only after approval and MUST measure a6-style de-obfuscation leaks per agent message —
D-041 firewall requirement / memory td4-deobfuscation-firewall):

  1. `corpora/obfuscation_map_b.yaml` — a SECOND obfuscation map built by the A6 procedure with
     DIFFERENT targets (so Agent B's vocabulary never overlaps Agent A's map-A vocabulary — the
     firewall). Same rules: token-count-preserving, casing regenerated at apply-time, collision-
     checked against the IIT+GNWT corpus, reversible, stored outside hashed dirs.
  2. `results/td4_items.json` + `review/td4_items.csv` — 30 seeded items. Each item = one A-side
     claim; B holds 6 candidates: 1 reference-matched (the persisted cross-theory correspondence
     partner, else answer = none) + 5 distractors (2 same-axis different-family, 2 different-axis
     lexically-similar by token overlap, 1 random). A ∈ {IIT, GNWT}; B = the other theory.
  3. `review/td4_schema.json` — the typed claim-card schema for the TYPED-CARD arm.

Emits review/td4_setup.md (AWAITING-ANU) covering the map, the item list, and the card schema.
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
SEED = int(CFG["seeds"]["global"])

import facts as F  # noqa: E402
import judge_program as JP  # noqa: E402
sys.path.insert(0, str(ENGINE / "pipeline"))
from p5_judge import value_family  # noqa: E402

# ---- map B (A6 procedure, DIFFERENT targets than corpora/obfuscation_map.yaml) ----
THEORY_NAMES_B = {
    "integrated information theory": "system omega model", "iit": "zq",
    "global neuronal workspace": "distributed relay network", "global workspace theory": "relay network theory",
    "global workspace": "distributed relay", "gnwt": "drn", "gwt": "rnt",
}
COINED_TERMS_B = {
    "integrated information": "bound synthesis", "φ": "omega-value", "phi": "omega-value",
    "ignition": "flare cascade", "workspace neurons": "relay neurons",
    "maximally irreducible": "maximally unsplittable", "cause-effect power": "source-effect capacity",
    "global availability": "distributed availability",
}
PEOPLE_B = {
    "tononi": "Author M1", "koch": "Author M2", "albantakis": "Author M3", "oizumi": "Author M4",
    "massimini": "Author M5", "boly": "Author M6", "marshall": "Author M7", "grasso": "Author M8",
    "findlay": "Author M9", "barbosa": "Author M10", "edelman": "Author M11",
    "dehaene": "Author N1", "changeux": "Author N2", "mashour": "Author N3", "kouider": "Author N4",
    "naccache": "Author N5", "baars": "Author N6", "sergent": "Author N7", "lau": "Author N8",
}


def _load_iit_gnwt_passages_text():
    def lp(slug):
        return [json.loads(l) for l in (ENGINE / "data" / "passages" / f"{slug}.jsonl").read_text().splitlines() if l.strip()]
    return " ".join(p["text"] for p in lp("iit") + lp("gnwt")).lower()


def build_map_b():
    low = _load_iit_gnwt_passages_text()

    def src_count(s):
        return len(re.findall(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", low))

    def collides(t):
        return src_count(t.lower()) > 0

    # guard: no map-B target may equal a map-A target (vocabularies must not overlap)
    mapa = yaml.safe_load((SPRINT / "corpora" / "obfuscation_map.yaml").read_text())
    a_targets = {v["target"].lower() for sec in ("theory_names", "coined_terms", "people")
                 for v in mapa.get(sec, {}).values()}
    sections = {"theory_names": THEORY_NAMES_B, "coined_terms": COINED_TERMS_B, "people": PEOPLE_B}
    out = {"_meta": {"scope": "v1 = IIT + GNWT", "role": "Agent-B obfuscation (TD4 firewall; distinct from map A)",
                     "applied_to": "passages/claims post-ingest (never PDFs)", "reversible": True,
                     "stored_outside_hashed_dirs": True,
                     "status": "PROPOSAL — awaiting Anu approval (review/td4_map_b.csv); td4_run.py runs only after"}}
    rows, collisions, overlaps = [], [], []
    seen = {}
    for sec, mp in sections.items():
        out[sec] = {}
        for s, t in mp.items():
            col = collides(t); over = t.lower() in a_targets
            dup = t.lower() in seen and seen[t.lower()] != s
            seen.setdefault(t.lower(), s)
            if col:
                collisions.append((sec, s, t))
            if over:
                overlaps.append((sec, s, t))
            out[sec][s] = {"target": t, "source_count": src_count(s),
                           "token_delta": len(t.split()) - len(s.split()),
                           "target_collision": col, "overlaps_map_a": over, "duplicate_target": dup}
            rows.append({"section": sec, "source": s, "proposed_target": t, "source_count": src_count(s),
                         "token_delta": len(t.split()) - len(s.split()),
                         "collision": "YES" if col else "", "overlaps_map_a": "YES" if over else "", "decision": ""})
    (SPRINT / "corpora").mkdir(exist_ok=True)
    (SPRINT / "corpora" / "obfuscation_map_b.yaml").write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    with open(SPRINT / "review" / "td4_map_b.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["section", "source", "proposed_target", "source_count",
                                           "token_delta", "collision", "overlaps_map_a", "decision"])
        w.writeheader(); w.writerows(rows)
    return rows, collisions, overlaps


# ---- 30-item list ----
def _nodes():
    g = F.load_graphs()
    nodes = {}
    for slug in ("iit", "gnwt"):
        for n in g[slug]["nodes"]:
            nodes[n["claim_id"]] = {**n, "slug": slug}
    return nodes, g


def _matched_partners():
    """cross-theory IIT↔GNWT correspondence partners from the VJ1 program (prefer partial>generative)."""
    g = F.load_graphs()
    A, B = g["iit"], g["gnwt"]
    o = JP.run_pair(A, B)
    rank = {"formal": 3, "partial": 2, "generative": 1}
    part = {}
    for (a, b, gr) in o["corrs"]:
        if gr == "smc":
            continue
        for x, y in ((a, b), (b, a)):
            if x not in part or rank.get(gr, 0) > rank.get(part[x][1], 0):
                part[x] = (y, gr)
    return part


def _distractors(a_claim, other_nodes, rng):
    """5 distractors from the other theory: 2 same-axis diff-family, 2 diff-axis lexically-similar, 1 random."""
    a_ax = a_claim["axis"]
    a_fam = set(value_family(a_claim["value"]))
    a_tokens = set(re.findall(r"[a-z]{4,}", a_claim["statement"].lower()))
    pool = [n for n in other_nodes]
    same_ax_diff_fam = [n for n in pool if n["axis"] == a_ax and not (set(value_family(n["value"])) & a_fam)]
    diff_ax = [n for n in pool if n["axis"] != a_ax]
    diff_ax_lex = sorted(diff_ax, key=lambda n: -len(a_tokens & set(re.findall(r"[a-z]{4,}", n["statement"].lower()))))
    picks, seen = [], set()

    def grab(cands, k, shuffle=False):
        c = list(cands)
        if shuffle:
            rng.shuffle(c)
        got = 0
        for n in c:
            if got >= k:
                break
            if n["claim_id"] not in seen:
                picks.append(n["claim_id"]); seen.add(n["claim_id"]); got += 1

    grab(same_ax_diff_fam, 2, shuffle=True)   # 2 same-axis, different value-family
    grab(diff_ax_lex, 2)                      # 2 different-axis, lexically similar (token overlap)
    grab([n for n in pool if n["claim_id"] not in seen], 1, shuffle=True)   # 1 random
    grab([n for n in pool if n["claim_id"] not in seen], 5 - len(picks), shuffle=True)  # top up if a stratum short
    return picks[:5]


def build_items():
    nodes, g = _nodes()
    part = _matched_partners()
    rng = random.Random(SEED)
    iit = [n for n in g["iit"]["nodes"]]
    gnwt = [n for n in g["gnwt"]["nodes"]]
    # A-claims: all IIT then all GNWT, seeded order, take 30 (24+19=43 available)
    a_pool = [(n, "iit") for n in iit] + [(n, "gnwt") for n in gnwt]
    for n in a_pool:
        n[0]["_slug"] = n[1]
    a_ids = sorted(f"{s}:{n['claim_id']}" for n, s in a_pool)
    rng.shuffle(a_ids)
    a_sel = a_ids[:30]
    items = []
    for key in a_sel:
        s, cid = key.split(":", 1)
        a = nodes[cid]
        other = gnwt if s == "iit" else iit
        other = [n for n in other if n["claim_id"] != cid]
        matched = part.get(cid)
        matched_id = matched[0] if matched else None
        distractors = _distractors(a, [n for n in other if n["claim_id"] != matched_id], rng)
        if matched_id:
            cand = distractors[:5] + [matched_id]
        else:
            cand = distractors[:5] + _distractors(a, [n for n in other if n["claim_id"] not in distractors], rng)[:1]
        rng.shuffle(cand)
        items.append({"item_id": f"td4_{len(items)+1:02d}", "a_theory": a["theory"], "a_slug": s,
                      "a_claim_id": cid, "a_statement": a["statement"], "a_axis": a["axis"],
                      "b_theory": "GNWT" if s == "iit" else "IIT",
                      "candidates": cand, "reference_match": matched_id or "none",
                      "reference_grade": (matched[1] if matched else "none")})
    (SPRINT / "results" / "td4_items.json").write_text(json.dumps(
        {"n": len(items), "seed": SEED, "items": items,
         "note": "A∈{IIT,GNWT} drawn seeded from 43 claims (target 30; corpus supports ≤43). candidates = "
                 "5 distractors + 1 reference-match (or 6 distractors when A has no cross-theory partner → answer=none)."},
        ensure_ascii=False, indent=2) + "\n")
    with open(SPRINT / "review" / "td4_items.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["item_id", "a_theory", "a_claim_id", "a_statement",
                                           "b_theory", "n_candidates", "reference_match", "reference_grade", "decision"])
        w.writeheader()
        for it in items:
            w.writerow({"item_id": it["item_id"], "a_theory": it["a_theory"], "a_claim_id": it["a_claim_id"],
                        "a_statement": it["a_statement"][:160], "b_theory": it["b_theory"],
                        "n_candidates": len(it["candidates"]), "reference_match": it["reference_match"],
                        "reference_grade": it["reference_grade"], "decision": ""})
    n_matched = sum(1 for it in items if it["reference_match"] != "none")
    return items, n_matched


CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_type": {"type": "string"},
        "axis": {"type": "string"},
        "polarity": {"enum": ["asserts", "denies"]},
        "value_description": {"type": "string", "maxWords": 12},
        "question": {"type": "string"},
    },
    "required": ["entity_type", "axis", "polarity", "value_description", "question"],
    "_note": "TYPED-CARD arm: every message must be valid claim-card JSON (invalid → schema bounce, counts as a turn). "
             "value_description ≤12 words is the DESIGNED leak channel (measured, not prevented: g2.value_field_leak_rate).",
}


def main() -> int:
    (SPRINT / "review").mkdir(exist_ok=True)
    rows, collisions, overlaps = build_map_b()
    items, n_matched = build_items()
    (SPRINT / "review" / "td4_schema.json").write_text(json.dumps(CARD_SCHEMA, indent=2))
    (SPRINT / "review" / "td4_setup.md").write_text(
        f"""# TD4 protocol-game SETUP — review  [AWAITING-ANU]

Role: approver (reading task). Three proposals; the game run (td4_run.py) happens only after approval.

**1. Agent-B obfuscation map** → review/td4_map_b.csv ({len(rows)} rows; `decision` ∈ {{approve, edit, reject}}).
A SECOND map (distinct targets from map A) so the two agents' vocabularies never overlap — the firewall.
Rows with `collision=YES` (target already in corpus) or `overlaps_map_a=YES` MUST be edited/rejected.
Collisions: {len(collisions)}; map-A overlaps: {len(overlaps)}.

**2. 30-item list** → review/td4_items.csv (`decision` ∈ {{approve, edit, reject}}). Each item = one A-side
claim; B holds 6 candidates (5 distractors + 1 reference-matched partner, or 6 distractors when A has no
cross-theory partner → correct answer is `none`). {n_matched}/{len(items)} items have a reference match.

**3. Typed claim-card schema** → review/td4_schema.json (approve/edit). Fields: entity_type, axis, polarity,
value_description (≤12 words — the DESIGNED leak channel, measured as g2.value_field_leak_rate), question.

On approval, td4_run.py runs both arms (free-text vs typed-card, ≤6 turns, two separate llm.py
conversations, game_agent model) and measures g2.task_acc/turns/tokens/firewall_leaks PLUS the D-041
requirement: per-message de-obfuscation leak counts (report the firewall as "surface-obfuscated,
identity not guaranteed hidden" unless leaks == 0).
""")
    print(f"[TD4-setup] map_b {len(rows)} rows (collisions {len(collisions)}, map-A overlaps {len(overlaps)}); "
          f"items {len(items)} ({n_matched} reference-matched); card schema proposed.")
    print("AWAITING-ANU: review/td4_setup.md (td4_map_b.csv + td4_items.csv + td4_schema.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
