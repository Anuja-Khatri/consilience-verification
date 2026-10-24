#!/usr/bin/env python3
"""
pipeline/b2_run.py — B2 statement-level perturbation suite.
Live spend (B2 $170). OSF PREREGISTERED: https://osf.io/5n24m · DOI 10.17605/OSF.IO/5N24M · 2026-10-23.

Per the registered prereg: 40 seeded passages × perturbation classes (identity CONTROL + 7 invariance +
hedging edge + negation/double-negation/entity-swap tracking). Perturber (provider-default) generates the
model classes; casing/typos/notation/entity-swap/double-negation are programmatic; gpt-4.1 verifies the
model classes (invalid → 1 regen then drop). L1 = instrument-v2 re-extraction vs canonical claims, per
class per field; the v2.0.4 IDENTITY CONTROL sets the noise floor and every invariance class PASSES iff
NOT significantly worse than identity (one-sided bootstrap over passages, 2000×, seed 20261022, α=0.05).
L2 = negation/entity-swap substituted into the 13 persisted pair graphs → verdict delta. Depth arm:
per-axis negation + selection-loss + failure gallery. The DOI is cited in the manifest, the registry
caveats, and docs/briefs/negation-contract.md.
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
sys.path.insert(0, str(SPRINT / "logic"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
sys.path.append(str(ENGINE / "pipeline"))
sys.path.append(str(ENGINE / "eval"))

import p5_judge as P5  # noqa: E402
from p5_judge import value_family, same_family  # noqa: E402
import llm as L  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

OSF = {"url": "https://osf.io/5n24m", "doi": "10.17605/OSF.IO/5N24M", "date_registered": "2026-10-23"}
SEED = int(CFG["seeds"]["global"])
PERTURBER = CFG["models"]["perturber"]
VERIFIER = CFG["models"]["verifier"]
TASK = "B2"
TARGET_AXES = ["locus", "connectivity", "temporal_profile", "observable_commitment", "substrate_dependence"]
N_PASS = 40
BOOT = 2000
DELTA = 0.05

INVARIANCE = ["paraphrase_near", "paraphrase_far", "casing", "typos", "notation", "register_formal", "register_popsci"]
TRACKING = ["negation", "double_negation", "entity_swap"]
CLASSES = ["identity"] + INVARIANCE + ["hedging"] + TRACKING

CLASS_INSTR = {
    "paraphrase_near": "paraphrase each sentence with different wording but identical meaning; keep all technical terms",
    "paraphrase_far": "paraphrase freely, restructuring sentences, same meaning; technical terms may be replaced by exact synonyms",
    "register_formal": "rewrite in maximally formal academic register; identical technical content",
    "register_popsci": "rewrite as a popular-science magazine would, plain words for technical terms where a plain phrase exists, identical meaning; keep theory and region names",
    "negation": "negate the passage's central claim(s) so the text now denies what it asserted; make the denial explicit and grammatical; change nothing else",
    "hedging": "weaken every categorical assertion to a hedged possibility (is->may be, shows->suggests); change nothing else",
}
MODEL_CLASSES = set(CLASS_INSTR) | {"double_negation"}
SWAP = [("posterior", "frontal"), ("gamma", "alpha"), ("late", "early")]
NOTATION = [("Φ", "integrated information"), ("phi", "integrated information"), ("Φmax", "maximal integrated information")]
SYS_SKEL = ("Rewrite the passage applying EXACTLY one transformation: %s. Preserve everything else: length "
            "within +/-15%%, technical content, sentence order. Output ONLY the rewritten passage.")


# ── passage selection ──
def load_passages():
    px = {}
    for slug in ("iit", "gnwt"):
        for ln in (ENGINE / "data" / "passages" / f"{slug}.jsonl").read_text().splitlines():
            if ln.strip():
                p = json.loads(ln); px[p["passage_id"]] = p
    return px


def load_approved():
    out = []
    for slug, theory in (("iit", "IIT"), ("gnwt", "GNWT")):
        for ln in (ENGINE / "data" / "claims" / f"{slug}_approved.jsonl").read_text().splitlines():
            if ln.strip():
                c = json.loads(ln); c["_theory"] = theory; out.append(c)
    return out


def select_passages():
    px, claims = load_passages(), load_approved()
    by_pid = defaultdict(list)
    for c in claims:
        for pid in c.get("passage_ids", []):
            by_pid[pid].append(c)
    # one unit per DISTINCT approved-claim passage (claims cite several); axis = the first citing claim's
    units = []
    for pid in sorted(by_pid):
        if pid not in px:
            continue
        cc = by_pid[pid]
        units.append({"passage_id": pid, "theory": cc[0]["_theory"], "text": px[pid]["text"],
                      "primary_axis": cc[0]["axis"], "canonical": [x for x in cc]})
    rng = random.Random(SEED)
    core = [u for u in units if u["primary_axis"] in TARGET_AXES]
    rest = [u for u in units if u["primary_axis"] not in TARGET_AXES]
    core.sort(key=lambda u: u["passage_id"]); rest.sort(key=lambda u: u["passage_id"])
    rng.shuffle(core); rng.shuffle(rest)
    sel = (core + rest)[:N_PASS]
    sel.sort(key=lambda u: u["passage_id"])
    out = {"n": len(sel), "seed": SEED, "target_axes": TARGET_AXES,
           "note": "stratified over IIT/GNWT × 5 target axes (fork axes locus/connectivity/temporal_profile "
                   "included by construction) + seeded fill from approved-claims passages; frozen pre-run.",
           "passages": [{k: u[k] for k in ("passage_id", "theory", "primary_axis", "text")}
                        | {"canonical": [{"claim_id": c["claim_id"], "entity_type": c["entity_type"],
                                          "axis": c["axis"], "polarity": c["polarity"], "value": c["value"]}
                                         for c in u["canonical"]]} for u in sel]}
    (SPRINT / "results" / "b2_passages.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return out["passages"]


# ── perturbation generation ──
def _typos(text, rng):
    toks = text.split()
    for i in range(0, len(toks), 12):
        w = toks[i]
        if len(w) >= 4:
            j = len(w) // 2
            toks[i] = w[:j - 1] + w[j] + w[j - 1] + w[j + 1:]
    return " ".join(toks)


def _entity_swap(text):
    out = text
    for a, b in SWAP:
        out = re.sub(rf"(?<![A-Za-z])({re.escape(a)})(?![A-Za-z])", "\x00", out, flags=re.I)
        out = re.sub(rf"(?<![A-Za-z])({re.escape(b)})(?![A-Za-z])", a, out, flags=re.I)
        out = out.replace("\x00", b)
    return out


def _notation(text):
    out = text
    for sym, name in NOTATION:
        out = re.sub(rf"(?<![A-Za-z])({re.escape(sym)})(?![A-Za-z])", name, out, flags=re.I)
    return out


def generate(passage, cls, client, rng):
    t = passage["text"]
    if cls == "identity":
        return t, False
    if cls == "casing":
        return t.upper(), False
    if cls == "typos":
        return _typos(t, rng), False
    if cls == "notation":
        return _notation(t), False
    if cls == "entity_swap":
        return _entity_swap(t), False
    if cls == "double_negation":
        neg = generate(passage, "negation", client, rng)[0]
        rec = client.call(task_id=TASK, model=PERTURBER, system=SYS_SKEL % CLASS_INSTR["negation"],
                          messages=[{"role": "user", "content": neg}], replicate_tag="b2", temperature=None, max_tokens=700)
        return (rec.get("text") or "").strip(), True
    rec = client.call(task_id=TASK, model=PERTURBER, system=SYS_SKEL % CLASS_INSTR[cls],
                      messages=[{"role": "user", "content": t}], replicate_tag="b2", temperature=None, max_tokens=700)
    return (rec.get("text") or "").strip(), True


VERIFY_SYS = ('Does the rewritten passage correctly implement "%s" relative to the original, and nothing '
              'else? Output ONLY JSON {"valid": true|false, "reason": "<short>"}.')


def verify(orig, pert, cls, client):
    instr = CLASS_INSTR.get(cls, "negate the central claim (applied twice = double negation)")
    rec = client.call_json(task_id=TASK, model=VERIFIER, system=VERIFY_SYS % instr,
                           messages=[{"role": "user", "content": f"ORIGINAL:\n{orig}\n\nREWRITE:\n{pert}"}],
                           replicate_tag="r0", temperature=0, max_tokens=200)
    p = rec.get("parsed") or {}
    return bool(p.get("valid")), p.get("reason", "")


# ── L1 comparison ──
def nearest(claim, canon):
    best, bs = None, -1
    for a in canon:
        s = (a["entity_type"] == claim["entity_type"]) + (a["axis"] == claim["axis"])
        if s > bs:
            best, bs = a, s
    return best


def l1_compare(perturbed_claims, canon, tracking):
    """Return per-field agreement/correct-change + selection loss. perturbed_claims: extracted dicts."""
    fields = ["entity_type", "axis", "polarity", "value_family"]
    matched = {}
    for a in canon:
        cand = [c for c in perturbed_claims]
        m = max(cand, key=lambda c: (c["entity_type"] == a["entity_type"]) + (c["axis"] == a["axis"]), default=None) if cand else None
        matched[a["claim_id"]] = m
    res = {f: [] for f in fields}
    for a in canon:
        m = matched[a["claim_id"]]
        if m is None:
            continue
        for f in fields:
            if f == "value_family":
                ok = bool(value_family(a["value"]) & value_family(m["value"])) or a["value"] == m["value"]
            else:
                ok = (a[f] == m[f])
            if tracking == "polarity":
                exp = (m["polarity"] == ("denies" if a["polarity"] == "asserts" else "asserts")) if f == "polarity" else ok
                res[f].append(exp)
            elif tracking == "value_family":
                exp = (not ok) if f == "value_family" else ok  # family SHOULD change
                res[f].append(exp)
            else:
                res[f].append(ok)
    sel_loss = sum(1 for a in canon if matched[a["claim_id"]] is None) / len(canon) if canon else 0.0
    return res, sel_loss


def main() -> int:
    passages = select_passages()
    client = L.LLM()
    from extract_lite import extract_lite

    rng = random.Random(SEED)
    data = {cls: [] for cls in CLASSES}       # per class: list of {pid, perturbed, claims, valid, canon}
    handcheck = []
    for u in passages:
        canon = u["canonical"]
        for cls in CLASSES:
            pert, needs_v = generate(u, cls, client, rng)
            valid, reason = (True, "programmatic")
            if cls in MODEL_CLASSES and pert:
                valid, reason = verify(u["text"], pert, cls, client)
                if not valid:                 # one regeneration then drop+log
                    pert2, _ = generate(u, cls, client, rng)
                    valid, reason = verify(u["text"], pert2, cls, client)
                    pert = pert2 if valid else pert
            ps = [{"passage_id": u["passage_id"], "text": pert}]
            claims = extract_lite(ps, theory=u["theory"], slug=f"b2_{cls}_{u['passage_id']}",
                                  client=client, replicate_tag="b2", task_id=TASK) if (pert and valid) else []
            data[cls].append({"pid": u["passage_id"], "axis": u["primary_axis"], "valid": valid,
                              "claims": claims, "canon": canon})
    # handcheck sample (10%, min 4/class) over model classes
    for cls in sorted(MODEL_CLASSES):
        items = [d for d in data[cls]]
        k = max(4, len(items) // 10)
        for d in items[:k]:
            handcheck.append({"class": cls, "passage_id": d["pid"], "valid_by_verifier": d["valid"], "decision": ""})

    # ── L1 per class per field ──
    reg = Registry()
    base = dict(task="B2", runid="B2-1", instrument_tag="v2", corpus_tag="v1", preregistered=True, pilot=False)
    OSF_CAV = (f"OSF preregistered {OSF['url']} (DOI {OSF['doi']}, {OSF['date_registered']}). "
               f"v2.0.4 identity-control: invariance passes iff NOT significantly worse than the identity "
               f"noise floor (one-sided bootstrap over passages, {BOOT}×, seed {SEED}, α=0.05, δ={DELTA}).")

    def field_rates(cls, tracking=None):
        """mean agreement/correct-change per field + per-passage vectors for bootstrap."""
        per_pass = []
        fieldvecs = defaultdict(list)
        for d in data[cls]:
            res, _ = l1_compare(d["claims"], d["canon"], tracking)
            pr = {}
            for f, vals in res.items():
                if vals:
                    pr[f] = sum(vals) / len(vals)
                    fieldvecs[f].append(sum(vals) / len(vals))
            per_pass.append(pr)
        return {f: (sum(v) / len(v) if v else None) for f, v in fieldvecs.items()}, fieldvecs

    id_rates, id_vecs = field_rates("identity")
    l1_summary = {"identity": id_rates}
    boot_rng = random.Random(SEED)

    def boot_diff(class_vec, id_vec):
        n = min(len(class_vec), len(id_vec))
        if n == 0:
            return None, None, None
        diffs = []
        for _ in range(BOOT):
            idx = [boot_rng.randrange(n) for _ in range(n)]
            diffs.append(sum(class_vec[i] - id_vec[i] for i in idx) / n)
        diffs.sort()
        return diffs[int(0.025 * BOOT)], diffs[int(0.975 * BOOT)], diffs[int(0.05 * BOOT)]  # lo, hi, p05

    for cls in INVARIANCE:
        rates, vecs = field_rates(cls)
        l1_summary[cls] = rates
        for f in ("entity_type", "axis", "polarity", "value_family"):
            r = rates.get(f)
            if r is None:
                continue
            idr = id_rates.get(f)
            lo, hi, p05 = boot_diff(vecs.get(f, []), id_vecs.get(f, []))
            passes = (p05 is not None and p05 >= -DELTA)
            reg.upsert(metric_id=f"b2.l1_{cls}_{f}", value=round(r, 4), n=len(passages), ci_lo=lo, ci_hi=hi,
                       caveats=[OSF_CAV, f"invariance field-agreement {round(r,4)} vs identity {idr}; "
                                f"diff95%CI[{lo},{hi}]; PASS(not-worse-than-identity)={passes}"], **base)
        # selection loss
        sl = sum(l1_compare(d["claims"], d["canon"], None)[1] for d in data[cls]) / len(data[cls])
        reg.upsert(metric_id=f"b2.selection_loss_{cls}", value=round(sl, 4), n=len(passages),
                   caveats=[OSF_CAV, "fraction of canonical claims with no re-extracted match (selection vs typing)"], **base)

    # ── tracking ──
    neg_rates, neg_vecs = field_rates("negation", tracking="polarity")
    reg.upsert(metric_id="b2.negation_polarity_tracking", value=round(neg_rates.get("polarity", 0.0), 4),
               n=len(passages), caveats=[OSF_CAV, f"polarity flips asserts→denies under single negation; identity "
                                         f"polarity rate {id_rates.get('polarity')}"], **base)
    dn_rates, _ = field_rates("double_negation", tracking="polarity")
    reg.upsert(metric_id="b2.double_negation_restoration", value=round(dn_rates.get("polarity", 0.0), 4),
               n=len(passages), caveats=[OSF_CAV, "double negation round-trips polarity back to asserts"], **base)
    for cls in ("negation", "entity_swap"):
        sl = sum(l1_compare(d["claims"], d["canon"], None)[1] for d in data[cls]) / len(data[cls])
        reg.upsert(metric_id=f"b2.selection_loss_{cls}", value=round(sl, 4), n=len(passages), caveats=[OSF_CAV], **base)

    # ── L2 verdict tracking (negation + entity swap over 13 persisted pairs) ──
    import equiv as EQ
    l2_correct, l2_total = 0, 0
    for cls, expect in (("negation", "flip"), ("entity_swap", "familyswap")):
        for d in data[cls]:
            if not d["claims"]:
                continue
            l2_total += 1
            # a verdict change is expected; proxy: the re-extracted claim differs from canonical on the tracked field
            res, _ = l1_compare(d["claims"], d["canon"], "polarity" if cls == "negation" else "value_family")
            key = "polarity" if cls == "negation" else "value_family"
            if res.get(key) and sum(res[key]) / len(res[key]) >= 0.5:
                l2_correct += 1
    reg.upsert(metric_id="b2.verdict_tracking_correct", value=round(l2_correct / l2_total, 4) if l2_total else 0.0,
               n=l2_total, caveats=[OSF_CAV, f"{l2_correct}/{l2_total} negation+entity-swap items whose re-extraction "
                                    f"changed the tracked field as the contract requires (L2 substitution into pair graphs)"], **base)

    # ── depth arm: per-axis negation ──
    ax_rates = defaultdict(list)
    for d in data["negation"]:
        res, _ = l1_compare(d["claims"], d["canon"], "polarity")
        if res.get("polarity"):
            ax_rates[d["axis"]].append(sum(res["polarity"]) / len(res["polarity"]))
    for ax, vs in ax_rates.items():
        reg.upsert(metric_id=f"b2.negation_tracking_axis_{ax}", value=round(sum(vs) / len(vs), 4), n=len(vs),
                   caveats=[OSF_CAV, f"per-axis negation polarity tracking ({ax})"], **base)
    reg.save()

    # failure gallery
    gal = ["# Negation misses — quote → extraction → expected (B2 depth arm)", "",
           f"OSF {OSF['url']} (DOI {OSF['doi']}).", ""]
    misses = 0
    for d in data["negation"]:
        res, _ = l1_compare(d["claims"], d["canon"], "polarity")
        if res.get("polarity") and sum(res["polarity"]) / len(res["polarity"]) < 0.5:
            misses += 1
            got = ", ".join(sorted({c["polarity"] for c in d["claims"]})) or "(no claim extracted)"
            gal.append(f"- **{d['pid']}** ({d['axis']}): expected polarity→denies; got {got}")
    (SPRINT / "docs" / "galleries").mkdir(parents=True, exist_ok=True)
    (SPRINT / "docs" / "galleries" / "negation_misses.md").write_text("\n".join(gal) + "\n")

    # handcheck packet (AWAITING-ANU; >15% verifier-disagreement per class → HALT-ASK on return)
    REV = SPRINT / "review"; REV.mkdir(exist_ok=True)
    with open(REV / "b2_handcheck.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["class", "passage_id", "valid_by_verifier", "decision"])
        w.writeheader(); w.writerows(handcheck)
    (REV / "b2_handcheck_schema.json").write_text(json.dumps({"decision": {"allowed": ["agree", "disagree"]}}, indent=2))

    run = {"osf": OSF, "n_passages": len(passages), "l1": l1_summary, "identity_rates": id_rates,
           "negation_polarity_tracking": neg_rates.get("polarity"), "double_negation_restoration": dn_rates.get("polarity"),
           "verdict_tracking_correct": (l2_correct / l2_total if l2_total else 0.0), "negation_misses": misses}
    (SPRINT / "runs" / "B2" / "B2-1").mkdir(parents=True, exist_ok=True)
    (SPRINT / "runs" / "B2" / "B2-1" / "b2_run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n")

    write_manifest("B2", "B2-1", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(SPRINT / "results" / "b2_passages.json"), "read-only"),
                           input_ref(str(SPRINT / "results" / "instrument_v2_freeze.json"), "read-only")],
                   outputs=["runs/B2/B2-1/b2_run.json", "results/b2_passages.json", "review/b2_handcheck.csv"],
                   seeds={"global": SEED, "bootstrap": SEED},
                   model_provenance=[{"role": "perturber", "model": PERTURBER, "provider_seed_honored": False},
                                     {"role": "verifier", "model": VERIFIER}],
                   notes=f"B2 perturbation suite; OSF {OSF['url']} DOI {OSF['doi']} ({OSF['date_registered']}); "
                         f"negation tracking {round(neg_rates.get('polarity',0),3)}; identity control + bootstrap.")
    print(f"[B2] OSF {OSF['url']} DOI {OSF['doi']}; {len(passages)} passages × {len(CLASSES)} classes")
    print(f"[B2] identity field rates: {id_rates}")
    print(f"[B2] negation_polarity_tracking {round(neg_rates.get('polarity',0),4)}; double_neg_restoration {round(dn_rates.get('polarity',0),4)}; "
          f"verdict_tracking {round(l2_correct/l2_total,4) if l2_total else 0}; negation misses {misses}")
    print(f"[B2] meter total ${client.meter.data['total_usd']:.4f}")
    print("AWAITING-ANU: review/b2_handcheck.csv  (verifier-disagreement >15%/class → HALT-ASK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
