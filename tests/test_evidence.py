import json
import sqlite3

import pytest

from learning_mode.db import Database
from learning_mode.evidence import EvidenceService, InvalidObservation, SessionNotActive
from learning_mode.ids import new_id
from learning_mode.migrations import migrate
from learning_mode.models import (
    AssistanceLevel,
    CandidateObservation,
    EvidenceStrength,
    EvidenceType,
    KnowledgeDimension,
    now_utc,
    to_db_timestamp,
)
from learning_mode.sessions import SessionService


class FakeConceptResolver:
    def __init__(self, db: Database):
        self.db = db

    def resolve_name(self, name: str):
        normalized = " ".join(name.casefold().split())
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT concept_id FROM concepts WHERE normalized_name = ?",
                (normalized,),
            ).fetchone()
            if row:
                return row["concept_id"]
            concept_id = new_id("concept")
            conn.execute(
                "INSERT INTO concepts VALUES (?, ?, ?, ?)",
                (concept_id, name.strip(), normalized, to_db_timestamp(now_utc())),
            )
            return concept_id


def make_candidate(
    session_id: str,
    evidence_type: EvidenceType = EvidenceType.GUIDED_APPLICATION,
    assistance_level: AssistanceLevel = AssistanceLevel.NONE,
) -> CandidateObservation:
    return CandidateObservation(
        session_id=session_id,
        concept_name="transaction isolation",
        evidence_type=evidence_type,
        assistance_level=assistance_level,
        dimensions={KnowledgeDimension.APPLICATION: EvidenceStrength.STRONG},
        agent_confidence="high",
        summary="Developer selected isolation for an invariant.",
    )


@pytest.fixture
def evidence_core(tmp_path):
    db = Database(tmp_path / "learning.db")
    migrate(db)
    sessions = SessionService(db)
    evidence = EvidenceService(db, sessions, FakeConceptResolver(db))
    return db, sessions, evidence


def test_submit_rejects_observation_when_session_off(evidence_core):
    _, sessions, evidence = evidence_core
    session = sessions.start(host="codex", project_id=None)
    candidate = CandidateObservation(
        session_id=session.session_id,
        concept_name="transaction isolation",
        evidence_type=EvidenceType.INDEPENDENT_APPLICATION,
        assistance_level=AssistanceLevel.NONE,
        dimensions={KnowledgeDimension.APPLICATION: EvidenceStrength.STRONG},
        agent_confidence="high",
        summary="Developer independently chose serializable isolation.",
    )

    with pytest.raises(SessionNotActive):
        evidence.submit(candidate)

    assert evidence.count_for_session(session.session_id) == 0


def test_agent_completed_cannot_claim_independent_application(evidence_core):
    _, sessions, evidence = evidence_core
    session = sessions.start(host="codex", project_id=None)
    sessions.activate(session.session_id)
    candidate = make_candidate(
        session.session_id,
        evidence_type=EvidenceType.INDEPENDENT_APPLICATION,
        assistance_level=AssistanceLevel.AGENT_COMPLETED,
    )

    with pytest.raises(InvalidObservation):
        evidence.submit(candidate)


def test_submit_inserts_one_immutable_event_and_discounts_assistance(evidence_core):
    db, sessions, evidence = evidence_core
    session = sessions.start(host="claude", project_id=None)
    sessions.activate(session.session_id)
    candidate = make_candidate(
        session.session_id,
        assistance_level=AssistanceLevel.SCAFFOLDED,
    )

    event = evidence.submit(candidate)

    assert event.event_id.startswith("evt_")
    assert evidence.count_for_session(session.session_id) == 1
    with db.connect() as conn:
        payload = json.loads(
            conn.execute(
                "SELECT payload_json FROM evidence_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()[0]
        )
    assert payload["claimed_dimensions"]["application"] == "strong"
    assert payload["dimensions"]["application"] == "weak"


def test_evidence_rows_reject_update_and_delete(evidence_core):
    db, sessions, evidence = evidence_core
    session = sessions.start(host="codex", project_id=None)
    sessions.activate(session.session_id)
    event = evidence.submit(make_candidate(session.session_id))

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with db.transaction() as conn:
            conn.execute(
                "UPDATE evidence_events SET event_type = 'exposure' WHERE event_id = ?",
                (event.event_id,),
            )

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with db.transaction() as conn:
            conn.execute(
                "DELETE FROM evidence_events WHERE event_id = ?", (event.event_id,)
            )

    assert evidence.count_for_session(session.session_id) == 1
