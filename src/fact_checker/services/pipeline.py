"""The check of one confirmed claim: verify, ground, then review."""

import hashlib
import time
from pathlib import Path

from pydantic import BaseModel

from fact_checker.contracts import (
    ConfirmedStatements,
    FinalAnswer,
    JudgeScores,
    RetrievalResult,
    Verdicts,
)
from fact_checker.finalize import _finalize_with_results
from fact_checker.llm.base import LLMClient, LLMError, Usage
from fact_checker.llm.config import Settings
from fact_checker.services.review import review
from fact_checker.services.verify import verify


class Event(BaseModel):
    """One step of a check: how it went and what it cost."""

    step: str
    ok: bool
    seconds: float
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    doc_ids: list[str] = []
    final_sha256: str | None = None


class CheckResult(BaseModel):
    """The outcome of a check; scores is None when the review failed, with review_error saying why."""

    verdicts: Verdicts
    final: FinalAnswer
    scores: JudgeScores | None
    review_error: str | None
    events: list[Event]


def _llm_event(step: str, usage: Usage, final_sha256: str | None = None) -> Event:
    return Event(
        step=step,
        ok=True,
        seconds=usage.seconds,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        final_sha256=final_sha256,
    )


def _doc_ids(results: dict[int, list[RetrievalResult]]) -> list[str]:
    ids = (hit.doc_id for per_statement in results.values() for result in per_statement for hit in result.hits)
    return list(dict.fromkeys(ids))


def run_check(
    confirmed: ConfirmedStatements, db: Path, verify_client: LLMClient, review_client: LLMClient, settings: Settings
) -> CheckResult:
    """Verify the confirmed statements, ground the verdicts once, then review; return all with step events.

    A failing review gives scores None and review_error and never changes the verdicts or the final answer.
    Raises LLMError if verification fails, and FileNotFoundError if db is missing.
    """
    verdicts, usage = verify(confirmed, db, verify_client, settings.verify_model, settings.verify_effort)
    events = [_llm_event("verify", usage)]
    started = time.monotonic()
    final, results = _finalize_with_results(confirmed, verdicts, db)
    sha = hashlib.sha256(final.model_dump_json().encode()).hexdigest()
    events.append(
        Event(step="finalize", ok=True, seconds=time.monotonic() - started, doc_ids=_doc_ids(results), final_sha256=sha)
    )
    started = time.monotonic()
    try:
        scores, usage = review(confirmed, verdicts, final, results, review_client, settings.review_model)
    except LLMError as error:
        events.append(
            Event(
                step="review",
                ok=False,
                seconds=time.monotonic() - started,
                model=settings.review_model,
                final_sha256=sha,
            )
        )
        return CheckResult(verdicts=verdicts, final=final, scores=None, review_error=str(error), events=events)
    events.append(_llm_event("review", usage, sha))
    return CheckResult(verdicts=verdicts, final=final, scores=scores, review_error=None, events=events)
