# A deterministic, auditable engine for cross-theory claim comparison

**The verification and evaluation release of the Consilience engine (paper v1).**

Typed-claim extraction + a deterministic rule-based judge that compares scientific claims across theories,
with built-in verification (the judge re-expressed as a logic program, an SMT theory, and proof objects)
and cross-field discovery (re-adjudication + held-out key recovery against explicit chance rates).

**All headline numbers below render from one numbers-locked registry snapshot**
(`paper/NUMBERS_LOCK.json`, sha `e9c877812c8c6897…`, 2026-10, instrument v2 / corpus v1) — the same number
appears in the paper and in every rendered table (numbers lock).

## Headline results
**Verification (the judge is a transparent, checkable function of typed fields):**
- Judge-as-logic-program verdict equivalence **1.0**; SMT congruence
  **1.0**; machine-checked proof coverage **0.9842**;
  **0** integrity-constraint violations.
- Statement-level contracts (OSF-preregistered, DOI 10.17605/OSF.IO/5N24M) with a re-extraction noise-floor
  control: the **negation headline** — explicit negation flips polarity only **0.1765**
  of the time (the extraction front-end under-propagates negation; the deterministic judge is correct given
  fields). Obfuscation control: fork recovery gap **0.072** but
  **12** de-obfuscation leaks (surface obfuscation does not blind the model to
  theory identity). Two-vendor reliability panel (gpt-4.1 × gemini-3.1-pro-preview): entity κ
  **0.525** / axis κ **0.503** / polarity PABAK
  **0.811**.

**Discovery (reported with chance rates and honest negatives):**
- Cross-field re-adjudication (A2): of pairs with a recorded prior tier, **0.8571**
  downgrade or withdraw under re-typing — a strict audit, not a headline win.
- Held-out key recovery: COGITATE **2 of 3** predictions (revised) but **not significant** against a
  1000-key permutation null (p = **0.075**); eLife synergistic-workspace **0 exact /
  6 partial of 14** validated rows — below chance (empirical p = **0.981**, n = 1000).
- Unification index (F2): rank stability τ **0.7165** (weight-sensitive, reported).

## Repository layout
- `pipeline/` — the one LLM wrapper (`llm.py`), extraction/judge ports, task drivers, CI checks.
- `logic/` — the verified-judge lane (minidatalog, judge.lp, Z3 congruence, proofs, integrity).
- `bench/` — the alignment bench (AB0–AB7). `paper/` — P1 + `NUMBERS_LOCK.json` + the arXiv build.
- `docs/tables/` — per-task tables rendered from the locked registry; `results/registry.json` — the locked
  metric store; `docs/` — engine artifacts (instrument freeze, falsifiability audit, judge port, env report).

## Reproduce
Determinism rests on the `llm.py` cache (sha256 of the full request + replicate_tag), not on decoding.
The integrity gate is lint + holdout scan + read-only/quarantine/secret guards + registry validation:
```
.venv/bin/python pipeline/lint_claims.py
.venv/bin/python pipeline/holdout_check2.py
.venv/bin/python pipeline/check_readonly.py
.venv/bin/python pipeline/check_quarantine.py
.venv/bin/python pipeline/check_secrets.py
.venv/bin/python pipeline/validate_registry.py
```
(`make ci` runs the same spine.) The full `pytest` suite depends on held-out answer-key material that is not
part of this public release (see below).

## Public release scope
This public mirror excludes the held-out answer keys and any held-out key text, the obfuscation maps, and
all corpus input PDFs, so some task drivers and tests cannot be re-run here without that material. Headline
numbers inject only from the locked registry snapshot. See `docs/RELEASE.md`.

## Limitations (headline)
Small corpus (95 claims, 6 theories); single-pass extraction noise floor (stability
**0.25**); near single-class polarity (92 asserts / 3 denies);
reference labels are judge-after-audit, not ground truth; held-out keys control the prompt, not training
data (the obfuscation control is the measured response); open-weight panel leg deferred (no key). Deeper
arms (AB3/AB4/SS pilots, TD extensions, protocol game, B5) are paper v2.

## Citation
Khatri, A. (2026). *A deterministic, auditable engine for cross-theory claim comparison: cross-field
discovery with built-in verification* (paper v1). Code and locked registry:
https://github.com/Anuja-Khatri/consilience-verification · Preregistration: DOI 10.17605/OSF.IO/5N24M.
