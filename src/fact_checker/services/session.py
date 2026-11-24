"""One web session of a claim: propose statements, confirm them, then verify, all traced and stored per run."""

import sqlite3
from pathlib import Path

from fact_checker.contracts import ConfirmedStatements, Edit, Statement
from fact_checker.llm.base import LLMClient, LLMError
from fact_checker.llm.config import Settings
from fact_checker.services.confirm import Issue, apply_edits, check_statements
from fact_checker.services.decompose import decompose
from fact_checker.services.pipeline import run_check
from fact_checker.store import create_run, get_run, init_store, update_run
from fact_checker.tracing import Tracer, TracingClient


def start_claim(
    db: Path, claim: str, decompose_client: LLMClient, settings: Settings
) -> tuple[str, list[Statement]]:
    """Create the run store tables if missing, create a run for the claim, decompose it, and return the run id and the proposed statements.

    Records a user span "claim" and an llm span "decompose", stores the proposed statements and leaves the
    status proposed. If decomposition fails the run is marked failed with the error, and the error is raised.
    """
    init_store(db)
    run_id = create_run(db, claim)
    tracer = Tracer(db, run_id)
    tracer.record("user", "claim", {"claim": claim}, None)
    client = TracingClient(decompose_client, tracer, "decompose")
    try:
        proposed, _ = decompose(claim, client, settings.decompose_model, settings.decompose_effort)
    except LLMError as error:
        update_run(db, run_id, status="failed", error=str(error))
        raise
    update_run(db, run_id, proposed=proposed, status="proposed")
    return run_id, proposed


def confirm_claim(
    db: Path, run_id: str, edits: list[Edit], check_client: LLMClient, settings: Settings
) -> ConfirmedStatements | list[Issue]:
    """Apply the user's edits to the run's proposed statements and check the edited ones.

    Records a user span "edits" and an llm span "falsifiability" per checked statement. Returns the
    confirmed statements, stored with status confirmed, or the issues when a statement is not falsifiable
    (the run stays proposed). Raises KeyError for an unknown run and ValueError for an edit naming an unknown
    statement or a run that has no proposed statements.
    """
    run = get_run(db, run_id)
    if run is None:
        raise KeyError(run_id)
    if run.proposed is None:
        raise ValueError(f"run {run_id} has no proposed statements")
    tracer = Tracer(db, run_id)
    tracer.record("user", "edits", {"edits": [e.model_dump() for e in edits]}, None)
    proposed = [Statement.model_validate(s) for s in run.proposed]
    confirmed = apply_edits(run.claim, proposed, edits)
    client = TracingClient(check_client, tracer, "falsifiability")
    checked, issues, _ = check_statements(confirmed, client, settings.decompose_model, settings.decompose_effort)
    if issues:
        return issues
    update_run(db, run_id, confirmed=checked, status="confirmed")
    return checked


def verify_claim(
    db: Path, run_id: str, verify_client: LLMClient, review_client: LLMClient, settings: Settings
) -> None:
    """Run the check of the run's confirmed statements and store the outcome.

    The status is verifying while it runs, then done with the CheckResult stored as the run's result, or
    failed with the error text when the check raises an LLMError, ValueError, OSError or sqlite3.Error; nothing is re-raised, so this is safe as a background
    task. Raises KeyError for an unknown run and ValueError for a run that is not confirmed.
    """
    run = get_run(db, run_id)
    if run is None:
        raise KeyError(run_id)
    if run.confirmed is None:
        raise ValueError(f"run {run_id} has no confirmed statements")
    update_run(db, run_id, status="verifying", error=None)
    try:
        result = run_check(
            ConfirmedStatements.model_validate(run.confirmed),
            db,
            verify_client,
            review_client,
            settings,
            Tracer(db, run_id),
        )
    except (LLMError, ValueError, OSError, sqlite3.Error) as error:
        update_run(db, run_id, status="failed", error=str(error))
        return
    update_run(db, run_id, result=result.model_dump(mode="json"), status="done")
