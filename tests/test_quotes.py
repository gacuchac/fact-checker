import json
from pathlib import Path

import pytest
from fact_checker.quotes import check_quote

ROOT = Path(__file__).parent
CASES = json.loads((ROOT / "fixtures" / "spike3_quotes.json").read_text())
ABSTRACTS = {d["doc_id"]: d["abstract"] for d in json.loads((ROOT.parent / "data" / "corpus.json").read_text())["docs"]}
VERBATIM = "performance is often highest when relevant information occurs at the beginning or end of the input context"
PASSAGE = "We observe that " + VERBATIM + ", and significantly degrades in the middle."


@pytest.mark.parametrize("case", CASES, ids=[c["label"] for c in CASES])
def test_us7_spike3_case(case):
    assert check_quote(case["quote"], ABSTRACTS[case["doc_id"]]) is case["expect"]


def test_us7_spike3_totals():
    genuine = [c for c in CASES if c["expect"]]
    fabricated = [c for c in CASES if not c["expect"]]
    accepted = sum(check_quote(c["quote"], ABSTRACTS[c["doc_id"]]) for c in genuine)
    leaked = sum(check_quote(c["quote"], ABSTRACTS[c["doc_id"]]) for c in fabricated)
    assert (len(genuine), len(fabricated)) == (11, 9)
    assert accepted == 11
    assert leaked == 0


def test_us7_verbatim_quote_is_accepted_control():
    assert check_quote(VERBATIM, PASSAGE) is True


@pytest.mark.parametrize("ellipsis", ["...", "…"])
def test_us7_rejects_ellipsis_ascii_and_unicode(ellipsis):
    quote = f"performance is often highest {ellipsis} when relevant information occurs at the beginning"
    passage = "performance is often highest " + ellipsis + " when relevant information occurs at the beginning"
    assert check_quote(quote, passage) is False


def test_us7_rejects_4_word_verbatim_substring():
    assert check_quote("often highest when relevant", PASSAGE) is False


def test_us7_accepts_5_word_verbatim_substring():
    assert check_quote("often highest when relevant information", PASSAGE) is True


def test_us7_accepts_latex_percent():
    passage = "Our method gives results that are better by up to 30\\%, while keeping speed."
    assert check_quote("results that are better by up to 30%", passage) is True


def test_us7_keeps_number_sign():
    passage = "the point estimate is slightly negative (-1.9 pp, p = 0.16) in this model"
    assert check_quote("slightly negative (1.9 pp, p = 0.16)", passage) is False
    assert check_quote("slightly negative (-1.9 pp, p = 0.16)", passage) is True


def test_us7_not_in_passage_is_rejected():
    assert check_quote("a quote that never appears in this passage at all", PASSAGE) is False
