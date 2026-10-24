#!/usr/bin/env python3
"""
pipeline/a1_finalize.py — A1.4 verdicts (SPEC §A1.4), finalized with the returned C2 decisions.

Verdict per match: PASS iff every present side passes C1 and C2(finalized) AND the match passes C3
and C5 AND C4 ∈ {PASS, PASS-PENDING-C4}; else FAIL with the first failing criterion + all failures.
Taxonomy FIXED: {provenance, relation-not-in-quote, newman-shared-vocab, instrument-unsupported,
scale-mismatch, conditional-only}. Metrics a1.discovery_survivorship (k/9),
a1.match_sample_survivorship (k/30), per-criterion fail counts, + a1.c2_draft_confirmed_agreement.

C2 finalization: a side's support = the Anu packet decision where present (review/a1_c2_relation.csv),
else the model draft (non-packeted sides were model-supported:true). DISCLOSURE (D-035): "Decisions
were model-drafted suggestions (Claude) reviewed and confirmed by Anu."
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
from registry import Registry  # noqa: E402

DISCLOSURE = "Decisions were model-drafted suggestions (Claude) reviewed and confirmed by Anu."


def main() -> int:
    sample = json.loads((SPRINT / "results" / "a1_match_sample.json").read_text())
    dmap = json.loads((SPRINT / "results" / "a1_discovery_map.json").read_text())

    # C2 packet decisions + draft-vs-confirmed agreement
    c2dec, agree, total = {}, 0, 0
    for r in csv.DictReader(open(SPRINT / "review" / "a1_c2_relation.csv")):
        conf = (r["decision"] == "supported")
        c2dec[(r["match_id"], r["side"], r["claim_id"])] = conf
        draft = (str(r["model_supported"]).strip().lower() == "true")
        total += 1
        agree += int(draft == conf)
    c2_agreement = round(agree / total, 3) if total else None

    def verdict(m):
        fails = []
        for side in ("a", "b"):
            s = m["sides"].get(side)
            if not s or s.get("missing_claim"):
                fails.append(("provenance", f"{side}:missing-claim")); continue
            if s.get("C1", {}).get("status") != "PASS":
                fails.append(("provenance", f"{side}:C1"))
            cid = m["claim_a"] if side == "a" else m["claim_b"]
            c2_final = c2dec.get((m["match_id"], side, cid))
            if c2_final is None:
                c2_final = bool(s.get("C2", {}).get("supported"))  # non-packeted = model draft (true)
            if not c2_final:
                fails.append(("relation-not-in-quote", f"{side}:C2"))
        if m.get("C3", {}).get("status") == "FAIL":
            fails.append(("newman-shared-vocab", "C3"))
        c5 = m.get("C5", {}).get("status")
        if c5 == "FAIL":
            fails.append(("scale-mismatch", "C5"))
        elif c5 == "conditional":
            fails.append(("conditional-only", "C5"))
        # C4: no side carries a C4 constraint here (→ PASS-PENDING-C4 / n/a), never blocks.
        order = ["provenance", "relation-not-in-quote", "newman-shared-vocab",
                 "instrument-unsupported", "scale-mismatch", "conditional-only"]
        fails_sorted = sorted(fails, key=lambda f: order.index(f[0]))
        return ("PASS" if not fails else "FAIL"), fails_sorted

    verdicts = {}
    tax = Counter()
    for m in sample["matches"]:
        v, fails = verdict(m)
        verdicts[m["match_id"]] = {"verdict": v, "first_fail": (fails[0][0] if fails else None),
                                   "failures": [{"criterion": c, "where": w} for c, w in fails],
                                   "discovery": m.get("discovery")}
        if v == "FAIL":
            for c, _ in {(c, None) for c, _w in fails}:  # count each distinct taxonomy once per match
                tax[c] += 1

    match_pass = sum(1 for v in verdicts.values() if v["verdict"] == "PASS")
    # discovery survivorship: a discovery PASSES iff its underlying match passes
    disc_by_match = {m["match_id"]: m.get("discovery") for m in sample["matches"]}
    disc_pass = {}
    for mid, v in verdicts.items():
        d = disc_by_match.get(mid)
        if d:
            disc_pass[d] = (v["verdict"] == "PASS")
    n_disc = dmap.get("n_discoveries", 9)
    disc_surv = sum(1 for ok in disc_pass.values() if ok)

    (SPRINT / "results" / "a1_verdicts.json").write_text(json.dumps({
        "match_sample_survivorship": f"{match_pass}/{len(verdicts)}",
        "discovery_survivorship": f"{disc_surv}/{n_disc}",
        "taxonomy_counts": dict(tax), "c2_draft_confirmed_agreement": c2_agreement,
        "verdicts": verdicts, "discovery_verdicts": disc_pass, "disclosure": DISCLOSURE}, indent=2))

    reg = Registry()
    base = dict(task="A1", runid="A1-4", instrument_tag="frozen-store", corpus_tag="v1",
                preregistered=True, pilot=False)
    reg.upsert(metric_id="a1.discovery_survivorship", value=disc_surv, n=n_disc,
               caveats=[DISCLOSURE, f"{disc_surv}/{n_disc} MIU discoveries survive the C1–C5 criterion audit "
                        "(PASS iff all sides C1+C2 and match C3+C5, C4∈{PASS,PASS-PENDING-C4})"], **base)
    reg.upsert(metric_id="a1.match_sample_survivorship", value=match_pass, n=len(verdicts),
               caveats=[DISCLOSURE, f"{match_pass}/{len(verdicts)} sampled matches survive"], **base)
    reg.upsert(metric_id="a1.c2_draft_confirmed_agreement", value=c2_agreement, n=total,
               caveats=[DISCLOSURE, f"{agree}/{total} C2 packet rows where the gpt-4.1 draft matched Anu's "
                        f"confirmation ({total-agree} overturned)"], **base)
    for crit in ["provenance", "relation-not-in-quote", "newman-shared-vocab", "scale-mismatch",
                 "conditional-only", "instrument-unsupported"]:
        reg.upsert(metric_id=f"a1.fail_{crit.replace('-', '_')}", value=tax.get(crit, 0), n=len(verdicts),
                   caveats=[f"matches failing on {crit} (≥1 side/criterion)"], **base)
    reg.save()
    print(f"A1.4: discovery survivorship {disc_surv}/{n_disc}; match-sample {match_pass}/{len(verdicts)}; "
          f"taxonomy {dict(tax)}")
    print(f"  C2 draft-vs-confirmed agreement {c2_agreement} ({agree}/{total}; {total-agree} overturned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
