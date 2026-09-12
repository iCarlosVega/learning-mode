from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LearningPaths:
    home: Path

    @property
    def database(self) -> Path:
        return self.home / "learning.db"

    @property
    def exports(self) -> Path:
        return self.home / "exports"


def resolve_project_root(start: Path) -> Path:
    """Resolve *start* to the nearest containing Git project, if any."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current
