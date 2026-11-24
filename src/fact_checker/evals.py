"""Seed eval cases: conversion to confirmed statements and code-only scoring of finished runs."""

from dataclasses import dataclass

from fact_checker.contracts import ConfirmedStatements, FinalAnswer, Statement


@dataclass(frozen=True)
class CaseRow:
    """The outcome of one case: its overall verdict against the label and its statement hits."""

    id: str
    label: str
    overall: str | None
    statements_correct: int
    statements_total: int


@dataclass(frozen=True)
class EvalReport:
    """Accuracy, statement accuracy, quote pass rate and gold-doc recall over a set of cases."""

    accuracy: float
    statement_accuracy: float
    quote_pass_rate: float
    doc_recall: float
    rows: list[CaseRow]


def case_to_confirmed(case: dict) -> ConfirmedStatements:
    """Build the confirmed statements (source "case", all marked confirmed) of a statements-mode case.

    A statement's implied_by is its own implied_by span of the claim when the case gives one, else its text.
    """
    block = case["factcheck"]
    statements = [
        Statement(
            id=i,
            text=s["text"],
            load_bearing=s["load_bearing"],
            implied_by=s.get("implied_by", s["text"]),
            query=s["query"],
            kind="explicit",
            mark="confirmed",
        )
        for i, s in enumerate(block["statements"])
    ]
    return ConfirmedStatements(
        claim=block["claim"], statements=statements, proposed=statements, edits=[], rounds=0, source="case"
    )


def _ratio(hits: int, total: int) -> float:
    return hits / total if total else 0.0


def _statements_correct(case: dict, final: FinalAnswer | None) -> int:
    if final is None:
        return 0
    gold = [s["gold_verdict"] for s in case["factcheck"]["statements"]]
    by_id = {s.id: s.verdict for s in final.statements}
    return sum(by_id.get(i) == verdict for i, verdict in enumerate(gold))


def _row(case: dict, final: FinalAnswer | None) -> CaseRow:
    return CaseRow(
        id=case["id"],
        label=case["factcheck"]["label"],
        overall=final.overall.verdict if final else None,
        statements_correct=_statements_correct(case, final),
        statements_total=len(case["factcheck"]["statements"]),
    )


def _quote_counts(final: FinalAnswer | None) -> tuple[int, int]:
    if final is None:
        return 0, 0
    kept = sum(len(s.evidence) for s in final.statements)
    return kept, kept + sum(len(s.dropped_quotes) for s in final.statements)


def _docs_found(case: dict, final: FinalAnswer | None) -> int:
    if final is None:
        return 0
    cited = {e.doc_id for s in final.statements for e in s.evidence}
    return len(cited & set(case["factcheck"]["gold_doc_ids"]))


def score_runs(cases: list[dict], finals: dict[str, FinalAnswer | None]) -> EvalReport:
    """Score each case's final answer against its gold; a missing final (None or absent) counts as wrong.

    accuracy is the share of cases whose overall verdict equals the label; statement_accuracy the share of
    gold statements whose verdict matches; quote_pass_rate kept / (kept + dropped) quotes of the present
    finals; doc_recall the share of gold_doc_ids cited in the evidence. Empty denominators give 0.0.
    """
    rows = [_row(c, finals.get(c["id"])) for c in cases]
    counts = [_quote_counts(finals.get(c["id"])) for c in cases]
    found = sum(_docs_found(c, finals.get(c["id"])) for c in cases)
    gold_total = sum(len(c["factcheck"]["gold_doc_ids"]) for c in cases)
    return EvalReport(
        accuracy=_ratio(sum(r.overall == r.label for r in rows), len(rows)),
        statement_accuracy=_ratio(sum(r.statements_correct for r in rows), sum(r.statements_total for r in rows)),
        quote_pass_rate=_ratio(sum(k for k, _ in counts), sum(t for _, t in counts)),
        doc_recall=_ratio(found, gold_total),
        rows=rows,
    )
