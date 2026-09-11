# Privacy model

Learning Mode is local-first and bounded by an explicit session lifecycle. Its
privacy guarantees are behavioral contracts tested in the Core and both host
adapters.

## Guarantees

- **OFF performs no learning observation or state mutation.** It also performs
  no learner-context request, concept classification for teaching, evidence
  inference, or project-state mutation. Project history never turns a new session
  on.
- **Raw evidence is not injected into coding-agent context.** Context and
  assessment responses contain only requested qualitative projections and
  project intent. They exclude event IDs, payloads, individual event timestamps,
  conversation/code excerpts, and unrelated concepts.
- **Canonical state is local SQLite.** The default database is
  `~/.learning-mode/learning.db`; `LEARNING_MODE_HOME` can select another private
  local directory. There is no cloud synchronization or telemetry in V1.
- **Project `.learning/` is local/private by default.** In Git projects the Core
  adds `/.learning/` to the repository-local Git exclude file, not the shared
  `.gitignore`. The directory holds stable project identity and declared learning
  intent. For another version-control system, configure an equivalent local
  ignore rule.
- **No extra Learning Mode LLM/API is called.** The active Codex or Claude model
  performs the teaching-supervisor reasoning from the shared protocol. The Core
  is deterministic Python and SQLite, so Learning Mode needs no additional API
  key.
- **Exports may contain sensitive learning history.** Protect exports and backups
  like developer data: keep them private, encrypt them when appropriate, and do
  not attach them to support requests or commits without inspection.

## What is stored while ON

The Core accepts concise candidate observations after completed interactions.
Each candidate includes a concept, evidence type, affected learning dimensions,
claimed strength, actual assistance level, agent confidence, and a short semantic
summary. The Core validates and discounts the claim before appending an immutable
event. Candidates are evidence proposals, not mastery declarations.

Project intent, the Project Understanding Contract, qualitative knowledge state,
retention metadata, misconception status, and understanding debt are derived or
maintained locally. There are no numeric mastery scores.

Candidate summaries should still be minimal. They should describe demonstrated
behavior without copying secrets, full prompts, source files, command output, or
transcripts.

## Hard cutoff and failures

Disabling Learning Mode closes the current activation interval. The adapter may
finalize only observations already completed before that request; it cannot
reconstruct evidence from later work. A database or adapter failure suspends
Learning Mode and tells the host to continue normally. Evidence from the outage
interval is never backfilled.

Raw evidence remains available only through owner-controlled maintenance/export
paths and direct local inspection. It is never part of the normal adapter context
API.
