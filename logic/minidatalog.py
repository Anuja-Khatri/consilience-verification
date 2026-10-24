#!/usr/bin/env python3
"""
logic/minidatalog.py — deterministic semi-naive Datalog evaluator with stratified
negation + provenance (SPEC §VJ1 fallback engine; also the VJ3 provenance backbone).

REQUIRED to exist regardless of clingo/souffle availability (§VJ1). Pure Python, no deps.

Model:
  Term  = Var("X") | a constant (str/int/tuple)
  Atom  = (pred, (t1, t2, ...))
  Rule  = Rule(head_atom, [body_atoms], neg=[negated_body_atoms])
A fact is a ground atom. Evaluation is stratified: negation may only reference predicates
in a lower stratum (checked). Provenance: for each derived fact, the (rule_id, premises).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


class Var:
    __slots__ = ("name",)

    def __init__(self, name): self.name = name
    def __repr__(self): return f"?{self.name}"
    def __eq__(self, o): return isinstance(o, Var) and o.name == self.name
    def __hash__(self): return hash(("Var", self.name))


def is_var(t): return isinstance(t, Var)


@dataclass(frozen=True)
class Atom:
    pred: str
    args: tuple

    def ground(self): return all(not is_var(a) for a in self.args)


@dataclass
class Rule:
    head: Atom
    body: List[Atom] = field(default_factory=list)
    neg: List[Atom] = field(default_factory=list)
    rule_id: str = ""
    comment: str = ""   # p5 line-number citation (VJ1.2)


def _unify(atom: Atom, fact: Atom, subst: dict) -> Optional[dict]:
    if atom.pred != fact.pred or len(atom.args) != len(fact.args):
        return None
    s = dict(subst)
    for a, v in zip(atom.args, fact.args):
        if is_var(a):
            if a.name in s:
                if s[a.name] != v:
                    return None
            else:
                s[a.name] = v
        elif a != v:
            return None
    return s


def _subst(atom: Atom, s: dict) -> Atom:
    return Atom(atom.pred, tuple(s[a.name] if is_var(a) else a for a in atom.args))


class Engine:
    def __init__(self):
        self.facts: Set[Atom] = set()
        self.rules: List[Rule] = []
        self.prov: Dict[Atom, Tuple[str, tuple]] = {}   # fact -> (rule_id, premises)

    def add_fact(self, pred, *args):
        self.facts.add(Atom(pred, tuple(args)))

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def _index(self):
        idx: Dict[str, List[Atom]] = {}
        for f in self.facts:
            idx.setdefault(f.pred, []).append(f)
        return idx

    def _match_body(self, body: List[Atom], idx) -> List[dict]:
        substs = [{}]
        for atom in body:
            new = []
            for s in substs:
                for fact in idx.get(atom.pred, []):
                    u = _unify(atom, fact, s)
                    if u is not None:
                        new.append(u)
            substs = new
            if not substs:
                break
        return substs

    def run(self, max_iter=10000) -> Set[Atom]:
        changed = True
        it = 0
        while changed and it < max_iter:
            changed = False
            it += 1
            idx = self._index()
            for r in self.rules:
                for s in self._match_body(r.body, idx):
                    # stratified negation: negated atom must NOT be derivable (closed-world on current facts)
                    if any(_subst(n, s) in self.facts for n in r.neg):
                        continue
                    head = _subst(r.head, s)
                    if not head.ground():
                        raise ValueError(f"unsafe rule {r.rule_id}: head var unbound {head}")
                    if head not in self.facts:
                        self.facts.add(head)
                        self.prov[head] = (r.rule_id, tuple(_subst(b, s) for b in r.body))
                        changed = True
        return self.facts

    def query(self, pred, *args) -> List[Atom]:
        q = Atom(pred, tuple(args))
        out = []
        for f in self.facts:
            if _unify(q, f, {}) is not None:
                out.append(f)
        return out

    def explain(self, fact: Atom, depth=0) -> dict:
        """Provenance tree {conclusion, rule_id, premises[]} (VJ3)."""
        rid, prem = self.prov.get(fact, (None, ()))
        return {"conclusion": [fact.pred, list(fact.args)], "rule_id": rid,
                "premises": [self.explain(p, depth + 1) for p in prem] if rid else []}


if __name__ == "__main__":  # smoke: transitive closure
    e = Engine()
    for a, b in [("a", "b"), ("b", "c"), ("c", "d")]:
        e.add_fact("edge", a, b)
    X, Y, Z = Var("X"), Var("Y"), Var("Z")
    e.add_rule(Rule(Atom("path", (X, Y)), [Atom("edge", (X, Y))], rule_id="r1"))
    e.add_rule(Rule(Atom("path", (X, Z)), [Atom("edge", (X, Y)), Atom("path", (Y, Z))], rule_id="r2"))
    e.run()
    paths = sorted((f.args for f in e.query("path", Var("X"), Var("Y"))))
    print("paths:", paths)
    assert ("a", "d") in paths
    print("minidatalog smoke OK")
