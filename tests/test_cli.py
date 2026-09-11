import json

from typer.testing import CliRunner

from learning_mode.cli import app
from learning_mode.models import CandidateObservation
from learning_mode.service import LearningService


runner = CliRunner()


def make_candidate(session_id: str) -> CandidateObservation:
    return CandidateObservation(
        session_id=session_id,
        concept_name="transactions",
        evidence_type="guided_application",
        assistance_level="targeted_hint",
        dimensions={"application": "moderate"},
        agent_confidence="high",
        summary="Developer applied a transaction with one targeted hint.",
    )


def test_storage_failure_suspends_learning_without_host_failure(monkeypatch, tmp_path):
    service = LearningService(tmp_path / "home")
    session = service.sessions.start("codex", None)
    service.sessions.activate(session.session_id)
    monkeypatch.setattr(
        service.evidence,
        "submit",
        lambda *_: (_ for _ in ()).throw(OSError("disk")),
    )

    result = service.safe_submit_observation(make_candidate(session.session_id))

    assert result.status == "suspended"
    assert result.host_should_continue is True
    assert service.sessions.get(session.session_id).status == "suspended"


def test_off_facade_returns_no_context_and_writes_no_evidence(tmp_path):
    service = LearningService(tmp_path / "home")
    root = tmp_path / "project"
    root.mkdir()
    project_result = service.register_project(root)
    project_id = project_result.data["project_id"]
    session = service.sessions.start("claude", project_id)

    context_result = service.learner_context(
        session_id=session.session_id,
        project_id=project_id,
        concept_ids=[],
        task_summary="Continue ordinary work",
    )
    observation_result = service.safe_submit_observation(
        make_candidate(session.session_id)
    )

    assert context_result.model_dump(exclude_none=True) == {
        "ok": True,
        "status": "off",
        "message": "Learning Mode is off for this session.",
        "host_should_continue": True,
    }
    assert observation_result.ok is False
    assert observation_result.status == "off"
    assert service.evidence.count_for_session(session.session_id) == 0


def test_learn_on_can_register_and_attach_current_project(tmp_path):
    service = LearningService(tmp_path / "home")
    root = tmp_path / "project"
    root.mkdir()
    session_result = service.session_start("codex")
    session_id = session_result.data["session_id"]

    result = service.learn_on(session_id, project_path=root)

    assert result.ok is True
    assert result.status == "on"
    assert service.sessions.get(session_id).project_id is not None


def test_invalid_candidate_is_rejected_without_crashing_host(tmp_path):
    service = LearningService(tmp_path / "home")
    session = service.sessions.start("codex", None)
    service.sessions.activate(session.session_id)
    candidate = CandidateObservation(
        session_id=session.session_id,
        concept_name="transactions",
        evidence_type="independent_application",
        assistance_level="agent_completed",
        dimensions={"application": "strong"},
        agent_confidence="high",
        summary="The agent did the implementation.",
    )

    result = service.safe_submit_observation(candidate)

    assert result.ok is False
    assert result.status == "rejected"
    assert result.host_should_continue is True


def test_session_start_defaults_off(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LEARNING_MODE_HOME", str(home))

    result = runner.invoke(app, ["session-start", "--host", "codex", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "off"
    assert payload["session_id"].startswith("sess_")


def test_host_session_id_maps_to_same_core_session(tmp_path, monkeypatch):
    monkeypatch.setenv("LEARNING_MODE_HOME", str(tmp_path / "home"))
    args = [
        "session-start",
        "--host",
        "claude",
        "--host-session-id",
        "host-123",
        "--json",
    ]

    first = json.loads(runner.invoke(app, args).stdout)
    second = json.loads(runner.invoke(app, args).stdout)

    assert first["data"]["session_id"] == second["data"]["session_id"]


def test_cli_hard_cutoff_rejects_post_off_observation(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LEARNING_MODE_HOME", str(home))
    started = runner.invoke(app, ["session-start", "--host", "codex", "--json"])
    session_id = json.loads(started.stdout)["data"]["session_id"]
    assert runner.invoke(app, ["on", "--session", session_id, "--json"]).exit_code == 0
    observation = tmp_path / "observation.json"
    observation.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "concept_name": "transactions",
                "evidence_type": "guided_application",
                "assistance_level": "targeted_hint",
                "dimensions": {"application": "moderate"},
                "agent_confidence": "high",
                "summary": "Developer applied the transaction after a targeted hint.",
            }
        )
    )

    before = runner.invoke(
        app, ["observe", "--input", str(observation), "--json"]
    )
    stopped = runner.invoke(app, ["off", "--session", session_id, "--json"])
    after = runner.invoke(
        app, ["observe", "--input", str(observation), "--json"]
    )

    assert json.loads(before.stdout)["status"] == "recorded"
    assert json.loads(stopped.stdout)["status"] == "off"
    assert json.loads(after.stdout)["status"] == "off"
    assert LearningService(home).evidence.count_for_session(session_id) == 1


def test_cli_help_lists_v1_command_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["session-start", "on", "off", "status", "context", "observe"]:
        assert command in result.stdout
    assert "project" in result.stdout
    assert "test" in result.stdout
