import pytest

from learning_mode.db import Database
from learning_mode.migrations import LATEST_SCHEMA_VERSION, migrate


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
