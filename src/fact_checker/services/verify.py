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
from fact_checker.finalize import statement_hits
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


def statement_queries(statement: Statement, claim: str) -> list[str]:
    """Return the retrieval queries of one statement: "<text> <query>", then the user's claim.

    The claim is searched too because the user's own wording often matches the abstract's key sentence better
    than the decomposed statement does; it is left out when it equals the first query.
    """
    own = f"{statement.text} {statement.query}"
    return [own] if claim.strip() == own.strip() else [own, claim]


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

    For each statement code retrieves k=5 passages (at most 2 per paper) for each of statement_queries, and
    the model sees each statement with the union of its own passages. Each verdict's queries are those
    retrieval queries, set by code, so finalize re-runs the same searches.
    With a tracer, each retrieval is recorded as a tool span with its query, k, per_doc and hits.
    Raises LLMError if the call fails or the verdict ids differ from the confirmed ids, and
    FileNotFoundError if db is missing.
    """
    queries = {s.id: statement_queries(s, confirmed.claim) for s in confirmed.statements}
    results = {i: [_retrieve(db, q, tracer) for q in qs] for i, qs in queries.items()}
    user = "\n\n".join(statement_block(s, statement_hits(results[s.id])) for s in confirmed.statements)
    output, usage = client.complete(load_prompt("verify"), user, VerdictsOutput, model, effort)
    verdicts = verdicts_from_output(output, queries)
    return verdicts, usage
