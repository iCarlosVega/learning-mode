from pathlib import Path

from learning_mode.ids import is_valid_id, new_id
from learning_mode.paths import LearningPaths, resolve_project_root


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
