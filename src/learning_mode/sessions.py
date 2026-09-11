from collections.abc import Callable
from datetime import datetime

from learning_mode.db import Database
from learning_mode.ids import new_id
from learning_mode.models import (
    SessionRecord,
    from_db_timestamp,
    now_utc,
    to_db_timestamp,
)


class SessionNotFound(LookupError):
    pass


class SessionService:
    def __init__(self, db: Database, now: Callable[[], datetime] = now_utc):
        self.db = db
        self._now = now

    def start(self, host: str, project_id: str | None) -> SessionRecord:
        if host not in {"codex", "claude"}:
            raise ValueError(f"unsupported host: {host}")
        session_id = new_id("sess")
        created_at = to_db_timestamp(self._now())
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, host, project_id, status, activated_at,
                    cutoff_at, created_at, suspension_reason
                ) VALUES (?, ?, ?, 'off', NULL, NULL, ?, NULL)
                """,
                (session_id, host, project_id, created_at),
            )
        return self.get(session_id)

    def get(self, session_id: str) -> SessionRecord:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        return self._record(row)

    def activate(self, session_id: str) -> SessionRecord:
        instant = to_db_timestamp(self._now())
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT status FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise SessionNotFound(session_id)
            if row["status"] != "on":
                conn.execute(
                    """
                    UPDATE sessions
                    SET status = 'on', activated_at = ?, cutoff_at = NULL,
                        suspension_reason = NULL
                    WHERE session_id = ?
                    """,
                    (instant, session_id),
                )
                conn.execute(
                    """
                    INSERT INTO session_intervals (session_id, started_at, ended_at)
                    VALUES (?, ?, NULL)
                    """,
                    (session_id, instant),
                )
        return self.get(session_id)

    def deactivate(
        self,
        session_id: str,
        finalize: Callable[[], None],
        after_cutoff: Callable[[], None] | None = None,
    ) -> SessionRecord:
        current = self.get(session_id)
        if current.status == "on":
            finalize()
            instant = to_db_timestamp(self._now())
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    UPDATE sessions
                    SET status = 'off', cutoff_at = ?, suspension_reason = NULL
                    WHERE session_id = ?
                    """,
                    (instant, session_id),
                )
                conn.execute(
                    """
                    UPDATE session_intervals SET ended_at = ?
                    WHERE session_id = ? AND ended_at IS NULL
                    """,
                    (instant, session_id),
                )
            if after_cutoff is not None:
                after_cutoff()
        return self.get(session_id)

    def suspend(self, session_id: str, reason: str) -> SessionRecord:
        instant = to_db_timestamp(self._now())
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE sessions
                SET status = 'suspended', cutoff_at = ?, suspension_reason = ?
                WHERE session_id = ?
                """,
                (instant, reason, session_id),
            )
            if cursor.rowcount == 0:
                raise SessionNotFound(session_id)
            conn.execute(
                """
                UPDATE session_intervals SET ended_at = ?
                WHERE session_id = ? AND ended_at IS NULL
                """,
                (instant, session_id),
            )
        return self.get(session_id)

    def is_active(self, session_id: str) -> bool:
        try:
            return self.get(session_id).status == "on"
        except SessionNotFound:
            return False

    def accepts_event_at(self, session_id: str, occurred_at: datetime) -> bool:
        if not self.is_active(session_id):
            return False
        occurred = to_db_timestamp(occurred_at)
        current = to_db_timestamp(self._now())
        if occurred > current:
            return False
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM session_intervals
                WHERE session_id = ?
                  AND started_at <= ?
                  AND (ended_at IS NULL OR ? <= ended_at)
                LIMIT 1
                """,
                (session_id, occurred, occurred),
            ).fetchone()
        return row is not None

    @staticmethod
    def _record(row) -> SessionRecord:
        return SessionRecord(
            session_id=row["session_id"],
            host=row["host"],
            project_id=row["project_id"],
            status=row["status"],
            activated_at=from_db_timestamp(row["activated_at"]),
            cutoff_at=from_db_timestamp(row["cutoff_at"]),
            created_at=from_db_timestamp(row["created_at"]),
            suspension_reason=row["suspension_reason"],
        )
