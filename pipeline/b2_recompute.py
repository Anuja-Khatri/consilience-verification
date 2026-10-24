#!/usr/bin/env python3
"""
pipeline/b2_recompute.py — B2 valid-only recompute + reviewable handcheck re-emit (owner follow-up). $0 (cache).

Reconstructs every B2 (passage × class) item from the llm.py cache (deterministic; $0), capturing the
original passage, the perturbed passage, the verifier verdict + reason, and the re-extracted claims. Then:
  • reports per class: n_generated, n_verifier_valid, n_used_in_metrics;
  • recomputes b2.* on VALID items only and marks N/A when n_valid==0;
  • FIXES b2.selection_loss_* to valid-only (the original counted verifier-invalid perturbations as 100%
    loss — conflating verifier-rejection with extraction-loss); reports both as-run and valid-only;
  • re-emits review/b2_handcheck.csv with full content per row (original, perturbed, class contract,
    verifier verdict + reason) — same 28 sampled rows.
Agreement/tracking rates were ALREADY valid-only (invalid items had claims=[] → contributed no field
values); this only corrects the reported n and the selection-loss denominator, and makes all-invalid
classes N/A instead of a misleading 0.0.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
import b2_run as B  # noqa: E402  (generate/verify/l1_compare/select_passages/CLASSES/MODEL_CLASSES/CLASS_INSTR)
import llm as L  # noqa: E402
from registry import Registry  # noqa: E402

CONTRACT = {
    "identity": "noise-floor CONTROL — unchanged passage; all typed fields SHOULD stay identical",
    "paraphrase_near": "INVARIANCE — reworded, same meaning; typed fields unchanged",
    "paraphrase_far": "INVARIANCE — freely restructured, same meaning; typed fields unchanged",
    "casing": "INVARIANCE — UPPERCASED; typed fields unchanged",
    "typos": "INVARIANCE — seeded typos (1/12 tokens); typed fields unchanged",
    "notation": "INVARIANCE — symbol↔name swap (Φ↔'integrated information'); typed fields unchanged",
    "register_formal": "INVARIANCE — formal academic rewrite; typed fields unchanged",
    "register_popsci": "INVARIANCE — popular-science rewrite; typed fields unchanged",
    "hedging": "DECLARED EDGE — assertions hedged; field behaviour REPORTED (polarity has no hedged value)",
    "negation": "TRACKING — central claim negated; polarity SHOULD FLIP asserts→denies (L2 verdict updates)",
    "double_negation": "TRACKING — negation applied twice; polarity SHOULD RETURN to asserts (round-trip)",
    "entity_swap": "TRACKING — entity table swap (posterior↔frontal, gamma↔alpha, late↔early); value-family SHOULD swap",
}
TRACK_FIELD = {"negation": "polarity", "double_negation": "polarity", "entity_swap": "value_family"}


def reconstruct():
    ps = B.select_passages()
    client = L.LLM()
    rng = random.Random(B.SEED)
    from extract_lite import extract_lite
    items = defaultdict(list)
    for u in ps:
        for cls in B.CLASSES:
            pert, _ = B.generate(u, cls, client, rng)
            valid, reason = True, "programmatic (correct by construction)"
            if cls in B.MODEL_CLASSES and pert:
                valid, reason = B.verify(u["text"], pert, cls, client)
                if not valid:
                    pert2, _ = B.generate(u, cls, client, rng)
                    v2, r2 = B.verify(u["text"], pert2, cls, client)
                    if v2:
                        pert, valid, reason = pert2, True, r2 + " (after 1 regen)"
                    else:
                        reason = reason + " | regen also invalid"
            claims = extract_lite([{"passage_id": u["passage_id"], "text": pert}], theory=u["theory"],
                                  slug=f"b2_{cls}_{u['passage_id']}", client=client, replicate_tag="b2",
                                  task_id="B2") if (pert and valid) else []
            items[cls].append({"pid": u["passage_id"], "axis": u["primary_axis"], "original": u["text"],
                               "perturbed": pert, "valid": valid, "reason": reason, "claims": claims,
                               "canon": u["canonical"]})
    return ps, items, client


def main() -> int:
    ps, items, client = reconstruct()
    N = len(ps)

    # per-class counts
    counts = {}
    for cls in B.CLASSES:
        nv = sum(1 for it in items[cls] if it["valid"])
        counts[cls] = {"n_generated": N, "n_verifier_valid": nv, "n_used_in_metrics": nv}

    def pass_vecs(cls, track=None):
        """{field: {pid: per-passage rate}} over VALID items (for bootstrap alignment vs identity)."""
        out = defaultdict(dict)
        for it in items[cls]:
            if not it["valid"]:
                continue
            res, _ = B.l1_compare(it["claims"], it["canon"], track)
            for f, vals in res.items():
                if vals:
                    out[f][it["pid"]] = sum(vals) / len(vals)
        return out

    def field_rates_valid(cls, track=None):
        pv = pass_vecs(cls, track)
        return {f: (round(sum(d.values()) / len(d), 4) if d else None, len(d)) for f, d in pv.items()}

    DELTA, BOOT = 0.05, 2000
    boot_rng = random.Random(B.SEED)
    ID_PV = pass_vecs("identity")

    def boot_pass(cls_pv_field, id_pv_field):
        """one-sided bootstrap over passages present in BOTH; PASS iff 5th pct of (class-identity) ≥ -δ."""
        pids = [p for p in cls_pv_field if p in id_pv_field]
        n = len(pids)
        if n == 0:
            return None, None, None
        cv = [cls_pv_field[p] for p in pids]; iv = [id_pv_field[p] for p in pids]
        diffs = []
        for _ in range(BOOT):
            idx = [boot_rng.randrange(n) for _ in range(n)]
            diffs.append(sum(cv[i] - iv[i] for i in idx) / n)
        diffs.sort()
        return diffs[int(0.025 * BOOT)], diffs[int(0.975 * BOOT)], diffs[int(0.05 * BOOT)]

    def sel_loss(cls, valid_only):
        pool = [it for it in items[cls] if (it["valid"] or not valid_only)]
        if not pool:
            return None
        return round(sum(B.l1_compare(it["claims"], it["canon"], None)[1] for it in pool) / len(pool), 4)

    reg = Registry()
    base = dict(task="B2", runid="B2-1", instrument_tag="v2", corpus_tag="v1", preregistered=True, pilot=False)
    OSF = "OSF https://osf.io/5n24m DOI 10.17605/OSF.IO/5N24M (2026-10-23)."
    VALIDONLY = ("VALID-ONLY recompute (owner follow-up): verifier-invalid perturbations are EXCLUDED "
                 "(they carried no re-extracted claims, so they never entered agreement/tracking rates; "
                 "the reported n is now n_verifier_valid, and all-invalid classes are N/A not 0.0).")

    # invariance + identity L1 per field (valid-only, n=n_valid, identity-control bootstrap PASS preserved)
    id_rates = {f: (sum(d.values()) / len(d) if d else None) for f, d in ID_PV.items()}
    for cls in ["identity"] + B.INVARIANCE:
        pv = pass_vecs(cls)
        for f in ("entity_type", "axis", "polarity", "value_family"):
            if f in pv and pv[f]:
                r = round(sum(pv[f].values()) / len(pv[f]), 4); nu = len(pv[f])
                extra = ""
                if cls in B.INVARIANCE:
                    lo, hi, p05 = boot_pass(pv[f], ID_PV.get(f, {}))
                    passes = (p05 is not None and p05 >= -DELTA)
                    extra = (f" vs identity {round(id_rates.get(f),4) if id_rates.get(f) is not None else None}; "
                             f"diff95%CI[{lo},{hi}]; PASS(not-worse-than-identity)={passes}")
                reg.upsert(metric_id=f"b2.l1_{cls}_{f}", value=r, n=nu,
                           caveats=[OSF, VALIDONLY, f"n_generated {N}, n_valid {counts[cls]['n_verifier_valid']}, "
                                    f"n_used {nu} (valid items matched on this field){extra}"], **base)
        # selection loss — valid-only (FIX) + as-run reported alongside
        sv, sr = sel_loss(cls, True), sel_loss(cls, False)
        reg.upsert(metric_id=f"b2.selection_loss_{cls}" if cls != "identity" else "b2.selection_loss_identity",
                   value=sv, n=counts[cls]["n_verifier_valid"],
                   caveats=[OSF, f"VALID-ONLY selection loss {sv} (was {sr} as-run incl. invalid-as-full-loss); "
                            f"fraction of canonical claims with no re-extracted match over valid perturbations."], **base)

    # tracking classes (valid-only; N/A if n_valid==0)
    def track_metric(mid, cls, field, note):
        fr = field_rates_valid(cls, track=field)
        if field in fr and fr[field][0] is not None:
            r, nu = fr[field]
            reg.upsert(metric_id=mid, value=r, n=nu,
                       caveats=[OSF, VALIDONLY, f"{note} over n_valid={counts[cls]['n_verifier_valid']} "
                                f"(n_used={nu}); n_generated {N}. Low-n: interpret with care." if nu < 15 else
                                f"{note} over n_valid={counts[cls]['n_verifier_valid']} (n_used={nu})."], **base)
        else:
            reg.upsert(metric_id=mid, value="not-applicable (0 verifier-valid perturbations)",
                       n=counts[cls]["n_verifier_valid"], caveats=[OSF, VALIDONLY,
                       f"{note}: 0 valid items → N/A (was a misleading 0.0 as-run)."], **base)
    track_metric("b2.negation_polarity_tracking", "negation", "polarity", "polarity flips asserts→denies under single negation")
    track_metric("b2.double_negation_restoration", "double_negation", "polarity", "double negation round-trips polarity to asserts")
    for cls in ("negation", "entity_swap"):
        sv, sr = sel_loss(cls, True), sel_loss(cls, False)
        reg.upsert(metric_id=f"b2.selection_loss_{cls}", value=sv, n=counts[cls]["n_verifier_valid"],
                   caveats=[OSF, f"VALID-ONLY {sv} (was {sr} as-run)."], **base)
    reg.save()

    # persist full per-item detail
    detail = {cls: [{k: (it[k][:600] if k in ("original", "perturbed") else it[k])
                     for k in ("pid", "axis", "original", "perturbed", "valid", "reason")}
                    | {"n_claims": len(it["claims"])} for it in items[cls]] for cls in B.CLASSES}
    (SPRINT / "runs" / "B2" / "B2-1" / "b2_items.json").write_text(
        json.dumps({"per_class_counts": counts, "items": detail}, ensure_ascii=False, indent=2) + "\n")

    # re-emit handcheck with FULL content — same 28 rows (first 4 passages × sorted model classes)
    rows = []
    for cls in sorted(B.MODEL_CLASSES):
        for it in items[cls][:4]:
            rows.append({"class": cls, "passage_id": it["pid"], "class_contract": CONTRACT[cls],
                         "original_passage": it["original"][:600], "perturbed_passage": it["perturbed"][:600],
                         "verifier_verdict": "valid" if it["valid"] else "invalid",
                         "verifier_reason": it["reason"][:300], "decision": ""})
    with open(SPRINT / "review" / "b2_handcheck.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["class", "passage_id", "class_contract", "original_passage",
                                          "perturbed_passage", "verifier_verdict", "verifier_reason", "decision"])
        w.writeheader(); w.writerows(rows)
    (SPRINT / "review" / "b2_handcheck_schema.json").write_text(json.dumps(
        {"decision": {"allowed": ["agree", "disagree"]},
         "note": "agree/disagree with the verifier_verdict after reading original vs perturbed against class_contract"}, indent=2))

    print("per-class n_generated / n_verifier_valid / n_used:")
    for cls in B.CLASSES:
        print(f"  {cls:18s} {counts[cls]['n_generated']:2d} / {counts[cls]['n_verifier_valid']:2d} / {counts[cls]['n_used_in_metrics']:2d}")
    print(f"\n[B2-recompute] handcheck re-emitted with full content ({len(rows)} rows).")
    print(f"[B2-recompute] meter total ${client.meter.data['total_usd']:.4f} (cache; $0 added)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
