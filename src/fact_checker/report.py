"""Pure rendering of the final answer and of the run files."""

import json
from collections.abc import Mapping

from fact_checker.contracts import (
    ConfirmedStatements,
    Dimensions,
    FinalAnswer,
    FinalEvidence,
    FinalStatement,
    JudgeScores,
    RetrievalResult,
    Verdicts,
)


def _byline(evidence: FinalEvidence) -> str:
    first = evidence.authors[0] if evidence.authors else "unknown author"
    et_al = " et al." if len(evidence.authors) > 1 else ""
    return f"{evidence.title} ({evidence.doc_id}, {evidence.published}; {first}{et_al})"


def _statement_lines(s: FinalStatement) -> list[str]:
    reason = f" ({s.downgrade_reason})" if s.downgrade_reason else ""
    weight = "load-bearing" if s.load_bearing else "not load-bearing"
    lines = [f"[{s.id}] {s.verdict}{reason} | {weight} | {s.mark}", f"  {s.text}"]
    if s.model_verdict != s.verdict:
        lines.append(f"  model verdict: {s.model_verdict}")
    lines += [f'  {e.stance}: "{e.quote}" - {_byline(e)}' for e in s.evidence]
    if s.dropped_quotes:
        lines.append(f"  dropped quotes: {len(s.dropped_quotes)}")
    return lines


def _judge_lines(scores: JudgeScores | None) -> list[str]:
    if scores is None:
        return ["Judge: not judged"]
    attention = "yes" if scores.needs_attention else "no"
    lines = [f"Judge ({scores.model}, {scores.seconds:.0f}s): needs attention: {attention}"]
    for name in Dimensions.model_fields:
        dimension = getattr(scores.dimensions, name)
        lines.append(f"  {name} {dimension.score}/5: {dimension.evidence}")
    lines += [f"  flagged [{f.statement_id}] {f.dimension}: {f.reason}" for f in scores.flagged]
    return lines


def render_answer(final: FinalAnswer, scores: JudgeScores | None) -> str:
    """Return the plain-text answer for final and the judge scores (None renders "not judged"), ending in one newline."""
    lines = [f"Claim: {final.claim}", f"Overall: {final.overall.verdict} (rule {final.overall.rule})", ""]
    for statement in final.statements:
        lines += _statement_lines(statement)
    lines += ["", *_judge_lines(scores)]
    return "\n".join(lines) + "\n"


def _trace(verdicts: Verdicts, results: Mapping[int, list[RetrievalResult]]) -> str:
    lines = [
        json.dumps(
            {
                "statement_id": sv.id,
                "query": result.query,
                "passage_ids": [h.passage_id for h in result.hits],
                "doc_ids": [h.doc_id for h in result.hits],
            }
        )
        for sv in verdicts.statements
        for result in results[sv.id]
    ]
    return "".join(line + "\n" for line in lines)


def _checks(verdicts: Verdicts, final: FinalAnswer, results: Mapping[int, list[RetrievalResult]]) -> str:
    final_by_id = {s.id: s for s in final.statements}
    statements = []
    for sv in verdicts.statements:
        grounded = final_by_id[sv.id]
        dropped = [(e.quote, e.stance) for e in grounded.dropped_quotes]
        statements.append(
            {
                "id": sv.id,
                "queries": sv.queries,
                "hit_count": sum(len(r.hits) for r in results[sv.id]),
                "model_verdict": grounded.model_verdict,
                "verdict": grounded.verdict,
                "downgrade_reason": grounded.downgrade_reason,
                "quotes": [
                    {
                        "quote": e.quote,
                        "stance": e.stance,
                        "claimed_passage_id": e.passage_id,
                        "kept": (e.quote, e.stance) not in dropped,
                    }
                    for e in sv.evidence
                ],
            }
        )
    body = {"statements": statements, "overall": final.overall.model_dump(), "counts": final.counts.model_dump()}
    return json.dumps(body, indent=2)


def _transcript(
    confirmed: ConfirmedStatements,
    verdicts: Verdicts,
    final: FinalAnswer,
    results: Mapping[int, list[RetrievalResult]],
    checks: dict,
) -> str:
    reasons = {sv.id: sv.reason for sv in verdicts.statements}
    lines = [f"# Claim\n\n{confirmed.claim}\n"]
    for s in final.statements:
        lines += [f"## [{s.id}] {s.text}\n", "Queries:"]
        lines += [f"- {r.query}" for r in results[s.id]]
        lines.append("\nPassages:")
        lines += [f"- {h.passage_id} ({h.title}): {h.text}" for r in results[s.id] for h in r.hits]
        reason = f" ({s.downgrade_reason})" if s.downgrade_reason else ""
        lines.append(f"\nModel verdict: {s.model_verdict}: {reasons[s.id]}")
        lines += [
            f'- {q["stance"]}: "{q["quote"]}" - {"kept" if q["kept"] else "dropped"}' for q in checks[s.id]["quotes"]
        ]
        lines.append(f"\nFinal verdict: {s.verdict}{reason}\n")
    lines.append(f"## Overall\n\n{final.overall.verdict} (rule {final.overall.rule})")
    return "\n".join(lines) + "\n"


def run_files(
    confirmed: ConfirmedStatements,
    verdicts: Verdicts,
    final: FinalAnswer,
    results: Mapping[int, list[RetrievalResult]],
) -> dict[str, str]:
    """Return the text of trace.jsonl, checks.json and transcript.md, keyed by file name.

    results maps a statement id to its re-retrieved results, one per query.
    """
    checks = _checks(verdicts, final, results)
    by_id = {s["id"]: s for s in json.loads(checks)["statements"]}
    return {
        "trace.jsonl": _trace(verdicts, results),
        "checks.json": checks,
        "transcript.md": _transcript(confirmed, verdicts, final, results, by_id),
    }
