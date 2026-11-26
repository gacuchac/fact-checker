"""The /api routes: claim sessions, runs and traces, and the abstracts."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fact_checker.contracts import Edit
from fact_checker.docs import Doc, DocSummary, get_doc, search_docs
from fact_checker.eval_cases import EvalCaseView, load_case_views
from fact_checker.llm.base import LLMError
from fact_checker.services.session import confirm_claim, start_claim, verify_claim
from fact_checker.store import (
    RunSummary,
    Span,
    count_runs_since,
    get_run,
    list_runs,
    list_spans,
    transition_status,
)

from .security import limit_posts, require_access_code

MAX_CLAIM_CHARS = 500
MAX_CONFIRM_ROUNDS = 3


class ClaimRequest(BaseModel):
    """The claim to check."""

    claim: str = Field(min_length=1, max_length=MAX_CLAIM_CHARS)


class ConfirmRequest(BaseModel):
    """The user's edits to the proposed statements."""

    edits: list[Edit]


class Trace(BaseModel):
    """The spans of one run in order."""

    run_id: str
    spans: list[Span]


def count_docs(db: Path) -> int:
    """Return how many papers the docs table of db holds; 0 when the table is missing."""
    with sqlite3.connect(db) as con:
        try:
            (count,) = con.execute("SELECT COUNT(*) FROM docs").fetchone()
        except sqlite3.OperationalError:
            return 0
    return count


def _start_of_today() -> str:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _run_or_404(request: Request, run_id: str):
    run = get_run(request.app.state.db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


def _require_status(status: str, expected: str) -> None:
    if status != expected:
        raise HTTPException(status_code=409, detail=f"run is {status}, not {expected}")


health_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_access_code), Depends(limit_posts)])


@health_router.get("/api/health")
def health(request: Request) -> dict:
    """Return {"ok": true, "docs": n} with the number of papers in the database; needs no access code."""
    return {"ok": True, "docs": count_docs(request.app.state.db)}


@router.post("/api/claims", status_code=201)
def post_claim(body: ClaimRequest, request: Request) -> dict:
    """Create a run for the claim and return its id, the claim and the proposed statements.

    429 when today's claims are at the daily cap; 502 if the model call fails.
    """
    state = request.app.state
    if count_runs_since(state.db, _start_of_today()) >= state.settings.daily_run_cap:
        raise HTTPException(status_code=429, detail="daily claim cap reached, try again tomorrow")
    try:
        run_id, proposed = start_claim(state.db, body.claim, state.clients.decompose, state.settings)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"run_id": run_id, "claim": body.claim, "proposed": [s.model_dump() for s in proposed]}


def _check_edit_lengths(edits: list[Edit]) -> None:
    if any(len(e.value or "") > MAX_CLAIM_CHARS for e in edits):
        raise HTTPException(status_code=422, detail=f"statement text must be at most {MAX_CLAIM_CHARS} characters")


def _confirm_rounds(db: Path, run_id: str) -> int:
    return sum(1 for s in list_spans(db, run_id) if (s.kind, s.name) == ("user", "edits"))


@router.post("/api/claims/{run_id}/confirm")
def post_confirm(run_id: str, body: ConfirmRequest, request: Request):
    """Apply the edits and confirm the statements.

    200 {"confirmed"}; 422 {"issues"} or {"detail"} (also a statement over 500 characters); 409 unless proposed
    or after 3 confirm rounds; 404; 502.
    """
    state = request.app.state
    _require_status(_run_or_404(request, run_id).status, "proposed")
    _check_edit_lengths(body.edits)
    if _confirm_rounds(state.db, run_id) >= MAX_CONFIRM_ROUNDS:
        raise HTTPException(status_code=409, detail="too many confirm rounds, start a new claim")
    try:
        outcome = confirm_claim(state.db, run_id, body.edits, state.clients.check, state.settings)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if isinstance(outcome, list):
        return JSONResponse({"issues": [i.model_dump() for i in outcome]}, status_code=422)
    return {"confirmed": outcome.model_dump()}


@router.post("/api/claims/{run_id}/verify", status_code=202)
def post_verify(run_id: str, request: Request, background: BackgroundTasks) -> dict:
    """Start the check of a confirmed run in the background: 202, 409 unless confirmed, 404."""
    state = request.app.state
    _require_status(_run_or_404(request, run_id).status, "confirmed")
    if not transition_status(state.db, run_id, "confirmed", "verifying"):
        raise HTTPException(status_code=409, detail="run is already being verified")
    background.add_task(
        verify_claim, state.db, run_id, state.clients.verify, state.clients.review, state.settings
    )
    return {"run_id": run_id, "status": "verifying"}


@router.get("/api/claims/{run_id}")
def get_claim(run_id: str, request: Request) -> dict:
    """Return the run's status, statements, result and error; 404 for an unknown run."""
    run = _run_or_404(request, run_id)
    return {
        "run_id": run.id,
        "claim": run.claim,
        "status": run.status,
        "proposed": run.proposed,
        "confirmed": run.confirmed,
        "result": run.result,
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


@router.get("/api/runs")
def get_runs(request: Request, limit: int = 50) -> list[RunSummary]:
    """Return the newest runs, newest first."""
    return list_runs(request.app.state.db, limit)


@router.get("/api/runs/{run_id}/trace")
def get_trace(run_id: str, request: Request) -> Trace:
    """Return the run's spans ordered by seq; 404 for an unknown run."""
    _run_or_404(request, run_id)
    return Trace(run_id=run_id, spans=list_spans(request.app.state.db, run_id))


@router.get("/api/docs")
def get_docs(request: Request, q: str = "", limit: int = 20) -> list[DocSummary]:
    """Search the papers; an empty query lists the newest."""
    return search_docs(request.app.state.db, q, limit)


@router.get("/api/docs/{doc_id}")
def get_doc_detail(doc_id: str, request: Request) -> Doc:
    """Return one paper; 404 when there is none."""
    doc = get_doc(request.app.state.db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="doc not found")
    return doc


@router.get("/api/evals")
def get_evals(request: Request) -> list[EvalCaseView]:
    """Return every eval case file in the configured folder as an EvalCaseView, malformed ones with `error` set."""
    return load_case_views(request.app.state.evals)
