---
name: learn-test
description: Use when the user explicitly requests a Learning Mode assessment of a concept or project.
disable-model-invocation: true
---

# Run a Learning Assessment

1. Run `learn status --session "$LEARNING_MODE_SESSION_ID" --json`. If status is not `on`, do not assess or record evidence.
2. Run `learn test request` with the requested `concept`, `project`, `weakest`, or `since` scope.
3. Use only the derived assessment brief. Create a fresh question, debugging scenario, prediction, or tradeoff prompt suited to the target; do not retrieve or repeat raw evidence.
4. Let the developer answer with safe productive struggle and the minimum necessary assistance.
5. Record the outcome and actual assistance using `learn test record --input <result.json> --json`. This creates new assessment evidence; it does not mutate mastery directly.
