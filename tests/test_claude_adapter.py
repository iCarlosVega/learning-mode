import json
import os
import subprocess
import sys


def test_claude_plugin_has_required_assets(repo_root):
    root = repo_root / "adapters" / "claude"
    assert (root / ".claude-plugin" / "plugin.json").exists()
    assert (root / "hooks" / "hooks.json").exists()
    assert (root / "skills" / "learn-on" / "SKILL.md").exists()
    assert (root / "skills" / "learn-off" / "SKILL.md").exists()
    hooks = json.loads((root / "hooks" / "hooks.json").read_text())
    assert {"SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"} <= set(
        hooks["hooks"]
    )


def make_fake_learn(tmp_path, response):
    executable = tmp_path / "fake-learn"
    log = tmp_path / "calls.jsonl"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['LEARN_CALL_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"print({json.dumps(json.dumps(response))})\n"
    )
    executable.chmod(0o755)
    return executable, log


def run_hook(repo_root, action, payload, env):
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "adapters" / "claude" / "scripts" / "hook.py"),
            action,
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_session_start_hook_maps_session_but_leaves_learning_off(repo_root, tmp_path):
    fake, log = make_fake_learn(
        tmp_path,
        {
            "ok": True,
            "status": "off",
            "session_id": "sess_abc",
            "host_should_continue": True,
        },
    )
    env_file = tmp_path / "claude-env"
    env = {
        **os.environ,
        "LEARNING_MODE_CLI": str(fake),
        "LEARN_CALL_LOG": str(log),
        "CLAUDE_ENV_FILE": str(env_file),
    }

    result = run_hook(
        repo_root,
        "session-start",
        {
            "session_id": "host-123",
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
            "source": "startup",
        },
        env,
    )

    assert result.returncode == 0
    assert json.loads(log.read_text().splitlines()[0])[:3] == [
        "session-start",
        "--host",
        "claude",
    ]
    assert "LEARNING_MODE_SESSION_ID" in env_file.read_text()
    assert "starts OFF" in result.stdout


def test_prompt_hook_when_off_only_checks_status_and_never_persists_prompt(
    repo_root, tmp_path
):
    fake, log = make_fake_learn(
        tmp_path,
        {"ok": True, "status": "off", "host_should_continue": True},
    )
    env = {
        **os.environ,
        "LEARNING_MODE_CLI": str(fake),
        "LEARN_CALL_LOG": str(log),
    }
    sentinel = "SENTINEL-PROMPT-SECRET-42"

    result = run_hook(
        repo_root,
        "active-context",
        {
            "session_id": "host-123",
            "cwd": str(tmp_path),
            "hook_event_name": "UserPromptSubmit",
            "prompt": sentinel,
        },
        env,
    )

    assert result.returncode == 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls == [
        [
            "status",
            "--host",
            "claude",
            "--host-session-id",
            "host-123",
            "--json",
        ]
    ]
    assert sentinel not in result.stdout
    assert all(sentinel not in path.read_text() for path in tmp_path.iterdir())


def test_hook_failure_is_fail_open(repo_root, tmp_path):
    env = {**os.environ, "LEARNING_MODE_CLI": str(tmp_path / "missing-learn")}

    result = run_hook(
        repo_root,
        "session-start",
        {
            "session_id": "host-123",
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
        },
        env,
    )

    assert result.returncode == 0
    assert "continue normally" in result.stdout


def test_resumed_active_session_is_not_reported_as_off(repo_root, tmp_path):
    fake, log = make_fake_learn(
        tmp_path,
        {
            "ok": True,
            "status": "on",
            "session_id": "sess_abc",
            "host_should_continue": True,
        },
    )
    env = {
        **os.environ,
        "LEARNING_MODE_CLI": str(fake),
        "LEARN_CALL_LOG": str(log),
    }

    result = run_hook(
        repo_root,
        "session-start",
        {
            "session_id": "host-123",
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
            "source": "resume",
        },
        env,
    )

    assert "Learning Mode is ON" in result.stdout
    assert "starts OFF" not in result.stdout
