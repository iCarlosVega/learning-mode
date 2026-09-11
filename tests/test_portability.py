import json
import zipfile

import pytest

from learning_mode.db import Database
from learning_mode.models import CandidateObservation
from learning_mode.paths import LearningPaths
from learning_mode.portability import PortabilityService
from learning_mode.service import LearningService


@pytest.fixture
def portable_state(tmp_path):
    service = LearningService(tmp_path / "source-home")
    root = tmp_path / "project"
    root.mkdir()
    project = service.projects.register(root)
    service.projects.set_intent(
        project.project_id, ["Learn transactions"], ["Python"], []
    )
    session = service.sessions.start("codex", project.project_id)
    service.sessions.activate(session.session_id)
    service.evidence.submit(
        CandidateObservation(
            session_id=session.session_id,
            project_id=project.project_id,
            concept_name="Transactions",
            evidence_type="independent_application",
            assistance_level="none",
            dimensions={"application": "strong"},
            agent_confidence="high",
            summary="Developer applied a transaction independently.",
        )
    )
    service.knowledge.rebuild_all()
    portability = PortabilityService(service.paths, service.db)
    return service, portability, project


def test_export_is_open_and_contains_registered_project_state(
    portable_state, tmp_path
):
    _, portability, project = portable_state
    target = tmp_path / "learning-export.zip"

    portability.export_bundle(target)

    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "global/evidence.jsonl" in names
        assert "global/concepts.json" in names
        assert f"projects/{project.project_id}/.learning/project.json" in names
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["format"] == "learning-mode-export"
    assert manifest["format_version"] == 1
    assert all("sha256" in item for item in manifest["files"])


def test_import_is_idempotent_by_stable_ids(portable_state, tmp_path):
    _, portability, _ = portable_state
    bundle = tmp_path / "learning-export.zip"
    portability.export_bundle(bundle)
    target = LearningService(tmp_path / "target-home")

    target.portability.import_bundle(bundle)
    with target.db.connect() as conn:
        first = tuple(
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("projects", "concepts", "evidence_events")
        )
    target.portability.import_bundle(bundle)
    with target.db.connect() as conn:
        second = tuple(
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("projects", "concepts", "evidence_events")
        )

    assert first == (1, 1, 1)
    assert second == first


def test_backup_restores_exact_database_into_empty_home(portable_state, tmp_path):
    _, portability, _ = portable_state
    backup = tmp_path / "learning-backup.zip"
    portability.backup(backup)
    restored_paths = LearningPaths(tmp_path / "restored-home")
    restored = PortabilityService(restored_paths, Database(restored_paths.database))

    restored.restore(backup)

    assert restored_paths.database.exists()
    with Database(restored_paths.database).connect() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM evidence_events").fetchone()[0] == 1


def test_restore_refuses_existing_database_without_force(portable_state, tmp_path):
    _, portability, _ = portable_state
    backup = tmp_path / "learning-backup.zip"
    portability.backup(backup)
    existing = LearningService(tmp_path / "existing-home")

    with pytest.raises(FileExistsError):
        existing.portability.restore(backup)
