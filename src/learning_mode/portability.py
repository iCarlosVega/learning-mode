import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath

from learning_mode import __version__
from learning_mode.db import Database
from learning_mode.models import now_utc, to_db_timestamp
from learning_mode.paths import LearningPaths


class PortabilityError(ValueError):
    pass


class PortabilityConflict(PortabilityError):
    pass


class PortabilityService:
    def __init__(self, paths: LearningPaths, db: Database):
        self.paths = paths
        self.db = db

    def export_bundle(self, path: Path) -> Path:
        files = self._open_export_files()
        manifest = self._manifest("learning-mode-export", files)
        self._write_archive(path, files, manifest)
        return path

    def import_bundle(self, path: Path) -> None:
        manifest, files = self._read_verified_archive(path)
        if manifest.get("format") != "learning-mode-export":
            raise PortabilityError("not a Learning Mode export")
        if manifest.get("format_version") != 1:
            raise PortabilityError("unsupported export format version")

        projects = self._decode_json(files, "global/projects.json")
        concepts_payload = self._decode_json(files, "global/concepts.json")
        sessions_payload = self._decode_json(files, "global/sessions.json")
        projections = self._decode_json(files, "global/projections.json")
        evidence = [
            json.loads(line)
            for line in files["global/evidence.jsonl"].decode().splitlines()
            if line.strip()
        ]

        with self.db.transaction() as conn:
            for project in projects:
                existing = conn.execute(
                    "SELECT * FROM projects WHERE project_id = ?",
                    (project["project_id"],),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO projects (
                            project_id, name, current_path, first_seen_at, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            project["project_id"],
                            project["name"],
                            project["current_path"],
                            project["first_seen_at"],
                            project["last_seen_at"],
                        ),
                    )

            for concept in concepts_payload["concepts"]:
                by_id = conn.execute(
                    "SELECT * FROM concepts WHERE concept_id = ?",
                    (concept["concept_id"],),
                ).fetchone()
                by_name = conn.execute(
                    "SELECT * FROM concepts WHERE normalized_name = ?",
                    (concept["normalized_name"],),
                ).fetchone()
                if by_id is not None and (
                    by_id["normalized_name"] != concept["normalized_name"]
                    or by_id["canonical_name"] != concept["canonical_name"]
                ):
                    raise PortabilityConflict(
                        f"concept identity conflict: {concept['concept_id']}"
                    )
                if by_name is not None and by_name["concept_id"] != concept["concept_id"]:
                    raise PortabilityConflict(
                        f"normalized concept conflict: {concept['normalized_name']}"
                    )
                if by_id is None:
                    conn.execute(
                        """
                        INSERT INTO concepts (
                            concept_id, canonical_name, normalized_name, created_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            concept["concept_id"],
                            concept["canonical_name"],
                            concept["normalized_name"],
                            concept["created_at"],
                        ),
                    )

            for session in sessions_payload["sessions"]:
                existing = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (session["session_id"],),
                ).fetchone()
                if existing is not None and (
                    existing["host"] != session["host"]
                    or existing["project_id"] != session["project_id"]
                    or existing["host_session_id"] != session["host_session_id"]
                ):
                    raise PortabilityConflict(
                        f"session identity conflict: {session['session_id']}"
                    )
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO sessions (
                            session_id, host, project_id, status, activated_at,
                            cutoff_at, created_at, suspension_reason, host_session_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session["session_id"],
                            session["host"],
                            session["project_id"],
                            session["status"],
                            session["activated_at"],
                            session["cutoff_at"],
                            session["created_at"],
                            session["suspension_reason"],
                            session["host_session_id"],
                        ),
                    )

            for interval in sessions_payload["intervals"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO session_intervals (
                        session_id, started_at, ended_at
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        interval["session_id"],
                        interval["started_at"],
                        interval["ended_at"],
                    ),
                )

            for edge in concepts_payload["edges"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO concept_edges (parent_id, child_id, relation)
                    VALUES (?, ?, ?)
                    """,
                    (edge["parent_id"], edge["child_id"], edge["relation"]),
                )

            for event in evidence:
                payload_json = json.dumps(event["payload"], sort_keys=True)
                existing = conn.execute(
                    "SELECT * FROM evidence_events WHERE event_id = ?",
                    (event["event_id"],),
                ).fetchone()
                stable_values = (
                    event["session_id"],
                    event["project_id"],
                    event["concept_id"],
                    event["event_type"],
                    event["assistance_level"],
                    payload_json,
                    event["created_at"],
                )
                if existing is not None:
                    existing_values = (
                        existing["session_id"],
                        existing["project_id"],
                        existing["concept_id"],
                        existing["event_type"],
                        existing["assistance_level"],
                        json.dumps(json.loads(existing["payload_json"]), sort_keys=True),
                        existing["created_at"],
                    )
                    if existing_values != stable_values:
                        raise PortabilityConflict(
                            f"evidence identity conflict: {event['event_id']}"
                        )
                    continue
                conn.execute(
                    """
                    INSERT INTO evidence_events (
                        event_id, session_id, project_id, concept_id, event_type,
                        assistance_level, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event["event_id"], *stable_values),
                )

            for state in projections["knowledge_state"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_state (
                        concept_id, state_json, derived_at
                    ) VALUES (?, ?, ?)
                    """,
                    (state["concept_id"], state["state_json"], state["derived_at"]),
                )
            for entry in projections["puc_entries"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO puc_entries (
                        project_id, concept_id, learning_depth, rationale, active
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        entry["project_id"],
                        entry["concept_id"],
                        entry["learning_depth"],
                        entry["rationale"],
                        entry["active"],
                    ),
                )
            for item in projections["understanding_debt"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO understanding_debt (
                        project_id, concept_id, status, rationale, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        item["project_id"],
                        item["concept_id"],
                        item["status"],
                        item["rationale"],
                        item["updated_at"],
                    ),
                )

        self._restore_project_files(files, projects, overwrite=False)

    def backup(self, path: Path) -> Path:
        with self.db.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
            projects = self._rows(conn, "projects")
        files = {"global/learning.db": self.db.path.read_bytes()}
        files.update(self._project_files(projects))
        manifest = self._manifest("learning-mode-backup", files)
        manifest["projects"] = {
            project["project_id"]: project["current_path"] for project in projects
        }
        self._write_archive(path, files, manifest)
        return path

    def restore(self, path: Path, force: bool = False) -> None:
        manifest, files = self._read_verified_archive(path)
        if manifest.get("format") != "learning-mode-backup":
            raise PortabilityError("not a Learning Mode backup")
        if manifest.get("format_version") != 1:
            raise PortabilityError("unsupported backup format version")
        if self.paths.database.exists() and not force:
            raise FileExistsError(self.paths.database)
        database_bytes = files.get("global/learning.db")
        if database_bytes is None:
            raise PortabilityError("backup does not contain the database")

        self.paths.home.mkdir(parents=True, exist_ok=True)
        temporary = self.paths.database.with_suffix(".restore.tmp")
        temporary.write_bytes(database_bytes)
        temporary.replace(self.paths.database)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.paths.database}{suffix}")
            if sidecar.exists():
                sidecar.unlink()

        projects = [
            {"project_id": project_id, "current_path": current_path}
            for project_id, current_path in manifest.get("projects", {}).items()
        ]
        self._restore_project_files(files, projects, overwrite=force)

    def _open_export_files(self) -> dict[str, bytes]:
        with self.db.connect() as conn:
            projects = self._rows(conn, "projects")
            concepts = self._rows(conn, "concepts")
            edges = self._rows(conn, "concept_edges")
            sessions = self._rows(conn, "sessions")
            intervals = self._rows(conn, "session_intervals")
            events = self._rows(conn, "evidence_events")
            knowledge = self._rows(conn, "knowledge_state")
            puc_entries = self._rows(conn, "puc_entries")
            debt = self._rows(conn, "understanding_debt")

        evidence_lines = []
        for event in events:
            event["payload"] = json.loads(event.pop("payload_json"))
            evidence_lines.append(json.dumps(event, sort_keys=True))
        files = {
            "global/projects.json": self._json_bytes(projects),
            "global/concepts.json": self._json_bytes(
                {"concepts": concepts, "edges": edges}
            ),
            "global/sessions.json": self._json_bytes(
                {"sessions": sessions, "intervals": intervals}
            ),
            "global/evidence.jsonl": (
                ("\n".join(evidence_lines) + ("\n" if evidence_lines else "")).encode()
            ),
            "global/projections.json": self._json_bytes(
                {
                    "knowledge_state": knowledge,
                    "puc_entries": puc_entries,
                    "understanding_debt": debt,
                }
            ),
        }
        files.update(self._project_files(projects))
        return files

    @staticmethod
    def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]

    @staticmethod
    def _json_bytes(value: object) -> bytes:
        return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()

    def _project_files(self, projects: list[dict]) -> dict[str, bytes]:
        files = {}
        for project in projects:
            learning_dir = Path(project["current_path"]) / ".learning"
            if not learning_dir.is_dir():
                continue
            for source in sorted(learning_dir.rglob("*")):
                if source.is_file() and not source.is_symlink():
                    relative = source.relative_to(learning_dir).as_posix()
                    member = (
                        f"projects/{project['project_id']}/.learning/{relative}"
                    )
                    files[member] = source.read_bytes()
        return files

    @staticmethod
    def _manifest(format_name: str, files: dict[str, bytes]) -> dict:
        return {
            "format": format_name,
            "format_version": 1,
            "created_at": to_db_timestamp(now_utc()),
            "learning_mode_version": __version__,
            "files": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                for name, content in sorted(files.items())
            ],
        }

    @classmethod
    def _write_archive(
        cls, path: Path, files: dict[str, bytes], manifest: dict
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", cls._json_bytes(manifest))
            for name, content in sorted(files.items()):
                archive.writestr(name, content)

    @staticmethod
    def _read_verified_archive(path: Path) -> tuple[dict, dict[str, bytes]]:
        try:
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                files = {}
                for item in manifest.get("files", []):
                    name = item["path"]
                    pure = PurePosixPath(name)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise PortabilityError(f"unsafe archive path: {name}")
                    content = archive.read(name)
                    if hashlib.sha256(content).hexdigest() != item["sha256"]:
                        raise PortabilityError(f"checksum mismatch: {name}")
                    files[name] = content
        except (KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            raise PortabilityError(f"invalid portability archive: {path}") from error
        return manifest, files

    @staticmethod
    def _decode_json(files: dict[str, bytes], name: str):
        try:
            return json.loads(files[name])
        except (KeyError, json.JSONDecodeError) as error:
            raise PortabilityError(f"missing or invalid export member: {name}") from error

    @staticmethod
    def _restore_project_files(
        files: dict[str, bytes], projects: list[dict], overwrite: bool
    ) -> None:
        paths = {
            project["project_id"]: Path(project["current_path"])
            for project in projects
        }
        for member, content in files.items():
            parts = PurePosixPath(member).parts
            if len(parts) < 4 or parts[0] != "projects" or parts[2] != ".learning":
                continue
            project_root = paths.get(parts[1])
            if project_root is None or not project_root.is_dir():
                continue
            target = project_root / ".learning" / Path(*parts[3:])
            if target.exists() and not overwrite:
                if target.read_bytes() != content:
                    raise PortabilityConflict(f"project metadata conflict: {target}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".restore.tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
