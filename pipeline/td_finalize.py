#!/usr/bin/env python3
"""
pipeline/td_finalize.py — TD1/TD1b/TD2 post-approval judge reruns (SPEC §TD1/§TD1b/§TD2). $0 (judge only).

Consumes the Anu-approved review/td{1,1b,2}_claims.csv. Owner standing rules recorded in D-054
(applied in the decisions, verified here):
  (i)   reject claims that insert "consciousness" into sources making no consciousness claim;
  (ii)  reject duplicate_of_engine=YES rows (nothing beyond the engine cluster);
  (iii) reject computability / substrate_dependence / observable_commitment used outside codebook meaning.

TD1  — merge the engine's 16 AIF claims + approved TD1 claims, rerun the ported judge on ActInf×{IIT,GNWT}
       in sprint graph copies → the NEW correspondences/forks attributable to the deepened AIF side
       (td1.new_claims / td1.new_correspondences / td1.new_forks), corpus_tag v2.
TD1b — store the approved ML claims (control_as_inference | pc_backprop | mbrl) as corpus v2b — the second
       side KR4's homology rows recover against (consumed by keys/kr4_diff.py). td1b.new_claims per theory.
TD2  — judge the engine IIT (IIT-3.0-era side) × approved IIT4 claims → within-family correspondence/fork
       list (td2.within_family_corrs / td2.within_family_forks + fork table), corpus_tag v2c.

Disclosure (D-035): decisions were model-drafted suggestions reviewed and confirmed by Anu.
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
sys.path.insert(0, str(SPRINT / "logic"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))

import p5_judge as P5  # noqa: E402
import facts as F  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

DISC = "Decisions were model-drafted suggestions (Claude) reviewed and confirmed by Anu."


def approved(key):
    return {r["claim_id"] for r in csv.DictReader(open(SPRINT / "review" / f"{key}_claims.csv"))
            if r["decision"] == "approve"}


def claims(key, runid):
    d = json.loads((SPRINT / "runs" / key.upper() / runid / "claims.json").read_text())
    return d["claims"]


def _corrkey(c):
    if c.get("kind") == "shared_measurement_space":
        return ("smc", tuple(c["left_ids"]), tuple(c["right_ids"]))
    return (c["left_ids"][0], c["right_ids"][0], c["grade"])


def _forkkey(f):
    return (f["left_ids"][0], f["right_ids"][0], f["axis"])


def td1(reg):
    ap = approved("td1")
    td = [c for c in claims("td1", "TD1-1") if c["claim_id"] in ap]
    dups = sum(1 for c in td if c.get("duplicate_of_engine"))
    g = F.load_graphs()
    eng_aif = g["active-inference"]
    merged = {"theory": "Active Inference", "nodes": eng_aif["nodes"] + td, "edges": eng_aif.get("edges", [])}
    new_corrs, new_forks, fork_rows = [], [], []
    for other_slug in ("iit", "gnwt"):
        other = g[other_slug]
        base = P5.judge_pair(eng_aif, other)
        mrg = P5.judge_pair(merged, other)
        bc = {_corrkey(c) for c in base["correspondences"]}
        bf = {_forkkey(f) for f in base["forks"]}
        for c in mrg["correspondences"]:
            if _corrkey(c) not in bc:
                new_corrs.append({"pair": f"aif×{other_slug}", "grade": c.get("grade", c.get("kind")),
                                  "left": c["left_ids"][0], "right": c["right_ids"][0]})
        for f in mrg["forks"]:
            if _forkkey(f) not in bf:
                new_forks.append({"pair": f"aif×{other_slug}", "axis": f["axis"],
                                  "left": f["left_ids"][0], "right": f["right_ids"][0]})
    out = {"new_claims": len(td), "duplicates_among_approved": dups, "new_correspondences": new_corrs,
           "new_forks": new_forks}
    (SPRINT / "runs" / "TD1" / "TD1-1" / "judge_rerun.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    base = dict(task="TD1", runid="TD1-1", instrument_tag="v2", corpus_tag="v2", preregistered=False, pilot=False)
    cav = (f"TD1 AIF deepening: engine 16 AIF claims + {len(td)} Anu-approved new = {16+len(td)}; judge rerun on "
           f"ActInf×{{IIT,GNWT}} vs the engine-only baseline → NEW corr/fork attributable to the added claims. "
           f"Owner rules: dropped consciousness-insertions, duplicate-of-engine rows, and off-codebook "
           f"computability/substrate/observable. {dups} duplicate(s) among approved. {DISC}")
    reg.upsert(metric_id="td1.new_claims", value=len(td), n=24, caveats=[cav, "engine 16 + new %d" % len(td)], **base)
    reg.upsert(metric_id="td1.new_correspondences", value=len(new_corrs), n=len(td),
               caveats=[cav, "; ".join(f"{c['pair']}:{c['grade']} {c['left']}~{c['right']}" for c in new_corrs[:8]) or "none"], **base)
    reg.upsert(metric_id="td1.new_forks", value=len(new_forks), n=len(td),
               caveats=[cav, "; ".join(f"{f['pair']}:{f['axis']} {f['left']}|{f['right']}" for f in new_forks[:8]) or "none"], **base)
    print(f"[TD1] merged AIF {16}+{len(td)}; new_corr {len(new_corrs)}, new_fork {len(new_forks)}, dup-among-approved {dups}")
    return out


def td1b(reg):
    ap = approved("td1b")
    td = [c for c in claims("td1b", "TD1b-1") if c["claim_id"] in ap]
    from collections import Counter
    bytheory = Counter(c["_theory"] for c in td)
    (SPRINT / "corpora" / "td1b" / "claims.json").write_text(json.dumps(
        {"corpus_tag": "v2b", "instrument_tag": "v2", "n": len(td), "by_theory": dict(bytheory),
         "claims": td}, ensure_ascii=False, indent=2) + "\n")
    base = dict(task="TD1B", runid="TD1b-1", instrument_tag="v2", corpus_tag="v2b", preregistered=False, pilot=False)
    cav = (f"TD1b ML-bridge corpus v2b stored for KR4 (the ML side of the homology recovery): {len(td)} approved "
           f"claims {dict(bytheory)}. Owner rules applied (no consciousness-insertion, no dup-of-engine, codebook "
           f"meanings). {DISC}")
    reg.upsert(metric_id="td1b.new_claims", value=len(td), n=27, caveats=[cav], **base)
    print(f"[TD1b] stored {len(td)} ML claims {dict(bytheory)} → corpora/td1b/claims.json (corpus v2b)")
    return td


def td2(reg):
    ap = approved("td2")
    td = [c for c in claims("td2", "TD2-1") if c["claim_id"] in ap]
    g = F.load_graphs()
    eng_iit = g["iit"]                                   # IIT-3.0-era side
    iit4 = {"theory": "iit4", "nodes": td, "edges": []}  # IIT-4.0 side
    out = P5.judge_pair(eng_iit, iit4)
    corrs = [c for c in out["correspondences"] if c.get("kind") != "shared_measurement_space"]
    forks = out["forks"]
    stmt = {c["claim_id"]: c for c in eng_iit["nodes"]}
    stmt.update({c["claim_id"]: c for c in td})
    fork_rows = [{"axis": f["axis"], "iit3": f["left_ids"][0], "iit4": f["right_ids"][0],
                  "iit3_value": stmt.get(f["left_ids"][0], {}).get("value"),
                  "iit4_value": stmt.get(f["right_ids"][0], {}).get("value")} for f in forks]
    rerun = {"within_family_corrs": len(corrs), "within_family_forks": len(forks),
             "corr_sample": [{"grade": c.get("grade"), "iit3": c["left_ids"][0], "iit4": c["right_ids"][0]} for c in corrs[:10]],
             "fork_table": fork_rows}
    (SPRINT / "runs" / "TD2" / "TD2-1" / "judge_rerun.json").write_text(json.dumps(rerun, ensure_ascii=False, indent=2) + "\n")
    base = dict(task="TD2", runid="TD2-1", instrument_tag="v2", corpus_tag="v2c", preregistered=False, pilot=False)
    cav = (f"TD2 IIT 3.0 (engine {len(eng_iit['nodes'])} claims) × IIT 4.0 ({len(td)} approved Albantakis claims) "
           f"within-family judge. Weak-IIT reading made mechanical: which commitments distinguish the variants "
           f"(no Φ-computation language). Owner rules applied. {DISC}")
    reg.upsert(metric_id="td2.within_family_corrs", value=len(corrs), n=len(td),
               caveats=[cav, f"heavy correspondence on shared commitments ({len(corrs)})"], **base)
    reg.upsert(metric_id="td2.within_family_forks", value=len(forks), n=len(td),
               caveats=[cav, "forks on revised postulates: " + ("; ".join(f"{r['axis']}:{r['iit3_value']}|{r['iit4_value']}" for r in fork_rows[:6]) or "none")], **base)
    print(f"[TD2] IIT3×IIT4: within_family_corrs {len(corrs)}, within_family_forks {len(forks)}")
    return rerun


def main() -> int:
    reg = Registry()
    td1(reg); td1b(reg); td2(reg)
    reg.save()
    write_manifest("TD", "TD-FINALIZE", instrument_tag="v2", corpus_tag="v2",
                   inputs=[input_ref(str(SPRINT / "runs" / "TD1" / "TD1-1" / "claims.json"), "extraction"),
                           input_ref(str(SPRINT / "runs" / "TD1B" / "TD1b-1" / "claims.json"), "extraction"),
                           input_ref(str(SPRINT / "runs" / "TD2" / "TD2-1" / "claims.json"), "extraction")],
                   outputs=["runs/TD1/TD1-1/judge_rerun.json", "runs/TD2/TD2-1/judge_rerun.json",
                            "corpora/td1b/claims.json"],
                   notes="TD1/TD1b/TD2 post-approval judge reruns + ML corpus v2b store.")
    print("[TD-finalize] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
