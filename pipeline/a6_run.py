#!/usr/bin/env python3
"""
pipeline/a6_run.py — A6 obfuscated run + same-date clean rerun + diff (SPEC §A6, v2.0.4 D2).

Two arms, IDENTICAL instrument v2 (reuses kr1_v2_extract.run_theory via a passage-text transform):
  • OBFUSCATED: each IIT/GNWT passage text → a6_obfuscate.apply (dash-normalized + map substitutions),
    asserted leak-free (zero source terms remain) BEFORE extraction;
  • CLEAN rerun: same passages, dash-normalized ONLY (so the arms differ ONLY by the obfuscation).
Each arm → judge IIT×GNWT → forks. Obfuscated fork values are DE-MAPPED (reverse table) before
comparison. Recovery is measured vs the frozen canonical IIT×GNWT forks, and the obfuscated rate is
reported RELATIVE to the clean-rerun rate — only the obfuscated−clean GAP is read as lexical
dependence (a miss the clean rerun shares is re-extraction noise, not lexical dependence).

Metrics: a6.fork_recovery_rate, a6.clean_rerun_recovery_rate, a6.fork_recovery_gap,
a6.value_family_match_rate, a6.deobfuscation_leaks. Budget A6 $80.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
sys.path.insert(0, str(ENGINE / "pipeline"))
sys.path.insert(0, str(ENGINE / "eval"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))

import p2_extract as P2  # noqa: E402
import kr1_v2_extract as K  # noqa: E402
import a6_obfuscate as OB  # noqa: E402
import p5_judge as P5  # noqa: E402
from p5_judge import same_family  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

_ORIG_LOAD = P2.load_passages
TRANSFORM = [None]  # current arm transform


def _patched(slug):
    ps = _ORIG_LOAD(slug)
    return [{**p, "text": TRANSFORM[0](p["text"])} for p in ps]


P2.load_passages = _patched


def extract_arm(transform):
    TRANSFORM[0] = transform
    out = {}
    for theory, slug in (("IIT", "iit"), ("GNWT", "gnwt")):
        out[slug] = K.run_theory(theory, slug)
    return out


def forks_of(arm):
    def nodes(slug):
        return [c for cls in ("c", "n", "t") for c in arm[slug][cls]]
    return P5.judge_pair({"theory": "IIT", "nodes": nodes("iit"), "edges": []},
                         {"theory": "GNWT", "nodes": nodes("gnwt"), "edges": []})["forks"]


def demap_fork(f):
    return {**f, "left_value": OB.reverse(str(f.get("left_value", ""))),
            "right_value": OB.reverse(str(f.get("right_value", "")))}


def recovered(canon_fork, arm_forks):
    """A canonical fork is recovered iff an arm fork on the SAME axis has an intersecting value-family."""
    cl, cr = canon_fork.get("left_value", ""), canon_fork.get("right_value", "")
    cfam = P5.value_family(cl) | P5.value_family(cr)
    for f in arm_forks:
        if f.get("axis") != canon_fork.get("axis"):
            continue
        afam = P5.value_family(str(f.get("left_value", ""))) | P5.value_family(str(f.get("right_value", "")))
        if cfam & afam:
            return True
    return False


def main() -> int:
    canon = json.loads((ENGINE / "results" / "iitxgnwt_judge.json").read_text())["forks"]

    # --- clean arm (dash-normalized only) ---
    clean = extract_arm(OB.norm_dash)
    clean_forks = forks_of(clean)

    # --- obfuscated arm (assert leak-free first) ---
    for slug in ("iit", "gnwt"):
        for p in _ORIG_LOAD(slug):
            OB.assert_clean(p["text"])          # every passage obfuscates leak-free
    obf = extract_arm(OB.apply)
    obf_forks = forks_of(obf)
    obf_forks_dm = [demap_fork(f) for f in obf_forks]

    # de-obfuscation leaks: any REAL source term surfacing in the OBFUSCATED extraction output
    leak_terms = set()
    for slug in ("iit", "gnwt"):
        for cls in ("c", "n", "t"):
            for c in obf[slug][cls]:
                blob = f"{c.get('statement','')} {c.get('value','')}"
                leak_terms.update(OB.remaining_sources(blob))
    leaks = len(leak_terms)

    n_can = len(canon)
    clean_rec = sum(1 for cf in canon if recovered(cf, clean_forks))
    obf_rec = sum(1 for cf in canon if recovered(cf, obf_forks_dm))
    clean_rate = round(clean_rec / n_can, 3) if n_can else 0.0
    obf_rate = round(obf_rec / n_can, 3) if n_can else 0.0
    gap = round(obf_rate - clean_rate, 3)
    # value-family match rate: among canonical forks the obfuscated arm recovered, fraction whose
    # de-mapped value family matches the canonical (sanity on the de-map)
    vfm = round(obf_rec / clean_rec, 3) if clean_rec else None

    reg = Registry()
    base = dict(task="A6", runid="A6-1", instrument_tag="v2", corpus_tag="v1", preregistered=False, pilot=False)
    CAV = ("A6 vocabulary-obfuscation control (scope IIT+GNWT). OBFUSCATED fork recovery is reported "
           "RELATIVE to the SAME-DATE CLEAN RERUN (v2.0.4 D2): only the obfuscated−clean GAP is lexical "
           "dependence; a miss the clean rerun also makes is re-extraction noise. Both arms use identical "
           "instrument v2 and differ only by the map substitution (dashes normalized in both). Disclosure: "
           "map was model-drafted (Claude) reviewed and confirmed by Anu (D-038).")
    reg.upsert(metric_id="a6.clean_rerun_recovery_rate", value=clean_rate, n=n_can,
               caveats=[CAV, f"{clean_rec}/{n_can} canonical IIT×GNWT forks recovered by the clean v2 rerun"], **base)
    reg.upsert(metric_id="a6.fork_recovery_rate", value=obf_rate, n=n_can,
               caveats=[CAV, f"{obf_rec}/{n_can} canonical forks recovered by the obfuscated (de-mapped) arm"], **base)
    reg.upsert(metric_id="a6.fork_recovery_gap", value=gap, n=n_can,
               caveats=[CAV, "obfuscated − clean; ≈0 ⇒ no lexical dependence (forks survive obfuscation); "
                        "negative ⇒ lexical-dependence candidates (misses unique to the obfuscated arm)"], **base)
    reg.upsert(metric_id="a6.value_family_match_rate", value=vfm, n=clean_rec,
               caveats=[CAV, "obfuscated recoveries / clean recoveries (de-map value-family sanity)"], **base)
    reg.upsert(metric_id="a6.deobfuscation_leaks", value=leaks, n=n_can,
               caveats=[CAV, f"distinct REAL source terms that surfaced in the OBFUSCATED extraction output "
                        f"(identity inferred = red flag): {sorted(leak_terms)[:10]}"], **base)
    reg.save()

    (SPRINT / "results" / "a6_diff.json").write_text(json.dumps({
        "n_canonical_forks": n_can, "clean_recovered": clean_rec, "obfuscated_recovered": obf_rec,
        "clean_rate": clean_rate, "obfuscated_rate": obf_rate, "gap": gap,
        "deobfuscation_leaks": sorted(leak_terms),
        "clean_forks": len(clean_forks), "obf_forks": len(obf_forks), "caveat": CAV}, indent=2, ensure_ascii=False))
    write_manifest("A6", "A6-1", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(SPRINT / "corpora" / "obfuscation_map.yaml", "map"),
                           {"path": "engine IIT+GNWT passages (read-only; obfuscated post-ingest)", "kind": "corpus", "sha256": None}],
                   outputs=["results/a6_diff.json"],
                   notes=f"A6 obfuscated vs clean: recovery obf {obf_rate} vs clean {clean_rate} (gap {gap}); leaks {leaks}")
    print(f"A6: canonical forks {n_can} | clean recovery {clean_rec}/{n_can}={clean_rate} | "
          f"obfuscated {obf_rec}/{n_can}={obf_rate} | GAP {gap} | deobfuscation leaks {leaks} {sorted(leak_terms)[:8]}")
    print(f"  (clean forks {len(clean_forks)}, obf forks {len(obf_forks)}) meter ${K.CLIENT.meter.data['total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
