"""Ground the model's verdicts against re-retrieved passages and aggregate the overall verdict."""

from pathlib import Path
from typing import Literal

from fact_checker.contracts import (
    ConfirmedStatements,
    Counts,
    Evidence,
    FinalAnswer,
    FinalEvidence,
    FinalStatement,
    Hit,
    Overall,
    RetrievalResult,
    Statement,
    StatementVerdict,
    Verdict,
    Verdicts,
)
from fact_checker.quotes import check_quote
from fact_checker.retrieve import _meta_passage, retrieve

DowngradeReason = Literal["quote_failed", "no_hits", "conflict"]
Grounded = tuple[Verdict, DowngradeReason | None, list[tuple[Evidence, Hit]], list[Evidence]]


def rerun_queries(sv: StatementVerdict, db: Path) -> list[RetrievalResult]:
    """Return one retrieval per query of the statement verdict, in order, with the default k and per_doc."""
    return [retrieve(db, query) for query in sv.queries]


def statement_hits(results: list[RetrievalResult]) -> list[Hit]:
    """Return the union of the hits in query order, de-duplicated by passage_id, first occurrence kept."""
    seen: dict[str, Hit] = {}
    for result in results:
        for hit in result.hits:
            seen.setdefault(hit.passage_id, hit)
    return list(seen.values())


def _split_quotes(sv: StatementVerdict, hits: list[Hit]) -> tuple[list[tuple[Evidence, Hit]], list[Evidence]]:
    kept: list[tuple[Evidence, Hit]] = []
    dropped: list[Evidence] = []
    for evidence in sv.evidence:
        match = next((hit for hit in hits if check_quote(evidence.quote, hit.text)), None)
        if match is None:
            dropped.append(evidence)
        else:
            kept.append((evidence, match))
    return kept, dropped


def _is_conflict(kept: list[tuple[Evidence, Hit]]) -> bool:
    supporting = {hit.doc_id for evidence, hit in kept if evidence.stance == "supports"}
    contradicting = {hit.doc_id for evidence, hit in kept if evidence.stance == "contradicts"}
    return any(a != b for a in supporting for b in contradicting)


def ground_statement(statement: Statement, sv: StatementVerdict, hits: list[Hit]) -> Grounded:
    """Return (verdict, downgrade_reason, kept, dropped) for one statement.

    A quote is kept only if it matches one of the statement's own hits. No hits gives unknown/no_hits,
    support and contradiction from different papers give unknown/conflict, and a supported or contradicted
    verdict without a kept quote of that stance gives unknown/quote_failed. Code never upgrades a verdict.
    """
    kept, dropped = _split_quotes(sv, hits)
    if not hits:
        return "unknown", "no_hits", kept, dropped
    if _is_conflict(kept):
        return "unknown", "conflict", kept, dropped
    needed = {"supported": "supports", "contradicted": "contradicts"}.get(sv.verdict)
    if needed and not any(evidence.stance == needed for evidence, _ in kept):
        return "unknown", "quote_failed", kept, dropped
    return sv.verdict, None, kept, dropped


def aggregate(statements: list[FinalStatement]) -> Overall:
    """Return the overall verdict over the load-bearing statements, by the first aggregation rule 0 to 4 that fires."""
    load_bearing = [s for s in statements if s.load_bearing]
    if not load_bearing:
        return Overall(verdict="unknown", rule=0)
    if any(s.downgrade_reason == "conflict" for s in load_bearing):
        return Overall(verdict="unknown", rule=1)
    if any(s.verdict == "contradicted" for s in load_bearing):
        return Overall(verdict="contradicted", rule=2)
    if any(s.verdict == "unknown" for s in load_bearing):
        return Overall(verdict="unknown", rule=3)
    return Overall(verdict="supported", rule=4)


def _final_statement(
    statement: Statement, sv: StatementVerdict, results: list[RetrievalResult], db: Path
) -> FinalStatement:
    hits = statement_hits(results)
    verdict, reason, kept, dropped = ground_statement(statement, sv, hits)
    evidence = []
    for item, hit in kept:
        authors, published = _meta_passage(db, hit.doc_id)
        evidence.append(
            FinalEvidence(
                doc_id=hit.doc_id,
                title=hit.title,
                authors=authors,
                published=published,
                quote=item.quote,
                stance=item.stance,
            )
        )
    return FinalStatement(
        id=statement.id,
        text=statement.text,
        load_bearing=statement.load_bearing,
        mark=statement.mark,
        model_verdict=sv.verdict,
        verdict=verdict,
        downgrade_reason=reason,
        evidence=evidence,
        dropped_quotes=dropped,
    )


def _finalize_with_results(
    confirmed: ConfirmedStatements, verdicts: Verdicts, db: Path
) -> tuple[FinalAnswer, dict[int, list[RetrievalResult]]]:
    """Return the final answer and, by statement id, the retrievals it was grounded on (one pass per query).

    Raises ValueError if the verdict ids differ from the confirmed ids and FileNotFoundError if db is missing.
    """
    by_id = {sv.id: sv for sv in verdicts.statements}
    if set(by_id) != {s.id for s in confirmed.statements}:
        raise ValueError("verdict ids must equal confirmed ids")
    results = {s.id: rerun_queries(by_id[s.id], db) for s in confirmed.statements}
    statements = [_final_statement(s, by_id[s.id], results[s.id], db) for s in confirmed.statements]
    marks = [s.mark for s in confirmed.statements]
    counts = Counts(
        confirmed=marks.count("confirmed"),
        user_edited=marks.count("user_edited"),
        user_added=marks.count("user_added"),
        dropped=sum(1 for e in confirmed.edits if e.op == "drop"),
    )
    final = FinalAnswer(claim=confirmed.claim, overall=aggregate(statements), statements=statements, counts=counts)
    return final, results


def finalize(confirmed: ConfirmedStatements, verdicts: Verdicts, db: Path) -> FinalAnswer:
    """Return the checked answer: each statement grounded against its own re-retrieved passages, then aggregated.

    Raises ValueError if the verdict ids differ from the confirmed ids and FileNotFoundError if db is missing.
    """
    return _finalize_with_results(confirmed, verdicts, db)[0]
