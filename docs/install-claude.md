# Install the Claude Code adapter

The Claude adapter is a native Claude Code plugin with lifecycle hooks and
explicit skills. Its startup hook maps a Claude session to the local Core but
leaves Learning Mode OFF. Prompt and tool hook payloads are never persisted.

## Prerequisites

Install the Core and keep its `learn` executable available to Claude Code:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
learn status --json
```

No Learning Mode API key is required. To use the executable outside the active
virtual environment, set `LEARNING_MODE_CLI` to its absolute path before starting
Claude Code.

## Validate and load the plugin

From the Learning Mode repository:

```bash
claude plugin validate ./adapters/claude
claude --plugin-dir /absolute/path/to/learning-mode/adapters/claude
```

`--plugin-dir` loads the plugin directly for development and local use. The
plugin structure and local loading workflow follow the official
[Claude Code plugin documentation](https://code.claude.com/docs/en/plugins) and
[plugin reference](https://code.claude.com/docs/en/plugins-reference).

## Session workflow

1. Start Claude Code with the plugin. The startup hook maps the host session and
   reports that Learning Mode starts OFF.
2. Run `/learning-mode:learn-on` to activate it explicitly for this session.
3. Use `/learning-mode:learn-status` to check the hard lifecycle state.
4. Use `/learning-mode:learn-test` only for an explicit assessment request.
5. Run `/learning-mode:learn-off` to finalize already-completed observations and
   establish the cutoff. Work after the cutoff is not observed or reconstructed.

The plugin's `UserPromptSubmit`, `PostToolUse`, and `Stop` hooks check only the
mapped session status while OFF. They do not send prompt text, tool payloads, or
conversation excerpts to the Core. Hook errors return success to Claude Code and
surface a short suspension message so normal coding can continue. See the
official [hooks guide](https://code.claude.com/docs/en/hooks) for host lifecycle
details.

To stop loading the development plugin, launch Claude Code without the
`--plugin-dir` option. This does not delete canonical local learning state.
