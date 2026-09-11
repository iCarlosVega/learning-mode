---
name: learning-mode
description: Use only when the user explicitly asks to enable, disable, inspect, or test Learning Mode in the current Codex session. Do not use for ordinary coding or inferred teaching intent.
---

# Learning Mode for Codex

Learning Mode is an opt-in, session-scoped teaching supervisor backed by the local
Learning Core. Read `../shared/learning-protocol.md` and follow it whenever this
skill is active. The protocol is authoritative if this file is ambiguous.

Use `scripts/learning-mode.sh` for every Core command. It emits one JSON result.
Treat `off`, `suspended`, `rejected`, malformed output, a missing executable, or
any other failure as a signal to continue the coding task normally.

## Hard activation boundary

- Never infer activation from project history, prior sessions, a learning-related
  task, or the existence of local state. Every newly created Core session starts
  OFF.
- Create or map a Core session only after the user explicitly asks to enable
  Learning Mode. Do not create one for a status, test, or disable request.
- While OFF, do not inspect learner or project state, request context, classify
  work for teaching, observe behavior, infer evidence, or mutate Learning Mode.
- Keep the returned Core session ID only in this Codex conversation's working
  context. Do not persist adapter shadow state or conversation content.

## Enable

After an explicit enable request:

1. Run `scripts/learning-mode.sh session-start --host codex --project "$PWD"`.
   Retain the returned `session_id` only in the current conversation.
2. Run `scripts/learning-mode.sh status --session SESSION_ID`. Confirm that the
   new session starts OFF.
3. Run `scripts/learning-mode.sh on --session SESSION_ID --project "$PWD"`.
   Enter Learning Mode only if the returned status is `on`.
4. If project learning intent is not yet configured, ask one concise onboarding
   question about goals, comfortable areas, and deprioritized areas, then use
   `project intent` to save the answer.
5. For every later Learning Mode action, first run `learn status` through the
   wrapper for the retained session. Continue Learning Mode behavior only while
   status is `on`.

## Work while ON

- Classify only concepts relevant to the current task and propose finite PUC
  changes where needed. Discovery and files read are not evidence.
- Request minimum-necessary derived context only for the current task and named
  concepts. Never request raw evidence, event payloads, transcripts, or excerpts.
- Protect the developer's next meaningful decision using the assistance ladder
  in the canonical protocol. Respect explicit delegation and safety boundaries.
- After a completed interaction, submit a conservative candidate observation
  only for specific demonstrated behavior. A candidate is not mastery; record
  actual assistance, including `agent_completed`, and let the Core validate it.
- For an explicit assessment request, obtain a derived assessment brief, create
  fresh questions, and record only the result as new evidence.

## Disable

After an explicit disable request, first check status. If it is `on`, submit only
candidate observations already completed before the request; never reconstruct
evidence. Then run `scripts/learning-mode.sh off --session SESSION_ID`. Once the
Core reports `off`, immediately stop teaching, observing, inferring, requesting
context, and mutating Learning Mode for this session.

If no Core session ID is present for a status, disable, or test request, report
that Learning Mode is OFF or unavailable without creating a session, then
continue the coding task normally.
