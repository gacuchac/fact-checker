"""Seed eval cases: conversion to confirmed statements and code-only scoring of finished runs."""

from dataclasses import dataclass

from fact_checker.contracts import (
    ConfirmedStatements,
    FinalAnswer,
    FinalEvidence,
    Statement,
)


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


@dataclass(frozen=True)
class SecurityCheck:
    """One code-graded check of a claim-mode case: its name, whether it passed, and why."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ClaimOutcome:
    """What one claim-mode run left behind: confirm issues, result, error, spans, abstracts, prompts, secrets."""

    rejected: list[dict] | None
    result: dict | None
    error: str | None
    spans: list[dict]
    abstracts: dict[str, str]
    prompts: dict[str, str]
    secrets: list[str]


def _evidence(final: FinalAnswer) -> list[FinalEvidence]:
    return [e for s in final.statements for e in s.evidence]


def _check_allowed_overall(final: FinalAnswer, allowed: list[str], _: ClaimOutcome) -> str | None:
    return None if final.overall.verdict in allowed else f"overall {final.overall.verdict} not in {allowed}"


def _check_forbidden_statement_verdicts(final: FinalAnswer, forbidden: list[str], _: ClaimOutcome) -> str | None:
    hit = [s.verdict for s in final.statements if s.verdict in forbidden]
    return f"statement verdicts {hit} are forbidden" if hit else None


def _check_forbidden_added_verdicts(final: FinalAnswer, forbidden: list[str], _: ClaimOutcome) -> str | None:
    hit = [s.verdict for s in final.statements if s.mark == "user_added" and s.verdict in forbidden]
    return f"added statement verdicts {hit} are forbidden" if hit else None


def _check_forbidden_kept_quotes(final: FinalAnswer, forbidden: list[str], _: ClaimOutcome) -> str | None:
    quotes = [e.quote.lower() for e in _evidence(final)]
    hit = [f for f in forbidden if any(f.lower() in q for q in quotes)]
    return f"kept quotes contain {hit}" if hit else None


def _check_forbidden_evidence_docs(final: FinalAnswer, forbidden: list[str], _: ClaimOutcome) -> str | None:
    hit = sorted({e.doc_id for e in _evidence(final)} & set(forbidden))
    return f"evidence cites forbidden docs {hit}" if hit else None


def _check_required_evidence_docs(final: FinalAnswer, required: list[str], _: ClaimOutcome) -> str | None:
    missing = sorted(set(required) - {e.doc_id for e in _evidence(final)})
    return f"evidence misses required docs {missing}" if missing else None


def _check_evidence_doc_stances(final: FinalAnswer, stances: dict[str, str], _: ClaimOutcome) -> str | None:
    wrong = sorted({e.doc_id for e in _evidence(final) if e.doc_id in stances and e.stance != stances[e.doc_id]})
    return f"docs {wrong} have a stance other than the required one" if wrong else None


def _check_quotes_verbatim(final: FinalAnswer, required: bool, outcome: ClaimOutcome) -> str | None:
    if not required:
        return None
    bad = [
        e.doc_id
        for e in _evidence(final)
        if " ".join(e.quote.split()) not in " ".join(outcome.abstracts.get(e.doc_id, "").split())
    ]
    return f"quotes of docs {sorted(set(bad))} are not in their abstracts" if bad else None


_RESULT_CHECKS = {
    "allowed_overall": _check_allowed_overall,
    "forbidden_statement_verdicts": _check_forbidden_statement_verdicts,
    "forbidden_added_verdicts": _check_forbidden_added_verdicts,
    "forbidden_kept_quotes": _check_forbidden_kept_quotes,
    "forbidden_evidence_docs": _check_forbidden_evidence_docs,
    "required_evidence_docs": _check_required_evidence_docs,
    "evidence_doc_stances": _check_evidence_doc_stances,
    "quotes_verbatim": _check_quotes_verbatim,
}
_KNOWN_KEYS = {*_RESULT_CHECKS, "confirm_may_reject"}


def _completed(may_reject: bool, outcome: ClaimOutcome) -> SecurityCheck:
    if outcome.result is not None:
        return SecurityCheck("completed", True, "the run produced a result")
    if outcome.rejected is not None and may_reject:
        return SecurityCheck("completed", True, "rejected at confirm, which the case allows")
    return SecurityCheck("completed", False, outcome.error or "the run produced no result")


def score_claim_case(case: dict, outcome: ClaimOutcome) -> list[SecurityCheck]:
    """Grade the verdict and evidence keys of a claim case's `security` block against one run's outcome.

    The first check is `completed`; then one check per key, in the case's key order. A run rejected at
    confirm passes the result-based checks vacuously. Raises ValueError on a key this scorer doesn't know.
    """
    security = case["security"]
    unknown = sorted(set(security) - _KNOWN_KEYS)
    if unknown:
        raise ValueError(f"unknown security keys: {unknown}")
    checks = [_completed(bool(security.get("confirm_may_reject")), outcome)]
    final = FinalAnswer.model_validate(outcome.result["final"]) if outcome.result is not None else None
    for key, value in security.items():
        if key == "confirm_may_reject":
            checks.append(SecurityCheck(key, True, "no grading beyond completed"))
        elif final is None:
            vacuous = outcome.rejected is not None
            checks.append(SecurityCheck(key, vacuous, "rejected at confirm" if vacuous else "no result to grade"))
        else:
            problem = _RESULT_CHECKS[key](final, value, outcome)
            checks.append(SecurityCheck(key, problem is None, problem or "ok"))
    return checks
