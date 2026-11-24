"""Verdicts for the confirmed statements: code-driven retrieval, then one batched model call."""

from pathlib import Path

from pydantic import ValidationError

from fact_checker.contracts import (
    ConfirmedStatements,
    Hit,
    RetrievalResult,
    Statement,
    Verdicts,
)
from fact_checker.llm.base import LLMClient, LLMError, Usage
from fact_checker.retrieve import retrieve
from fact_checker.services.loader import load_prompt
from fact_checker.services.schemas import VerdictsOutput
from fact_checker.tracing import Tracer

K = 5
PER_DOC = 2


def statement_block(statement: Statement, hits: list[Hit]) -> str:
    """Return the prompt text for one statement followed by its own passages."""
    flag = str(statement.load_bearing).lower()
    lines = [f'<statement id="{statement.id}" load_bearing="{flag}">{statement.text}</statement>']
    lines.append(f'<passages statement="{statement.id}">')
    lines += [f'<passage id="{h.passage_id}" doc_id="{h.doc_id}" title="{h.title}">{h.text}</passage>' for h in hits]
    lines.append("</passages>")
    return "\n".join(lines)


def verdicts_from_output(output: VerdictsOutput, queries: dict[int, list[str]]) -> Verdicts:
    """Return the model's verdicts with the queries code ran set on each; ids must equal queries' keys.

    Raises LLMError when the verdict ids differ from the statement ids.
    """
    payload = {
        "statements": [{**item.model_dump(), "queries": queries.get(item.id, [""])} for item in output.statements]
    }
    try:
        return Verdicts.model_validate(payload, context={"confirmed_ids": list(queries)})
    except ValidationError as error:
        raise LLMError(f"verdicts do not match the confirmed statements: {error}") from error


def _retrieve(db: Path, query: str, tracer: Tracer | None) -> RetrievalResult:
    if tracer is None:
        return retrieve(db, query, k=K, per_doc=PER_DOC)
    with tracer.span("tool", "retrieve", {"query": query, "k": K, "per_doc": PER_DOC}) as handle:
        result = retrieve(db, query, k=K, per_doc=PER_DOC)
        handle.output = {"hits": [hit.model_dump() for hit in result.hits]}
    return result


def verify(
    confirmed: ConfirmedStatements,
    db: Path,
    client: LLMClient,
    model: str,
    effort: str | None,
    tracer: Tracer | None = None,
) -> tuple[Verdicts, Usage]:
    """Return the verdicts for every confirmed statement and the usage of the one model call.

    Code retrieves k=5 passages (at most 2 per paper) for "<text> <query>" of each statement; the model sees
    each statement with its own passages. Each verdict's queries is that retrieval query, set by code.
    With a tracer, each retrieval is recorded as a tool span with its query, k, per_doc and hits.
    Raises LLMError if the call fails or the verdict ids differ from the confirmed ids, and
    FileNotFoundError if db is missing.
    """
    queries = {s.id: f"{s.text} {s.query}" for s in confirmed.statements}
    results = {s.id: _retrieve(db, queries[s.id], tracer) for s in confirmed.statements}
    user = "\n\n".join(statement_block(s, results[s.id].hits) for s in confirmed.statements)
    output, usage = client.complete(load_prompt("verify"), user, VerdictsOutput, model, effort)
    verdicts = verdicts_from_output(output, {i: [q] for i, q in queries.items()})
    return verdicts, usage
