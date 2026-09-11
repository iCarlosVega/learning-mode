from learning_mode.db import Database

LATEST_SCHEMA_VERSION = 3


_MIGRATION_1 = """
CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  current_path TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  host TEXT NOT NULL CHECK(host IN ('codex','claude')),
  project_id TEXT REFERENCES projects(project_id),
  status TEXT NOT NULL CHECK(status IN ('on','off','suspended')),
  activated_at TEXT,
  cutoff_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE concepts (
  concept_id TEXT PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_concepts_normalized_name
ON concepts(normalized_name);

CREATE TABLE concept_edges (
  parent_id TEXT NOT NULL REFERENCES concepts(concept_id),
  child_id TEXT NOT NULL REFERENCES concepts(concept_id),
  relation TEXT NOT NULL CHECK(relation IN ('parent_child','related')),
  PRIMARY KEY(parent_id, child_id, relation)
);

CREATE TABLE evidence_events (
  event_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  project_id TEXT REFERENCES projects(project_id),
  concept_id TEXT REFERENCES concepts(concept_id),
  event_type TEXT NOT NULL,
  assistance_level TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE knowledge_state (
  concept_id TEXT PRIMARY KEY REFERENCES concepts(concept_id),
  state_json TEXT NOT NULL,
  derived_at TEXT NOT NULL
);

CREATE TABLE puc_entries (
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  concept_id TEXT NOT NULL REFERENCES concepts(concept_id),
  learning_depth TEXT NOT NULL,
  rationale TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(project_id, concept_id)
);

CREATE TABLE understanding_debt (
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  concept_id TEXT NOT NULL REFERENCES concepts(concept_id),
  status TEXT NOT NULL,
  rationale TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id, concept_id)
);
"""

_MIGRATION_2 = """
ALTER TABLE sessions ADD COLUMN suspension_reason TEXT;

CREATE TABLE session_intervals (
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  started_at TEXT NOT NULL,
  ended_at TEXT,
  PRIMARY KEY(session_id, started_at)
);
"""

_MIGRATION_3 = """
CREATE TRIGGER evidence_events_no_update
BEFORE UPDATE ON evidence_events
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;

CREATE TRIGGER evidence_events_no_delete
BEFORE DELETE ON evidence_events
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
"""


def migrate(db: Database) -> None:
    """Bring *db* to the latest schema version."""
    with db.transaction() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.executescript(_MIGRATION_1)
            conn.execute("PRAGMA user_version = 1")
            version = 1
        if version < 2:
            conn.executescript(_MIGRATION_2)
            conn.execute("PRAGMA user_version = 2")
            version = 2
        if version < 3:
            conn.executescript(_MIGRATION_3)
            conn.execute("PRAGMA user_version = 3")
