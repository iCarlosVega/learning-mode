---
name: learn-status
description: Use when the user asks whether Learning Mode is enabled in the current Claude Code session.
disable-model-invocation: true
---

# Learning Mode Status

Run `learn status --session "$LEARNING_MODE_SESSION_ID" --json` and report its status concisely. Do not enable Learning Mode, inspect derived learner context, or infer learning evidence as part of a status request.
