"""research_graph.models — single canonical Pydantic schema file.

Every other module imports from here. Splits would buy nothing until the
schema exceeds ~30 types; right now (v0.1) the whole graph fits in one file.

Schemas follow the canonical glossary in ``.claude/CONTEXT.md``:
Paper, Author, Professor, Institution, ResearchGroup, Concept, Method,
Application, OpenProblem, Limitation, FutureWork, Dataset, Implementation,
Keyword, Claim, ClaimWithEvidence, ExtractionRecord, ProjectIdea,
TypedEdge, EvidenceStrength, ProviderResult.
"""

from __future__ import annotations

import enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ---------- Enums --------------------------------------------------------------

class EvidenceStrength(str, enum.Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class Origin(str, enum.Enum):
    """Source axis on every Claim / Limitation / OpenProblem."""
    DECLARED = "declared"   # text from the paper itself
    INFERRED = "inferred"   # LLM-derived


class EdgeType(str, enum.Enum):
    AUTHORED_BY = "AUTHORED_BY"
    AFFILIATED_WITH = "AFFILIATED_WITH"
    MEMBER_OF_GROUP = "MEMBER_OF_GROUP"
    CITES = "CITES"
    CITED_BY = "CITED_BY"
    SIMILAR_TO = "SIMILAR_TO"
    USES_METHOD = "USES_METHOD"
    REPLACES_METHOD = "REPLACES_METHOD"
    APPLIES_TO = "APPLIES_TO"
    ADDRESSES_PROBLEM = "ADDRESSES_PROBLEM"
    LEAVES_OPEN = "LEAVES_OPEN"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"
    BELONGS_TO_GROUP = "BELONGS_TO_GROUP"
    SHARES_CONCEPT = "SHARES_CONCEPT"
    SHARES_KEYWORD = "SHARES_KEYWORD"
    EVALUATED_ON = "EVALUATED_ON"
    PROPOSES_IDEA = "PROPOSES_IDEA"


# ---------- Base ---------------------------------------------------------------

class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# ---------- Bibliographic entities --------------------------------------------

class Paper(_Base):
    paper_id: str
    title: str
    year: int | None = None
    doi: str | None = None
    urls: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    affiliations: list[str] = Field(default_factory=list)
    abstract: str | None = None
    venue: str | None = None
    source_provenance: dict[str, list[str]] = Field(default_factory=dict)
    """field_name -> list of providers that supplied a value for it"""

    @field_validator("doi")
    @classmethod
    def _normalize_doi(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "doi.org/"):
            if v.startswith(prefix):
                v = v[len(prefix):]
        return v or None


class Author(_Base):
    author_id: str
    family: str | None = None
    given: str | None = None
    display_name: str
    orcid: str | None = None
    aliases: list[str] = Field(default_factory=list)


class Institution(_Base):
    institution_id: str
    display_name: str
    ror: str | None = None
    country: str | None = None
    homepage: str | None = None


class ResearchGroup(_Base):
    group_id: str
    name: str
    parent_institution_id: str | None = None
    homepage: str | None = None


class Concept(_Base):
    concept_id: str
    label: str
    level: int = 0  # 0..5 (OpenAlex convention)
    parent_concept_id: str | None = None


class Method(_Base):
    method_key: str  # normalized label + declaring paper_id
    label: str
    evidence_paper_ids: list[str] = Field(default_factory=list)


class Application(_Base):
    application_id: str
    label: str
    evidence_paper_ids: list[str] = Field(default_factory=list)


class Dataset(_Base):
    dataset_id: str
    label: str
    url: str | None = None
    evidence_paper_ids: list[str] = Field(default_factory=list)


class Implementation(_Base):
    implementation_id: str
    label: str
    url: str | None = None
    language: str | None = None
    method_key: str | None = None
    paper_id: str | None = None


class Keyword(_Base):
    keyword: str  # free-text; lower-trust than Concept


# ---------- Claims / limitations / future work / open problems --------------

class Claim(_Base):
    claim: str
    evidence_type: Literal["empirical", "theoretical", "cited", "inference"]
    source_location: str  # e.g. "Section 4.2" or "abstract" or "Table 3"
    confidence: float = Field(ge=0.0, le=1.0)
    origin: Origin = Origin.DECLARED


class ClaimWithEvidence(_Base):
    claim: str
    evidence_type: Literal["empirical", "theoretical", "cited", "inference"]
    source_location: str
    confidence: float = Field(ge=0.0, le=1.0)
    origin: Origin = Origin.DECLARED


class Limitation(_Base):
    text: str
    declared_by_paper_id: str
    evidence_location: str
    confidence: float = Field(ge=0.0, le=1.0)
    origin: Origin = Origin.DECLARED


class FutureWork(_Base):
    text: str
    supporting_paper_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    origin: Origin = Origin.DECLARED


class OpenProblem(_Base):
    statement: str
    problem_hash: str  # SHA-1 of NFC+lower+ws-collapsed statement
    supporting_paper_ids: list[str] = Field(default_factory=list)
    declared_by_paper_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    origin: Origin = Origin.DECLARED


# ---------- Extraction record (LLM output, validated) -------------------------

class ExtractionRecord(_Base):
    paper_id: str
    research_area: list[str] = Field(default_factory=list)
    problem: str
    research_question: str | None = None
    hypothesis: str | None = None
    main_contribution: str
    technical_components: list[str] = Field(default_factory=list)
    baseline_or_replaced_technique: list[str] = Field(default_factory=list)
    proposed_technique: list[str] = Field(default_factory=list)
    application_domain: list[str] = Field(default_factory=list)
    security_properties: list[str] = Field(default_factory=list)
    evaluation_metrics: list[str] = Field(default_factory=list)
    datasets_or_experimental_setup: list[str] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    future_work: list[FutureWork] = Field(default_factory=list)
    open_questions: list[OpenProblem] = Field(default_factory=list)
    claims_with_evidence: list[ClaimWithEvidence] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


# ---------- Project idea (LLM synthesis, validated) ---------------------------

class Difficulty(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Fit(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProjectIdea(_Base):
    project_title: str
    one_sentence_proposal: str
    research_problem: str
    baseline: str
    proposed_change: str
    property_to_prove_or_measure: str
    research_question: str
    hypotheses: list[str] = Field(default_factory=list)
    implementation_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    evaluation_metrics: list[str] = Field(default_factory=list)
    required_background: list[str] = Field(default_factory=list)
    difficulty: Difficulty = Difficulty.MEDIUM
    master_thesis_fit: Fit = Fit.MEDIUM
    novelty_risk: Fit = Fit.MEDIUM
    future_extensions: list[str] = Field(default_factory=list)
    supporting_papers: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    @field_validator("supporting_papers")
    @classmethod
    def _at_least_two_papers(cls, v: list[str]) -> list[str]:
        # soft rule: keep raw list; gating happens in synthesis.project_ideas
        # before this model is constructed.
        return v


# ---------- Typed graph edge --------------------------------------------------

class TypedEdge(_Base):
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    source: str  # provider name, "llm", "user", etc.
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_text: str | None = None
    evidence_location: str | None = None


# ---------- Provider result wrapper -------------------------------------------

class ProviderResult(_Base):
    status: Literal["ok", "partial", "failed"]
    data: Any | None = None
    error: str | None = None
    raw: dict[str, Any] | None = None
    source: str  # provider name (e.g. "openalex")
