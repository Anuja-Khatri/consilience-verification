#!/usr/bin/env python3
"""
pipeline/a5_stability.py — A5.1 stability arms (SPEC §2 A5.1, amended v2.0.1).

Scope mirrors Task 5 EXACTLY: IIT 8 + GNWT 8 = 16 first-pass candidate windows
(window selection reused verbatim from eval/t5_reliability.py → p2_extract.candidates/
WINDOW). Arms:
  (a) production temperature × 5 replicates — REUSED from the warm Task-5 cache
      (eval_out/cache, run_index 0..4) at $0 ("REUSE, never redo"); 5 distinct replicates
      preserved (not collapsed — honours the v2.0.1 anti-collapse rule).
  (b) temperature 0 × 5 REAL replicates (v2.0.1 6c: measured, not assumed).
  (c) consensus-of-5 over arm (a).
  (d) confidence-weighted consensus (G6/CISC): arm-(a)-style prompt + per-claim
      "confidence"; keep a cluster iff Σ(confidence) ≥ 2.0 OR present in ≥4/5 runs.

Cluster identity (A5, fixed): same (entity_type, axis, polarity) AND value-family-equal
(ported value_family). Consensus keeps clusters in ≥4/5 runs; canonical = lowest replicate.

All model calls go through pipeline/llm.py. Arm (a) reuse reads the prior cache directly
by the reconstructed prior key (deliberate reuse, not the r0 auto-fallback).

Metrics → registry (instrument_tag v1 — these are v1-prompt extraction variability arms;
the definitions-augmented v2 prompt is A5.2, the freeze/adoption is A5.3):
  a5.stability_consensus (arm a/c), a5.stability_t0 (arm b), a5.stability_confweighted (d),
  a5.approved_coverage_<arm>, a5.cost_multiplier_<arm>. Baseline a5.stability_baseline =
  Task-5 27.1% imported from eval_out/t5/stability.md (cited, NOT re-measured).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
EVAL_PRIOR = Path(os.path.expanduser(CFG["paths"]["eval_prior"]))
PRIOR_CACHE = EVAL_PRIOR / "eval_out" / "cache" / "claude-sonnet-4-6"

sys.path.insert(0, str(ENGINE / "pipeline"))
import p2_extract as P2  # noqa: E402  (read-only: constants + candidates/load_passages/_json_block)
from p5_judge import value_family  # noqa: E402  (ported family fn via engine_copy on path)

import llm as L  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

THEORIES = [("IIT", "iit"), ("GNWT", "gnwt")]
SEEDS = CFG["seeds"]["extraction_runs"]  # [11,22,33,44,55] → replicate_tags a11..a55 etc.
N_RUNS = len(SEEDS)
SONNET = P2.SONNET
MAXTOK = 1500
KEEP_MIN = CFG["thresholds"]["consensus_keep_min_runs"]  # 4
CONF_SUM_KEEP = 2.0
A5 = SPRINT / "runs" / "A5"


# ── window + prompt reconstruction (verbatim from t5_reliability.py) ──
def windows_for(slug):
    cands = P2.candidates(P2.load_passages(slug))
    return [cands[i:i + P2.WINDOW] for i in range(0, len(cands), P2.WINDOW)]


def extract_system():
    return (
        "You extract the STRUCTURALLY CENTRAL, typed claims a theory of consciousness commits to. "
        "You read and type; you never judge correspondence. Use ONLY the controlled vocabulary.\n"
        f"entity_type (one of): {sorted(P2.ENTITY_TYPES)}\n"
        f"axis (one of, or 'none'): {sorted(P2.AXES)}\n"
        "polarity: 'asserts' or 'denies'.\n" + P2.FEWSHOT + "\n"
        "Rules: only claims actually supported by the passages; each claim MUST cite the passage_ids "
        "it comes from (from the provided ids only); value = a short canonical token (snake_case); "
        f"return at MOST {P2.CLAIMS_PER_WINDOW} of the most central claims; skip method/reference chatter. "
        'Output ONLY a JSON array of {"statement","entity_type","axis","value","polarity","passage_ids"}.'
    )


CONF_SYSTEM = extract_system().replace(
    'Output ONLY a JSON array of {"statement","entity_type","axis","value","polarity","passage_ids"}.',
    'Additionally include a "confidence": a number 0.0-1.0 for how certain you are of the typing. '
    'Output ONLY a JSON array of {"statement","entity_type","axis","value","polarity","passage_ids","confidence"}.')


def extract_user(theory, window):
    passages_txt = "\n".join(f'[{p["passage_id"]}] {p["text"]}' for p in window)
    return f"Theory: {theory}\nPassages:\n{passages_txt}"


def parse_claims(text, window, want_conf=False):
    ids = {p["passage_id"] for p in window}
    out = []
    for c in P2._json_block(text):
        pids = [i for i in c.get("passage_ids", []) if i in ids]
        if not pids:
            continue
        axis = c.get("axis") if c.get("axis") in P2.AXES else "none"
        rec = {"statement": c.get("statement", ""), "entity_type": c.get("entity_type"),
               "axis": axis, "value": str(c.get("value", "")), "polarity": c.get("polarity"),
               "passage_ids": sorted(pids)}
        if want_conf:
            try:
                rec["confidence"] = float(c.get("confidence", 0.0))
            except Exception:
                rec["confidence"] = 0.0
        out.append(rec)
    return out


# ── prior-cache reuse (arm a) ──
def _prior_key(system, user, temperature, run_index):
    parts = [SONNET, system, user, repr(float(temperature)), str(int(MAXTOK)), f"run={run_index}"]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def arm_a_from_cache(wins, system):
    """5 replicate claim-lists per window, read from the warm Task-5 cache ($0)."""
    runs = {}
    misses = 0
    for theory, slug, k, w in wins:
        user = extract_user(theory, w)
        per = []
        for r in range(N_RUNS):
            f = PRIOR_CACHE / f"{_prior_key(system, user, 1.0, r)}.json"
            if not f.exists():
                misses += 1
                per.append([])
                continue
            per.append(parse_claims(json.loads(f.read_text()).get("text", ""), w))
        runs[(slug, k)] = per
    return runs, misses


# ── live arms (b, d) via llm.py ──
def arm_live(wins, system, temperature, tag_prefix, want_conf=False, dry=False):
    runs = {}
    client = None if dry else L.LLM()
    planned = 0
    for theory, slug, k, w in wins:
        user = extract_user(theory, w)
        per = []
        for r in range(N_RUNS):
            planned += 1
            if dry:
                per.append([])
                continue
            rec = client.call(task_id="A5", model=SONNET, system=system,
                              messages=[{"role": "user", "content": user}],
                              replicate_tag=f"{tag_prefix}{SEEDS[r]}", temperature=temperature,
                              max_tokens=MAXTOK, est_in=len(system + user) // 4, est_out=400)
            per.append(parse_claims(rec.get("text") or "", w, want_conf=want_conf))
        runs[(slug, k)] = per
    return runs, planned


# ── clustering (A5 identity) + metrics ──
def _fam(v):
    return value_family(v)


def cluster_identity(c):
    return (c.get("entity_type"), c.get("axis"), c.get("polarity"))


def cluster_runs(per_run):
    """Cluster claims across replicates by A5 identity: same (entity_type,axis,polarity)
    AND value-family intersection. Returns clusters as {run_index: claim}."""
    clusters = []
    for r, claims in enumerate(per_run):
        for c in claims:
            fam = _fam(c["value"])
            placed = False
            for cl in clusters:
                m = next(iter(cl.values()))
                if cluster_identity(m) == cluster_identity(c):
                    mf = _fam(m["value"])
                    if (fam & mf) or (not fam and not mf and m["value"] == c["value"]):
                        cl.setdefault(r, c)
                        placed = True
                        break
            if not placed:
                clusters.append({r: c})
    return clusters


def stability(per_run):
    """Fraction of clusters present in ≥KEEP_MIN of N_RUNS replicates."""
    clusters = cluster_runs(per_run)
    if not clusters:
        return 0.0, 0, 0
    keep = sum(1 for cl in clusters if len(cl) >= KEEP_MIN)
    return keep / len(clusters), keep, len(clusters)


def stability_confweighted(per_run):
    """Keep a cluster iff Σ(confidence over member replicates) ≥ 2.0 OR present ≥KEEP_MIN."""
    clusters = cluster_runs(per_run)
    if not clusters:
        return 0.0, 0, 0
    keep = 0
    for cl in clusters:
        conf_sum = sum(float(c.get("confidence", 0.0)) for c in cl.values())
        if conf_sum >= CONF_SUM_KEEP or len(cl) >= KEEP_MIN:
            keep += 1
    return keep / len(clusters), keep, len(clusters)


def pooled(runs):
    """Flatten {(slug,k): [per-run lists]} → one per-run list over ALL windows (aligned by r)."""
    per_run = [[] for _ in range(N_RUNS)]
    for (slug, k), per in runs.items():
        for r in range(N_RUNS):
            per_run[r].extend(per[r] if r < len(per) else [])
    return per_run


ALL_SLUGS = ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]


def _kept_clusters(runs):
    """≥KEEP_MIN consensus clusters, tagged with their theory slug (theory-aware match)."""
    kept = []
    for (slug, k), per in runs.items():
        for cl in cluster_runs(per):
            if len(cl) >= KEEP_MIN:
                kept.append((slug, next(iter(cl.values()))))
    return kept


def _recovered(approved_with_slug, kept):
    rec = 0
    for slug, a in approved_with_slug:
        aid = (a.get("entity_type"), a.get("axis"), a.get("polarity"))
        af = _fam(str(a.get("value", "")))
        if any(ks == slug and cluster_identity(c) == aid
               and ((_fam(c["value"]) & af) or c["value"] == a.get("value"))
               for ks, c in kept):
            rec += 1
    return rec


def approved_coverage(runs):
    """v2.0.3 dual denominators. Returns {'windowed':(frac,rec,n), 'all95':(frac,rec,n)}.
    windowed = approved IIT+GNWT claims whose source passages lie in A5.1 windows;
    all95 = all 95 approved claims (the preregistered-but-unattainable denominator).
    Matching is theory-aware (same slug) + cluster identity + value-family."""
    win_pids = {s: set() for s in ("iit", "gnwt")}
    for slug in ("iit", "gnwt"):
        for w in windows_for(slug):
            win_pids[slug] |= {p["passage_id"] for p in w}
    windowed, all95 = [], []
    for slug in ALL_SLUGS:
        p = ENGINE / "data" / "claims" / f"{slug}_approved.jsonl"
        for ln in p.read_text().splitlines():
            if not ln.strip():
                continue
            c = json.loads(ln)
            all95.append((slug, c))
            if slug in ("iit", "gnwt") and set(c.get("passage_ids", [])) & win_pids[slug]:
                windowed.append((slug, c))
    kept = _kept_clusters(runs)
    rw, ra = _recovered(windowed, kept), _recovered(all95, kept)
    return {"windowed": (rw / len(windowed) if windowed else 0.0, rw, len(windowed)),
            "all95": (ra / len(all95) if all95 else 0.0, ra, len(all95))}


def import_baseline():
    """a5.stability_baseline = Task-5 27.1% from eval_out/t5/stability.md (cited, not re-measured)."""
    f = EVAL_PRIOR / "eval_out" / "t5" / "stability.md"
    if not f.exists():
        return None, "eval_out/t5/stability.md not found"
    m = re.search(r"\*\*(\d+)/(\d+)\*\*\s*\(([\d.]+)%\)", f.read_text())
    if m:
        return float(m.group(3)) / 100.0, f"{m.group(1)}/{m.group(2)} from eval_out/t5/stability.md"
    return None, "pattern not found in stability.md"


def _fmt_cov(c):
    return f"{c[0]:.3f} ({c[1]}/{c[2]})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print planned live calls; no spend")
    args = ap.parse_args()

    system = extract_system()
    wins = [(t, s, k, w) for t, s in THEORIES for k, w in enumerate(windows_for(s))]
    print(f"[A5.1] windows: {len(wins)} (IIT 8 + GNWT 8), N_RUNS={N_RUNS} {SEEDS}, keep≥{KEEP_MIN}/{N_RUNS}")

    # arm (a) LIVE rerun (v2.0.3 step 4): production prompt, NO temperature, tags a11..a55.
    runs_a, planned_a = arm_live(wins, system, None, "a", dry=args.dry_run)
    # arm (d) conf-weighted LIVE: production prompt + per-claim confidence, tags d11..d55.
    runs_d, planned_d = arm_live(wins, CONF_SYSTEM, None, "d", want_conf=True, dry=args.dry_run)
    # cache-era arm (a): Task-5 baseline replication (reported, not an arm) — reuse warm cache.
    runs_a_cache, misses = arm_a_from_cache(wins, system)

    if args.dry_run:
        print(f"[A5.1] --dry-run: planned LIVE — arm(a) {planned_a} + arm(d) {planned_d} = "
              f"{planned_a + planned_d} Sonnet calls. arm(b)/t0 NOT-APPLICABLE (API 400: temperature "
              f"'Extra inputs are not permitted' for {SONNET}). cache replication: misses={misses}.")
        return 0

    # metrics
    stab_a, keep_a, tot_a = stability(pooled(runs_a))        # arm (c) = consensus-of-5 over live (a)
    cov_a = approved_coverage(runs_a)
    stab_d, keep_d, tot_d = stability_confweighted(pooled(runs_d))
    cov_d = approved_coverage(runs_d)
    stab_ac, keep_ac, tot_ac = stability(pooled(runs_a_cache))   # Task-5 replication (cache-era)
    baseline, baseline_src = import_baseline()
    cost_mult = float(N_RUNS)

    # adoption evaluation (v2.0.3): gate = windowed coverage & stability ≥0.70/≥0.85.
    GATE_S, GATE_C = CFG["thresholds"]["adopt_consensus_min_stability"], CFG["thresholds"]["adopt_min_approved_coverage"]
    cand = ("confweighted", stab_d, cov_d["windowed"][0]) if stab_d > stab_a else ("consensus", stab_a, cov_a["windowed"][0])
    gate_pass = cand[1] >= GATE_S and cand[2] >= GATE_C
    adoption = (f"candidate={cand[0]} (stab={cand[1]:.3f}, windowed_cov={cand[2]:.3f}); "
                f"gate(≥{GATE_S}/≥{GATE_C}) {'PASS→adopt candidate' if gate_pass else 'FAIL'}; "
                + ("" if gate_pass else "fallback t0-vs-baseline, but t0 NOT-APPLICABLE (no temperature) → keep baseline. "
                   "FINAL (pending A5.3 Anu gate): keep single-pass baseline decoding."))

    A5.mkdir(parents=True, exist_ok=True)
    (A5 / "A5.1").mkdir(exist_ok=True)
    (A5 / "A5.1" / "runs.json").write_text(json.dumps(
        {"arm_a_live": {f"{s}_w{k}": v for (s, k), v in runs_a.items()},
         "arm_d_live": {f"{s}_w{k}": v for (s, k), v in runs_d.items()},
         "arm_a_cache_replication": {f"{s}_w{k}": v for (s, k), v in runs_a_cache.items()}},
        ensure_ascii=False, indent=2))

    man = write_manifest(
        "A5", "A5.1", instrument_tag="v1", corpus_tag="v1",
        inputs=[input_ref(ENGINE / "data" / "claims" / "iit_approved.jsonl", "frozen-store"),
                input_ref(ENGINE / "data" / "claims" / "gnwt_approved.jsonl", "frozen-store"),
                {"path": "sprint cache (arm a + d live)", "kind": "extraction", "sha256": None},
                {"path": "eval_out/cache (Task-5 replication)", "kind": "extraction", "sha256": None}],
        outputs=["runs/A5/A5.1/runs.json"],
        seeds={"replicate_tags": SEEDS},
        notes="A5.1 stability arms (v2.0.3): arm(a) LIVE a11..a55, arm(c) consensus, arm(d) "
              "conf-weighted LIVE d11..d55. arm(b)/t0 NOT-APPLICABLE (API rejects temperature). "
              "cache-era (a) kept as Task-5 replication. v1 prompt.")

    CAV = ("A5.1 pre-freeze stability arm on the v1 (production) prompt; informs A5.3 adoption. "
           "Cluster identity = (entity_type,axis,polarity)+value-family (A5 rule); Task-5 baseline "
           "used axis+passage-Jaccard clustering (not recomputed).")
    T0NA = ("not-applicable: API 400 'temperature: Extra inputs are not permitted' for "
            "claude-sonnet-4-6 — no t0 decoding exists (v2.0.3 ruling, 400 branch).")
    reg = Registry()
    common = dict(task="A5", runid="A5.1", instrument_tag="v1", corpus_tag="v1",
                  preregistered=True, pilot=False)
    reg.upsert(metric_id="a5.stability_consensus", value=round(stab_a, 4), n=tot_a,
               caveats=[CAV, f"arm(a)/(c) LIVE: {keep_a}/{tot_a} clusters recur ≥{KEEP_MIN}/{N_RUNS}"], **common)
    reg.upsert(metric_id="a5.stability_confweighted", value=round(stab_d, 4), n=tot_d,
               caveats=[CAV, f"arm(d) G6/CISC: {keep_d}/{tot_d}; keep iff Σconf≥{CONF_SUM_KEEP} or ≥{KEEP_MIN}/{N_RUNS}"], **common)
    reg.upsert(metric_id="a5.stability_t0", value=T0NA, n=None,
               caveats=[CAV, "arm (b) unrunnable; adoption falls through to baseline"], **common)
    reg.upsert(metric_id="a5.stability_cache_replication", value=round(stab_ac, 4), n=tot_ac,
               caveats=["Task-5 baseline replication from the warm cache (cache-era arm a); "
                        f"{keep_ac}/{tot_ac} ≥{KEEP_MIN}/{N_RUNS}; reported, not an adoption arm"],
               task="A5", runid="A5.1", instrument_tag="v1", corpus_tag="v1",
               preregistered=False, pilot=False)
    # coverage — dual denominators (v2.0.3): windowed (adoption) + all-95 (preregistered, printed beside)
    reg.upsert(metric_id="a5.approved_coverage_windowed_consensus", value=round(cov_a["windowed"][0], 4),
               n=cov_a["windowed"][2], caveats=[CAV, "adoption denominator (windowed)", f"{cov_a['windowed'][1]}/{cov_a['windowed'][2]}"], **common)
    reg.upsert(metric_id="a5.approved_coverage_consensus", value=round(cov_a["all95"][0], 4),
               n=cov_a["all95"][2], caveats=[CAV, "preregistered all-95 denominator (unattainable by construction; printed beside windowed)", f"{cov_a['all95'][1]}/95"], **common)
    reg.upsert(metric_id="a5.approved_coverage_windowed_confweighted", value=round(cov_d["windowed"][0], 4),
               n=cov_d["windowed"][2], caveats=[CAV, "adoption denominator (windowed)", f"{cov_d['windowed'][1]}/{cov_d['windowed'][2]}"], **common)
    reg.upsert(metric_id="a5.approved_coverage_confweighted", value=round(cov_d["all95"][0], 4),
               n=cov_d["all95"][2], caveats=[CAV, "preregistered all-95 denominator", f"{cov_d['all95'][1]}/95"], **common)
    reg.upsert(metric_id="a5.cost_multiplier_consensus", value=cost_mult, n=None,
               caveats=[f"{N_RUNS} replicate calls vs 1 single-pass per window"], **common)
    if baseline is not None:
        reg.upsert(metric_id="a5.stability_baseline", value=round(baseline, 4), n=None,
                   caveats=[f"Task-5 import ({baseline_src}); NOT re-measured; axis+passage-Jaccard clustering"],
                   task="A5", runid="A5.1", instrument_tag="v1", corpus_tag="v1",
                   preregistered=False, pilot=False)
    reg.save()

    print(f"[A5.1] stability LIVE — consensus(a/c)={stab_a:.3f} ({keep_a}/{tot_a}), "
          f"confweighted(d)={stab_d:.3f} ({keep_d}/{tot_d})")
    print(f"[A5.1] t0(b) = NOT-APPLICABLE (API rejects temperature)")
    print(f"[A5.1] cache replication (Task-5) stability={stab_ac:.3f} ({keep_ac}/{tot_ac}); baseline={baseline}")
    print(f"[A5.1] coverage consensus — windowed={_fmt_cov(cov_a['windowed'])}, all95={_fmt_cov(cov_a['all95'])}")
    print(f"[A5.1] coverage confweighted — windowed={_fmt_cov(cov_d['windowed'])}, all95={_fmt_cov(cov_d['all95'])}")
    print(f"[A5.1] ADOPTION: {adoption}")
    print(f"[A5.1] meter total spent: ${L.LLM().meter.data['total_usd']:.4f}")
    print(f"  manifest: {man.relative_to(SPRINT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
