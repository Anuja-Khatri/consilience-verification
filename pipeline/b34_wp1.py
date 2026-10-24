#!/usr/bin/env python3
"""pipeline/b34_wp1.py — B3.4 WP1 annotation pack (SPEC §4 B3.4). Repackage the EXISTING
Task-4 materials (codebook defs + sheets) into docs/wp1/: annotation_guide.md, form_spec.html
(static, keyboard-first, JSONL download), power_analysis.md (kappa CI halfwidth vs n), and
ethics_note.md. Designed-and-unrun (linter-enforced). $0, no API."""
import json, os, sys
from pathlib import Path
import yaml
SPRINT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((SPRINT/"pipeline"/"config.yaml").read_text())
ENGINE = Path(os.path.expanduser(CFG["paths"]["engine"]))
sys.path.insert(0, str(ENGINE/"eval")); sys.path.insert(0, str(ENGINE/"pipeline"))
import t4_annotation as t4
WP1 = SPRINT/"docs"/"wp1"; WP1.mkdir(parents=True, exist_ok=True)
ed, ad = t4.entity_defs(), t4.axis_defs()

guide = ["# WP1 annotation guide (codebook v2) — designed-and-unrun", "",
         "Repackaged from the prior Task-4 materials. A trained annotator applying the published",
         "codebook (never a domain expert). Label each claim's (entity_type, axis, polarity) from",
         "the quoted passage alone.", "", "## entity_type"]
guide += [f"- **{k}**: {v}" for k, v in sorted(ed.items())]
guide += ["", "## axis"] + [f"- **{k}**: {v}" for k, v in sorted(ad.items())]
guide += ["- **none**: the claim commits to no axis in the controlled list.", "",
          "## polarity", "- **asserts** / **denies** (hedged assertions have NO polarity value —",
          "  log as a vocabulary limitation, not a label; this is the B2 hedging edge rule).", "",
          "## worked examples", "- 'Consciousness IS the posterior hot zone' → entity=locus-claim, axis=locus,",
          "  value=posterior_hot_zone, polarity=asserts.", "- 'X does NOT require a global workspace' →",
          "  polarity=denies on the connectivity axis (negation flips polarity).", ""]
(WP1/"annotation_guide.md").write_text("\n".join(guide)+"\n")

(WP1/"form_spec.html").write_text("""<h1>WP1 annotation form (static, keyboard-first)</h1>
<p>One claim per card; keys 1-9 pick entity_type, a-l pick axis, +/- pick polarity; Enter = next.
Download results as JSONL (client-side; no server). Blinding: only the claim statement + cited
passages are shown — never the theory name or the approved label.</p>
<form id="f"><textarea id="claim" rows="3" cols="80" readonly></textarea><br>
<input id="out" type="button" value="Download JSONL"></form>
<script>/* static keyboard-first stub; real items injected at deploy; JSONL via Blob download */</script>
""")

# power analysis: Cohen's kappa asymptotic SE halfwidth vs n, for kappa in {0.4,0.5,0.6}, pe~0.5
import math
def halfwidth(kappa, n, pe=0.5, z=1.96):
    po = kappa*(1-pe)+pe
    se = math.sqrt(max(po*(1-po),1e-9)/(n*(1-pe)**2))
    return z*se
rows = ["# WP1 power analysis — Cohen's kappa CI halfwidth vs n (2-3 raters)", "",
        "Asymptotic SE (pe≈0.5 binary field). Recommend n for 95% CI halfwidth ≤ 0.10.", "",
        "| n | κ=0.4 | κ=0.5 | κ=0.6 |", "|---|---|---|---|"]
rec = {}
for n in (30, 50, 80, 120, 160, 200, 300):
    rows.append(f"| {n} | {halfwidth(0.4,n):.3f} | {halfwidth(0.5,n):.3f} | {halfwidth(0.6,n):.3f} |")
for k in (0.4,0.5,0.6):
    n=30
    while halfwidth(k,n)>0.10 and n<2000: n+=5
    rec[k]=n
rows += ["", f"**Recommended n (halfwidth ≤0.10): κ=0.4→{rec[0.4]}, κ=0.5→{rec[0.5]}, κ=0.6→{rec[0.6]}.**",
         "2-3 raters; blind sheets; human-human κ + each human vs judge-after-audit reference.", ""]
(WP1/"power_analysis.md").write_text("\n".join(rows)+"\n")

(WP1/"ethics_note.md").write_text("""# WP1 ethics note
Annotators are trained raters applying the published codebook, compensated, and consent to
their (anonymised) labels being released as CC-BY-4.0 annotations. No personal data; claims are
drawn from published scientific texts (quotes ≤25 words, cited). Annotators may withdraw. The
reference is judge-after-audit, not an authority claim about which theory is correct.
""")
print(f"B3.4 WP1 pack -> docs/wp1/ (guide {len(ed)} entity + {len(ad)} axis defs; "
      f"power rec n: {rec}); designed-and-unrun")
