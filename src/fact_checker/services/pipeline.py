"""The check of one confirmed claim: verify, ground, review, and one revision round when the review asks."""

import hashlib
import time
from pathlib import Path

from pydantic import BaseModel

from fact_checker.contracts import (
    ConfirmedStatements,
    FinalAnswer,
    Flag,
    JudgeScores,
    RetrievalResult,
    Verdicts,
)
from fact_checker.finalize import _finalize_with_results
from fact_checker.llm.base import LLMClient, LLMError, Usage
from fact_checker.llm.config import Settings
from fact_checker.report import render_answer
from fact_checker.services.consistency import one_sided_unknowns
from fact_checker.services.review import review
from fact_checker.services.revise import revise
from fact_checker.services.verify import verify
from fact_checker.tracing import Tracer, TracingClient

Results = dict[int, list[RetrievalResult]]


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
    """The outcome of a check.

    verdicts, final and scores are the last round's; scores is None when the last review failed, with
    review_error saying why. first_final is the answer before any revision (equal to final when revised is
    False) and first_scores the review of it (None when not revised). consistency_flags are the code checks of
    the first answer (one_sided_unknowns). final_message is the rendered answer.
    """

    verdicts: Verdicts
    final: FinalAnswer
    scores: JudgeScores | None
    review_error: str | None
    events: list[Event]
    first_final: FinalAnswer
    first_scores: JudgeScores | None
    revised: bool
    final_message: str
    consistency_flags: list[Flag] = []


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


def _doc_ids(results: Results) -> list[str]:
    ids = (hit.doc_id for per_statement in results.values() for result in per_statement for hit in result.hits)
    return list(dict.fromkeys(ids))


def _traced(client: LLMClient, tracer: Tracer | None, name: str) -> LLMClient:
    return client if tracer is None else TracingClient(client, tracer, name)


def _kept_and_dropped(final: FinalAnswer) -> dict:
    return {
        "overall": final.overall.model_dump(),
        "statements": [
            {
                "id": s.id,
                "model_verdict": s.model_verdict,
                "verdict": s.verdict,
                "downgrade_reason": s.downgrade_reason,
                "kept_quotes": [e.model_dump() for e in s.evidence],
                "dropped_quotes": [e.model_dump() for e in s.dropped_quotes],
            }
            for s in final.statements
        ],
    }


def _record_retrievals(tracer: Tracer, parent_id: str, results: Results) -> None:
    for per_statement in results.values():
        for result in per_statement:
            tracer.record(
                "tool",
                "retrieve",
                {"query": result.query, "k": result.k, "per_doc": result.per_doc},
                {"hits": [hit.model_dump() for hit in result.hits]},
                parent_id=parent_id,
            )


def _ground(
    confirmed: ConfirmedStatements, verdicts: Verdicts, db: Path, tracer: Tracer | None
) -> tuple[FinalAnswer, Results, Event]:
    started = time.monotonic()
    if tracer is None:
        final, results = _finalize_with_results(confirmed, verdicts, db)
    else:
        with tracer.span("code", "finalize", {"verdicts": verdicts.model_dump()}) as handle:
            final, results = _finalize_with_results(confirmed, verdicts, db)
            handle.output = _kept_and_dropped(final)
            _record_retrievals(tracer, handle.id, results)
    sha = hashlib.sha256(final.model_dump_json().encode()).hexdigest()
    event = Event(
        step="finalize", ok=True, seconds=time.monotonic() - started, doc_ids=_doc_ids(results), final_sha256=sha
    )
    return final, results, event


def _review(
    confirmed: ConfirmedStatements,
    verdicts: Verdicts,
    final: FinalAnswer,
    results: Results,
    client: LLMClient,
    model: str,
    sha: str | None,
) -> tuple[JudgeScores | None, str | None, Event]:
    started = time.monotonic()
    try:
        scores, usage = review(confirmed, verdicts, final, results, client, model)
    except LLMError as error:
        failed = Event(step="review", ok=False, seconds=time.monotonic() - started, model=model, final_sha256=sha)
        return None, str(error), failed
    return scores, None, _llm_event("review", usage, sha)


def _changed(first: FinalAnswer, second: FinalAnswer) -> int:
    before = {s.id: s for s in first.statements}
    return sum(1 for s in second.statements if before.get(s.id) != s)


def _message(final: FinalAnswer, scores: JudgeScores | None, first: FinalAnswer, trigger: str | None) -> str:
    answer = render_answer(final, scores)
    if trigger is None:
        return answer
    return f"Revised after {trigger}: {_changed(first, final)} statement(s) changed.\n{answer}"


def _consistency(final: FinalAnswer, tracer: Tracer | None) -> list[Flag]:
    flags = one_sided_unknowns(final)
    if tracer is not None:
        tracer.record("code", "consistency", {"check": "one_sided_unknowns"}, {"flags": [f.model_dump() for f in flags]})
    return flags


def run_check(
    confirmed: ConfirmedStatements,
    db: Path,
    verify_client: LLMClient,
    review_client: LLMClient,
    settings: Settings,
    tracer: Tracer | None = None,
) -> CheckResult:
    """Verify the confirmed statements, ground them once, review, and revise once if the review or code asks.

    After grounding, code flags each statement left unknown although all its kept quotes take one stance
    (one_sided_unknowns). A review that needs attention, or any such flag, gives one revision round with the
    reviewer's flags plus the code flags: revise, ground again, review again. A failing
    review gives scores None and review_error and skips revision; a failing revision keeps the first answer
    (revised False) and records a failed revise event. Returns the last round's answer with both rounds'
    finals, the step events and the final message rendered by code. The clients are raw: with a tracer, each
    call is recorded as an llm span named verify, review or revise, the retrievals as tool spans, each
    grounding and the consistency check as code spans and the final message as a system span. Raises LLMError if verification fails,
    and FileNotFoundError if db is missing.
    """
    verifier = _traced(verify_client, tracer, "verify")
    reviewer = _traced(review_client, tracer, "review")
    verdicts, usage = verify(confirmed, db, verifier, settings.verify_model, settings.verify_effort, tracer)
    events = [_llm_event("verify", usage)]
    final, results, event = _ground(confirmed, verdicts, db, tracer)
    events.append(event)
    flags = _consistency(final, tracer)
    scores, error, event = _review(
        confirmed, verdicts, final, results, reviewer, settings.review_model, event.final_sha256
    )
    events.append(event)
    first_final, first_scores, revised, trigger = final, None, False, None
    if scores is not None and (scores.needs_attention or flags):
        reviser = _traced(verify_client, tracer, "revise")
        started = time.monotonic()
        try:
            asked = scores.model_copy(update={"flagged": [*scores.flagged, *flags]})
            new_verdicts, usage = revise(
                confirmed, verdicts, final, results, asked, reviser, settings.verify_model, settings.verify_effort
            )
        except LLMError:
            events.append(Event(step="revise", ok=False, seconds=time.monotonic() - started, model=settings.verify_model))
        else:
            events.append(_llm_event("revise", usage))
            trigger = "review" if scores.needs_attention else "the code consistency check"
            first_scores, revised, verdicts = scores, True, new_verdicts
            final, results, event = _ground(confirmed, verdicts, db, tracer)
            events.append(event)
            scores, error, event = _review(
                confirmed, verdicts, final, results, reviewer, settings.review_model, event.final_sha256
            )
            events.append(event)
    message = _message(final, scores, first_final, trigger)
    if tracer is not None:
        tracer.record("system", "final_message", {"revised": revised}, {"message": message})
    return CheckResult(
        verdicts=verdicts,
        final=final,
        scores=scores,
        review_error=error,
        events=events,
        first_final=first_final,
        first_scores=first_scores,
        revised=revised,
        final_message=message,
        consistency_flags=flags,
    )
