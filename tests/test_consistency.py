import pytest
from pipeline_helpers import COMMITTED, review_output, v6_confirmed, v6_output

from fact_checker.corpus import load_corpus
from fact_checker.finalize import finalize
from fact_checker.index import build_index
from fact_checker.llm.base import LLMError
from fact_checker.llm.config import Settings
from fact_checker.llm.fake import FakeClient
from fact_checker.services.consistency import one_sided_unknowns
from fact_checker.services.pipeline import run_check
from fact_checker.services.schemas import VerdictOutputItem, VerdictsOutput
from fact_checker.services.verify import verdicts_from_output
from fact_checker.store import create_run, init_store, list_spans
from fact_checker.tracing import Tracer


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "f.sqlite"
    build_index(load_corpus(COMMITTED), path)
    init_store(path)
    return path


def settings():
    return Settings(decompose_model="opus", verify_model="sonnet", verify_effort="high", review_model="sol")


def one_sided_output():
    """V6 with statement 1 left unknown although its one kept quote contradicts it."""
    first, second = v6_output().statements
    unknown = VerdictOutputItem(id=1, evidence=second.evidence, verdict="unknown", reason="not settled")
    return VerdictsOutput(statements=[first, unknown])


def as_verdicts(output):
    return verdicts_from_output(output, {s.id: [f"{s.text} {s.query}"] for s in v6_confirmed().statements})


def test_one_sided_unknown_is_flagged_with_its_stance(db):
    final = finalize(v6_confirmed(), as_verdicts(one_sided_output()), db)
    assert final.statements[1].evidence and final.statements[1].downgrade_reason is None
    (flag,) = one_sided_unknowns(final)
    assert flag.statement_id == 1 and flag.dimension == "unknown_calibration"
    assert "every kept quote contradicts the statement" in flag.reason


def test_unknown_without_quotes_or_with_settled_verdicts_is_not_flagged(db):
    first, _ = v6_output().statements
    bare = VerdictsOutput(statements=[first, VerdictOutputItem(id=1, evidence=[], verdict="unknown", reason="r")])
    assert one_sided_unknowns(finalize(v6_confirmed(), as_verdicts(bare), db)) == []
    assert one_sided_unknowns(finalize(v6_confirmed(), as_verdicts(v6_output()), db)) == []


def test_code_flag_alone_triggers_one_revision_with_the_flag(db):
    verify_client = FakeClient([one_sided_output(), v6_output()])
    review_client = FakeClient([review_output(), review_output()])
    result = run_check(v6_confirmed(), db, verify_client, review_client, settings())
    assert result.revised is True and result.first_scores.needs_attention is False
    assert [f.statement_id for f in result.consistency_flags] == [1]
    assert "Code check: every kept quote contradicts" in verify_client.calls[1].user
    assert result.final.statements[1].verdict == "contradicted"
    assert result.final_message.startswith("Revised after the code consistency check: 1 statement(s) changed.")


def test_no_flag_and_clean_review_means_no_revision(db):
    result = run_check(v6_confirmed(), db, FakeClient([v6_output()]), FakeClient([review_output()]), settings())
    assert result.revised is False and result.consistency_flags == []


def test_failed_review_skips_revision_even_with_a_code_flag(db):
    verify_client = FakeClient([one_sided_output()])
    result = run_check(v6_confirmed(), db, verify_client, FakeClient([LLMError("down")]), settings())
    assert result.revised is False and len(verify_client.calls) == 1
    assert [f.statement_id for f in result.consistency_flags] == [1]


def test_consistency_check_is_traced_as_a_code_span(db, tmp_path):
    store = tmp_path / "s.sqlite"
    init_store(store)
    run_id = create_run(store, "c")
    verify_client = FakeClient([one_sided_output(), v6_output()])
    run_check(
        v6_confirmed(),
        db,
        verify_client,
        FakeClient([review_output(), review_output()]),
        settings(),
        Tracer(store, run_id),
    )
    (span,) = [s for s in list_spans(store, run_id) if s.name == "consistency"]
    assert span.kind == "code" and [f["statement_id"] for f in span.output["flags"]] == [1]
