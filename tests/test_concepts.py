import pytest

from learning_mode.concepts import ConceptCycleError, ConceptService
from learning_mode.db import Database
from learning_mode.migrations import migrate
from learning_mode.models import ConceptProposal, RelationCandidate


@pytest.fixture
def concept_service(tmp_path):
    db = Database(tmp_path / "learning.db")
    migrate(db)
    return ConceptService(db)


def test_exact_normalized_name_reuses_concept(concept_service):
    first = concept_service.resolve(ConceptProposal(name="Database Transactions"))
    second = concept_service.resolve(
        ConceptProposal(name="... database   transactions !!!")
    )
    assert first.concept_id == second.concept_id
    assert second.created is False


def test_ambiguous_candidate_remains_separate(concept_service):
    first = concept_service.resolve(ConceptProposal(name="Transactions"))
    second = concept_service.resolve(
        ConceptProposal(
            name="Distributed transactions",
            relation_candidates=[
                RelationCandidate(
                    target_id=first.concept_id,
                    relation="equivalent",
                    confidence="ambiguous",
                )
            ],
        )
    )
    assert first.concept_id != second.concept_id
    assert concept_service.list_edges() == []


def test_only_high_confidence_structural_relations_create_edges(concept_service):
    parent = concept_service.resolve(ConceptProposal(name="Databases"))
    high_child = concept_service.resolve(
        ConceptProposal(
            name="Transactions",
            relation_candidates=[
                RelationCandidate(
                    target_id=parent.concept_id,
                    relation="parent_child",
                    confidence="high",
                )
            ],
        )
    )
    concept_service.resolve(
        ConceptProposal(
            name="Indexes",
            relation_candidates=[
                RelationCandidate(
                    target_id=parent.concept_id,
                    relation="related",
                    confidence="low",
                )
            ],
        )
    )

    assert concept_service.list_edges() == [
        (parent.concept_id, high_child.concept_id, "parent_child")
    ]


def test_parent_child_cycle_is_rejected(concept_service):
    a = concept_service.resolve(ConceptProposal(name="A"))
    b = concept_service.resolve(ConceptProposal(name="B"))
    c = concept_service.resolve(ConceptProposal(name="C"))
    concept_service.add_edge(a.concept_id, b.concept_id, "parent_child", "high")
    concept_service.add_edge(b.concept_id, c.concept_id, "parent_child", "high")

    assert concept_service.would_create_cycle(c.concept_id, a.concept_id)
    with pytest.raises(ConceptCycleError):
        concept_service.add_edge(
            c.concept_id, a.concept_id, "parent_child", "high"
        )
