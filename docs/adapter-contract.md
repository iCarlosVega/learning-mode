# Learning Mode Adapter Contract

Host adapters call the installed `learn` executable and never import database, migration, repository, or projection internals. `learning_mode.service.LearningService` is the public Python boundary. Canonical state is local SQLite; adapters persist no shadow learner state.

Set `LEARNING_MODE_HOME` to select a local state directory. It defaults to `~/.learning-mode`.

Every adapter call passes `--json`. Standard output contains exactly one JSON object. The common envelope is:

```json
{
  "ok": true,
  "status": "off",
  "message": "Human-readable summary.",
  "host_should_continue": true,
  "data": {}
}
```

`data` is omitted when there is no payload. Adapters decide behavior from `ok` and `status`, not process prose. A learning failure returns `status: "suspended"` with `host_should_continue: true`; it must not block normal coding.

## Lifecycle

Create or recover the Core mapping for one host session:

```bash
learn session-start --host claude --host-session-id "$CLAUDE_SESSION_ID" --project "$PWD" --json
```

The top-level `session_id` is the opaque Core session identifier. Reusing the same host and host-session ID returns the same mapping without silently enabling learning.

```bash
learn on --session "$SESSION_ID" --project "$PWD" --json
learn status --session "$SESSION_ID" --json
learn status --host claude --host-session-id "$CLAUDE_SESSION_ID" --json
learn off --session "$SESSION_ID" --json
```

`learn off` establishes the hard cutoff. An observation attempted afterward returns `status: "off"` and writes nothing.

## Project state

```bash
learn project register --path "$PWD" --json
learn project intent \
  --project-id "$PROJECT_ID" \
  --goal "Understand cache invalidation" \
  --comfortable "Python" \
  --deprioritized "CSS" \
  --json
learn project puc --project-id "$PROJECT_ID" --input puc-proposals.json --json
```

`puc-proposals.json` is a JSON list (or an object with a `proposals` list):

```json
[
  {
    "concept_name": "Redis cache invalidation",
    "learning_depth": "primary",
    "rationale": "Explicit project learning goal"
  }
]
```

## Derived context

```bash
learn context \
  --session "$SESSION_ID" \
  --project-id "$PROJECT_ID" \
  --concept concept_abc \
  --task "Add Redis caching" \
  --json
```

The response includes only the requested concepts' qualitative dimensions, retention, misconception status, PUC depth, debt state, and project intent. It never includes raw evidence, event IDs, individual event timestamps, conversation/code excerpts, or unrelated concepts. When the session is OFF, `data` is omitted.

## Candidate observations

```bash
learn observe --input observation.json --json
```

```json
{
  "session_id": "sess_abc",
  "project_id": "proj_abc",
  "concept_name": "Redis cache invalidation",
  "evidence_type": "independent_application",
  "assistance_level": "none",
  "dimensions": {"application": "strong", "tradeoffs": "moderate"},
  "agent_confidence": "high",
  "summary": "Developer selected and justified a cache invalidation strategy.",
  "context_key": "project-a-cache"
}
```

The Core validates the candidate, discounts assistance, resolves the concept conservatively, and appends one immutable event. A repeated explicit event ID with the same semantic payload returns `status: "duplicate"`; a conflicting payload is rejected.

## Explicit assessments

```bash
learn test request --scope project --project-id "$PROJECT_ID" --json
learn test request --scope concept --concept concept_abc --json
learn test request --scope weakest --project-id "$PROJECT_ID" --json
learn test record --input assessment-result.json --json
```

The brief contains derived targets only. The host agent writes fresh questions or scenarios, conducts the assessment, and records the result. The Core never supplies memorized raw exchanges as assessment material.

## Semantic operation mapping

| Adapter operation | CLI boundary |
| --- | --- |
| Session start | `learn session-start` |
| Activate/deactivate | `learn on` / `learn off` |
| Status check | `learn status` |
| Project discovery proposal | `learn project register` |
| Derived context request | `learn context` |
| Candidate observation | `learn observe` |
| PUC proposal | `learn project puc` |
| Assessment request/result | `learn test request` / `learn test record` |

All semantic teaching behavior follows `adapters/shared/learning-protocol.md`.
