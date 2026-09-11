from pathlib import Path

import json
import pytest

from learning_mode.db import Database
from learning_mode.ids import is_valid_id, new_id
from learning_mode.migrations import migrate
from learning_mode.paths import LearningPaths, resolve_project_root
from learning_mode.projects import ProjectService


@pytest.fixture
def project_service(tmp_path):
    db = Database(tmp_path / "home" / "learning.db")
    migrate(db)
    return ProjectService(db)


def test_learning_paths_are_local_to_configured_home(tmp_path: Path):
    paths = LearningPaths(home=tmp_path / ".learning-mode")
    assert paths.database == tmp_path / ".learning-mode" / "learning.db"
    assert paths.exports == tmp_path / ".learning-mode" / "exports"


def test_new_ids_are_prefixed_and_unique():
    first = new_id("proj")
    second = new_id("proj")
    assert first != second
    assert is_valid_id(first, "proj")
    assert is_valid_id(second, "proj")


def test_project_root_prefers_git_root(tmp_path: Path):
    root = tmp_path / "repo"
    child = root / "src" / "pkg"
    (root / ".git").mkdir(parents=True)
    child.mkdir(parents=True)
    assert resolve_project_root(child) == root


def test_register_creates_stable_project_identity(project_service, tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)

    first = project_service.register(root)
    second = project_service.register(root)

    assert first.project_id == second.project_id
    metadata = json.loads((root / ".learning" / "project.json").read_text())
    assert metadata == {"project_id": first.project_id, "schema_version": 1}


def test_moved_project_reassociates_by_project_file(project_service, tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    project = project_service.register(old)
    old.rename(new)

    rediscovered = project_service.discover(new)
    assert rediscovered.project_id == project.project_id
    assert rediscovered.current_path == str(new.resolve())


def test_register_uses_git_info_exclude_not_gitignore(project_service, tmp_path):
    root = tmp_path / "repo"
    (root / ".git" / "info").mkdir(parents=True)
    (root / ".gitignore").write_text("dist/\n")

    project_service.register(root)

    assert "/.learning/" in (root / ".git" / "info" / "exclude").read_text()
    assert (root / ".gitignore").read_text() == "dist/\n"


def test_register_worktree_uses_common_git_exclude(project_service, tmp_path):
    root = tmp_path / "repo"
    gitdir = tmp_path / "git" / "worktrees" / "repo"
    common = tmp_path / "git"
    (common / "info").mkdir(parents=True)
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n")
    root.mkdir()
    (root / ".git").write_text(f"gitdir: {gitdir}\n")

    project_service.register(root)

    assert "/.learning/" in (common / "info" / "exclude").read_text()


def test_set_intent_persists_only_in_project_learning_directory(
    project_service, tmp_path
):
    root = tmp_path / "repo"
    root.mkdir()
    project = project_service.register(root)

    intent = project_service.set_intent(
        project.project_id,
        goals=["Understand transactions"],
        comfortable=["Python"],
        deprioritized=["CSS"],
    )

    persisted = json.loads((root / ".learning" / "intent.json").read_text())
    assert persisted["goals"] == ["Understand transactions"]
    assert intent.comfortable == ["Python"]
