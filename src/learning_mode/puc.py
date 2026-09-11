from collections.abc import Sequence

from learning_mode.concepts import ConceptService
from learning_mode.db import Database
from learning_mode.models import (
    ConceptProposal,
    LearningDepth,
    PUCEntry,
    PUCProposal,
)


class PUCService:
    def __init__(self, db: Database, concepts: ConceptService):
        self.db = db
        self.concepts = concepts

    def apply_proposals(
        self, project_id: str, proposals: Sequence[PUCProposal]
    ) -> list[PUCEntry]:
        resolved = [
            (self.concepts.resolve(ConceptProposal(name=proposal.concept_name)), proposal)
            for proposal in proposals
        ]
        with self.db.transaction() as conn:
            for concept, proposal in resolved:
                active = proposal.learning_depth is not LearningDepth.INCIDENTAL
                conn.execute(
                    """
                    INSERT INTO puc_entries (
                        project_id, concept_id, learning_depth, rationale, active
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, concept_id) DO UPDATE SET
                        learning_depth = excluded.learning_depth,
                        rationale = excluded.rationale,
                        active = excluded.active
                    """,
                    (
                        project_id,
                        concept.concept_id,
                        proposal.learning_depth.value,
                        proposal.rationale,
                        int(active),
                    ),
                )
        return self.list_active(project_id)

    def require(
        self,
        project_id: str,
        concept_id: str,
        learning_depth: LearningDepth | str,
        rationale: str,
    ) -> PUCEntry:
        depth = LearningDepth(learning_depth)
        active = depth is not LearningDepth.INCIDENTAL
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO puc_entries (
                    project_id, concept_id, learning_depth, rationale, active
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, concept_id) DO UPDATE SET
                    learning_depth = excluded.learning_depth,
                    rationale = excluded.rationale,
                    active = excluded.active
                """,
                (project_id, concept_id, depth.value, rationale, int(active)),
            )
        return self.get(project_id, concept_id)

    def deactivate(self, project_id: str, concept_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE puc_entries SET active = 0
                WHERE project_id = ? AND concept_id = ?
                """,
                (project_id, concept_id),
            )

    def get(self, project_id: str, concept_id: str) -> PUCEntry:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM puc_entries
                WHERE project_id = ? AND concept_id = ?
                """,
                (project_id, concept_id),
            ).fetchone()
        if row is None:
            raise LookupError((project_id, concept_id))
        return self._entry(row)

    def list_active(self, project_id: str) -> list[PUCEntry]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM puc_entries
                WHERE project_id = ? AND active = 1
                ORDER BY concept_id
                """,
                (project_id,),
            ).fetchall()
        return [self._entry(row) for row in rows]

    @staticmethod
    def _entry(row) -> PUCEntry:
        return PUCEntry(
            project_id=row["project_id"],
            concept_id=row["concept_id"],
            learning_depth=row["learning_depth"],
            rationale=row["rationale"],
            active=bool(row["active"]),
        )
