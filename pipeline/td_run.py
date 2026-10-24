#!/usr/bin/env python3
"""
pipeline/td_run.py — TD1 / TD1b / TD2 corpus extensions, run to their Anu claims packets (SPEC §TD1/§TD1b/§TD2).

Shared pipeline (same for all three, = "copy p1 logic"): the engine's own p1_ingest.ingest_doc is
imported and run over the dropped PDF (sentence split + window + passage ids `<doc_id>_<k>`), then
P2.candidates scores passages, then extract_lite (the p2 replica under frozen instrument v2) extracts
typed claims, then an approve/reject/edit-value Anu packet is emitted. The judge rerun (ActInf×{IIT,GNWT}
for TD1/TD1b; IIT×IIT4 for TD2) + the new_corr/new_fork metrics land AFTER approval (td_finalize.py).

  TD1   Buckley 2017 FEP review        → doc aif2, theory "Active Inference", corpus_tag v2 (deepens the engine's 16 AIF claims)
  TD1b  Levine / Millidge / Moerland   → docs cai/pcbp/mbrl, theory control_as_inference|pc_backprop|mbrl, corpus_tag v2b
        (Moerland: §4 Dynamics-Model-Learning / world-models only, pages 6–16); td1b.untypeable_rate per source
  TD2   Albantakis IIT4                → doc iit4, theory iit4, corpus_tag v2c (engine IIT = the IIT-3.0-era side)

HOLDOUT: only these corpus PDFs are ingested; the keysrc/ key PDFs (KR3/KR4) are NEVER read here.
Disclosure (D-035): packet decisions are model-drafted suggestions for Anu to confirm.
"""
from __future__ import annotations

import argparse
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
sys.path.append(str(ENGINE / "pipeline"))
sys.path.append(str(ENGINE / "eval"))

import p1_ingest as P1  # noqa: E402  (authoritative ingest; imported, not reimplemented)
import p2_extract as P2  # noqa: E402
from p5_judge import value_family, same_family  # noqa: E402
import llm as L  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

REV = SPRINT / "review"

TASKS = {
    "td1": {"task_id": "TD1_aif", "corpus_tag": "v2", "runid": "TD1-1",
            "sources": [{"doc_id": "aif2", "theory": "Active Inference",
                         "pdf": "corpora/td1/buckley_2017_fep_review.pdf", "slug": "aif2"}],
            "dedup_vs": "active-inference"},
    "td1b": {"task_id": "TD1b_ml", "corpus_tag": "v2b", "runid": "TD1b-1",
             "sources": [{"doc_id": "cai", "theory": "control_as_inference",
                          "pdf": "corpora/td1b/levine_2018_control_as_inference.pdf", "slug": "cai"},
                         {"doc_id": "pcbp", "theory": "pc_backprop",
                          "pdf": "corpora/td1b/millidge_2022_pc_backprop.pdf", "slug": "pcbp"},
                         {"doc_id": "mbrl", "theory": "mbrl",
                          "pdf": "corpora/td1b/moerland_2023_mbrl_worldmodels.pdf", "slug": "mbrl",
                          "core_pages": [[6, 16]]}],
             "dedup_vs": None},
    "td2": {"task_id": "TD2_variants", "corpus_tag": "v2c", "runid": "TD2-1",
            "sources": [{"doc_id": "iit4", "theory": "iit4",
                         "pdf": "corpora/td2/albantakis_2023_iit4.pdf", "slug": "iit4"}],
            "dedup_vs": "iit"},
}


def engine_cluster_keys(slug):
    """(entity_type, axis, polarity, value_family-frozenset) clusters of an engine theory's approved claims."""
    p = ENGINE / "data" / "claims" / f"{slug}_approved.jsonl"
    out = []
    if p.exists():
        for ln in p.read_text().splitlines():
            if ln.strip():
                c = json.loads(ln)
                out.append((c["entity_type"], c["axis"], c["polarity"], c.get("value", "")))
    return out


def dup_of(claim, clusters):
    for (et, ax, pol, val) in clusters:
        if et == claim["entity_type"] and ax == claim["axis"] and pol == claim["polarity"] \
                and (same_family(val, claim["value"]) or val == claim["value"]):
            return True
    return False


def run_task(key):
    from extract_lite import extract_lite  # deferred (engine import)
    cfg = TASKS[key]
    client = L.LLM()
    clusters = engine_cluster_keys(cfg["dedup_vs"]) if cfg["dedup_vs"] else []
    all_claims, per_source = [], []
    for src in cfg["sources"]:
        pdf = SPRINT / src["pdf"]
        if not pdf.exists():
            per_source.append({"doc_id": src["doc_id"], "error": "PDF missing", "n_claims": 0})
            continue
        passages, q, extractor, flag = P1.ingest_doc(src["doc_id"], src["theory"], pdf, src.get("core_pages"))
        if flag:
            per_source.append({"doc_id": src["doc_id"], "error": flag, "n_passages": len(passages), "n_claims": 0})
            continue
        cands = P2.candidates(passages)
        claims = extract_lite(cands, theory=src["theory"], slug=src["slug"], client=client,
                              replicate_tag=key, task_id=cfg["task_id"])
        for c in claims:
            c["_doc_id"] = src["doc_id"]; c["_theory"] = src["theory"]
            c["duplicate_of_engine"] = dup_of(c, clusters)
        none_n = sum(1 for c in claims if c["axis"] == "none")
        per_source.append({"doc_id": src["doc_id"], "theory": src["theory"], "n_passages": len(passages),
                           "n_candidates": len(cands), "quality": round(q, 3), "extractor": extractor,
                           "n_claims": len(claims), "axis_none": none_n,
                           "untypeable_rate": round(none_n / len(claims), 3) if claims else None,
                           "n_duplicate_of_engine": sum(1 for c in claims if c["duplicate_of_engine"])})
        all_claims += claims

    rundir = SPRINT / "runs" / key.upper() / cfg["runid"]
    rundir.mkdir(parents=True, exist_ok=True)
    (rundir / "claims.json").write_text(json.dumps(
        {"task": key, "corpus_tag": cfg["corpus_tag"], "instrument_tag": "v2",
         "per_source": per_source, "claims": all_claims}, ensure_ascii=False, indent=2) + "\n")

    # Anu packet
    REV.mkdir(exist_ok=True)
    rows = [{"doc_id": c["_doc_id"], "theory": c["_theory"], "claim_id": c["claim_id"],
             "statement": c["statement"][:200], "type": c["entity_type"], "axis": c["axis"],
             "value": c["value"], "polarity": c["polarity"],
             "duplicate_of_engine": "YES" if c["duplicate_of_engine"] else "",
             "quote": (c.get("passage_ids") or [""])[0], "decision": ""} for c in all_claims]
    with open(REV / f"{key}_claims.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["doc_id", "theory", "claim_id", "statement", "type", "axis",
                                          "value", "polarity", "duplicate_of_engine", "quote", "decision"])
        w.writeheader(); w.writerows(rows)
    (REV / f"{key}_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["approve", "reject", "edit-value"]},
         "edit-value": {"format": "edit-value: <snake_case_token>"}}, indent=2))
    us = "; ".join(f"{s['doc_id']}: {s.get('n_claims',0)} claims"
                   + (f", untypeable {s['untypeable_rate']}" if s.get('untypeable_rate') is not None else "")
                   + (f", {s['n_duplicate_of_engine']} dup-of-engine" if s.get('n_duplicate_of_engine') else "")
                   for s in per_source)
    (REV / f"{key}_claims.md").write_text(
        f"""# {key.upper()} corpus-extension claims — review  [AWAITING-ANU]

Role: **annotator applying the published codebook.** Instrument v2 extraction over the dropped PDF(s).
Per source — {us}. For each row set `decision` ∈ {{approve, reject, edit-value}} by reading the quote
against the entity_type/axis codebook. `duplicate_of_engine=YES` flags a claim that matches an existing
engine cluster (A5 identity) — approve only if it adds something; it will be counted `duplicate-of`, not
double-counted. EXAMPLES: `approve`; `reject` (not supported/mis-typed); `edit-value: <token>`.
Companion schema: review/{key}_schema.json. Disclosure (D-035): model-drafted suggestions for your review.

{len(rows)} claims → review/{key}_claims.csv
After approval: pipeline/td_finalize.py runs the judge rerun + registers the new_corr/new_fork metrics.
""")

    # td1b.untypeable_rate lands now (property of extraction, pre-approval), per source
    reg = Registry()
    base = dict(task=key.upper(), runid=cfg["runid"], instrument_tag="v2", corpus_tag=cfg["corpus_tag"],
                preregistered=False, pilot=False)
    if key == "td1b":
        for s in per_source:
            if s.get("untypeable_rate") is not None:
                undiffable = s["untypeable_rate"] > 0.60
                reg.upsert(metric_id=f"td1b.untypeable_rate_{s['doc_id']}", value=s["untypeable_rate"],
                           n=s["n_claims"], caveats=[
                               f"axis:none rate for source {s['doc_id']} ({s['theory']}) under the consciousness-"
                               f"tuned v1 vocab (DRAFT, pre-approval). >0.60 ⇒ this source's KR4 rows become "
                               f"`undiffable (vocabulary)` — a domain-transfer FINDING, never patched by vocab edits. "
                               f"This source: {'UNDIFFABLE' if undiffable else 'diffable'}."], **base)
        reg.save()

    print(f"[{key.upper()}] sources: {us}")
    print(f"[{key.upper()}] total extracted {len(all_claims)} claims → review/{key}_claims.csv")
    print(f"[{key.upper()}] meter total ${client.meter.data['total_usd']:.4f}")

    write_manifest(key.upper(), cfg["runid"], instrument_tag="v2", corpus_tag=cfg["corpus_tag"],
                   inputs=[input_ref(str(SPRINT / s["pdf"]), "extraction") for s in cfg["sources"]],
                   outputs=[f"runs/{key.upper()}/{cfg['runid']}/claims.json", f"review/{key}_claims.csv"],
                   seeds={"global": CFG["seeds"]["global"]},
                   model_provenance=[{"role": "extractor", "model": CFG["models"]["extractor"],
                                      "instrument": "v2", "provider_seed_honored": False}],
                   notes=f"{key.upper()} ingest(p1)+extract_lite(v2) to claims packet; judge rerun post-approval.")
    print(f"AWAITING-ANU: review/{key}_claims.csv")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["td1", "td1b", "td2", "all"], default="all")
    a = ap.parse_args()
    keys = ["td1", "td1b", "td2"] if a.task == "all" else [a.task]
    for k in keys:
        run_task(k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
