import pytest
from datetime import UTC, datetime, timedelta

from learning_mode.db import Database
from learning_mode.migrations import LATEST_SCHEMA_VERSION, migrate
from learning_mode.sessions import SessionService


@pytest.fixture
def session_service(tmp_path):
    db = Database(tmp_path / "learning.db")
    migrate(db)
    return SessionService(db)


def test_migrate_creates_latest_schema(tmp_path):
    db = Database(tmp_path / "learning.db")
    migrate(db)

    with db.connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert version == LATEST_SCHEMA_VERSION
    assert {
        "projects",
        "sessions",
        "concepts",
        "concept_edges",
        "evidence_events",
        "knowledge_state",
        "puc_entries",
        "understanding_debt",
    } <= tables


def test_transaction_rolls_back_on_failure(tmp_path):
    db = Database(tmp_path / "learning.db")
    migrate(db)

    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO concepts VALUES (?, ?, ?, ?)",
                ("concept_a", "A", "a", "2026-09-11T00:00:00Z"),
            )
            raise RuntimeError("boom")

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 0


def test_new_session_starts_off(session_service):
    session = session_service.start(host="codex", project_id=None)
    assert session.status == "off"


def test_activate_then_deactivate_sets_hard_cutoff(session_service):
    session = session_service.start(host="claude", project_id=None)
    active = session_service.activate(session.session_id)
    stopped = session_service.deactivate(active.session_id, finalize=lambda: None)
    assert stopped.status == "off"
    assert stopped.cutoff_at is not None


def test_deactivate_finalizes_before_cutoff(session_service):
    order = []
    session = session_service.start(host="claude", project_id=None)
    session_service.activate(session.session_id)
    session_service.deactivate(
        session.session_id,
        finalize=lambda: order.append("finalize"),
        after_cutoff=lambda: order.append("cutoff"),
    )
    assert order == ["finalize", "cutoff"]


def test_suspend_disables_observation_without_blocking_host(session_service):
    session = session_service.start(host="codex", project_id=None)
    session_service.activate(session.session_id)
    suspended = session_service.suspend(session.session_id, "database unavailable")
    assert suspended.status == "suspended"
    assert not session_service.is_active(session.session_id)


def test_event_time_must_be_inside_current_active_interval(tmp_path):
    db = Database(tmp_path / "learning.db")
    migrate(db)
    instant = datetime(2026, 9, 11, tzinfo=UTC)
    current = instant
    service = SessionService(db, now=lambda: current)
    session = service.start(host="codex", project_id=None)

    current += timedelta(seconds=1)
    service.activate(session.session_id)
    assert service.accepts_event_at(session.session_id, current)
    assert not service.accepts_event_at(session.session_id, instant)

    current += timedelta(seconds=1)
    service.deactivate(session.session_id, finalize=lambda: None)
    assert not service.accepts_event_at(session.session_id, current)
