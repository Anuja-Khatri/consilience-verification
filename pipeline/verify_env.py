#!/usr/bin/env python3
"""
W0.1 — Day-0 environment verification (SPEC v2.0 §0.2).

Writes PASS/FAIL table to stdout, results/env_report.json, docs/ENV.md, and
results/engine_fingerprint.json. Any FATAL failure or count-assert mismatch is a
HALT-ASK trigger (§0.10): this script exits non-zero and prints the discrepancy
with both the spec's expectation and the observed reality.

READ-ONLY DISCIPLINE: this script never opens anything outside ~/consilience-verification in
write mode. The engine, MIU, and prior-eval trees are read with open(path) only.
"""
import os
import sys
import json
import glob
import hashlib
import importlib.util
from pathlib import Path

HOME = Path.home()
SPRINT = HOME / "consilience-verification"
ENGINE = HOME / "consilience-demo" / "demo"
MIU = HOME / "miu-demo"
EVAL_PRIOR = ENGINE  # prior eval workspace located here (eval/, eval_out/, EVAL_LOG.md)

RESULTS = SPRINT / "results"
DOCS = SPRINT / "docs"
VENV_PY = SPRINT / ".venv" / "bin" / "python"
REQ_LOCK = SPRINT / "requirements.lock"
ENV_FILE = SPRINT / ".env"


def _bootstrap():
    """Re-point at the venv interpreter (SPEC v2.0.1 B.4) and load keys from
    ~/consilience-verification/.env (B.5) before any check runs. Never echoes key values."""
    # Re-exec under the venv python if present and not already active.
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        if os.environ.get("VERIFY_ENV_REEXEC") != "1":
            os.environ["VERIFY_ENV_REEXEC"] = "1"
            os.execv(str(VENV_PY), [str(VENV_PY), os.path.abspath(__file__)] + sys.argv[1:])
    # Load .env (keys live here; llm.py loads the same file). Non-fatal if dotenv
    # or the file is absent — the API-key check reports the actual result.
    if ENV_FILE.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_FILE)
        except Exception:
            pass


_bootstrap()

# ---- result accumulator -----------------------------------------------------
rows = []            # (group, check, status, detail)   status in PASS/FAIL/WARN/INFO
fatal = []           # list of HALT-ASK strings


def record(group, check, status, detail=""):
    rows.append({"group": group, "check": check, "status": status, "detail": str(detail)})


def exists_check(group, label, path, kind="file", fatal_if_missing=True):
    p = Path(path)
    ok = p.is_dir() if kind == "dir" else p.exists()
    status = "PASS" if ok else "FAIL"
    detail = str(p) + ("" if ok else "  <-- MISSING")
    record(group, label, status, detail)
    if not ok and fatal_if_missing:
        fatal.append(f"[{group}] missing {kind}: {p}")
    return ok


# ---- 1. Engine paths --------------------------------------------------------
def check_engine_paths():
    g = "1. Engine paths"
    pipe = ENGINE / "pipeline"
    for f in ["p1_ingest.py", "p2_extract.py", "p5_judge.py", "p6_decidability.py",
              "p6b_evidence.py", "p7_answerkey_diff.py", "holdout_check.py"]:
        exists_check(g, f"pipeline/{f}", pipe / f)
    for f in ["axes.yaml", "entity_types.yaml"]:
        exists_check(g, f"vocab/{f}", ENGINE / "vocab" / f)
    exists_check(g, "data/manifest.json", ENGINE / "data" / "manifest.json")

    # results/ glob *.json — print the list
    res = ENGINE / "results"
    jsons = sorted(glob.glob(str(res / "*.json")))
    if jsons:
        record(g, "results/*.json", "PASS",
               f"{len(jsons)} files: " + ", ".join(Path(j).name for j in jsons))
    else:
        record(g, "results/*.json", "FAIL", f"no *.json under {res}")
        fatal.append(f"[{g}] no results/*.json under {res}")

    # per-theory graphs dir: locate by globbing for files with grounds/entails edge keys
    candidates = []
    for jf in glob.glob(str(ENGINE / "data" / "**" / "*.json"), recursive=True):
        try:
            with open(jf) as fh:
                txt = fh.read()
        except Exception:
            continue
        if '"grounds"' in txt or '"entails"' in txt:
            candidates.append(jf)
    graph_dirs = sorted({str(Path(c).parent) for c in candidates})
    if candidates:
        record(g, "per-theory graphs dir", "PASS",
               "dirs: " + "; ".join(graph_dirs) +
               f" | {len(candidates)} files w/ grounds/entails: " +
               ", ".join(Path(c).name for c in sorted(candidates)))
    else:
        record(g, "per-theory graphs dir", "FAIL",
               "no json containing grounds/entails edge keys found under data/")
        fatal.append(f"[{g}] per-theory graphs dir not located")


# ---- 2. MIU paths -----------------------------------------------------------
def check_miu_paths():
    g = "2. MIU paths"
    exists_check(g, "demo/demo_data.json", MIU / "demo" / "demo_data.json")
    exists_check(g, "extraction/", MIU / "extraction", kind="dir")
    exists_check(g, "extraction_text/", MIU / "extraction_text", kind="dir")
    exists_check(g, "correspondences/correspondences.json", MIU / "correspondences" / "correspondences.json")
    exists_check(g, "correspondences/rejections.json", MIU / "correspondences" / "rejections.json")
    exists_check(g, "correspondences/supplementary/", MIU / "correspondences" / "supplementary", kind="dir")
    exists_check(g, "correspondences/engine-discovered/", MIU / "correspondences" / "engine-discovered", kind="dir")
    exists_check(g, "correspondences/_index/all_claims.json", MIU / "correspondences" / "_index" / "all_claims.json")


# ---- 3. Prior eval ----------------------------------------------------------
def check_prior_eval():
    g = "3. Prior eval"
    # §0.2: these are expected to EXIST; absence of any -> HALT-ASK (no silent fallback)
    exists_check(g, "REPORT.md", EVAL_PRIOR / "eval_out" / "REPORT.md")
    exists_check(g, "EVAL_LOG.md", EVAL_PRIOR / "EVAL_LOG.md")
    exists_check(g, "eval/", EVAL_PRIOR / "eval", kind="dir")
    exists_check(g, "eval_out/", EVAL_PRIOR / "eval_out", kind="dir")
    exists_check(g, "eval_out/cache/", EVAL_PRIOR / "eval_out" / "cache", kind="dir")
    exists_check(g, "eval/stats.py", EVAL_PRIOR / "eval" / "stats.py")
    record(g, "eval_prior resolved at", "INFO", str(EVAL_PRIOR))


# ---- 4. Counts assert -------------------------------------------------------
THEORY_FILES = {
    "IIT": "iit_approved.jsonl",
    "GNWT": "gnwt_approved.jsonl",
    "actinf": "active-inference_approved.jsonl",
    "CEMI": "cemi_approved.jsonl",
    "orch-or": "orch-or_approved.jsonl",
    "NREP": "nrep_approved.jsonl",
}
EXPECT_CLAIMS = {"IIT": 24, "GNWT": 19, "actinf": 16, "CEMI": 15, "orch-or": 11, "NREP": 10}
EXPECT_TOTAL = 95
EXPECT_CORR = 221
EXPECT_PAIRS = 13


def check_counts():
    g = "4. Counts assert"
    observed = {}
    claims_dir = ENGINE / "data" / "claims"
    total = 0
    for th, fname in THEORY_FILES.items():
        p = claims_dir / fname
        if not p.exists():
            record(g, f"claims:{th}", "FAIL", f"missing {p}")
            fatal.append(f"[{g}] approved-claims file missing: {p}")
            observed[th] = None
            continue
        n = sum(1 for ln in open(p) if ln.strip())
        observed[th] = n
        total += n
        ok = n == EXPECT_CLAIMS[th]
        record(g, f"claims:{th}", "PASS" if ok else "FAIL",
               f"observed {n}, expected {EXPECT_CLAIMS[th]}")
        if not ok:
            fatal.append(f"[{g}] claim count {th}: observed {n} != spec {EXPECT_CLAIMS[th]}")
    ok_total = total == EXPECT_TOTAL
    record(g, "claims:total", "PASS" if ok_total else "FAIL",
           f"observed {total}, expected {EXPECT_TOTAL}")
    if not ok_total:
        fatal.append(f"[{g}] total claims: observed {total} != spec {EXPECT_TOTAL}")

    # correspondences + persisted pairs from results/*_judge.json
    judge_files = sorted(glob.glob(str(ENGINE / "results" / "*_judge.json")))
    corr_total = 0
    persisted = 0
    bykind = {}
    for jf in judge_files:
        try:
            d = json.load(open(jf))
        except Exception as e:
            record(g, "corr:" + Path(jf).name, "FAIL", f"unparseable: {e}")
            fatal.append(f"[{g}] unparseable judge file {jf}: {e}")
            continue
        corr = d.get("correspondences", [])
        corr_total += len(corr)
        if len(corr) > 0:
            persisted += 1
        for c in corr:
            key = f"{c.get('kind')}/{c.get('grade')}"
            bykind[key] = bykind.get(key, 0) + 1
    ok_corr = corr_total == EXPECT_CORR
    record(g, "correspondences:total", "PASS" if ok_corr else "FAIL",
           f"observed {corr_total}, expected {EXPECT_CORR} | breakdown {bykind}")
    if not ok_corr:
        fatal.append(f"[{g}] correspondence total: observed {corr_total} != spec {EXPECT_CORR}")
    ok_pairs = persisted == EXPECT_PAIRS
    record(g, "persisted pairs", "PASS" if ok_pairs else "FAIL",
           f"observed {persisted} (judge files w/ >=1 corr), expected {EXPECT_PAIRS}")
    if not ok_pairs:
        fatal.append(f"[{g}] persisted-pair count: observed {persisted} != spec {EXPECT_PAIRS}")

    return {"claims": observed, "claims_total": total,
            "correspondences_total": corr_total, "corr_breakdown": bykind,
            "persisted_pairs": persisted}


# ---- 5. API keys ------------------------------------------------------------
def check_api_keys():
    g = "5. API keys"
    out = {}
    # fatal keys
    for env in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        present = bool(os.environ.get(env))
        out[env] = present
        record(g, env, "PASS" if present else "FAIL",
               "present" if present else "MISSING (fatal)")
        if not present:
            fatal.append(f"[{g}] fatal API key missing: {env}")
    # non-fatal: gemini/google (either satisfies)
    gem = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    out["GEMINI_or_GOOGLE_API_KEY"] = gem
    record(g, "GEMINI_API_KEY / GOOGLE_API_KEY", "PASS" if gem else "WARN",
           "present" if gem else "absent (non-fatal; B3 fallback affected)")
    # optional hosted open-weight
    hosted = {k: bool(os.environ.get(k)) for k in ["TOGETHER_API_KEY", "FIREWORKS_API_KEY"]}
    out["hosted_open_weight"] = hosted
    any_hosted = any(hosted.values())
    record(g, "TOGETHER/FIREWORKS key", "INFO" if any_hosted else "INFO",
           f"recorded: {hosted}")
    return out


# ---- 6. Python deps ---------------------------------------------------------
# import-name map where pip name != import name
DEPS = [
    ("pymupdf", "fitz"),
    ("pdfplumber", "pdfplumber"),
    ("datasketch", "datasketch"),
    ("scikit-learn", "sklearn"),
    ("sentence-transformers", "sentence_transformers"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("pyyaml", "yaml"),
    ("jsonschema", "jsonschema"),
    ("matplotlib", "matplotlib"),
    ("networkx", "networkx"),
    ("pot", "ot"),
    ("dit", "dit"),
    ("clingo", "clingo"),
    ("z3-solver", "z3"),
]
# non-fatal optionals (spec: dit has a dit-only fallback for broja2pid; gemini non-fatal)
OPTIONAL_DEPS = {"broja2pid"}


def check_deps():
    g = "6. Python deps"
    out = {}
    for pip_name, import_name in DEPS:
        spec = importlib.util.find_spec(import_name)
        ok = spec is not None
        out[pip_name] = ok
        record(g, f"import {import_name} ({pip_name})", "PASS" if ok else "FAIL",
               "importable" if ok else "NOT importable (pip install needed)")
        if not ok:
            fatal.append(f"[{g}] dependency not importable: {pip_name} (import {import_name})")
    # optional broja2pid
    for opt in OPTIONAL_DEPS:
        ok = importlib.util.find_spec(opt) is not None
        out[opt] = ok
        record(g, f"import {opt} (optional)", "PASS" if ok else "WARN",
               "importable" if ok else "absent (non-fatal; dit fallback)")

    # GPU present?
    gpu = False
    try:
        import torch  # noqa
        gpu = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
        if not gpu and getattr(getattr(torch, "backends", None), "mps", None):
            gpu = torch.backends.mps.is_available()
    except Exception:
        gpu = False
    out["gpu"] = gpu
    record(g, "gpu", "INFO", f"gpu: {gpu}")

    # Web access?
    web = False
    try:
        import socket
        socket.setdefaulttimeout(3)
        socket.getaddrinfo("api.anthropic.com", 443)
        web = True
    except Exception:
        web = False
    out["web"] = web
    record(g, "web", "INFO", f"web: {web}")
    return out


# ---- 7. Engine fingerprint --------------------------------------------------
FINGERPRINT_FILES = {
    "p2_extract.py": ENGINE / "pipeline" / "p2_extract.py",
    "p5_judge.py": ENGINE / "pipeline" / "p5_judge.py",
    "p6_decidability.py": ENGINE / "pipeline" / "p6_decidability.py",
    "p6b_evidence.py": ENGINE / "pipeline" / "p6b_evidence.py",
    "p7_answerkey_diff.py": ENGINE / "pipeline" / "p7_answerkey_diff.py",
    "holdout_check.py": ENGINE / "pipeline" / "holdout_check.py",
    "axes.yaml": ENGINE / "vocab" / "axes.yaml",
    "entity_types.yaml": ENGINE / "vocab" / "entity_types.yaml",
    "manifest.json": ENGINE / "data" / "manifest.json",
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_fingerprint():
    g = "7. Engine fingerprint"
    fp = {}
    all_ok = True
    for label, path in FINGERPRINT_FILES.items():
        if not Path(path).exists():
            record(g, f"sha256 {label}", "FAIL", f"missing {path}")
            fatal.append(f"[{g}] cannot fingerprint missing file: {path}")
            all_ok = False
            continue
        digest = sha256_of(path)
        fp[label] = digest
        record(g, f"sha256 {label}", "PASS", digest[:16] + "…")
    # combined fingerprint over sorted (label: digest)
    combined = hashlib.sha256(
        json.dumps({k: fp[k] for k in sorted(fp)}, sort_keys=True).encode()
    ).hexdigest()
    payload = {
        "files": fp,
        "combined_sha256": combined,
        "engine_root": str(ENGINE),
        "artifact_stamp": "2026-10",  # no wall clock inside hashed artifacts (§0.3)
    }
    if all_ok:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(RESULTS / "engine_fingerprint.json", "w") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        record(g, "engine_fingerprint.json", "PASS",
               f"written; combined {combined[:16]}…")
    else:
        record(g, "engine_fingerprint.json", "FAIL",
               "not written (a fingerprint input was missing)")
    return payload


# ---- rendering --------------------------------------------------------------
def print_table():
    print("\n" + "=" * 78)
    print("W0.1 DAY-0 ENVIRONMENT VERIFICATION — PASS/FAIL TABLE (SPEC §0.2)")
    print("=" * 78)
    cur = None
    for r in rows:
        if r["group"] != cur:
            cur = r["group"]
            print(f"\n### {cur}")
        print(f"  [{r['status']:4}] {r['check']}")
        if r["detail"]:
            # wrap long details
            det = r["detail"]
            print(f"         {det}")
    print("\n" + "-" * 78)


def write_env_md(report):
    DOCS.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("# docs/ENV.md — Day-0 Environment Verification (W0.1)")
    lines.append("")
    lines.append("SPEC v2.0 §0.2. Generated by `pipeline/verify_env.py`. "
                 "Artifact stamp: 2026-10 (no wall clock inside hashed artifacts).")
    lines.append("")
    status_counts = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    overall = "PASS" if not report["fatal"] else "HALT-ASK (fatal failures present)"
    lines.append(f"**Overall: {overall}**  ")
    lines.append(f"Summary: " + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items())))
    lines.append("")
    lines.append("| Group | Check | Status | Detail |")
    lines.append("|---|---|---|---|")
    for r in rows:
        det = r["detail"].replace("|", "\\|")
        lines.append(f"| {r['group']} | {r['check']} | {r['status']} | {det} |")
    lines.append("")
    if report["fatal"]:
        lines.append("## FATAL / HALT-ASK")
        for f in report["fatal"]:
            lines.append(f"- {f}")
        lines.append("")
    lines.append("## Interpreter / lock")
    for k, v in report["venv"].items():
        lines.append(f"- `{k}` = `{v}`")
    lines.append("")
    lines.append("## Resolved paths")
    for k, v in report["paths"].items():
        lines.append(f"- `{k}` = `{v}`")
    lines.append("")
    with open(DOCS / "ENV.md", "w") as f:
        f.write("\n".join(lines))


def check_production_parity():
    """Owner add-on (W0.4/W0.2 follow-up): assert config.models.{extractor,checker}
    equal the PRODUCTION strings in p2_extract.py; record max_tokens + system-prompt
    construction provenance. Mismatch → HALT-ASK quoting both (never edit config silently)."""
    import re as _re
    import yaml as _yaml
    g = "8. Production parity"
    p2 = ENGINE / "pipeline" / "p2_extract.py"
    if not p2.exists():
        record(g, "p2_extract.py", "FAIL", f"missing {p2}")
        fatal.append(f"[{g}] p2_extract.py missing: {p2}")
        return {}
    src = p2.read_text()

    def _const(pat, cast=str):
        m = _re.search(pat, src, _re.M)
        return cast(m.group(1)) if m else None

    prod_extractor = _const(r'^SONNET\s*=\s*["\'](.+?)["\']')
    prod_checker = _const(r'^HAIKU\s*=\s*["\'](.+?)["\']')
    claims_per_window = _const(r'^CLAIMS_PER_WINDOW\s*=\s*(\d+)', int)
    m_ex = _re.search(r'model=SONNET,\s*max_tokens=(\d+)', src)
    m_hk = _re.search(r'model=HAIKU,\s*max_tokens=(\d+)', src)
    extract_max_tokens = int(m_ex.group(1)) if m_ex else None
    haiku_max_tokens = int(m_hk.group(1)) if m_hk else None
    # system-prompt construction provenance: sha of the extract_window function body
    ew = _re.search(r'def extract_window\(.*?\n(?=def )', src, _re.S)
    sysprompt_sha = hashlib.sha256(ew.group(0).encode()).hexdigest() if ew else None

    cfg = _yaml.safe_load((SPRINT / "pipeline" / "config.yaml").read_text())
    cfg_extractor = cfg["models"]["extractor"]
    cfg_checker = cfg["models"]["checker"]

    ex_match = cfg_extractor == prod_extractor
    hk_match = cfg_checker == prod_checker
    record(g, "extractor parity", "PASS" if ex_match else "FAIL",
           f"config={cfg_extractor!r} vs production SONNET={prod_extractor!r}")
    record(g, "checker parity", "PASS" if hk_match else "FAIL",
           f"config={cfg_checker!r} vs production HAIKU={prod_checker!r}")
    record(g, "max_tokens (extract/haiku)", "INFO",
           f"extract={extract_max_tokens}, haiku={haiku_max_tokens}, CLAIMS_PER_WINDOW={claims_per_window}")
    record(g, "system-prompt construction sha256", "INFO",
           (sysprompt_sha[:16] + "…") if sysprompt_sha else "NOT FOUND")
    if not ex_match:
        fatal.append(f"[{g}] extractor mismatch — config.models.extractor={cfg_extractor!r} "
                     f"!= production SONNET={prod_extractor!r} (HALT-ASK; do not edit config silently)")
    if not hk_match:
        fatal.append(f"[{g}] checker mismatch — config.models.checker={cfg_checker!r} "
                     f"!= production HAIKU={prod_checker!r} (HALT-ASK; do not edit config silently)")
    return {"extractor_config": cfg_extractor, "extractor_production": prod_extractor,
            "checker_config": cfg_checker, "checker_production": prod_checker,
            "extract_max_tokens": extract_max_tokens, "haiku_max_tokens": haiku_max_tokens,
            "claims_per_window": claims_per_window,
            "system_prompt_construction_sha256": sysprompt_sha,
            "extractor_match": ex_match, "checker_match": hk_match}


def check_venv():
    """SPEC v2.0.1 B.3–B.4: record interpreter + requirements.lock sha256."""
    g = "0. Interpreter / lock"
    pyver = sys.version.split()[0]
    on_venv = Path(sys.executable).resolve() == VENV_PY.resolve() if VENV_PY.exists() else False
    record(g, "python version", "INFO", pyver)
    record(g, "interpreter", "PASS" if on_venv else "WARN",
           sys.executable + ("" if on_venv else "  <-- not the sprint .venv"))
    if VENV_PY.exists():
        record(g, "sprint .venv", "PASS", str(VENV_PY))
    else:
        record(g, "sprint .venv", "WARN", f"absent: {VENV_PY}")
    lock_sha = None
    if REQ_LOCK.exists():
        lock_sha = sha256_of(REQ_LOCK)
        record(g, "requirements.lock", "PASS", f"{REQ_LOCK.name} sha256 {lock_sha[:16]}…")
    else:
        record(g, "requirements.lock", "WARN", f"absent: {REQ_LOCK}")
    record(g, ".env present", "PASS" if ENV_FILE.exists() else "INFO",
           "yes (loaded; values never echoed)" if ENV_FILE.exists() else "no")
    return {"python_version": pyver, "interpreter": sys.executable,
            "on_sprint_venv": on_venv, "requirements_lock_sha256": lock_sha,
            "env_file_present": ENV_FILE.exists()}


def main():
    venv = check_venv()
    check_engine_paths()
    check_miu_paths()
    check_prior_eval()
    counts = check_counts()
    keys = check_api_keys()
    deps = check_deps()
    fp = check_fingerprint()
    parity = check_production_parity()

    report = {
        "spec": "v2.0.1 §0.2 W0.1",
        "artifact_stamp": "2026-10",
        "venv": venv,
        "paths": {
            "engine": str(ENGINE),
            "miu": str(MIU),
            "eval_prior": str(EVAL_PRIOR),
            "sprint": str(SPRINT),
        },
        "rows": rows,
        "counts": counts,
        "api_keys": keys,
        "deps": deps,
        "engine_fingerprint": fp,
        "production_parity": parity,
        "fatal": fatal,
        "overall": "PASS" if not fatal else "HALT-ASK",
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / "env_report.json", "w") as f:
        json.dump(report, f, indent=2, sort_keys=False)
    write_env_md(report)

    print_table()
    print(f"\nWrote: {RESULTS / 'env_report.json'}")
    print(f"Wrote: {DOCS / 'ENV.md'}")
    print(f"Wrote: {RESULTS / 'engine_fingerprint.json'}"
          if not any(r['check'] == 'engine_fingerprint.json' and r['status'] == 'FAIL' for r in rows)
          else "engine_fingerprint.json NOT written (missing input)")

    if fatal:
        print("\n" + "!" * 78)
        print("HALT-ASK — fatal failures / count mismatches (§0.10). "
              "Do not proceed until resolved:")
        for f in fatal:
            print("  - " + f)
        print("!" * 78)
        sys.exit(1)
    else:
        print("\nAll checks PASS. No HALT-ASK triggers. Awaiting Day-0 approval.")
        sys.exit(0)


if __name__ == "__main__":
    main()
