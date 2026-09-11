from __future__ import annotations

from learning_mode.db import Database
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.models import (
    ConceptKnowledgeState,
    LearningDepth,
    QualitativeLevel,
    UnderstandingDebtItem,
    from_db_timestamp,
    now_utc,
    to_db_timestamp,
)


_LEVEL_ORDER = {
    QualitativeLevel.UNSEEN: 0,
    QualitativeLevel.INSUFFICIENT_EVIDENCE: 0,
    QualitativeLevel.INTRODUCED: 1,
    QualitativeLevel.PRACTICED: 2,
    QualitativeLevel.DEMONSTRATED: 3,
    QualitativeLevel.DURABLE: 4,
}


class DebtService:
    def __init__(self, db: Database, projector: KnowledgeProjector):
        self.db = db
        self.projector = projector

    def rebuild(self, project_id: str) -> list[UnderstandingDebtItem]:
        with self.db.connect() as conn:
            obligations = conn.execute(
                """
                SELECT concept_id, learning_depth, rationale
                FROM puc_entries
                WHERE project_id = ? AND active = 1
                  AND learning_depth != 'incidental'
                ORDER BY concept_id
                """,
                (project_id,),
            ).fetchall()

        updated_at = now_utc()
        items = []
        for obligation in obligations:
            state = self.projector.rebuild(obligation["concept_id"])
            depth = LearningDepth(obligation["learning_depth"])
            missing = self._missing_requirements(state, depth)
            status = "open" if missing else "resolved"
            rationale = (
                f"Missing required understanding: {', '.join(missing)}"
                if missing
                else "Current derived state satisfies the project obligation."
            )
            items.append(
                UnderstandingDebtItem(
                    project_id=project_id,
                    concept_id=obligation["concept_id"],
                    status=status,
                    rationale=rationale,
                    updated_at=updated_at,
                )
            )

        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM understanding_debt WHERE project_id = ?", (project_id,)
            )
            for item in items:
                conn.execute(
                    """
                    INSERT INTO understanding_debt (
                        project_id, concept_id, status, rationale, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        item.project_id,
                        item.concept_id,
                        item.status,
                        item.rationale,
                        to_db_timestamp(item.updated_at),
                    ),
                )
        return items

    def list(self, project_id: str) -> list[UnderstandingDebtItem]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM understanding_debt
                WHERE project_id = ? ORDER BY concept_id
                """,
                (project_id,),
            ).fetchall()
        return [
            UnderstandingDebtItem(
                project_id=row["project_id"],
                concept_id=row["concept_id"],
                status=row["status"],
                rationale=row["rationale"],
                updated_at=from_db_timestamp(row["updated_at"]),
            )
            for row in rows
        ]

    @classmethod
    def _missing_requirements(
        cls, state: ConceptKnowledgeState, depth: LearningDepth
    ) -> list[str]:
        if depth is LearningDepth.INCIDENTAL:
            return []
        missing = []
        conceptual = state.dimensions["conceptual"].level
        application = state.dimensions["application"].level
        implementation = state.dimensions["implementation"].level
        debugging = state.dimensions["debugging"].level

        conceptual_target = QualitativeLevel.DEMONSTRATED
        application_target = (
            QualitativeLevel.DEMONSTRATED
            if depth is LearningDepth.PRIMARY
            else QualitativeLevel.PRACTICED
        )
        if _LEVEL_ORDER[conceptual] < _LEVEL_ORDER[conceptual_target]:
            missing.append("conceptual")
        if depth is LearningDepth.PRIMARY and _LEVEL_ORDER[application] < _LEVEL_ORDER[
            application_target
        ]:
            missing.append("application")

        technical_levels = [implementation, debugging]
        technical_is_relevant = any(
            level not in {QualitativeLevel.UNSEEN, QualitativeLevel.INSUFFICIENT_EVIDENCE}
            for level in technical_levels
        )
        if depth is LearningDepth.PROJECT_REQUIREMENT:
            applied_levels = [application, debugging]
            applied_is_relevant = any(
                level
                not in {QualitativeLevel.UNSEEN, QualitativeLevel.INSUFFICIENT_EVIDENCE}
                for level in applied_levels
            )
            if applied_is_relevant and not any(
                _LEVEL_ORDER[level] >= _LEVEL_ORDER[QualitativeLevel.PRACTICED]
                for level in applied_levels
            ):
                missing.append("application_or_debugging")
        elif technical_is_relevant and not any(
            _LEVEL_ORDER[level] >= _LEVEL_ORDER[QualitativeLevel.DEMONSTRATED]
            for level in technical_levels
        ):
            missing.append("implementation_or_debugging")
        return missing
