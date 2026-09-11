#!/usr/bin/env python3
"""Fail-open Claude Code lifecycle bridge for the local Learning Core."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def _call_learn(arguments: list[str]) -> dict:
    executable = os.environ.get("LEARNING_MODE_CLI", "learn")
    completed = subprocess.run(
        [executable, *arguments, "--json"],
        text=True,
        capture_output=True,
        timeout=8,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "learn command failed")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("learn did not emit exactly one JSON document")
    return json.loads(lines[0])


def _emit_context(event_name: str, message: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "additionalContext": message,
                }
            }
        )
    )


def _status(host_session_id: str) -> dict:
    return _call_learn(
        [
            "status",
            "--host",
            "claude",
            "--host-session-id",
            host_session_id,
        ]
    )


def _remember_core_session(session_id: str) -> None:
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    with Path(env_file).open("a") as stream:
        stream.write(
            f"export LEARNING_MODE_SESSION_ID={shlex.quote(session_id)}\n"
        )


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
        host_session_id = payload.get("session_id")
        event_name = payload.get("hook_event_name", "SessionStart")
        if not host_session_id:
            raise ValueError("hook input has no session_id")

        if action == "session-start":
            cwd = payload.get("cwd") or os.getcwd()
            result = _call_learn(
                [
                    "session-start",
                    "--host",
                    "claude",
                    "--host-session-id",
                    host_session_id,
                    "--project",
                    cwd,
                ]
            )
            core_session_id = result.get("session_id")
            if core_session_id:
                _remember_core_session(core_session_id)
            if result.get("status") == "on":
                _emit_context(
                    event_name,
                    "Learning Mode is ON for this resumed session. Follow the canonical "
                    "protocol and request only minimum task-relevant derived context.",
                )
            else:
                _emit_context(
                    event_name,
                    "Learning Mode Core session is mapped and starts OFF. "
                    "Do not observe, infer, teach, or request learner context unless the "
                    "user explicitly invokes /learning-mode:learn-on.",
                )
            return 0

        result = _status(host_session_id)
        if result.get("status") != "on":
            return 0
        if action == "active-context":
            _emit_context(
                event_name,
                "Learning Mode is ON for this session. Follow the canonical protocol, "
                "request only minimum task-relevant derived context, and submit only "
                "conservative candidate observations after completed interactions.",
            )
        elif action == "stop":
            _emit_context(
                event_name,
                "Learning Mode remains ON. Before ending, submit only any candidate "
                "observation already completed during this turn; do not infer mastery.",
            )
        return 0
    except Exception as error:
        event_name = "SessionStart"
        try:
            event_name = payload.get("hook_event_name", event_name)
        except (NameError, AttributeError):
            pass
        _emit_context(
            event_name,
            f"Learning Mode is unavailable ({type(error).__name__}); continue normally.",
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
