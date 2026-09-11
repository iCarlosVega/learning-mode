import json
import os
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

import typer
from pydantic import ValidationError

from learning_mode.models import (
    AssessmentResult,
    CandidateObservation,
    LearningSuspended,
    PUCProposal,
    ResultEnvelope,
)
from learning_mode.service import LearningService


app = typer.Typer(no_args_is_help=True, help="Local-first Learning Mode core.")
project_app = typer.Typer(no_args_is_help=True, help="Manage project learning state.")
test_app = typer.Typer(no_args_is_help=True, help="Request or record assessments.")
app.add_typer(project_app, name="project")
app.add_typer(test_app, name="test")


def _service() -> LearningService:
    home = Path(os.environ.get("LEARNING_MODE_HOME", "~/.learning-mode")).expanduser()
    return LearningService(home)


def _invoke(operation: Callable[[LearningService], ResultEnvelope]) -> ResultEnvelope:
    try:
        return operation(_service())
    except (OSError, sqlite3.Error) as error:
        return LearningSuspended(
            message=f"Learning Mode suspended; host work should continue: {error}"
        )
    except (ValidationError, ValueError, LookupError, json.JSONDecodeError) as error:
        return ResultEnvelope(
            ok=False,
            status="rejected",
            message=f"Request rejected: {error}",
        )


def _emit(result: ResultEnvelope, json_output: bool) -> None:
    del json_output
    typer.echo(result.model_dump_json(exclude_none=True))


def _read_json(path: Path) -> object:
    text = sys.stdin.read() if str(path) == "-" else path.read_text()
    return json.loads(text)


@app.command("session-start")
def session_start(
    host: str = typer.Option(..., "--host"),
    host_session_id: str | None = typer.Option(None, "--host-session-id"),
    project: Path | None = typer.Option(None, "--project"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    result = _invoke(
        lambda service: service.session_start(
            host=host,
            host_session_id=host_session_id,
            project_path=project,
        )
    )
    _emit(result, json_output)


@app.command("on")
def learn_on(
    session: str = typer.Option(..., "--session"),
    project: Path | None = typer.Option(None, "--project"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(
        _invoke(lambda service: service.learn_on(session, project_path=project)),
        json_output,
    )


@app.command("off")
def learn_off(
    session: str = typer.Option(..., "--session"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(_invoke(lambda service: service.learn_off(session)), json_output)


@app.command("status")
def status(
    session: str | None = typer.Option(None, "--session"),
    host: str | None = typer.Option(None, "--host"),
    host_session_id: str | None = typer.Option(None, "--host-session-id"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(
        _invoke(
            lambda service: service.status(
                session_id=session,
                host=host,
                host_session_id=host_session_id,
            )
        ),
        json_output,
    )


@app.command("context")
def context(
    session: str = typer.Option(..., "--session"),
    project_id: str = typer.Option(..., "--project-id"),
    concept: list[str] | None = typer.Option(None, "--concept"),
    task_summary: str = typer.Option(..., "--task"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(
        _invoke(
            lambda service: service.learner_context(
                session, project_id, concept or [], task_summary
            )
        ),
        json_output,
    )


@app.command("observe")
def observe(
    input_path: Path = typer.Option(..., "--input"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(
        _invoke(
            lambda service: service.submit_observation(
                CandidateObservation.model_validate(_read_json(input_path))
            )
        ),
        json_output,
    )


@project_app.command("register")
def project_register(
    path: Path = typer.Option(Path("."), "--path"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(_invoke(lambda service: service.register_project(path)), json_output)


@project_app.command("intent")
def project_intent(
    project_id: str = typer.Option(..., "--project-id"),
    goal: list[str] | None = typer.Option(None, "--goal"),
    comfortable: list[str] | None = typer.Option(None, "--comfortable"),
    deprioritized: list[str] | None = typer.Option(None, "--deprioritized"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(
        _invoke(
            lambda service: service.set_project_intent(
                project_id, goal or [], comfortable or [], deprioritized or []
            )
        ),
        json_output,
    )


@project_app.command("puc")
def project_puc(
    project_id: str = typer.Option(..., "--project-id"),
    input_path: Path = typer.Option(..., "--input"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    def operation(service: LearningService) -> ResultEnvelope:
        payload = _read_json(input_path)
        values = payload.get("proposals", []) if isinstance(payload, dict) else payload
        proposals = [PUCProposal.model_validate(item) for item in values]
        return service.apply_puc_proposals(project_id, proposals)

    _emit(_invoke(operation), json_output)


@test_app.command("request")
def test_request(
    scope: str = typer.Option(..., "--scope"),
    project_id: str | None = typer.Option(None, "--project-id"),
    concept: list[str] | None = typer.Option(None, "--concept"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(
        _invoke(
            lambda service: service.assessment_request(
                scope, project_id=project_id, concept_ids=concept
            )
        ),
        json_output,
    )


@test_app.command("record")
def test_record(
    input_path: Path = typer.Option(..., "--input"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _emit(
        _invoke(
            lambda service: service.assessment_result(
                AssessmentResult.model_validate(_read_json(input_path))
            )
        ),
        json_output,
    )


if __name__ == "__main__":
    app()
