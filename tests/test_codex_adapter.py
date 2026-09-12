import os
import subprocess


def test_codex_adapter_has_discoverable_skill_and_wrapper(repo_root):
    root = repo_root / "adapters" / "codex"
    skill = root / "SKILL.md"
    wrapper = root / "scripts" / "learning-mode.sh"

    assert skill.exists()
    assert (root / "AGENTS.snippet.md").exists()
    assert wrapper.exists()
    assert os.access(wrapper, os.X_OK)

    text = skill.read_text()
    assert text.startswith("---\nname: learning-mode\n")
    assert "description:" in text.split("---", 2)[1]
    assert "../shared/learning-protocol.md" in text


def test_codex_wrapper_forwards_arguments_and_requests_json(repo_root, tmp_path):
    fake = tmp_path / "learn"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\"\n"
    )
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}

    result = subprocess.run(
        [
            str(
                repo_root
                / "adapters"
                / "codex"
                / "scripts"
                / "learning-mode.sh"
            ),
            "status",
            "--session",
            "sess_example",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "status",
        "--session",
        "sess_example",
        "--json",
    ]


def test_codex_skill_enforces_explicit_activation_and_off_cutoff(repo_root):
    text = (repo_root / "adapters" / "codex" / "SKILL.md").read_text().lower()

    assert "explicit" in text
    assert "starts off" in text
    assert "never infer activation" in text
    assert "learn status" in text
    assert "derived context" in text
    assert "never request raw evidence" in text
    assert "candidate" in text
    assert "not mastery" in text
    assert "immediately stop" in text
    assert "continue the coding task normally" in text


def test_codex_agents_snippet_is_advertising_only(repo_root):
    text = (
        repo_root / "adapters" / "codex" / "AGENTS.snippet.md"
    ).read_text().lower()

    assert "explicit" in text
    assert "$learning-mode" in text
    assert "do not activate" in text
    assert "do not inspect" in text
    assert "do not observe" in text
