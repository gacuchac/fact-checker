"""Verdicts for the confirmed statements: code-driven retrieval, then one batched model call."""

from pathlib import Path

from pydantic import ValidationError

from fact_checker.contracts import (
    ConfirmedStatements,
    RetrievalResult,
    Statement,
    Verdicts,
)
from fact_checker.llm.base import LLMClient, LLMError, Usage
from fact_checker.retrieve import retrieve
from fact_checker.services.loader import load_prompt
from fact_checker.services.schemas import VerdictsOutput

K = 5
PER_DOC = 2


def _block(statement: Statement, result: RetrievalResult) -> str:
    flag = str(statement.load_bearing).lower()
    lines = [f'<statement id="{statement.id}" load_bearing="{flag}">{statement.text}</statement>']
    lines.append(f'<passages statement="{statement.id}">')
    lines += [
        f'<passage id="{h.passage_id}" doc_id="{h.doc_id}" title="{h.title}">{h.text}</passage>' for h in result.hits
    ]
    lines.append("</passages>")
    return "\n".join(lines)


def verify(
    confirmed: ConfirmedStatements, db: Path, client: LLMClient, model: str, effort: str | None
) -> tuple[Verdicts, Usage]:
    """Return the verdicts for every confirmed statement and the usage of the one model call.

    Code retrieves k=5 passages (at most 2 per paper) for "<text> <query>" of each statement; the model sees
    each statement with its own passages. Each verdict's queries is that retrieval query, set by code.
    Raises LLMError if the call fails or the verdict ids differ from the confirmed ids, and
    FileNotFoundError if db is missing.
    """
    queries = {s.id: f"{s.text} {s.query}" for s in confirmed.statements}
    results = {s.id: retrieve(db, queries[s.id], k=K, per_doc=PER_DOC) for s in confirmed.statements}
    user = "\n\n".join(_block(s, results[s.id]) for s in confirmed.statements)
    output, usage = client.complete(load_prompt("verify"), user, VerdictsOutput, model, effort)
    payload = {
        "statements": [{**item.model_dump(), "queries": [queries.get(item.id, "")]} for item in output.statements]
    }
    try:
        verdicts = Verdicts.model_validate(payload, context={"confirmed_ids": list(queries)})
    except ValidationError as error:
        raise LLMError(f"verdicts do not match the confirmed statements: {error}") from error
    return verdicts, usage
