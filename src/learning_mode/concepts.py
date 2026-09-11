import sqlite3
import unicodedata

from learning_mode.db import Database
from learning_mode.ids import new_id
from learning_mode.models import (
    ConceptProposal,
    ConceptResolution,
    now_utc,
    to_db_timestamp,
)


class ConceptCycleError(ValueError):
    pass


class ConceptService:
    def __init__(self, db: Database):
        self.db = db

    def resolve(self, proposal: ConceptProposal) -> ConceptResolution:
        normalized = self.normalize(proposal.name)
        if not normalized:
            raise ValueError("concept name must contain non-punctuation characters")

        existing = self._find_by_normalized_name(normalized)
        created = existing is None
        if existing is None:
            concept_id = new_id("concept")
            try:
                with self.db.transaction() as conn:
                    conn.execute(
                        """
                        INSERT INTO concepts (
                            concept_id, canonical_name, normalized_name, created_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            concept_id,
                            proposal.name.strip(),
                            normalized,
                            to_db_timestamp(now_utc()),
                        ),
                    )
            except sqlite3.IntegrityError:
                existing = self._find_by_normalized_name(normalized)
                if existing is None:
                    raise
                concept_id = existing["concept_id"]
                created = False
        else:
            concept_id = existing["concept_id"]

        for candidate in proposal.relation_candidates:
            if candidate.confidence != "high" or candidate.relation == "equivalent":
                continue
            if candidate.relation == "related":
                self.add_edge(
                    candidate.target_id, concept_id, "related", candidate.confidence
                )
            elif candidate.direction == "target_parent":
                self.add_edge(
                    candidate.target_id,
                    concept_id,
                    "parent_child",
                    candidate.confidence,
                )
            else:
                self.add_edge(
                    concept_id,
                    candidate.target_id,
                    "parent_child",
                    candidate.confidence,
                )

        row = self._find_by_normalized_name(normalized)
        return ConceptResolution(
            concept_id=row["concept_id"],
            canonical_name=row["canonical_name"],
            normalized_name=row["normalized_name"],
            created=created,
        )

    def resolve_name(self, name: str) -> str:
        return self.resolve(ConceptProposal(name=name)).concept_id

    def add_edge(
        self,
        parent_id: str,
        child_id: str,
        relation: str,
        confidence: str,
    ) -> bool:
        if confidence != "high" or relation not in {"parent_child", "related"}:
            return False
        if relation == "related" and child_id < parent_id:
            parent_id, child_id = child_id, parent_id
        with self.db.transaction() as conn:
            if relation == "parent_child" and self._would_create_cycle(
                conn, parent_id, child_id
            ):
                raise ConceptCycleError(f"{parent_id} -> {child_id}")
            conn.execute(
                """
                INSERT OR IGNORE INTO concept_edges (parent_id, child_id, relation)
                VALUES (?, ?, ?)
                """,
                (parent_id, child_id, relation),
            )
        return True

    def would_create_cycle(self, parent_id: str, child_id: str) -> bool:
        with self.db.connect() as conn:
            return self._would_create_cycle(conn, parent_id, child_id)

    def list_edges(self) -> list[tuple[str, str, str]]:
        with self.db.connect() as conn:
            return [
                (row["parent_id"], row["child_id"], row["relation"])
                for row in conn.execute(
                    """
                    SELECT parent_id, child_id, relation FROM concept_edges
                    ORDER BY parent_id, child_id, relation
                    """
                )
            ]

    def get(self, concept_id: str) -> ConceptResolution:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM concepts WHERE concept_id = ?", (concept_id,)
            ).fetchone()
        if row is None:
            raise LookupError(concept_id)
        return ConceptResolution(
            concept_id=row["concept_id"],
            canonical_name=row["canonical_name"],
            normalized_name=row["normalized_name"],
            created=False,
        )

    def _find_by_normalized_name(self, normalized_name: str):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT * FROM concepts WHERE normalized_name = ?",
                (normalized_name,),
            ).fetchone()

    @staticmethod
    def normalize(name: str) -> str:
        value = name.strip()
        while value and unicodedata.category(value[0]).startswith("P"):
            value = value[1:].lstrip()
        while value and unicodedata.category(value[-1]).startswith("P"):
            value = value[:-1].rstrip()
        return " ".join(value.casefold().split())

    @staticmethod
    def _would_create_cycle(conn, parent_id: str, child_id: str) -> bool:
        if parent_id == child_id:
            return True
        return (
            conn.execute(
                """
                WITH RECURSIVE descendants(concept_id) AS (
                    SELECT child_id FROM concept_edges
                    WHERE parent_id = ? AND relation = 'parent_child'
                    UNION
                    SELECT edge.child_id
                    FROM concept_edges AS edge
                    JOIN descendants ON edge.parent_id = descendants.concept_id
                    WHERE edge.relation = 'parent_child'
                )
                SELECT 1 FROM descendants WHERE concept_id = ? LIMIT 1
                """,
                (child_id, parent_id),
            ).fetchone()
            is not None
        )
