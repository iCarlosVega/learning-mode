"""Validated public models shared by Core services and host adapters."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_db_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def from_db_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SessionRecord(BaseModel):
    session_id: str
    host: Literal["codex", "claude"]
    project_id: str | None
    status: Literal["on", "off", "suspended"]
    activated_at: datetime | None
    cutoff_at: datetime | None
    created_at: datetime
    suspension_reason: str | None = None
