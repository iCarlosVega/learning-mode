from datetime import datetime
from typing import Literal

from learning_mode.concepts import ConceptService
from learning_mode.debt import DebtService
from learning_mode.evidence import EvidenceService
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.models import (
    AssessmentBrief,
    AssessmentResult,
    AssessmentTarget,
    CandidateObservation,
    EvidenceEvent,
)
from learning_mode.puc import PUCService
from learning_mode.sessions import SessionService


class AssessmentService:
    def __init__(
        self,
        sessions: SessionService,
        concepts: ConceptService,
        projector: KnowledgeProjector,
        puc: PUCService,
        debt: DebtService,
        evidence: EvidenceService,
    ):
        self.sessions = sessions
        self.concepts = concepts
        self.projector = projector
        self.puc = puc
        self.debt = debt
        self.evidence = evidence

    def request(
        self,
        scope: Literal["concept", "project", "weakest", "since"],
        project_id: str | None = None,
        concept_ids: list[str] | None = None,
        since: datetime | None = None,
    ) -> AssessmentBrief:
        if scope != "concept" and project_id is None:
            raise ValueError(f"project_id is required for {scope} assessment")
        if scope == "concept" and not concept_ids:
            raise ValueError("concept assessment requires at least one concept_id")

        puc_entries = self.puc.list_active(project_id) if project_id else []
        puc_by_concept = {entry.concept_id: entry for entry in puc_entries}
        selected = list(dict.fromkeys(concept_ids or []))
        if scope in {"project", "weakest", "since"} and not selected:
            selected = [entry.concept_id for entry in puc_entries]

        debt_by_concept = {
            item.concept_id: item
            for item in (self.debt.rebuild(project_id) if project_id else [])
        }
        if scope == "weakest":
            open_debt = [
                concept_id
                for concept_id in selected
                if concept_id in debt_by_concept
                and debt_by_concept[concept_id].status == "open"
            ]
            selected = (open_debt or selected)[:1]

        targets = []
        for concept_id in selected:
            concept = self.concepts.get(concept_id)
            state = self.projector.get(concept_id)
            if scope == "since" and since is not None and state.derived_at < since:
                continue
            puc_entry = puc_by_concept.get(concept_id)
            debt_item = debt_by_concept.get(concept_id)
            targets.append(
                AssessmentTarget(
                    concept_id=concept_id,
                    name=concept.canonical_name,
                    learning_depth=(
                        puc_entry.learning_depth.value if puc_entry is not None else None
                    ),
                    dimensions={
                        dimension: dimension_state.level
                        for dimension, dimension_state in state.dimensions.items()
                    },
                    misconception_status=state.current_misconception_status,
                    understanding_debt=(
                        "open"
                        if debt_item is not None and debt_item.status == "open"
                        else "none"
                    ),
                )
            )
        return AssessmentBrief(
            scope=scope,
            project_id=project_id,
            targets=targets,
            instruction=(
                "Create fresh questions or scenarios dynamically. Do not reveal answers "
                "or infer mastery; submit only the resulting candidate evidence."
            ),
        )

    def record_result(self, result: AssessmentResult) -> list[EvidenceEvent]:
        session = self.sessions.get(result.session_id)
        concept = self.concepts.get(result.concept_id)
        event = self.evidence.submit(
            CandidateObservation(
                session_id=result.session_id,
                project_id=session.project_id,
                concept_name=concept.canonical_name,
                evidence_type="assessment",
                assistance_level=result.assistance_level,
                dimensions=result.dimensions,
                agent_confidence="high",
                summary=result.summary,
                context_key=result.context_key,
            )
        )
        return [event]
