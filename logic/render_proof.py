#!/usr/bin/env python3
"""
logic/render_proof.py — VJ3 proof-tree renderer (SPEC §VJ3).

Reads logic/proofs/provenance.jsonl → per-pair collapsible HTML proof trees
(logic/proofs/<pair>.html), linkable from the fork briefs.
"""
from __future__ import annotations

import collections
import html
import json
import sys
from pathlib import Path

SPRINT = Path(__file__).resolve().parent.parent
PROOFS = SPRINT / "logic" / "proofs"


def node_html(tree) -> str:
    pred, args = tree["conclusion"]
    label = f'{pred}({", ".join(map(str, args))})'
    rid = tree.get("rule_id")
    if not tree.get("premises"):
        tag = " <em>[fact]</em>" if not rid else f" <em>[{html.escape(rid)}]</em>"
        return f"<li><code>{html.escape(label)}</code>{tag}</li>"
    kids = "".join(node_html(p) for p in tree["premises"])
    return (f"<li><details open><summary><code>{html.escape(label)}</code> "
            f"<em>[{html.escape(rid)}]</em></summary><ul>{kids}</ul></details></li>")


def main() -> int:
    jl = PROOFS / "provenance.jsonl"
    bypair = collections.defaultdict(list)
    for line in jl.read_text().splitlines():
        d = json.loads(line)
        bypair[d["pair"]].append(d)
    for pair, verdicts in bypair.items():
        body = [f"<h1>Proof objects — {html.escape(pair)}</h1>",
                "<style>ul{list-style:none} code{background:#f4f4f4;padding:1px 3px} "
                "em{color:#888;font-size:.85em}</style>",
                f"<p>{len(verdicts)} verdicts. Each tree is the minidatalog rule derivation "
                "(VJ1 logic program ≡ Python judge, equivalence 1.0).</p>"]
        for v in verdicts:
            if v["verdict"] == "smc":
                body.append(f"<p><code>smc({', '.join(v['left'])} ↔ {', '.join(v['right'])})</code> "
                            "<em>[materialised measurement-space fact]</em></p>")
            else:
                body.append(f"<ul>{node_html(v['tree'])}</ul>")
        (PROOFS / f"{pair}.html").write_text("\n".join(body) + "\n")
    print(f"VJ3 render: {len(bypair)} per-pair proof HTML files → logic/proofs/*.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
