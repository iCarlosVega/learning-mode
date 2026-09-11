# Install the Codex CLI adapter

The Codex adapter is a repository-backed skill plus a small deterministic shell
wrapper. Codex discovers repository skills from `.agents/skills` and loads the
full `SKILL.md` only when selected. The adapter does not wrap or proxy Codex.

## Prerequisites

Install the Core from the Learning Mode repository and confirm the CLI is visible:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
learn status --json
```

No API key is required by Learning Mode. Codex itself retains its normal account
or provider configuration.

## Link the skill into a project

From the project where you launch Codex:

```bash
mkdir -p .agents/skills
ln -s /absolute/path/to/learning-mode/adapters/codex .agents/skills/learning-mode
```

Use an absolute source path. The symlink keeps the skill next to its canonical
shared protocol in the Learning Mode checkout. Restart Codex if an already-open
session does not show the newly linked skill. In Codex CLI, `/skills` lists
available skills and `$learning-mode` explicitly selects this one.

You may also copy the short guidance in `adapters/codex/AGENTS.snippet.md` into a
project `AGENTS.md`. It only advertises the skill; it does not enable Learning
Mode or authorize silent observation.

Codex skill discovery and invocation are described in the official
[Build skills documentation](https://learn.chatgpt.com/docs/build-skills), and
project instruction precedence is described in the official
[`AGENTS.md` documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## Session workflow

1. Start Codex normally. Learning Mode is OFF, and no Core session is created by
   ordinary work.
2. Explicitly invoke `$learning-mode` and ask it to enable Learning Mode.
3. The skill creates a Core session, confirms it starts OFF, activates it, and
   keeps the returned ID only in the current Codex conversation.
4. While ON, the skill checks `learn status` before Learning Mode behavior and
   requests only task-relevant derived context.
5. Ask `$learning-mode` to run an assessment or report status when needed.
6. Ask `$learning-mode` to disable Learning Mode. After `off` is confirmed, the
   adapter immediately stops teaching, observation, inference, and state writes.

If `learn` is missing, its JSON is malformed, or the local database is
unavailable, the skill suspends Learning Mode behavior and Codex continues the
coding task normally.

## Remove the project link

Remove only the `.agents/skills/learning-mode` symlink from the target project.
This does not delete the Learning Mode source checkout or the local canonical
state. Removing an adapter is separate from deleting learner data.
