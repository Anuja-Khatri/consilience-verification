"""Demo data contracts (pydantic v2). Fields are EXACTLY as specified in
demo-development-plan.md; entity_type / axis / relation are validated against the
frozen demo_v0 vocab files. DEMO-SCOPED — not ontology v1.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, field_validator, model_validator

VOCAB_DIR = Path(__file__).resolve().parent.parent / "vocab"


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((VOCAB_DIR / name).read_text(encoding="utf-8"))


ENTITY_TYPES = set(_load_yaml("entity_types.yaml")["types"].keys())
AXES = set(_load_yaml("axes.yaml")["axes"]) | {"none"}
RELATIONS = set(_load_yaml("relations.yaml")["relations"].keys())

Polarity = Literal["asserts", "denies"]
Status = Literal["draft", "approved", "rejected"]


class Passage(BaseModel):
    passage_id: str
    doc_id: str
    theory: str
    text: str
    locator: str  # page/section


class Claim(BaseModel):
    claim_id: str
    theory: str
    entity_type: str
    axis: str
    value: str
    polarity: Polarity
    statement: str
    passage_ids: List[str]
    extractor_model: str
    agreement: bool
    status: Status = "draft"

    @field_validator("entity_type")
    @classmethod
    def _entity_type_in_vocab(cls, v: str) -> str:
        if v not in ENTITY_TYPES:
            raise ValueError(f"entity_type '{v}' not in demo_v0 vocab: {sorted(ENTITY_TYPES)}")
        return v

    @field_validator("axis")
    @classmethod
    def _axis_in_vocab(cls, v: str) -> str:
        if v not in AXES:
            raise ValueError(f"axis '{v}' not in demo_v0 vocab: {sorted(AXES)}")
        return v

    @field_validator("passage_ids")
    @classmethod
    def _provenance_required(cls, v: List[str]) -> List[str]:
        # Plan rule 5: a claim without provenance is invalid and must be dropped, never kept.
        if not v:
            raise ValueError("claim has no passage_ids; provenance is required")
        return v


class Edge(BaseModel):
    src_claim_id: str
    dst_claim_id: str
    relation: str
    source: str = "rule"  # rule | llm_suggested | oracle_authored (provenance)

    @field_validator("relation")
    @classmethod
    def _relation_in_vocab(cls, v: str) -> str:
        if v not in RELATIONS:
            raise ValueError(f"relation '{v}' not in demo_v0 vocab: {sorted(RELATIONS)}")
        return v

    @field_validator("source")
    @classmethod
    def _source_known(cls, v: str) -> str:
        if v not in {"rule", "llm_suggested", "oracle_authored"}:
            raise ValueError(f"edge source '{v}' unknown (rule|llm_suggested|oracle_authored)")
        return v


class Graph(BaseModel):
    theory: str
    nodes: List[Claim]  # approved only
    edges: List[Edge]

    @model_validator(mode="after")
    def _nodes_approved_only(self) -> "Graph":
        bad = [n.claim_id for n in self.nodes if n.status != "approved"]
        if bad:
            raise ValueError(f"Graph nodes must be approved claims; not approved: {bad}")
        return self


class Correspondence(BaseModel):
    pair: str
    left_ids: List[str]
    right_ids: List[str]
    kind: Literal["node", "subtree"]
    grade: Literal["formal", "partial", "generative", "thematic"]
    rationale: str
    status: str


class Fork(BaseModel):
    pair: str
    axis: str
    left_ids: List[str]
    right_ids: List[str]
    left_value: str
    right_value: str

    @field_validator("axis")
    @classmethod
    def _axis_in_vocab(cls, v: str) -> str:
        if v not in AXES:
            raise ValueError(f"axis '{v}' not in demo_v0 vocab: {sorted(AXES)}")
        return v


class Verdict(BaseModel):
    fork_ref: str
    decidability: Literal["now", "bridge", "not_current"]
    shared_observables: List[str]
    bridge_note: Optional[str] = None
    rationale: str
