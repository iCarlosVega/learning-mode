# Learning Mode

Learning Mode is a local-first, opt-in teaching layer for Codex CLI and Claude
Code. The active coding agent uses one shared protocol to protect meaningful
developer decisions, while a deterministic Python Core stores conservative
evidence and derives qualitative learning state.

Every host session starts OFF. A user must explicitly enable Learning Mode for
that session; project history never activates it. When OFF, the adapters perform
no learning observation, inference, context lookup, or state mutation. If the
Core fails, coding continues normally.

## V1 at a glance

- Canonical state is local SQLite at `~/.learning-mode/learning.db` by default.
- Project identity and intent live in a local `.learning/` directory.
- Raw evidence is never injected into coding-agent context. Adapters receive only
  minimum, task-relevant derived state.
- Evidence is append-only, assistance-aware, and treated as fallible. The Core
  derives qualitative states; it does not maintain a numeric mastery score.
- Codex and Claude share the same local Core and stable project/concept identity.
- No additional Learning Mode LLM, remote service, telemetry, or API key is
  required.

Obsidian synchronization, dashboards, cloud sync, and scheduled spaced
repetition are possible future work, not V1 features.

## Install the Core

Python 3.12 or newer is required.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
learn status --json
```

The final command returns one JSON object with status `off` when no session is
selected. Keep the virtual environment active when launching a host, or make the
installed `learn` executable available on that host's `PATH`.

To use a separate local state directory:

```bash
export LEARNING_MODE_HOME=/absolute/private/path/learning-mode-home
```

## Connect a host

- [Install the Codex skill](docs/install-codex.md)
- [Install the Claude Code plugin](docs/install-claude.md)

Activation syntax differs by host, but activation is always explicit and scoped
to the current host session. For example, invoke `$learning-mode` in Codex or
`/learning-mode:learn-on` in Claude Code. Disabling establishes a hard cutoff:
subsequent interactions are neither observed nor reconstructed later.

## Privacy and ownership

The normal context API returns learning goals, requested concepts, qualitative
dimension levels, retention, misconception status, PUC depth, and understanding
debt. It excludes event IDs, event payloads, raw conversation/code excerpts, and
unrelated concepts. See the [privacy model](docs/privacy.md) for the full data
boundary.

The owner can create an open logical export or an exact local backup. Both can
contain sensitive learning history and must be protected like other developer
data. See [portability](docs/portability.md) for export/import and backup/restore.

## Development

```bash
python -m pip install -e '.[dev]'
pytest -q
```

The adapter-facing CLI contract is documented in
[docs/adapter-contract.md](docs/adapter-contract.md); teaching semantics live in
[adapters/shared/learning-protocol.md](adapters/shared/learning-protocol.md).
