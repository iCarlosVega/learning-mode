import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path

from learning_mode.assessment import AssessmentService
from learning_mode.concepts import ConceptService
from learning_mode.context import ContextService
from learning_mode.db import Database
from learning_mode.debt import DebtService
from learning_mode.evidence import EvidenceService, InvalidObservation, SessionNotActive
from learning_mode.knowledge import KnowledgeProjector
from learning_mode.migrations import migrate
from learning_mode.models import (
    CandidateObservation,
    AssessmentResult,
    LearningSuspended,
    PUCProposal,
    ResultEnvelope,
)
from learning_mode.paths import LearningPaths
from learning_mode.projects import ProjectService
from learning_mode.puc import PUCService
from learning_mode.sessions import SessionNotFound, SessionService


class LearningService:
    """The only Core boundary used by host adapters and the CLI."""

    def __init__(self, home: Path | LearningPaths):
        self.paths = home if isinstance(home, LearningPaths) else LearningPaths(home)
        self.db = Database(self.paths.database)
        migrate(self.db)
        self.sessions = SessionService(self.db)
        self.projects = ProjectService(self.db)
        self.concepts = ConceptService(self.db)
        self.evidence = EvidenceService(self.db, self.sessions, self.concepts)
        self.knowledge = KnowledgeProjector(self.db, self.evidence)
        self.puc = PUCService(self.db, self.concepts)
        self.debt = DebtService(self.db, self.knowledge)
        self.context = ContextService(
            self.projects, self.concepts, self.knowledge, self.puc, self.debt
        )
        self.assessment = AssessmentService(
            sessions=self.sessions,
            concepts=self.concepts,
            projector=self.knowledge,
            puc=self.puc,
            debt=self.debt,
            evidence=self.evidence,
        )

    def session_start(
        self,
        host: str,
        project_id: str | None = None,
        host_session_id: str | None = None,
        project_path: Path | None = None,
    ) -> ResultEnvelope:
        try:
            if project_path is not None:
                project_id = self.projects.register(project_path).project_id
            session = self.sessions.start(host, project_id, host_session_id)
            return ResultEnvelope(
                ok=True,
                status=session.status,
                message="Learning Mode session created; learning starts off.",
                session_id=session.session_id,
                data=session.model_dump(mode="json"),
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(None, error)

    def learn_on(
        self, session_id: str, project_path: Path | None = None
    ) -> ResultEnvelope:
        try:
            if project_path is not None:
                project = self.projects.register(project_path)
                self.sessions.attach_project(session_id, project.project_id)
            session = self.sessions.activate(session_id)
            return ResultEnvelope(
                ok=True,
                status="on",
                message="Learning Mode is active for this session.",
                data=session.model_dump(mode="json"),
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(session_id, error)

    def learn_off(
        self, session_id: str, finalize: Callable[[], None] | None = None
    ) -> ResultEnvelope:
        try:
            session = self.sessions.deactivate(
                session_id, finalize=finalize or (lambda: None)
            )
            return ResultEnvelope(
                ok=True,
                status="off",
                message="Learning Mode is off for this session.",
                data=session.model_dump(mode="json"),
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(session_id, error)

    def status(
        self,
        session_id: str | None = None,
        host: str | None = None,
        host_session_id: str | None = None,
    ) -> ResultEnvelope:
        try:
            session = None
            if session_id is not None:
                session = self.sessions.get(session_id)
            elif host is not None and host_session_id is not None:
                session = self.sessions.find_by_host_session(host, host_session_id)
            if session is None:
                return ResultEnvelope(
                    ok=True,
                    status="off",
                    message="No Learning Mode session is active or selected.",
                )
            return ResultEnvelope(
                ok=True,
                status=session.status,
                message=f"Learning Mode is {session.status} for this session.",
                data=session.model_dump(mode="json"),
            )
        except SessionNotFound:
            return ResultEnvelope(
                ok=False,
                status="off",
                message="Learning Mode session was not found.",
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(session_id, error)

    def register_project(self, path: Path) -> ResultEnvelope:
        try:
            project = self.projects.register(path)
            return ResultEnvelope(
                ok=True,
                status="registered",
                message="Project identity is registered locally.",
                data=project.model_dump(mode="json"),
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(None, error)

    def set_project_intent(
        self,
        project_id: str,
        goals: Sequence[str],
        comfortable: Sequence[str],
        deprioritized: Sequence[str],
    ) -> ResultEnvelope:
        try:
            intent = self.projects.set_intent(
                project_id, goals, comfortable, deprioritized
            )
            return ResultEnvelope(
                ok=True,
                status="updated",
                message="Project learning intent updated.",
                data=intent.model_dump(mode="json"),
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(None, error)

    def learner_context(
        self,
        session_id: str,
        project_id: str,
        concept_ids: list[str],
        task_summary: str,
    ) -> ResultEnvelope:
        if not self.sessions.is_active(session_id):
            return ResultEnvelope(
                ok=True,
                status="off",
                message="Learning Mode is off for this session.",
            )
        try:
            context = self.context.for_task(project_id, concept_ids, task_summary)
            return ResultEnvelope(
                ok=True,
                status="on",
                message="Derived learner context ready.",
                data=context.model_dump(mode="json"),
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(session_id, error)

    def submit_observation(
        self, candidate: CandidateObservation
    ) -> ResultEnvelope:
        return self.safe_submit_observation(candidate)

    def safe_submit_observation(
        self, candidate: CandidateObservation
    ) -> ResultEnvelope:
        try:
            event = self.evidence.submit(candidate)
            return ResultEnvelope(
                ok=True,
                status="recorded",
                message="Candidate observation was validated and recorded.",
                data={"event_id": event.event_id, "concept_id": event.concept_id},
            )
        except SessionNotActive:
            return ResultEnvelope(
                ok=False,
                status="off",
                message="Observation rejected because Learning Mode is off.",
            )
        except InvalidObservation as error:
            return ResultEnvelope(
                ok=False,
                status="rejected",
                message=f"Candidate observation rejected: {error}",
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(candidate.session_id, error)

    def apply_puc_proposals(
        self, project_id: str, proposals: Sequence[PUCProposal]
    ) -> ResultEnvelope:
        try:
            entries = self.puc.apply_proposals(project_id, proposals)
            return ResultEnvelope(
                ok=True,
                status="updated",
                message="Project Understanding Contract updated.",
                data=[entry.model_dump(mode="json") for entry in entries],
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(None, error)

    def assessment_request(
        self,
        scope: str,
        project_id: str | None = None,
        concept_ids: list[str] | None = None,
    ) -> ResultEnvelope:
        try:
            brief = self.assessment.request(
                scope=scope, project_id=project_id, concept_ids=concept_ids
            )
            return ResultEnvelope(
                ok=True,
                status="ready",
                message="Assessment brief ready for the active host agent.",
                data=brief.model_dump(mode="json"),
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(None, error)

    def assessment_result(self, result: AssessmentResult) -> ResultEnvelope:
        try:
            events = self.assessment.record_result(result)
            return ResultEnvelope(
                ok=True,
                status="recorded",
                message="Assessment result recorded as new evidence.",
                data=[
                    {"event_id": event.event_id, "concept_id": event.concept_id}
                    for event in events
                ],
            )
        except SessionNotActive:
            return ResultEnvelope(
                ok=False,
                status="off",
                message="Assessment result rejected because Learning Mode is off.",
            )
        except InvalidObservation as error:
            return ResultEnvelope(
                ok=False,
                status="rejected",
                message=f"Assessment result rejected: {error}",
            )
        except (OSError, sqlite3.Error) as error:
            return self._suspended(result.session_id, error)

    def _suspended(
        self, session_id: str | None, error: BaseException
    ) -> LearningSuspended:
        if session_id is not None:
            try:
                self.sessions.suspend(session_id, str(error))
            except (OSError, sqlite3.Error):
                pass
        return LearningSuspended(
            message=f"Learning Mode suspended; host work should continue: {error}"
        )
