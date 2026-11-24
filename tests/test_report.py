from pathlib import Path

import pytest
from fact_checker.report import render_answer

from fact_checker.contracts import Dimensions, FinalAnswer, JudgeScores

FIX = Path(__file__).parent / "fixtures" / "report"


@pytest.fixture
def final():
    return FinalAnswer.model_validate_json((FIX / "final.json").read_text())


@pytest.fixture
def scores():
    return JudgeScores.model_validate_json((FIX / "scores.json").read_text())


def test_us10_none_scores_renders_not_judged(final):
    assert "not judged" in render_answer(final, None)


def test_us10_with_scores_has_no_not_judged_and_lists_6_dimensions(final, scores):
    text = render_answer(final, scores)
    assert "not judged" not in text
    assert "needs attention: yes" in text
    for name in Dimensions.model_fields:
        score = getattr(scores.dimensions, name).score
        assert f"{name} {score}/5" in text


def test_us10_deterministic(final, scores):
    assert render_answer(final, scores) == render_answer(final, scores)
    again = FinalAnswer.model_validate_json(final.model_dump_json())
    assert render_answer(again, None) == render_answer(final, None)


def test_us10_contains_overall_rule_and_every_statement(final):
    text = render_answer(final, None)
    assert "Overall: unknown (rule 1)" in text
    assert "[0] unknown (conflict)" in text
    assert "[1] supported" in text
    assert "[2] unknown (quote_failed)" in text
    for s in final.statements:
        assert s.text in text


def test_us10_every_quote_and_doc_id_rendered(final):
    text = render_answer(final, None)
    for s in final.statements:
        for e in s.evidence:
            assert e.quote in text
            assert e.doc_id in text
            assert e.stance in text


def test_us10_dropped_quote_count_and_model_verdict_when_differs(final):
    text = render_answer(final, None)
    assert "dropped quotes: 1" in text
    assert "model verdict: contradicted" in text


def test_us10_flag_reason_rendered(final, scores):
    text = render_answer(final, scores)
    assert scores.flagged[0].reason in text
    assert "flagged [2] unknown_calibration" in text


def test_us10_ends_with_single_newline(final, scores):
    for s in (None, scores):
        text = render_answer(final, s)
        assert text.endswith("\n")
        assert not text.endswith("\n\n")
