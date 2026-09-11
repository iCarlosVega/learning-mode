from concurrent.futures import ThreadPoolExecutor

from learning_mode.models import CandidateObservation
from learning_mode.service import LearningService


def candidate(session_id: str, summary: str, event_id: str | None = None):
    return CandidateObservation(
        session_id=session_id,
        concept_name="Concurrent transactions",
        evidence_type="guided_application",
        assistance_level="targeted_hint",
        dimensions={"application": "moderate"},
        agent_confidence="high",
        summary=summary,
        event_id=event_id,
    )


def test_concurrent_observations_are_all_persisted(tmp_path):
    home = tmp_path / "home"
    coordinator = LearningService(home)
    session = coordinator.sessions.start("codex", None)
    coordinator.sessions.activate(session.session_id)

    def submit(index: int):
        service = LearningService(home)
        return service.safe_submit_observation(
            candidate(session.session_id, f"event-{index}")
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(50)))

    assert all(result.ok for result in results)
    assert coordinator.evidence.count_for_session(session.session_id) == 50


def test_concurrent_duplicate_event_id_is_idempotent(tmp_path):
    home = tmp_path / "home"
    coordinator = LearningService(home)
    session = coordinator.sessions.start("claude", None)
    coordinator.sessions.activate(session.session_id)
    observation = candidate(
        session.session_id,
        "Same host callback delivered twice.",
        event_id="evt_00000000000000000000000000000001",
    )

    def submit(_):
        return LearningService(home).safe_submit_observation(observation)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))

    assert sorted(result.status for result in results) == ["duplicate", "recorded"]
    assert coordinator.evidence.count_for_session(session.session_id) == 1
    assert coordinator.sessions.get(session.session_id).status == "on"
