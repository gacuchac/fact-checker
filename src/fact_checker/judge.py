"""The judge: Sol scores a final answer through codex_review.py."""

import json
import os
import re
import subprocess
import time
from pathlib import Path

from pydantic import ValidationError

from fact_checker.contracts import FinalAnswer, JudgeScores

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CODEX_REVIEW = "~/Developing/scripts/codex_review.py"
DEFAULT_MODEL = "gpt-6-sol"
CONTEXT_FILES = ("final.json", "transcript.md", "trace.jsonl", "checks.json")
ATTENTION_DIMENSIONS = ("statement_verdicts", "overreach", "evidence_relevance")
ATTENTION_MAX_SCORE = 2
HEADER = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)
FENCE = re.compile(r"\A```[a-z]*\n(.*?)\n?```\s*\Z", re.DOTALL)


def _strip(text: str) -> str:
    body = HEADER.sub("", text, count=1).strip()
    fenced = FENCE.match(body)
    return fenced.group(1) if fenced else body


def _needs_attention(scores: JudgeScores) -> bool:
    low = any(getattr(scores.dimensions, name).score <= ATTENTION_MAX_SCORE for name in ATTENTION_DIMENSIONS)
    return bool(scores.flagged) or low


def _as_scores_data(text: str) -> dict[str, object]:
    data = json.loads(_strip(text))
    if not isinstance(data, dict):
        raise TypeError("judge output is not a JSON object")
    if "dimensions" not in data:
        flagged = data.pop("flagged", [])
        data = {"dimensions": data, "flagged": flagged}
    return data


def parse_scores(text: str, model: str, seconds: float, statement_ids: set[int]) -> JudgeScores:
    """Parse Sol's output into JudgeScores.

    Strips a leading `<!-- ... -->` header and a Markdown code fence, then validates six dimensions scored
    1-5 and flags naming a known dimension and a statement id in statement_ids. Sets model and seconds, and
    needs_attention (a non-empty flagged, or a score of 2 or less on statement_verdicts, overreach or
    evidence_relevance). Raises ValueError on any invalid output.
    """
    try:
        data = _as_scores_data(text)
        shaped = JudgeScores.model_validate({**data, "model": model, "seconds": seconds, "needs_attention": False})
        unknown = [f.statement_id for f in shaped.flagged if f.statement_id not in statement_ids]
        if unknown:
            raise ValueError(f"flag for unknown statement id: {unknown}")
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise ValueError(f"invalid judge output: {exc}") from exc
    return shaped.model_copy(update={"needs_attention": _needs_attention(shaped)})


def judge(final: FinalAnswer, run: Path) -> JudgeScores:
    """Score a final answer with Sol through codex_review.py and return JudgeScores.

    Runs codex_review.py (env FC_CODEX_REVIEW overrides its path) with the model from env FC_JUDGE_MODEL
    (default gpt-6-sol), cwd = the project root, and the run's final.json, transcript.md, trace.jsonl and
    checks.json as context. Raises ValueError on a non-zero exit or invalid output.
    """
    script = Path(os.environ.get("FC_CODEX_REVIEW", DEFAULT_CODEX_REVIEW)).expanduser()
    model = os.environ.get("FC_JUDGE_MODEL", DEFAULT_MODEL)
    cmd = ["python3", str(script), "judge", "--model", model, "--run-dir", str(run)]
    for name in CONTEXT_FILES:
        cmd += ["--context-file", str(run / name)]
    started = time.monotonic()
    done = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    seconds = time.monotonic() - started
    if done.returncode != 0:
        raise ValueError(f"codex_review.py exited {done.returncode}: {done.stderr.strip()}")
    return parse_scores(done.stdout, model, seconds, {s.id for s in final.statements})
