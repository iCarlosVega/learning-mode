import json
from collections.abc import Callable
from typing import Protocol

from learning_mode.db import Database
from learning_mode.ids import new_id
from learning_mode.models import (
    AssistanceLevel,
    CandidateObservation,
    EvidenceEvent,
    EvidenceStrength,
    EvidenceType,
    KnowledgeDimension,
    from_db_timestamp,
    now_utc,
    to_db_timestamp,
)
from learning_mode.sessions import SessionService


class SessionNotActive(RuntimeError):
    pass


class InvalidObservation(ValueError):
    pass


class ConceptResolver(Protocol):
    def resolve_name(self, name: str) -> str: ...


_STRENGTH_RANK = {
    EvidenceStrength.WEAK: 0,
    EvidenceStrength.MODERATE: 1,
    EvidenceStrength.STRONG: 2,
}
_ASSISTANCE_CAP = {
    AssistanceLevel.NONE: EvidenceStrength.STRONG,
    AssistanceLevel.LIGHT_HINT: EvidenceStrength.MODERATE,
    AssistanceLevel.TARGETED_HINT: EvidenceStrength.MODERATE,
    AssistanceLevel.CONCEPTUAL_EXPLANATION: EvidenceStrength.MODERATE,
    AssistanceLevel.SCAFFOLDED: EvidenceStrength.WEAK,
    AssistanceLevel.PAIRED: EvidenceStrength.WEAK,
    AssistanceLevel.AGENT_COMPLETED: EvidenceStrength.WEAK,
}


class EvidenceService:
    def __init__(
        self,
        db: Database,
        sessions: SessionService,
        concepts: ConceptResolver,
        now: Callable = now_utc,
    ):
        self.db = db
        self.sessions = sessions
        self.concepts = concepts
        self._now = now

    def submit(self, candidate: CandidateObservation) -> EvidenceEvent:
        if not self.sessions.accepts_event_at(
            candidate.session_id, candidate.occurred_at
        ):
            raise SessionNotActive(candidate.session_id)
        self._validate_compatibility(candidate)

        concept_id = self.concepts.resolve_name(candidate.concept_name)
        event_id = candidate.event_id or new_id("evt")
        created_at = self._now()
        effective = self._discount_dimensions(
            candidate.dimensions, candidate.assistance_level
        )
        payload = {
            "concept_name": candidate.concept_name,
            "dimensions": {
                dimension.value: strength.value
                for dimension, strength in effective.items()
            },
            "claimed_dimensions": {
                dimension.value: strength.value
                for dimension, strength in candidate.dimensions.items()
            },
            "agent_confidence": candidate.agent_confidence,
            "summary": candidate.summary,
            "occurred_at": to_db_timestamp(candidate.occurred_at),
            "context_key": candidate.context_key,
        }

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO evidence_events (
                    event_id, session_id, project_id, concept_id, event_type,
                    assistance_level, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    candidate.session_id,
                    candidate.project_id,
                    concept_id,
                    candidate.evidence_type.value,
                    candidate.assistance_level.value,
                    json.dumps(payload, sort_keys=True),
                    to_db_timestamp(created_at),
                ),
            )
        return self.get(event_id)

    def get(self, event_id: str) -> EvidenceEvent:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evidence_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            raise LookupError(event_id)
        payload = json.loads(row["payload_json"])
        return EvidenceEvent(
            event_id=row["event_id"],
            session_id=row["session_id"],
            project_id=row["project_id"],
            concept_id=row["concept_id"],
            concept_name=payload["concept_name"],
            event_type=row["event_type"],
            assistance_level=row["assistance_level"],
            dimensions=payload["dimensions"],
            claimed_dimensions=payload["claimed_dimensions"],
            agent_confidence=payload["agent_confidence"],
            summary=payload["summary"],
            occurred_at=from_db_timestamp(payload["occurred_at"]),
            created_at=from_db_timestamp(row["created_at"]),
            context_key=payload.get("context_key"),
        )

    def list_for_concept(self, concept_id: str) -> list[EvidenceEvent]:
        with self.db.connect() as conn:
            event_ids = [
                row["event_id"]
                for row in conn.execute(
                    """
                    SELECT event_id FROM evidence_events
                    WHERE concept_id = ? ORDER BY created_at, event_id
                    """,
                    (concept_id,),
                )
            ]
        return [self.get(event_id) for event_id in event_ids]

    def count_for_session(self, session_id: str) -> int:
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM evidence_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]

    @staticmethod
    def _validate_compatibility(candidate: CandidateObservation) -> None:
        if (
            candidate.evidence_type
            in {EvidenceType.INDEPENDENT_APPLICATION, EvidenceType.TRANSFER}
            and candidate.assistance_level is not AssistanceLevel.NONE
        ):
            raise InvalidObservation(
                f"{candidate.evidence_type.value} requires no assistance"
            )
        if (
            candidate.evidence_type in {EvidenceType.EXPLANATION, EvidenceType.ASSESSMENT}
            and candidate.assistance_level is AssistanceLevel.AGENT_COMPLETED
        ):
            raise InvalidObservation(
                f"{candidate.evidence_type.value} cannot be agent-completed"
            )

    @staticmethod
    def _discount_dimensions(
        dimensions: dict[KnowledgeDimension, EvidenceStrength],
        assistance: AssistanceLevel,
    ) -> dict[KnowledgeDimension, EvidenceStrength]:
        cap = _ASSISTANCE_CAP[assistance]
        return {
            dimension: (
                strength
                if _STRENGTH_RANK[strength] <= _STRENGTH_RANK[cap]
                else cap
            )
            for dimension, strength in dimensions.items()
        }
