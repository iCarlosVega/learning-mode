---
name: learn-on
description: Use when the user explicitly asks to enable Learning Mode for the current Claude Code session.
disable-model-invocation: true
---

# Enable Learning Mode

1. Require `LEARNING_MODE_SESSION_ID` from the SessionStart hook. If it is absent, report that Learning Mode is unavailable and continue as normal Claude Code.
2. Run `learn status --session "$LEARNING_MODE_SESSION_ID" --json`.
3. Run `learn on --session "$LEARNING_MODE_SESSION_ID" --project "$PWD" --json`. Continue only when its status is `on`.
4. If `.learning/intent.json` does not exist, ask the user one concise onboarding question covering goals, comfortable areas, and deprioritized areas; persist the answer with `learn project intent`.
5. Read `../shared/learning-protocol.md` relative to this repository's `adapters/claude` directory and follow it for the rest of this session while status remains `on`.
6. Classify only concepts relevant to the current task. Propose PUC entries, then request derived context for the returned concept IDs. Never request raw evidence.

Learning Mode is session-scoped. Prior project history does not activate it. Any Core error suspends learning behavior but never blocks the coding task.
