import json
import re
from pathlib import Path

import pytest
from fact_checker.finalize import aggregate, finalize, ground_statement, rerun_queries
from fact_checker.quotes import check_quote

from fact_checker.contracts import (
    ConfirmedStatements,
    Evidence,
    FinalStatement,
    Hit,
    Statement,
    StatementVerdict,
    Verdicts,
)
from fact_checker.index import build_index

ROOT = Path(__file__).parent
SPIKE6 = ROOT / "fixtures" / "spike6"
COMMITTED = ROOT.parent / "data" / "corpus.json"
CASES = ["V1", "V2", "V3", "V4", "V5", "V6"]


@pytest.fixture
def full_db(tmp_path):
    from fact_checker.corpus import load_corpus

    path = tmp_path / "index.sqlite"
    build_index(load_corpus(COMMITTED), path)
    return path


def load(case):
    d = SPIKE6 / case
    confirmed = ConfirmedStatements.model_validate_json((d / "confirmed.json").read_text())
    verdicts = load_verdicts((d / "verdicts.json").read_text(), confirmed)
    expected = json.loads((d / "expected.json").read_text())
    return confirmed, verdicts, expected


def load_verdicts(text, confirmed):
    ids = [s.id for s in confirmed.statements]
    return Verdicts.model_validate_json(text, context={"confirmed_ids": ids})


def compare(final, expected):
    got = {str(s.id): {"verdict": s.verdict, "downgrade_reason": s.downgrade_reason} for s in final.statements}
    return got == expected["statements"] and final.overall.model_dump() == expected["overall"]


@pytest.mark.integration
@pytest.mark.parametrize("case", CASES)
def test_us8_spike6_case(case, full_db):
    confirmed, verdicts, expected = load(case)
    final = finalize(confirmed, verdicts, full_db)
    got = {str(s.id): {"verdict": s.verdict, "downgrade_reason": s.downgrade_reason} for s in final.statements}
    assert got == expected["statements"]
    assert final.overall.model_dump() == expected["overall"]


@pytest.mark.integration
def test_us8_spike6_six_of_six(full_db):
    matched = [compare(finalize(*load(c)[:2], full_db), load(c)[2]) for c in CASES]
    assert matched == [True] * 6


@pytest.mark.integration
def test_us8_v4_keeps_both_quotes_from_two_docs(full_db):
    confirmed, verdicts, _ = load("V4")
    s0 = finalize(confirmed, verdicts, full_db).statements[0]
    assert len(s0.evidence) == 2
    assert {e.stance for e in s0.evidence} == {"supports", "contradicts"}
    assert {e.doc_id for e in s0.evidence} == {"2312.05934v3", "2604.23801v1"}


@pytest.mark.integration
def test_us8_evidence_carries_paper_meta(full_db):
    confirmed, verdicts, _ = load("V1")
    ev = finalize(confirmed, verdicts, full_db).statements[0].evidence[0]
    assert ev.doc_id == "2307.03172v3"
    assert ev.title.startswith("Lost in the Middle")
    assert ev.authors
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ev.published)


@pytest.mark.integration
def test_us8_evidence_quote_is_as_the_model_wrote_it(full_db):
    confirmed, verdicts, _ = load("V6")
    ev = finalize(confirmed, verdicts, full_db).statements[0].evidence[0]
    assert ev.quote == verdicts.statements[0].evidence[0].quote
    assert ev.stance == "supports"


@pytest.mark.integration
def test_us8_fabricated_quote_dropped_supported_becomes_quote_failed(full_db):
    confirmed, verdicts, _ = load("V1")
    fake = "performance is often lowest when relevant information occurs at the beginning"
    verdicts.statements[0].evidence[0].quote = fake
    s0 = finalize(confirmed, verdicts, full_db).statements[0]
    assert [e.quote for e in s0.dropped_quotes] == [fake]
    assert s0.evidence == []
    assert s0.verdict == "unknown"
    assert s0.downgrade_reason == "quote_failed"
    assert s0.model_verdict == "supported"


@pytest.mark.integration
def test_us8_quote_from_other_statements_passages_dropped(full_db):
    confirmed, verdicts, _ = load("V3")
    quote = "Fine tuning, while beneficial for small LMs, requires extensive resources"
    by_id = {sv.id: sv for sv in verdicts.statements}
    s0, s1 = by_id[0], by_id[1]
    assert any(check_quote(quote, h.text) for r in rerun_queries(s1, full_db) for h in r.hits)
    assert not any(check_quote(quote, h.text) for r in rerun_queries(s0, full_db) for h in r.hits)
    s0.verdict = "supported"
    s0.evidence = [Evidence(passage_id="2403.01432v5#7", quote=quote, stance="supports")]
    got = finalize(confirmed, verdicts, full_db).statements[0]
    assert got.verdict == "unknown"
    assert got.downgrade_reason == "quote_failed"
    assert [e.quote for e in got.dropped_quotes] == [quote]
    assert got.evidence == []


@pytest.mark.integration
def test_us8_wrong_passage_id_still_kept_when_text_matches(full_db):
    confirmed, verdicts, _ = load("V1")
    verdicts.statements[0].evidence[0].passage_id = "9999.99999v1#0"
    s0 = finalize(confirmed, verdicts, full_db).statements[0]
    assert s0.verdict == "supported"
    assert [e.doc_id for e in s0.evidence] == ["2307.03172v3"]
    assert s0.dropped_quotes == []


@pytest.mark.integration
def test_us8_no_hits_gives_unknown_no_hits(full_db):
    confirmed, verdicts, _ = load("V5")
    sv = verdicts.statements[0]
    sv.queries = ["photosynthesis in plants"]
    sv.verdict = "supported"
    assert rerun_queries(sv, full_db)[0].hits == []
    s0 = finalize(confirmed, verdicts, full_db).statements[0]
    assert (s0.verdict, s0.downgrade_reason) == ("unknown", "no_hits")


@pytest.mark.integration
def test_us8_empty_queries_counts_as_no_hits(full_db):
    confirmed, verdicts, _ = load("V1")
    verdicts.statements[0].queries = []
    s0 = finalize(confirmed, verdicts, full_db).statements[0]
    assert (s0.verdict, s0.downgrade_reason) == ("unknown", "no_hits")


@pytest.mark.integration
def test_us8_model_unknown_is_never_upgraded(full_db):
    confirmed, verdicts, _ = load("V1")
    verdicts.statements[0].verdict = "unknown"
    s0 = finalize(confirmed, verdicts, full_db).statements[0]
    assert (s0.verdict, s0.downgrade_reason) == ("unknown", None)


@pytest.mark.integration
def test_us8_statements_follow_confirmed_order_and_carry_fields(full_db):
    confirmed, verdicts, _ = load("V6")
    verdicts.statements.reverse()
    final = finalize(confirmed, verdicts, full_db)
    assert [s.id for s in final.statements] == [0, 1]
    assert final.claim == confirmed.claim
    assert final.statements[0].text == confirmed.statements[0].text
    assert final.statements[0].model_verdict == "supported"


def stmt(i, mark):
    return Statement(
        id=i,
        text=f"Statement number {i}",
        load_bearing=True,
        implied_by=f"Statement number {i}",
        query=f"statement {i}",
        kind="explicit",
        mark=mark,
    )


@pytest.mark.integration
def test_us8_counts_by_mark_and_drops(full_db):
    marks = ["confirmed", "user_edited", "user_added"]
    sts = [stmt(i, m) for i, m in enumerate(marks)]
    claim = " ".join(s.text for s in sts)
    confirmed = ConfirmedStatements.model_validate(
        {
            "claim": claim,
            "statements": [s.model_dump() for s in sts],
            "proposed": [s.model_dump() for s in sts],
            "edits": [
                {"op": "drop", "id": 3, "value": None},
                {"op": "drop", "id": 4, "value": None},
                {"op": "feedback", "id": None, "value": "ok"},
            ],
            "rounds": 1,
            "source": "chat",
        }
    )
    verdicts = Verdicts(
        statements=[StatementVerdict(id=i, queries=[], evidence=[], verdict="unknown", reason="r") for i in range(3)]
    )
    counts = finalize(confirmed, verdicts, full_db).counts
    assert (counts.confirmed, counts.user_edited, counts.user_added, counts.dropped) == (1, 1, 1, 2)


@pytest.mark.integration
def test_us8_finalize_raises_on_id_mismatch(full_db):
    confirmed, verdicts, _ = load("V6")
    verdicts.statements.pop()
    with pytest.raises(ValueError):
        finalize(confirmed, verdicts, full_db)


def fs(load_bearing, verdict, reason=None):
    return FinalStatement(
        id=0,
        text="t",
        load_bearing=load_bearing,
        mark="confirmed",
        model_verdict=verdict,
        verdict=verdict,
        downgrade_reason=reason,
        evidence=[],
        dropped_quotes=[],
    )


ROWS = [
    ([], "unknown", 0),
    ([fs(False, "supported"), fs(False, "supported")], "unknown", 0),
    ([fs(True, "unknown", "conflict"), fs(True, "contradicted")], "unknown", 1),
    ([fs(True, "contradicted"), fs(True, "unknown")], "contradicted", 2),
    ([fs(True, "unknown"), fs(True, "supported")], "unknown", 3),
    ([fs(True, "supported"), fs(True, "supported")], "supported", 4),
    ([fs(True, "supported"), fs(False, "contradicted")], "supported", 4),
    ([fs(True, "supported"), fs(False, "unknown", "conflict")], "supported", 4),
    ([fs(True, "unknown", "quote_failed"), fs(True, "supported")], "unknown", 3),
]


@pytest.mark.parametrize(("statements", "verdict", "rule"), ROWS, ids=[f"row{i}" for i in range(len(ROWS))])
def test_us9_aggregate_truth_table(statements, verdict, rule):
    overall = aggregate(statements)
    assert (overall.verdict, overall.rule) == (verdict, rule)


def test_us9_ground_statement_same_doc_both_stances_is_not_conflict():
    statement = stmt(0, "confirmed")
    hits = [
        Hit(
            passage_id="d1#0",
            doc_id="d1",
            title="T",
            score=1.0,
            text="alpha beta gamma delta epsilon is true. zeta eta theta iota kappa is false.",
        ),
    ]
    sv = StatementVerdict(
        id=0,
        queries=["q"],
        verdict="supported",
        reason="r",
        evidence=[
            Evidence(passage_id="d1#0", quote="alpha beta gamma delta epsilon", stance="supports"),
            Evidence(passage_id="d1#0", quote="zeta eta theta iota kappa", stance="contradicts"),
        ],
    )
    verdict, reason, kept, dropped = ground_statement(statement, sv, hits)
    assert (verdict, reason) == ("supported", None)
    assert len(kept) == 2
    assert dropped == []


def test_us9_ground_statement_different_docs_both_stances_is_conflict():
    statement = stmt(0, "confirmed")
    hits = [
        Hit(passage_id="d1#0", doc_id="d1", title="T", score=1.0, text="alpha beta gamma delta epsilon is true."),
        Hit(passage_id="d2#0", doc_id="d2", title="U", score=0.9, text="zeta eta theta iota kappa is false."),
    ]
    sv = StatementVerdict(
        id=0,
        queries=["q"],
        verdict="supported",
        reason="r",
        evidence=[
            Evidence(passage_id="d1#0", quote="alpha beta gamma delta epsilon", stance="supports"),
            Evidence(passage_id="d2#0", quote="zeta eta theta iota kappa", stance="contradicts"),
        ],
    )
    verdict, reason, kept, _ = ground_statement(statement, sv, hits)
    assert (verdict, reason) == ("unknown", "conflict")
    assert len(kept) == 2
