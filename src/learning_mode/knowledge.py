from collections.abc import Callable
from datetime import datetime, timedelta

from learning_mode.db import Database
from learning_mode.evidence import EvidenceService
from learning_mode.models import (
    ConceptKnowledgeState,
    DimensionKnowledgeState,
    EvidenceEvent,
    EvidenceStrength,
    EvidenceType,
    KnowledgeDimension,
    QualitativeLevel,
    now_utc,
    to_db_timestamp,
)


_POSITIVE_TYPES = {
    EvidenceType.EXPOSURE,
    EvidenceType.EXPLANATION,
    EvidenceType.GUIDED_APPLICATION,
    EvidenceType.INDEPENDENT_APPLICATION,
    EvidenceType.TRANSFER,
    EvidenceType.ASSESSMENT,
}
_DEMONSTRATION_TYPES = {
    EvidenceType.EXPLANATION,
    EvidenceType.INDEPENDENT_APPLICATION,
    EvidenceType.TRANSFER,
    EvidenceType.ASSESSMENT,
}
_NEGATIVE_TYPES = {
    EvidenceType.MISCONCEPTION,
    EvidenceType.DEPENDENCE,
    EvidenceType.FRAGILITY,
}


class KnowledgeProjector:
    def __init__(
        self,
        db: Database,
        evidence: EvidenceService,
        now: Callable[[], datetime] = now_utc,
        stale_after: timedelta = timedelta(days=90),
    ):
        self.db = db
        self.evidence = evidence
        self._now = now
        self._stale_after = stale_after

    def rebuild(self, concept_id: str) -> ConceptKnowledgeState:
        events = self.evidence.list_for_concept(concept_id)
        derived_at = self._now()
        misconception_status = self._misconception_status(events)
        dimensions = {
            dimension: self._project_dimension(events, dimension, derived_at)
            for dimension in KnowledgeDimension
        }
        state = ConceptKnowledgeState(
            concept_id=concept_id,
            dimensions=dimensions,
            current_misconception_status=misconception_status,
            derived_at=derived_at,
        )
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_state (concept_id, state_json, derived_at)
                VALUES (?, ?, ?)
                ON CONFLICT(concept_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    derived_at = excluded.derived_at
                """,
                (
                    concept_id,
                    state.model_dump_json(),
                    to_db_timestamp(derived_at),
                ),
            )
        return state

    def rebuild_all(self) -> list[ConceptKnowledgeState]:
        with self.db.connect() as conn:
            concept_ids = [
                row["concept_id"]
                for row in conn.execute("SELECT concept_id FROM concepts")
            ]
        return [self.rebuild(concept_id) for concept_id in concept_ids]

    def get(self, concept_id: str) -> ConceptKnowledgeState:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM knowledge_state WHERE concept_id = ?",
                (concept_id,),
            ).fetchone()
        if row is None:
            return self.rebuild(concept_id)
        return ConceptKnowledgeState.model_validate_json(row["state_json"])

    def _project_dimension(
        self,
        events: list[EvidenceEvent],
        dimension: KnowledgeDimension,
        derived_at: datetime,
    ) -> DimensionKnowledgeState:
        relevant = [event for event in events if dimension in event.dimensions]
        positive = [event for event in relevant if event.event_type in _POSITIVE_TYPES]
        if not positive:
            level = (
                QualitativeLevel.INSUFFICIENT_EVIDENCE
                if any(event.event_type in _NEGATIVE_TYPES for event in relevant)
                else QualitativeLevel.UNSEEN
            )
            return DimensionKnowledgeState(level=level, retention="unknown")

        level = QualitativeLevel.INTRODUCED
        if any(
            event.event_type is EvidenceType.GUIDED_APPLICATION
            and event.dimensions[dimension]
            in {EvidenceStrength.MODERATE, EvidenceStrength.STRONG}
            for event in positive
        ):
            level = QualitativeLevel.PRACTICED

        demonstrations = [
            event
            for event in positive
            if event.event_type in _DEMONSTRATION_TYPES
            and event.dimensions[dimension] is EvidenceStrength.STRONG
        ]
        if demonstrations:
            level = QualitativeLevel.DEMONSTRATED
        if self._is_durable(demonstrations):
            level = QualitativeLevel.DURABLE

        last_correction = self._latest_time(events, {EvidenceType.CORRECTION})
        last_negative = self._latest_time(relevant, _NEGATIVE_TYPES)
        last_demonstration = max(
            (event.occurred_at for event in demonstrations), default=None
        )
        if (
            last_negative is not None
            and (last_correction is None or last_negative > last_correction)
            and (last_demonstration is None or last_negative > last_demonstration)
        ):
            level = QualitativeLevel.INSUFFICIENT_EVIDENCE

        latest_positive = max(event.occurred_at for event in positive)
        retention = (
            "stale"
            if derived_at - latest_positive > self._stale_after
            else "current"
        )
        return DimensionKnowledgeState(level=level, retention=retention)

    @staticmethod
    def _is_durable(demonstrations: list[EvidenceEvent]) -> bool:
        if len(demonstrations) < 2 or not any(
            event.event_type in {EvidenceType.TRANSFER, EvidenceType.ASSESSMENT}
            for event in demonstrations
        ):
            return False
        contexts = {event.context_key for event in demonstrations if event.context_key}
        separated_by_context = len(contexts) >= 2
        times = [event.occurred_at for event in demonstrations]
        separated_by_time = max(times) - min(times) >= timedelta(days=7)
        return separated_by_context or separated_by_time

    @classmethod
    def _misconception_status(cls, events: list[EvidenceEvent]) -> str:
        last_misconception = cls._latest_time(events, {EvidenceType.MISCONCEPTION})
        if last_misconception is None:
            return "none"
        last_correction = cls._latest_time(events, {EvidenceType.CORRECTION})
        return (
            "corrected"
            if last_correction is not None and last_correction >= last_misconception
            else "active"
        )

    @staticmethod
    def _latest_time(
        events: list[EvidenceEvent], event_types: set[EvidenceType]
    ) -> datetime | None:
        return max(
            (
                event.occurred_at
                for event in events
                if event.event_type in event_types
            ),
            default=None,
        )
