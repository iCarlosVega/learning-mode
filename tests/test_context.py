import pytest

from learning_mode.concepts import ConceptService
from learning_mode.context import ContextService
from learning_mode.db import Database
from learning_mode.debt import DebtService
from learning_mode.evidence import EvidenceService
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.migrations import migrate
from learning_mode.models import CandidateObservation, ConceptProposal
from learning_mode.projects import ProjectService
from learning_mode.puc import PUCService
from learning_mode.sessions import SessionService


@pytest.fixture
def populated_context(tmp_path):
    db = Database(tmp_path / "home" / "learning.db")
    migrate(db)
    projects = ProjectService(db)
    root = tmp_path / "project"
    root.mkdir()
    project = projects.register(root)
    projects.set_intent(
        project.project_id,
        goals=["Understand Redis caching"],
        comfortable=["Python"],
        deprioritized=[],
    )
    concepts = ConceptService(db)
    redis = concepts.resolve(ConceptProposal(name="Redis caching"))
    sql = concepts.resolve(ConceptProposal(name="SQL joins"))
    sessions = SessionService(db)
    session = sessions.start("codex", project.project_id)
    sessions.activate(session.session_id)
    evidence = EvidenceService(db, sessions, concepts)
    evidence.submit(
        CandidateObservation(
            session_id=session.session_id,
            project_id=project.project_id,
            concept_name="Redis caching",
            evidence_type="independent_application",
            assistance_level="none",
            dimensions={"application": "strong"},
            agent_confidence="high",
            summary="SENTINEL raw conversation and code must stay private.",
        )
    )
    projector = KnowledgeProjector(db, evidence)
    puc = PUCService(db, concepts)
    puc.require(project.project_id, redis.concept_id, "primary", "explicit goal")
    debt = DebtService(db, projector)
    context = ContextService(projects, concepts, projector, puc, debt)
    return context, project, redis, sql


def test_context_never_contains_raw_evidence(populated_context):
    context_service, project, redis, _ = populated_context
    context = context_service.for_task(
        project_id=project.project_id,
        concept_ids=[redis.concept_id],
        task_summary="Add Redis caching",
    )
    serialized = context.model_dump_json()
    assert "event_id" not in serialized
    assert "payload_json" not in serialized
    assert "raw_evidence" not in serialized
    assert "SENTINEL" not in serialized
    assert "Redis" in serialized


def test_context_omits_unrelated_global_knowledge(populated_context):
    context_service, project, redis, _ = populated_context

    context = context_service.for_task(
        project_id=project.project_id,
        concept_ids=[redis.concept_id],
        task_summary="Add Redis caching",
    )

    assert [item.name for item in context.concepts] == ["Redis caching"]
    assert "SQL joins" not in context.model_dump_json()
