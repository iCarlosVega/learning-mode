import json
from collections.abc import Sequence
from pathlib import Path

from learning_mode.db import Database
from learning_mode.ids import is_valid_id, new_id
from learning_mode.models import (
    ProjectIntent,
    ProjectRecord,
    from_db_timestamp,
    now_utc,
    to_db_timestamp,
)
from learning_mode.paths import resolve_project_root


class ProjectNotFound(LookupError):
    pass


class InvalidProjectMetadata(ValueError):
    pass


class ProjectService:
    def __init__(self, db: Database):
        self.db = db

    def discover(self, path: Path) -> ProjectRecord:
        return self.register(path)

    def register(self, path: Path) -> ProjectRecord:
        root = resolve_project_root(path)
        learning_dir = root / ".learning"
        learning_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_private_by_default(root)

        metadata_path = learning_dir / "project.json"
        project_id = self._metadata_project_id(metadata_path)
        instant = to_db_timestamp(now_utc())
        resolved_path = str(root)

        with self.db.transaction() as conn:
            if project_id is None:
                existing = conn.execute(
                    "SELECT project_id FROM projects WHERE current_path = ?",
                    (resolved_path,),
                ).fetchone()
                project_id = existing["project_id"] if existing else new_id("proj")

            row = conn.execute(
                "SELECT project_id FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO projects (
                        project_id, name, current_path, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (project_id, root.name, resolved_path, instant, instant),
                )
            else:
                conn.execute(
                    """
                    UPDATE projects
                    SET name = ?, current_path = ?, last_seen_at = ?
                    WHERE project_id = ?
                    """,
                    (root.name, resolved_path, instant, project_id),
                )

        self._write_json(
            metadata_path, {"project_id": project_id, "schema_version": 1}
        )
        return self.get(project_id)

    def get(self, project_id: str) -> ProjectRecord:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise ProjectNotFound(project_id)
        return ProjectRecord(
            project_id=row["project_id"],
            name=row["name"],
            current_path=row["current_path"],
            first_seen_at=from_db_timestamp(row["first_seen_at"]),
            last_seen_at=from_db_timestamp(row["last_seen_at"]),
        )

    def set_intent(
        self,
        project_id: str,
        goals: Sequence[str],
        comfortable: Sequence[str],
        deprioritized: Sequence[str],
    ) -> ProjectIntent:
        project = self.get(project_id)
        intent = ProjectIntent(
            goals=list(goals),
            comfortable=list(comfortable),
            deprioritized=list(deprioritized),
        )
        target = Path(project.current_path) / ".learning" / "intent.json"
        self._write_json(target, intent.model_dump())
        return intent

    def get_intent(self, project_id: str) -> ProjectIntent:
        project = self.get(project_id)
        target = Path(project.current_path) / ".learning" / "intent.json"
        if not target.exists():
            return ProjectIntent(goals=[], comfortable=[], deprioritized=[])
        return ProjectIntent.model_validate_json(target.read_text())

    @staticmethod
    def _metadata_project_id(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
            project_id = payload["project_id"]
            if payload.get("schema_version") != 1 or not is_valid_id(
                project_id, "proj"
            ):
                raise InvalidProjectMetadata(str(path))
            return project_id
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise InvalidProjectMetadata(str(path)) from error

    @staticmethod
    def _ensure_private_by_default(root: Path) -> None:
        dot_git = root / ".git"
        exclude: Path | None = None
        if dot_git.is_dir():
            exclude = dot_git / "info" / "exclude"
        elif dot_git.is_file():
            marker = dot_git.read_text().strip()
            if marker.startswith("gitdir:"):
                git_dir = Path(marker.removeprefix("gitdir:").strip())
                if not git_dir.is_absolute():
                    git_dir = (root / git_dir).resolve()
                common_marker = git_dir / "commondir"
                common_dir = git_dir
                if common_marker.exists():
                    common_value = Path(common_marker.read_text().strip())
                    common_dir = (
                        common_value
                        if common_value.is_absolute()
                        else (git_dir / common_value).resolve()
                    )
                exclude = common_dir / "info" / "exclude"

        if exclude is None:
            return
        exclude.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude.read_text() if exclude.exists() else ""
        lines = existing.splitlines()
        if "/.learning/" not in lines:
            prefix = existing if not existing or existing.endswith("\n") else existing + "\n"
            exclude.write_text(prefix + "/.learning/\n")

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)
