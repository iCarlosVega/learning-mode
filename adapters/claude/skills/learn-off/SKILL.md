---
name: learn-off
description: Use when the user explicitly asks to disable Learning Mode for the current Claude Code session.
disable-model-invocation: true
---

# Disable Learning Mode

1. Run `learn status --session "$LEARNING_MODE_SESSION_ID" --json`.
2. If status is `on`, submit only any candidate observation already completed before this request. Do not manufacture or reconstruct evidence.
3. Run `learn off --session "$LEARNING_MODE_SESSION_ID" --json`.
4. When status is `off`, immediately stop all Learning Mode teaching, observation, inference, context requests, and state mutation. Continue as normal Claude Code.

If the Core fails, report suspension briefly and continue the coding task normally.

