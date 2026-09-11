import pytest

from learning_mode.assessment import AssessmentService
from learning_mode.concepts import ConceptService
from learning_mode.db import Database
from learning_mode.debt import DebtService
from learning_mode.evidence import EvidenceService
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.migrations import migrate
from learning_mode.models import AssessmentResult, ConceptProposal
from learning_mode.projects import ProjectService
from learning_mode.puc import PUCService
from learning_mode.sessions import SessionService


@pytest.fixture
def assessment_core(tmp_path):
    db = Database(tmp_path / "home" / "learning.db")
    migrate(db)
    projects = ProjectService(db)
    root = tmp_path / "project"
    root.mkdir()
    project = projects.register(root)
    concepts = ConceptService(db)
    concept = concepts.resolve(ConceptProposal(name="Transaction isolation"))
    sessions = SessionService(db)
    session = sessions.start("codex", project.project_id)
    sessions.activate(session.session_id)
    evidence = EvidenceService(db, sessions, concepts)
    projector = KnowledgeProjector(db, evidence)
    puc = PUCService(db, concepts)
    puc.require(project.project_id, concept.concept_id, "primary", "learning goal")
    debt = DebtService(db, projector)
    assessment = AssessmentService(
        sessions=sessions,
        concepts=concepts,
        projector=projector,
        puc=puc,
        debt=debt,
        evidence=evidence,
    )
    return assessment, project, session, concept, evidence


def test_project_assessment_brief_contains_no_raw_events(assessment_core):
    assessment, project, _, concept, _ = assessment_core

    brief = assessment.request(scope="project", project_id=project.project_id)

    dumped = brief.model_dump_json()
    assert concept.concept_id in dumped
    assert "event_id" not in dumped
    assert "raw_evidence" not in dumped
    assert "summary" not in dumped


def test_recorded_assessment_becomes_new_evidence(assessment_core):
    assessment, _, session, concept, evidence = assessment_core
    result = AssessmentResult(
        session_id=session.session_id,
        concept_id=concept.concept_id,
        dimensions={"debugging": "strong"},
        outcome="demonstrated",
        assistance_level="none",
        summary="Developer diagnosed a novel failure scenario independently.",
    )

    events = assessment.record_result(result)

    assert events[0].event_type == "assessment"
    assert evidence.count_for_session(session.session_id) == 1


def test_weakest_scope_prefers_open_debt(assessment_core):
    assessment, project, _, concept, _ = assessment_core

    brief = assessment.request(scope="weakest", project_id=project.project_id)

    assert [target.concept_id for target in brief.targets] == [concept.concept_id]
