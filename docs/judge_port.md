# docs/judge_port.md — Judge/Decidability Port (W0.4)

Port location: `pipeline/engine_copy/` (mirrors the engine `demo/` layout so the
byte-identical copies resolve `vocab/` and `data/` via `parent.parent`). **Import ONLY
from the copy**; never from `~/consilience-demo`. Byte-hash-asserted against
`results/engine_fingerprint.json` (p5_judge.py, p6_decidability.py, p6b_evidence.py,
axes.yaml, entity_types.yaml) in `tests/test_judge_port.py`.

## (a) Input graph schema the judge consumes
`judge_pair(graph_a, graph_b)` takes a dict (or pydantic `Graph.model_dump()`):
```
{ "theory": <str>,
  "nodes": [ {claim_id, theory, entity_type, axis, value, polarity, statement,
              passage_ids, status="approved", ...} ],
  "edges": [ {src_claim_id, dst_claim_id, relation, source} ] }
```
Only `claim_id, theory, entity_type, axis, value, polarity` (nodes) and
`src_claim_id, dst_claim_id, relation` (edges) are read by the judge. Schema is
authoritative in `schemas.py` (`Claim`, `Edge`, `Graph`). **Input shape was clear from
code → no HALT-ASK.**

## (b) `_GENERIC` stem list (verbatim from p5_judge.py)
```
subst corti corte cereb consc infor integ cogni proce neura brain syste struc
cause effec conne requi thres locus tempo archi mecha
```
(`compu`/`funda` are deliberately NOT excluded — there the shared token IS the
commitment.) `_STOP` = {the,and,of,a,to,for,per,some,full,not,with,by,half}.

## (c) value-family function (verbatim)
`value_family(v) = frozenset(w[:5] for w in re.findall(r"[a-zΦ0-9]+", v.lower())
if len(w) >= 4 and w not in _STOP and w[:5] not in _GENERIC)`;
`same_family(a,b)` = non-empty intersection of families, else exact-string fallback.

## (d) grade definitions (from the p5 docstring + code)
- **fork**: `axis ∈ FORK_AXES` AND (different value-family OR opposed polarity). FORK_AXES
  = locus, temporal_profile, connectivity, substrate_dependence, mechanism_scale,
  observable_commitment, computability.
- **formal**: same axis, same family, matching neighbour VALUES ≥2
  (`relation ∧ endpoint-axis ∧ endpoint value-family`). Cross-theory formal is hard-capped
  to **partial** (`capped_from: formal`).
- **partial**: same axis, same family, a shared incident relation (but <2 neighbour-value
  matches); ALSO the first-class `shared_measurement_space` correspondence (both theories'
  measurement claims commit to intersecting observable spaces at equal scale).
- **generative**: same axis, same family but no shared relation; OR same axis, different
  family on a NON-fork axis.
- axis mismatch = the ONLY hard veto; `entity_type` mismatch → `type_divergence:true`
  (signal, not a veto); opposed polarity on a non-fork axis → neither corr nor fork.
Grade definitions are present in the docstring → **no Anu packet needed.**

## Decidability (p6_decidability.py)
`decide(axis, left_theory, right_theory)` → `now` (shared observable id at equal scale),
`bridge` (authored unproven bridge in `data/answer_keys/bridges.yaml`), or `not_current`.
Uses `vocab/axes.yaml:observable_links` × `vocab/observables.yaml:scale`.

## Port validation
`port_validated: reproduced-stored-correspondences` — re-judging all 13 persisted pairs
from their stored embedded inputs reproduces **all 221 correspondences byte-identically**
(canonical-JSON equal), 0 mismatches. This is STRONGER than the spec's self-consistency
fallback (stored inputs were recoverable). Stored `forks` additionally carry a
`decidability` field injected by p6 downstream; the raw `judge_pair` forks match modulo
that enrichment (out of scope for the 221-correspondence fixture).
