import pytest

from learning_mode.concepts import ConceptService
from learning_mode.db import Database
from learning_mode.evidence import EvidenceService
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.migrations import migrate
from learning_mode.models import CandidateObservation
from learning_mode.sessions import SessionService


@pytest.fixture
def knowledge_core(tmp_path):
    db = Database(tmp_path / "learning.db")
    migrate(db)
    sessions = SessionService(db)
    session = sessions.start("codex", None)
    sessions.activate(session.session_id)
    concepts = ConceptService(db)
    evidence = EvidenceService(db, sessions, concepts)
    projector = KnowledgeProjector(db, evidence)
    return session, evidence, projector


@pytest.fixture
def event_factory(knowledge_core):
    session, evidence, _ = knowledge_core

    def add(
        event_type,
        dimension,
        strength,
        assistance="none",
        *,
        concept_name="Transactions",
        context_key=None,
        occurred_at=None,
    ):
        candidate = CandidateObservation(
            session_id=session.session_id,
            concept_name=concept_name,
            evidence_type=event_type,
            assistance_level=assistance,
            dimensions={dimension: strength},
            agent_confidence="high",
            summary=f"Observed {event_type} for {dimension}.",
            context_key=context_key,
            **({"occurred_at": occurred_at} if occurred_at else {}),
        )
        return evidence.submit(candidate).concept_id

    return add


@pytest.fixture
def projector(knowledge_core):
    return knowledge_core[2]


def test_exposure_only_does_not_become_practiced(projector, event_factory):
    concept_id = event_factory("exposure", "conceptual", "weak")
    state = projector.rebuild(concept_id)
    assert state.dimensions["conceptual"].level == "introduced"


def test_one_independent_application_is_not_automatically_durable(
    projector, event_factory
):
    concept_id = event_factory("independent_application", "application", "strong")
    state = projector.rebuild(concept_id)
    assert state.dimensions["application"].level == "demonstrated"
    assert state.dimensions["application"].level != "durable"


def test_agent_completed_work_does_not_raise_implementation_mastery(
    projector, event_factory
):
    concept_id = event_factory(
        "guided_application",
        "implementation",
        "strong",
        assistance="agent_completed",
    )
    state = projector.rebuild(concept_id)
    assert state.dimensions["implementation"].level in {
        "introduced",
        "insufficient_evidence",
    }


def test_correction_revises_state_without_erasing_misconception(
    knowledge_core, event_factory
):
    _, evidence, projector = knowledge_core
    concept_id = event_factory("misconception", "conceptual", "strong")
    event_factory("correction", "conceptual", "strong")

    state = projector.rebuild(concept_id)

    assert state.current_misconception_status == "corrected"
    events = evidence.list_for_concept(concept_id)
    assert sum(event.event_type == "misconception" for event in events) == 1
    assert sum(event.event_type == "correction" for event in events) == 1


def test_durable_requires_repeated_independent_evidence_across_contexts(
    projector, event_factory
):
    concept_id = event_factory(
        "independent_application",
        "application",
        "strong",
        context_key="project-a",
    )
    event_factory(
        "transfer",
        "application",
        "strong",
        context_key="project-b",
    )

    state = projector.rebuild(concept_id)

    assert state.dimensions["application"].level == "durable"
