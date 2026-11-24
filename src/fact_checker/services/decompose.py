"""Decomposition of a claim into statements."""

from fact_checker.contracts import Statement
from fact_checker.llm.base import LLMClient, LLMError, Usage
from fact_checker.services.loader import load_prompt
from fact_checker.services.schemas import DecomposedStatement, DecomposeOutput

MAX_STATEMENTS = 5


def _span_checked(proposed: list[DecomposedStatement], claim: str) -> list[DecomposedStatement]:
    first = proposed[0]
    if first.implied_by not in claim:
        first = first.model_copy(update={"implied_by": claim})
    return [first, *(s for s in proposed[1:] if s.implied_by in claim)]


def decompose(claim: str, client: LLMClient, model: str, effort: str | None) -> tuple[list[Statement], Usage]:
    """Return the claim's statements (ids 0..n-1, mark "confirmed", at most 5) and the call's usage.

    A statement whose implied_by is not a verbatim span of the claim is dropped, except statement 0, whose
    implied_by becomes the whole claim; statement 0 is always load-bearing. Raises LLMError when the model returns no statement.
    """
    output, usage = client.complete(load_prompt("decompose"), f"<claim>{claim}</claim>", DecomposeOutput, model, effort)
    if not output.statements:
        raise LLMError("decomposition returned no statements")
    kept = _span_checked(output.statements, claim)[:MAX_STATEMENTS]
    statements = [
        Statement(
            id=i,
            text=s.text,
            load_bearing=s.load_bearing or i == 0,
            implied_by=s.implied_by,
            query=s.query,
            kind=s.kind,
            mark="confirmed",
        )
        for i, s in enumerate(kept)
    ]
    return statements, usage
