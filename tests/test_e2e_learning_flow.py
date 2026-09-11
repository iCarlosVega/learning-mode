import json
import zipfile

from learning_mode.models import CandidateObservation, PUCProposal
from learning_mode.service import LearningService


def _candidate(path, *, session_id, project_id):
    payload = json.loads(path.read_text())
    return CandidateObservation(
        **payload,
        session_id=session_id,
        project_id=project_id,
    )


def test_codex_and_claude_share_one_private_learning_lifecycle(repo_root, tmp_path):
    home = tmp_path / "learning-home"
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    fixtures = repo_root / "tests" / "fixtures"

    codex = LearningService(home)
    codex_start = codex.session_start(
        host="codex",
        host_session_id="codex-e2e",
        project_path=project_root,
    )
    assert codex_start.status == "off"
    codex_session_id = codex_start.session_id
    assert codex_session_id is not None
    project_id = codex_start.data["project_id"]

    assert codex.learn_on(codex_session_id, project_path=project_root).status == "on"
    intent = codex.set_project_intent(
        project_id,
        goals=["Understand Redis caching"],
        comfortable=["Python"],
        deprioritized=[],
    )
    assert intent.status == "updated"

    first = codex.submit_observation(
        _candidate(
            fixtures / "codex" / "redis-independent.json",
            session_id=codex_session_id,
            project_id=project_id,
        )
    )
    assert first.status == "recorded"
    redis_concept_id = first.data["concept_id"]

    assert codex.learn_off(codex_session_id).status == "off"
    rejected = codex.submit_observation(
        _candidate(
            fixtures / "codex" / "redis-independent.json",
            session_id=codex_session_id,
            project_id=project_id,
        ).model_copy(update={"context_key": "after-codex-cutoff"})
    )
    assert rejected.status == "off"
    assert codex.evidence.count_for_session(codex_session_id) == 1

    claude = LearningService(home)
    claude_start = claude.session_start(
        host="claude",
        host_session_id="claude-e2e",
        project_path=project_root,
    )
    assert claude_start.status == "off"
    claude_session_id = claude_start.session_id
    assert claude_session_id is not None
    assert claude.learn_on(claude_session_id, project_path=project_root).status == "on"

    context = claude.learner_context(
        claude_session_id,
        project_id,
        [redis_concept_id],
        "Choose a Redis invalidation strategy",
    )
    context_json = context.model_dump_json()
    assert context.status == "on"
    assert context.data["concepts"][0]["dimensions"]["application"] == "demonstrated"
    assert "event_id" not in context_json
    assert "payload_json" not in context_json
    assert "E2E-RAW-SENTINEL" not in context_json

    second = claude.submit_observation(
        _candidate(
            fixtures / "claude" / "redis-explanation.json",
            session_id=claude_session_id,
            project_id=project_id,
        )
    )
    assert second.status == "recorded"
    puc = claude.apply_puc_proposals(
        project_id,
        [
            PUCProposal(
                concept_name="Redis caching",
                learning_depth="primary",
                rationale="Explicit project learning goal",
            )
        ],
    )
    assert puc.status == "updated"

    rebuilt = claude.learner_context(
        claude_session_id,
        project_id,
        [redis_concept_id],
        "Review the Redis project requirement",
    )
    assert rebuilt.data["concepts"][0]["understanding_debt"] == "none"
    assert rebuilt.data["concepts"][0]["learning_depth"] == "primary"

    export_path = tmp_path / "shared-learning-export.zip"
    claude.portability.export_bundle(export_path)
    with zipfile.ZipFile(export_path) as archive:
        names = set(archive.namelist())
        evidence = archive.read("global/evidence.jsonl").decode()
        sessions = archive.read("global/sessions.json").decode()
    assert f"projects/{project_id}/.learning/project.json" in names
    assert f"projects/{project_id}/.learning/intent.json" in names
    assert evidence.count('"event_id"') == 2
    assert '"host": "codex"' in sessions
    assert '"host": "claude"' in sessions


def test_database_outage_suspends_learning_without_retroactive_evidence(tmp_path):
    home = tmp_path / "learning-home"
    project_root = tmp_path / "project"
    project_root.mkdir()
    service = LearningService(home)
    started = service.session_start(host="claude", project_path=project_root)
    session_id = started.session_id
    project_id = started.data["project_id"]
    service.learn_on(session_id, project_path=project_root)
    before = service.evidence.count_for_session(session_id)

    candidate = CandidateObservation(
        session_id=session_id,
        project_id=project_id,
        concept_name="Redis outage handling",
        evidence_type="guided_application",
        assistance_level="targeted_hint",
        dimensions={"debugging": "moderate"},
        agent_confidence="medium",
        summary="This interaction occurred while the Core was unavailable.",
        context_key="database-outage-interval",
    )

    database = service.paths.database
    saved_database = database.with_suffix(".temporarily-unavailable")
    database.rename(saved_database)
    database.mkdir()
    try:
        unavailable = service.submit_observation(candidate)
    finally:
        database.rmdir()
        saved_database.rename(database)

    assert unavailable.status == "suspended"
    assert unavailable.host_should_continue is True
    assert service.evidence.count_for_session(session_id) == before
    assert service.learn_off(session_id).status == "off"
    with service.db.connect() as connection:
        retroactive = connection.execute(
            "SELECT COUNT(*) FROM evidence_events WHERE payload_json LIKE ?",
            ("%database-outage-interval%",),
        ).fetchone()[0]
    assert retroactive == 0
