"""The revision of the verdicts after a review that needs attention."""

import json
from collections.abc import Mapping

from fact_checker.contracts import (
    ConfirmedStatements,
    FinalAnswer,
    JudgeScores,
    RetrievalResult,
    Verdicts,
)
from fact_checker.finalize import statement_hits
from fact_checker.llm.base import LLMClient, Usage
from fact_checker.services.loader import load_prompt
from fact_checker.services.schemas import VerdictsOutput
from fact_checker.services.verify import statement_block, verdicts_from_output


def _review_block(scores: JudgeScores) -> str:
    dimensions = {name: score.model_dump() for name, score in scores.dimensions}
    flagged = [flag.model_dump() for flag in scores.flagged]
    return (
        "<review>\n"
        f"<dimensions>{json.dumps(dimensions, indent=2)}</dimensions>\n"
        f"<flagged>{json.dumps(flagged, indent=2)}</flagged>\n"
        "</review>"
    )


def revise(
    confirmed: ConfirmedStatements,
    verdicts: Verdicts,
    final: FinalAnswer,
    results: Mapping[int, list[RetrievalResult]],
    scores: JudgeScores,
    client: LLMClient,
    model: str,
    effort: str | None,
) -> tuple[Verdicts, Usage]:
    """Return new verdicts for every confirmed statement, and the usage of the one model call.

    The model sees each statement with the passages it was grounded on, its previous verdicts and the
    reviewer's dimension scores, evidence and flags. Each verdict's queries stay those of the previous
    verdicts, set by code. Raises LLMError if the call fails or the verdict ids differ from the confirmed ids.
    """
    blocks = "\n\n".join(statement_block(s, statement_hits(results[s.id])) for s in confirmed.statements)
    previous = f"<previous_verdicts>\n{verdicts.model_dump_json(indent=2)}\n</previous_verdicts>"
    overall = f'<previous_overall verdict="{final.overall.verdict}" rule="{final.overall.rule}" />'
    user = "\n\n".join([blocks, previous, overall, _review_block(scores)])
    output, usage = client.complete(load_prompt("revise"), user, VerdictsOutput, model, effort)
    queries = {sv.id: sv.queries for sv in verdicts.statements}
    return verdicts_from_output(output, queries), usage
