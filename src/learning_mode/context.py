from learning_mode.concepts import ConceptService
from learning_mode.debt import DebtService
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.models import (
    ConceptContext,
    LearnerContext,
    LearnerContextRequest,
)
from learning_mode.projects import ProjectService
from learning_mode.puc import PUCService


class ContextService:
    def __init__(
        self,
        projects: ProjectService,
        concepts: ConceptService,
        projector: KnowledgeProjector,
        puc: PUCService,
        debt: DebtService,
    ):
        self.projects = projects
        self.concepts = concepts
        self.projector = projector
        self.puc = puc
        self.debt = debt

    def for_task(
        self,
        project_id: str,
        concept_ids: list[str],
        task_summary: str,
    ) -> LearnerContext:
        request = LearnerContextRequest(
            project_id=project_id,
            concept_ids=concept_ids,
            task_summary=task_summary,
        )
        intent = self.projects.get_intent(project_id)
        puc_by_concept = {
            entry.concept_id: entry for entry in self.puc.list_active(project_id)
        }
        debt_by_concept = {
            item.concept_id: item for item in self.debt.rebuild(project_id)
        }
        contexts = []
        seen = set()
        for concept_id in request.concept_ids:
            if concept_id in seen:
                continue
            seen.add(concept_id)
            concept = self.concepts.get(concept_id)
            state = self.projector.rebuild(concept_id)
            retention_values = {
                dimension.retention for dimension in state.dimensions.values()
            }
            if "stale" in retention_values:
                retention = "stale"
            elif "current" in retention_values:
                retention = "current"
            else:
                retention = "unknown"
            puc_entry = puc_by_concept.get(concept_id)
            debt_item = debt_by_concept.get(concept_id)
            contexts.append(
                ConceptContext(
                    concept_id=concept_id,
                    name=concept.canonical_name,
                    dimensions={
                        dimension: dimension_state.level
                        for dimension, dimension_state in state.dimensions.items()
                    },
                    retention=retention,
                    misconception_status=state.current_misconception_status,
                    understanding_debt=(
                        "open"
                        if debt_item is not None and debt_item.status == "open"
                        else "none"
                    ),
                    learning_depth=(
                        puc_entry.learning_depth.value if puc_entry is not None else None
                    ),
                )
            )
        return LearnerContext(
            project_id=project_id,
            task_summary=request.task_summary,
            goals=intent.goals,
            comfortable=intent.comfortable,
            deprioritized=intent.deprioritized,
            concepts=contexts,
        )
