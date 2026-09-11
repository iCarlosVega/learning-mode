"""Validated public models shared by Core services and host adapters."""

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_db_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def from_db_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SessionRecord(BaseModel):
    session_id: str
    host: Literal["codex", "claude"]
    project_id: str | None
    status: Literal["on", "off", "suspended"]
    activated_at: datetime | None
    cutoff_at: datetime | None
    created_at: datetime
    suspension_reason: str | None = None


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    current_path: str
    first_seen_at: datetime
    last_seen_at: datetime


class ProjectIntent(BaseModel):
    schema_version: int = 1
    goals: list[str]
    comfortable: list[str]
    deprioritized: list[str]


class EvidenceType(str, Enum):
    EXPOSURE = "exposure"
    EXPLANATION = "explanation"
    GUIDED_APPLICATION = "guided_application"
    INDEPENDENT_APPLICATION = "independent_application"
    TRANSFER = "transfer"
    MISCONCEPTION = "misconception"
    DEPENDENCE = "dependence"
    FRAGILITY = "fragility"
    CORRECTION = "correction"
    ASSESSMENT = "assessment"


class AssistanceLevel(str, Enum):
    NONE = "none"
    LIGHT_HINT = "light_hint"
    TARGETED_HINT = "targeted_hint"
    CONCEPTUAL_EXPLANATION = "conceptual_explanation"
    SCAFFOLDED = "scaffolded"
    PAIRED = "paired"
    AGENT_COMPLETED = "agent_completed"


class KnowledgeDimension(str, Enum):
    CONCEPTUAL = "conceptual"
    APPLICATION = "application"
    IMPLEMENTATION = "implementation"
    DEBUGGING = "debugging"
    TRADEOFFS = "tradeoffs"
    TRANSFER = "transfer"


class EvidenceStrength(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class CandidateObservation(BaseModel):
    session_id: str
    project_id: str | None = None
    concept_name: str = Field(min_length=1)
    evidence_type: EvidenceType
    assistance_level: AssistanceLevel
    dimensions: dict[KnowledgeDimension, EvidenceStrength] = Field(min_length=1)
    agent_confidence: Literal["low", "medium", "high", "ambiguous"]
    summary: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=now_utc)
    context_key: str | None = None
    event_id: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


class EvidenceEvent(BaseModel):
    event_id: str
    session_id: str
    project_id: str | None
    concept_id: str
    concept_name: str
    event_type: EvidenceType
    assistance_level: AssistanceLevel
    dimensions: dict[KnowledgeDimension, EvidenceStrength]
    claimed_dimensions: dict[KnowledgeDimension, EvidenceStrength]
    agent_confidence: Literal["low", "medium", "high", "ambiguous"]
    summary: str
    occurred_at: datetime
    created_at: datetime
    context_key: str | None = None


class RelationCandidate(BaseModel):
    target_id: str
    relation: Literal["equivalent", "parent_child", "related"]
    confidence: Literal["low", "high", "ambiguous"]
    direction: Literal["target_parent", "target_child"] = "target_parent"


class ConceptProposal(BaseModel):
    name: str = Field(min_length=1)
    relation_candidates: list[RelationCandidate] = Field(default_factory=list)


class ConceptResolution(BaseModel):
    concept_id: str
    canonical_name: str
    normalized_name: str
    created: bool
