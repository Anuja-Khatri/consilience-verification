#!/usr/bin/env python3
"""
pipeline/ss2_oinformation.py — SS2 O-information over claim systems (SPEC §6 SS2 = R2; pilot).

Arm 1 (per theory + whole-corpus PRIMARY): variables = typed fields {entity_type, axis,
family} as categoricals (polarity EXCLUDED — single-class: 95 asserts / 0 denies, zero
entropy; reported in ss2.excluded_vars). O-information sign: >0 redundancy-dominated,
<0 synergy-dominated. Arm 2 (cross-theory): (axisA_family, axisB_family, grade) over the
221 persisted correspondences. NULLS (mandatory): 1000 per-column field-shuffle surrogates
→ z-score per system. No O-info number ships without its surrogate z. Frozen-store, API-free.
Brief: docs/briefs/o-information.md (§0.11 pilot sentence mandatory).
"""
from __future__ import annotations

import glob
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

import yaml
import dit
import dit.multivariate as mv

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import p5_judge as P5  # noqa: E402
from registry import Registry  # noqa: E402

CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
GRAPHS = ENGINE / "data" / "graphs"
SLUGS = ["active-inference", "cemi", "gnwt", "iit", "nrep", "orch-or"]
SEED = CFG["seeds"]["global"]
N_SURROGATE = 1000


def fam(v):
    s = sorted(P5.value_family(v))
    return "|".join(s) if s else "∅"


CLAIMS_DIR = ENGINE / "data" / "claims"


def claims():
    """APPROVED claims store (data/claims/*_approved.jsonl) — the canonical typed record;
    polarity is single-class here (95 asserts), unlike the judge graphs which carry 3
    deliberate POLARITY_REENCODE flips for judging."""
    out = []
    for slug in SLUGS:
        for ln in (CLAIMS_DIR / f"{slug}_approved.jsonl").read_text().splitlines():
            if not ln.strip():
                continue
            c = json.loads(ln)
            out.append({"theory": c["theory"], "entity_type": c["entity_type"], "axis": c["axis"],
                        "polarity": c["polarity"], "family": fam(c["value"]), "claim_id": c["claim_id"],
                        "value": c["value"]})
    return out


def o_info(samples):
    """O-information of a list of equal-length tuples (empirical distribution)."""
    if not samples or len(samples[0]) < 3:
        return None
    n = len(samples)
    c = Counter(samples)
    d = dit.Distribution({k: v / n for k, v in c.items()})
    return float(mv.o_information(d))


def surrogate_z(samples, seed=SEED, n=N_SURROGATE):
    real = o_info(samples)
    if real is None:
        return real, None, "too few vars/samples"
    k = len(samples[0])
    cols = [[s[j] for s in samples] for j in range(k)]
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        shuffled = [list(col) for col in cols]
        for col in shuffled:
            rng.shuffle(col)
        surr = [tuple(shuffled[j][i] for j in range(k)) for i in range(len(samples))]
        oi = o_info(surr)
        if oi is not None:
            vals.append(oi)
    import statistics as st
    mu = st.mean(vals); sd = st.pstdev(vals)
    z = (real - mu) / sd if sd > 1e-12 else None
    return real, z, f"null μ={mu:.4f} σ={sd:.4f} (n={len(vals)})"


def main() -> int:
    cl = claims()
    reg = Registry()
    base = dict(task="SS2", runid="SS2-1", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=True)
    results = {}

    # Arm 1 — whole corpus (PRIMARY), fields: entity_type, axis, family (polarity excluded)
    corpus = [(c["entity_type"], c["axis"], c["family"]) for c in cl]
    oi, z, note = surrogate_z(corpus)
    results["corpus"] = (oi, z, note, len(corpus))
    reg.upsert(metric_id="ss2.o_info_corpus", value=round(oi, 4), n=len(corpus),
               caveats=[f"whole-corpus O-info over (entity_type,axis,family); sign "
                        f"{'redundancy' if oi > 0 else 'synergy'}-dominated; {note}",
                        "polarity EXCLUDED (single-class 95 asserts/0 denies, zero entropy)"], **base)
    reg.upsert(metric_id="ss2.null_z_corpus", value=(round(z, 4) if z is not None else "undefined"),
               n=N_SURROGATE, caveats=[f"z vs {N_SURROGATE} per-column field-shuffle surrogates; {note}"], **base)

    # Arm 1 — per theory (pilot n)
    theories = sorted({c["theory"] for c in cl})
    for si, th in enumerate(theories):
        sub = [(c["entity_type"], c["axis"], c["family"]) for c in cl if c["theory"] == th]
        if len(sub) < 4:
            continue
        oi, z, note = surrogate_z(sub, seed=SEED + si + 1)
        slug = th.lower().replace(" ", "-")
        results[slug] = (oi, z, note, len(sub))
        reg.upsert(metric_id=f"ss2.o_info_{slug}", value=round(oi, 4), n=len(sub),
                   caveats=[f"per-theory pilot ({th}, n={len(sub)}); sign "
                            f"{'redundancy' if oi > 0 else 'synergy'}-dominated; {note}"], **base)

    # Arm 2 — cross-theory (axisA_family, axisB_family, grade) over persisted corrs.
    # Families from the APPROVED canonical values (consistent with Arm 1).
    cmap = {c["claim_id"]: c for c in cl}
    cross = []
    for jf in sorted(glob.glob(str(ENGINE / "results" / "*_judge.json"))):
        for c in json.loads(Path(jf).read_text()).get("correspondences", []):
            if c.get("kind") != "node":
                continue
            a, b = cmap.get(c["left_ids"][0]), cmap.get(c["right_ids"][0])
            if a and b:
                cross.append((a["family"], b["family"], c["grade"]))
    oi, z, note = surrogate_z(cross)
    results["crosstheory"] = (oi, z, note, len(cross))
    reg.upsert(metric_id="ss2.o_info_crosstheory", value=round(oi, 4), n=len(cross),
               caveats=[f"cross-theory O-info over (axisA_family,axisB_family,grade); sign "
                        f"{'redundancy' if oi > 0 else 'synergy'}-dominated; {note}"], **base)
    reg.upsert(metric_id="ss2.null_z_crosstheory", value=(round(z, 4) if z is not None else "undefined"),
               n=N_SURROGATE, caveats=[f"z vs {N_SURROGATE} field-shuffle surrogates; {note}"], **base)
    reg.upsert(metric_id="ss2.excluded_vars", value="polarity",
               n=1, caveats=["polarity excluded from Arm 1 — single-class (95 asserts, 0 denies), "
                             "zero entropy; the single-class fact is itself a finding (see B3 PABAK note)"], **base)
    reg.save()

    L = [f"# O-information over claim systems (SS2 / Sussex)", "",
         "This is a pilot-scale feasibility study (N=95 claims; cross-theory N=221 correspondences); "
         "it demonstrates that the measurement is constructible and runs end-to-end, not that the "
         "estimate is tight.", "",
         "Polarity is excluded from the per-system fields — single-class (95 asserts, 0 denies), "
         "zero entropy (itself a finding). Every O-info carries a surrogate z (1000 field-shuffle "
         "nulls; Rosas's nulls doctrine).", "",
         "| system | N | O-info | sign | surrogate z |", "|---|---|---|---|---|"]
    def row(name, r):
        oi, z, note, n = r
        sign = "redundancy" if oi and oi > 0 else "synergy"
        L.append(f"| {name} | {n} | {oi:.4f} | {sign}-dominated | {z if z is None else round(z,3)} |")
    row("whole-corpus (primary)", results["corpus"])
    row("cross-theory (corrs)", results["crosstheory"])
    for slug in SLUGS:
        if slug in results:
            row(f"{slug} (pilot)", results[slug])
    L += ["", "Shares the SS1 spectrometer figure style — one build, two instruments (Imperial PID "
          "+ Sussex O-info). No O-info number ships without its surrogate z."]
    (SPRINT / "docs" / "briefs").mkdir(parents=True, exist_ok=True)
    (SPRINT / "docs" / "briefs" / "o-information.md").write_text("\n".join(L) + "\n")
    print(f"SS2: corpus O-info {results['corpus'][0]:.4f} (z={results['corpus'][1]}); "
          f"cross-theory {results['crosstheory'][0]:.4f} (z={results['crosstheory'][1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
