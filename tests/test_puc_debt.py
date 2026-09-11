import pytest

from learning_mode.concepts import ConceptService
from learning_mode.db import Database
from learning_mode.debt import DebtService
from learning_mode.evidence import EvidenceService
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.migrations import migrate
from learning_mode.models import CandidateObservation, ConceptProposal, PUCProposal
from learning_mode.projects import ProjectService
from learning_mode.puc import PUCService
from learning_mode.sessions import SessionService


@pytest.fixture
def puc_core(tmp_path):
    db = Database(tmp_path / "home" / "learning.db")
    migrate(db)
    projects = ProjectService(db)
    root = tmp_path / "project"
    root.mkdir()
    project = projects.register(root)
    concepts = ConceptService(db)
    sessions = SessionService(db)
    session = sessions.start("codex", project.project_id)
    sessions.activate(session.session_id)
    evidence = EvidenceService(db, sessions, concepts)
    projector = KnowledgeProjector(db, evidence)
    puc = PUCService(db, concepts)
    debt = DebtService(db, projector)
    return project, session, concepts, evidence, puc, debt


def test_incidental_detail_is_not_puc_obligation(puc_core):
    project, _, _, _, puc, _ = puc_core
    puc.apply_proposals(
        project.project_id,
        [
            PUCProposal(
                concept_name="package import syntax",
                learning_depth="incidental",
                rationale="mechanical",
            )
        ],
    )
    assert puc.list_active(project.project_id) == []


def test_agent_built_primary_target_creates_understanding_debt(puc_core):
    project, _, concepts, _, puc, debt = puc_core
    concept = concepts.resolve(ConceptProposal(name="Redis caching"))
    puc.require(
        project.project_id,
        concept.concept_id,
        "primary",
        "explicit learning goal",
    )

    items = debt.rebuild(project.project_id)

    assert items[0].concept_id == concept.concept_id
    assert items[0].status == "open"


def test_primary_debt_resolves_after_conceptual_and_application_demonstration(
    puc_core,
):
    project, session, concepts, evidence, puc, debt = puc_core
    concept = concepts.resolve(ConceptProposal(name="Redis caching"))
    puc.require(project.project_id, concept.concept_id, "primary", "goal")
    evidence.submit(
        CandidateObservation(
            session_id=session.session_id,
            project_id=project.project_id,
            concept_name="Redis caching",
            evidence_type="explanation",
            assistance_level="none",
            dimensions={"conceptual": "strong"},
            agent_confidence="high",
            summary="Developer explained cache invalidation tradeoffs.",
        )
    )
    evidence.submit(
        CandidateObservation(
            session_id=session.session_id,
            project_id=project.project_id,
            concept_name="Redis caching",
            evidence_type="independent_application",
            assistance_level="none",
            dimensions={"application": "strong"},
            agent_confidence="high",
            summary="Developer independently chose a valid caching strategy.",
        )
    )

    items = debt.rebuild(project.project_id)

    assert items[0].status == "resolved"


def test_deactivating_puc_entry_preserves_inactive_row(puc_core):
    project, _, concepts, _, puc, _ = puc_core
    concept = concepts.resolve(ConceptProposal(name="SQL joins"))
    puc.require(project.project_id, concept.concept_id, "project_requirement", "used")

    puc.deactivate(project.project_id, concept.concept_id)

    assert puc.list_active(project.project_id) == []
    with puc.db.connect() as conn:
        row = conn.execute(
            "SELECT active FROM puc_entries WHERE project_id = ? AND concept_id = ?",
            (project.project_id, concept.concept_id),
        ).fetchone()
    assert row["active"] == 0
