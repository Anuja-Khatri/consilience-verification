#!/usr/bin/env python3
"""
pipeline/td4_run.py — TD4 (= G2) typed-claims inter-agent protocol game (SPEC §TD4). Live spend (TD4_game $60).

Two agent contexts (same model `game_agent`, STRICTLY SEPARATE llm.py conversations). Agent A holds one
A-side claim rendered in OBFUSCATED vocabulary A (corpora/obfuscation_map.yaml); Agent B holds a 6-candidate
set rendered in a SECOND obfuscation map B (corpora/obfuscation_map_b.yaml) — distinct targets, so neither
agent ever sees the other's raw vocabulary (the firewall). 30 approved items (review/td4_items.csv). Two
arms on the same items: (i) FREE-TEXT (≤80 words/turn), (ii) TYPED-CARD (each message must be valid claim-
card JSON per review/td4_schema.json; invalid → schema bounce, counts as a turn). ≤6 exchange turns, then a
read-out: B commits a candidate (or none). Owner fixes applied to BOTH maps (D-052): GNW alias family +
theory-identifying coined terms (PSC, MICS, exclusion, Φmax/Φ-structure, C1/C2), word-boundary case-
insensitive + dash-normalised; PRE-FLIGHT asserts ZERO source terms remain in every rendered item.

Metrics: g2.task_acc_<arm>, g2.turns_mean_<arm>, g2.tokens_mean_<arm>, g2.firewall_leaks (a map-A target in
B's messages or a map-B target in A's), g2.value_field_leak_rate. D-041 (memory td4-deobfuscation-firewall):
per-message de-obfuscation leak counts (REAL source terms resurfacing despite obfuscated inputs) →
g2.deobf_leaks; the firewall is reported "surface-obfuscated, identity NOT guaranteed hidden" unless leaks==0.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import yaml

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "logic"))
CFG = yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
import facts as F  # noqa: E402
import llm as L  # noqa: E402
from registry import Registry  # noqa: E402
from runmanifest import write_manifest, input_ref  # noqa: E402

GAME_MODEL = CFG["models"]["game_agent"]
MAX_TURNS = 6
TASK = "TD4_game"
_DASH = {ord("–"): "-", ord("—"): "-", ord("‒"): "-", ord("−"): "-"}


def norm_dash(s):
    return s.translate(_DASH)


class Obfuscator:
    """Parameterised a6_obfuscate: word-boundary, case-insensitive, dash-normalised, longest-first."""
    def __init__(self, map_path):
        m = yaml.safe_load(Path(map_path).read_text())
        self.pairs = {}
        for sec in ("theory_names", "coined_terms", "people"):
            for src, rec in (m.get(sec) or {}).items():
                self.pairs[norm_dash(str(src).lower())] = (rec["target"] if isinstance(rec, dict) else rec)
        self.sources = sorted(self.pairs, key=len, reverse=True)
        self.targets = sorted({t.lower() for t in self.pairs.values()}, key=len, reverse=True)
        self._rx = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(s) for s in self.sources) + r")(?![A-Za-z0-9])",
                              re.IGNORECASE) if self.sources else None

    def _recase(self, matched, target):
        if matched.isupper():
            return target.upper()
        if matched.istitle():
            return target.title()
        if matched[:1].isupper():
            return target[:1].upper() + target[1:]
        return target

    def apply(self, text):
        t = norm_dash(text)
        return self._rx.sub(lambda mo: self._recase(mo.group(1), self.pairs[norm_dash(mo.group(1).lower())]), t) if self._rx else t

    def remaining_sources(self, text):
        t = norm_dash(text.lower())
        return [s for s in self.sources if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", t)]

    def assert_clean(self, text):
        left = self.remaining_sources(self.apply(text))
        assert not left, f"TD4 LEAK: source terms survived: {left}"

    def target_hits(self, text):
        t = norm_dash(text.lower())
        return [g for g in self.targets if re.search(r"(?<![a-z0-9])" + re.escape(g) + r"(?![a-z0-9])", t)]


OBF_A = Obfuscator(SPRINT / "corpora" / "obfuscation_map.yaml")
OBF_B = Obfuscator(SPRINT / "corpora" / "obfuscation_map_b.yaml")
REAL_SOURCES = sorted(set(OBF_A.sources) | set(OBF_B.sources), key=len, reverse=True)


def deobf_leaks(text):
    """D-041: distinct REAL source terms (original theory vocab) that resurface in an agent message."""
    t = norm_dash(text.lower())
    return sorted({s for s in REAL_SOURCES if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", t)})


def _valid_card(txt):
    try:
        c = json.loads(re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip())
    except Exception:
        return None
    need = {"entity_type", "axis", "polarity", "value_description", "question"}
    if not isinstance(c, dict) or not need <= set(c):
        return None
    if len(str(c.get("value_description", "")).split()) > 12:
        return None
    return c


def dialogue(client, a_text, cands, arm):
    """Run one ≤6-turn A↔B exchange (separate conversations) + B read-out. Returns dict."""
    if arm == "free":
        a_sys = ("You are Agent A in a coordination game across a vocabulary firewall. You hold ONE claim "
                 "(below), in your own vocabulary. Help your partner decide which of THEIR candidate claims "
                 "means the same as yours (or that none do). Reply in natural language, <=80 words/turn.")
        b_sys = ("You are Agent B. You hold 6 candidate claims (below), in your own vocabulary. Exchange with "
                 "your partner to decide which ONE of your candidates means the same as the partner's claim, or "
                 "that NONE do. Reply in natural language, <=80 words/turn.")
    else:
        a_sys = ("You are Agent A in a coordination game across a vocabulary firewall. You hold ONE claim. "
                 "EVERY message MUST be a single valid claim-card JSON: {\"entity_type\",\"axis\",\"polarity\" "
                 "(asserts|denies),\"value_description\" (<=12 words),\"question\"}. Use the card to convey your "
                 "claim and ask what you need. No prose outside the JSON.")
        b_sys = ("You are Agent B. You hold 6 candidate claims. EVERY message MUST be a single valid claim-card "
                 "JSON {\"entity_type\",\"axis\",\"polarity\",\"value_description\" (<=12 words),\"question\"}. "
                 "Use cards to compare your candidates to the partner's and decide which (if any) matches.")
    a_init = f"Your claim: {a_text}\nBegin: send your first message to Agent B."
    b_init = "Your candidate claims:\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(cands)) + \
             "\nAgent A will message you first; respond each turn."
    histA = [{"role": "user", "content": a_init}]
    histB = [{"role": "user", "content": b_init}]
    msgs, turns, tokens, bounces = [], 0, 0, 0
    for t in range(MAX_TURNS):
        agent, sys_p, hist, other = ("A", a_sys, histA, histB) if t % 2 == 0 else ("B", b_sys, histB, histA)
        rec = client.call(task_id=TASK, model=GAME_MODEL, system=sys_p, messages=hist,
                          replicate_tag="td4", temperature=None, max_tokens=260)
        txt = (rec.get("text") or "").strip()
        tokens += rec.get("usage", {}).get("output_tokens", 0) if isinstance(rec.get("usage"), dict) else 0
        turns += 1
        if arm == "typed" and _valid_card(txt) is None:   # schema bounce (counts as a turn)
            bounces += 1
            hist.append({"role": "assistant", "content": txt})
            hist.append({"role": "user", "content": "INVALID CARD — resend a single valid claim-card JSON."})
            continue
        hist.append({"role": "assistant", "content": txt})
        other.append({"role": "user", "content": f"Partner ({agent}) says:\n{txt}"})
        msgs.append({"agent": agent, "text": txt})
    # read-out (B commits; not counted as an exchange turn, but tokens/leaks counted)
    histB.append({"role": "user", "content": "Final decision. Output ONLY JSON: "
                  "{\"choice\": <candidate number 1-6, or \"none\">}."})
    rec = client.call(task_id=TASK, model=GAME_MODEL, system=b_sys if arm == "free" else
                      "Output ONLY JSON {\"choice\": <1-6 or \"none\">}.", messages=histB,
                      replicate_tag="td4", temperature=None, max_tokens=40)
    try:
        choice = json.loads(re.sub(r"^```(?:json)?|```$", "", (rec.get("text") or "").strip(), flags=re.M).strip()).get("choice")
    except Exception:
        choice = None
    return {"msgs": msgs, "turns": turns, "tokens": tokens, "bounces": bounces, "choice": choice}


def main() -> int:
    items = json.loads((SPRINT / "results" / "td4_items.json").read_text())["items"]
    approved = {r["item_id"] for r in csv.DictReader(open(SPRINT / "review" / "td4_items.csv"))
                if r["decision"] == "approve"}
    items = [it for it in items if it["item_id"] in approved]
    g = F.load_graphs()
    stmt = {n["claim_id"]: n["statement"] for s in g.values() for n in s["nodes"]}

    # PRE-FLIGHT (owner d): zero source terms remain in every rendered item
    preflight_fail = []
    for it in items:
        if OBF_A.remaining_sources(OBF_A.apply(stmt[it["a_claim_id"]])):
            preflight_fail.append((it["item_id"], "A", OBF_A.remaining_sources(OBF_A.apply(stmt[it["a_claim_id"]]))))
        for cid in it["candidates"]:
            if OBF_B.remaining_sources(OBF_B.apply(stmt[cid])):
                preflight_fail.append((it["item_id"], cid, OBF_B.remaining_sources(OBF_B.apply(stmt[cid]))))
    if preflight_fail:
        print(f"TD4 PRE-FLIGHT FAIL (source terms remain): {preflight_fail[:8]}")
        return 1
    print(f"[TD4] pre-flight PASS — 0 source terms remain across {len(items)} items × both maps.")

    client = L.LLM()
    results = {"free": [], "typed": []}
    for it in items:
        a_text = OBF_A.apply(stmt[it["a_claim_id"]])
        cands = [OBF_B.apply(stmt[cid]) for cid in it["candidates"]]
        ref = it["reference_match"]
        ref_idx = (it["candidates"].index(ref) + 1) if ref != "none" and ref in it["candidates"] else "none"
        for arm in ("free", "typed"):
            d = dialogue(client, a_text, cands, arm)
            correct = (str(d["choice"]) == str(ref_idx)) if ref_idx != "none" else (str(d["choice"]).lower() == "none")
            # leaks per message
            fw = sum(1 for m in d["msgs"] if (m["agent"] == "B" and OBF_A.target_hits(m["text"]))
                     or (m["agent"] == "A" and OBF_B.target_hits(m["text"])))
            deobf = sum(len(deobf_leaks(m["text"])) for m in d["msgs"])
            vfl = 0
            if arm == "typed":
                for m in d["msgs"]:
                    c = _valid_card(m["text"])
                    if c and (OBF_A.target_hits(str(c.get("value_description", ""))) + OBF_B.target_hits(str(c.get("value_description", "")))
                              + deobf_leaks(str(c.get("value_description", "")))):
                        vfl += 1
            results[arm].append({"item_id": it["item_id"], "ref_idx": ref_idx, "choice": d["choice"],
                                 "correct": correct, "turns": d["turns"], "tokens": d["tokens"],
                                 "bounces": d["bounces"], "firewall_leaks": fw, "deobf_leaks": deobf,
                                 "value_field_leaks": vfl})

    def agg(arm):
        rs = results[arm]
        n = len(rs)
        return {"n": n, "task_acc": round(sum(r["correct"] for r in rs) / n, 4),
                "turns_mean": round(sum(r["turns"] for r in rs) / n, 3),
                "tokens_mean": round(sum(r["tokens"] for r in rs) / n, 1),
                "firewall_leaks": sum(r["firewall_leaks"] for r in rs),
                "deobf_leaks": sum(r["deobf_leaks"] for r in rs),
                "value_field_leaks": sum(r["value_field_leaks"] for r in rs),
                "bounces": sum(r["bounces"] for r in rs)}
    A = {arm: agg(arm) for arm in ("free", "typed")}
    total_deobf = A["free"]["deobf_leaks"] + A["typed"]["deobf_leaks"]
    vfl_den = sum(len(r["item_id"]) and 1 for r in results["typed"]) * MAX_TURNS or 1
    vfl_rate = round(A["typed"]["value_field_leaks"] / (len(results["typed"]) * MAX_TURNS), 4)
    firewall_verdict = ("surface-obfuscated, identity NOT guaranteed hidden (de-obfuscation leaks > 0)"
                        if total_deobf > 0 else "firewall holds (0 de-obfuscation leaks across all agent messages)")

    rundir = SPRINT / "runs" / "TD4" / "TD4-1"
    rundir.mkdir(parents=True, exist_ok=True)
    (rundir / "game.json").write_text(json.dumps({"agg": A, "firewall_verdict": firewall_verdict,
                                                   "results": results}, ensure_ascii=False, indent=2) + "\n")

    reg = Registry()
    base = dict(task="TD4", runid="TD4-1", instrument_tag="v2", corpus_tag="v1", preregistered=True, pilot=True)
    cav = (f"TD4 (=G2) protocol game, {A['free']['n']} items, two separate game_agent conversations across a "
           f"vocabulary firewall (map A vs map B, distinct targets; owner fixes D-052; pre-flight: 0 source "
           f"terms remain in any rendered item). §0.11 pilot. D-041 FIREWALL VERDICT: {firewall_verdict}.")
    for arm in ("free", "typed"):
        reg.upsert(metric_id=f"g2.task_acc_{arm}", value=A[arm]["task_acc"], n=A[arm]["n"],
                   caveats=[cav, f"{arm}: turns_mean {A[arm]['turns_mean']}, tokens_mean {A[arm]['tokens_mean']}, "
                                f"schema-bounces {A[arm]['bounces']}"], **base)
        reg.upsert(metric_id=f"g2.turns_mean_{arm}", value=A[arm]["turns_mean"], n=A[arm]["n"], caveats=[cav], **base)
        reg.upsert(metric_id=f"g2.tokens_mean_{arm}", value=A[arm]["tokens_mean"], n=A[arm]["n"], caveats=[cav], **base)
    reg.upsert(metric_id="g2.firewall_leaks", value=A["free"]["firewall_leaks"] + A["typed"]["firewall_leaks"],
               n=A["free"]["n"] + A["typed"]["n"],
               caveats=[cav, f"map-A target in B's msgs or map-B target in A's: free {A['free']['firewall_leaks']}, "
                             f"typed {A['typed']['firewall_leaks']} (free-text leaks are EXPECTED, part of the finding)"], **base)
    reg.upsert(metric_id="g2.value_field_leak_rate", value=vfl_rate, n=len(results["typed"]) * MAX_TURNS,
               caveats=[cav, "fraction of typed-card messages whose value_description (the ≤12-word free field, the "
                             "DESIGNED leak channel) carries a cross-map target or real source term"], **base)
    reg.upsert(metric_id="g2.deobf_leaks", value=total_deobf, n=A["free"]["n"] + A["typed"]["n"],
               caveats=[cav, f"D-041 per-message de-obfuscation leak count (real source terms resurfacing): "
                             f"free {A['free']['deobf_leaks']}, typed {A['typed']['deobf_leaks']}. "
                             f"Firewall reported as '{firewall_verdict}'."], **base)
    reg.save()

    write_manifest("TD4", "TD4-1", instrument_tag="v2", corpus_tag="v1",
                   inputs=[input_ref(str(SPRINT / "results" / "td4_items.json"), "read-only"),
                           input_ref(str(SPRINT / "corpora" / "obfuscation_map.yaml"), "read-only"),
                           input_ref(str(SPRINT / "corpora" / "obfuscation_map_b.yaml"), "read-only")],
                   outputs=["runs/TD4/TD4-1/game.json"], seeds={"global": CFG["seeds"]["global"]},
                   model_provenance=[{"role": "game_agent", "model": GAME_MODEL, "provider_seed_honored": False}],
                   notes=f"TD4 protocol game free vs typed; acc {A['free']['task_acc']}/{A['typed']['task_acc']}; firewall verdict: {firewall_verdict}")
    print(f"[TD4] free:  acc {A['free']['task_acc']} turns {A['free']['turns_mean']} tokens {A['free']['tokens_mean']} fw_leaks {A['free']['firewall_leaks']} deobf {A['free']['deobf_leaks']}")
    print(f"[TD4] typed: acc {A['typed']['task_acc']} turns {A['typed']['turns_mean']} tokens {A['typed']['tokens_mean']} fw_leaks {A['typed']['firewall_leaks']} deobf {A['typed']['deobf_leaks']} bounces {A['typed']['bounces']} vfl_rate {vfl_rate}")
    print(f"[TD4] D-041 firewall verdict: {firewall_verdict}")
    print(f"[TD4] meter total ${client.meter.data['total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
