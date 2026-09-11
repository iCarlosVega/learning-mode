# Portability, backup, and restore

Learning Mode provides two deliberately separate portability mechanisms through
`LearningService.portability`:

- **Export/import** is an open, versioned logical format for migration and
  inspection. A ZIP contains a checksummed manifest, JSONL evidence history, JSON
  project/concept/session/projection metadata, and registered project
  `.learning/` directories.
- **Backup/restore** is an exact local recovery format. A ZIP contains the SQLite
  database bytes after a full WAL checkpoint, project `.learning/` directories,
  and a checksummed manifest.

## Python API

```python
from pathlib import Path

from learning_mode.service import LearningService

service = LearningService(Path.home() / ".learning-mode")

service.portability.export_bundle(Path("learning-export.zip"))
service.portability.import_bundle(Path("learning-export.zip"))

service.portability.backup(Path("learning-backup.zip"))
service.portability.restore(Path("learning-backup.zip"))
```

Restore refuses to overwrite an existing database. An owner who has deliberately
verified the target can opt into replacement with
`restore(path, force=True)`. Keep a separate recovery copy before replacing any
existing state.

## Stable identity and repeat imports

Project, concept, session, and event IDs remain stable across export/import.
Importing the same bundle twice is idempotent: immutable events are not duplicated.
If a stable ID or normalized concept name conflicts with different content, the
import rejects the conflict instead of silently overwriting canonical history.

Registered projects recover their `.learning/project.json` and
`.learning/intent.json` files when the recorded project path exists. Because the
stable project ID lives in `.learning/project.json`, moving a project together
with that directory preserves its identity when it is registered again.

## Choosing a format

Use export/import to migrate between installations, inspect the logical format,
or support future schema-aware tooling. Use backup/restore for an exact local
recovery point on the current V1 implementation. Neither format is an
adapter-context response.

Both formats can contain event IDs, semantic summaries, project paths, learning
goals, and other sensitive developer history. Store them in a private location,
exclude them from version control, and protect them in transit.
