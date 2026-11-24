"""The review of a final answer against the rubric."""

from collections.abc import Mapping
from pathlib import Path

from fact_checker.contracts import (
    ConfirmedStatements,
    FinalAnswer,
    JudgeScores,
    RetrievalResult,
    Verdicts,
)
from fact_checker.judge import parse_scores
from fact_checker.llm.base import LLMClient, LLMError, Usage
from fact_checker.report import run_files
from fact_checker.services.loader import load_prompt
from fact_checker.services.schemas import ReviewOutput

CONTEXT_ORDER = ("transcript.md", "trace.jsonl", "checks.json")


def _transcript(files: Mapping[str, str], final: FinalAnswer) -> str:
    sections = [f"=== {name} ===\n{files[name]}" for name in CONTEXT_ORDER]
    sections.append(f"=== final.json ===\n{final.model_dump_json(indent=2)}")
    return "\n\n".join(sections)


def _rubric(rubric_path: Path | None) -> str:
    return load_prompt("review") if rubric_path is None else rubric_path.read_text(encoding="utf-8")


def review(
    confirmed: ConfirmedStatements,
    verdicts: Verdicts,
    final: FinalAnswer,
    results: Mapping[int, list[RetrievalResult]],
    client: LLMClient,
    model: str,
    rubric_path: Path | None = None,
) -> tuple[JudgeScores, Usage]:
    """Return the judge scores for the final answer and the usage of the one model call.

    The system prompt is the packaged rubric (prompts/review.md, identical to the Codex judge rubric), or the
    file at rubric_path when given; the user message is transcript.md, trace.jsonl,
    checks.json and final.json. The model returns only dimensions and flags: model, seconds and
    needs_attention are set by parse_scores. Raises LLMError if the call fails or a flag names an unknown
    statement id, and FileNotFoundError if the rubric is missing.
    """
    files = run_files(confirmed, verdicts, final, results)
    output, usage = client.complete(
        _rubric(rubric_path), _transcript(files, final), ReviewOutput, model
    )
    try:
        scores = parse_scores(
            output.model_dump_json(),
            model=usage.model,
            seconds=usage.seconds,
            statement_ids={s.id for s in final.statements},
        )
    except ValueError as error:
        raise LLMError(str(error)) from error
    return scores, usage
