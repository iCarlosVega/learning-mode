from concurrent.futures import ThreadPoolExecutor
from threading import Event

from learning_mode.models import CandidateObservation, ConceptProposal
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


def test_cutoff_rejects_observation_that_has_not_started_its_write(tmp_path):
    service = LearningService(tmp_path / "home")
    session = service.sessions.start("codex", None)
    service.sessions.activate(session.session_id)
    concept = service.concepts.resolve(ConceptProposal(name="Cutoff races"))
    resolver_entered = Event()
    allow_resolution = Event()

    class BlockingResolver:
        def resolve_name(self, _name):
            resolver_entered.set()
            assert allow_resolution.wait(timeout=5)
            return concept.concept_id

    service.evidence.concepts = BlockingResolver()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            service.safe_submit_observation,
            candidate(session.session_id, "Must not cross the hard cutoff."),
        )
        assert resolver_entered.wait(timeout=5)
        assert service.learn_off(session.session_id).status == "off"
        allow_resolution.set()
        result = pending.result(timeout=5)

    assert result.status == "off"
    assert service.evidence.count_for_session(session.session_id) == 0
