import pytest
from pipeline_helpers import (
    COMMITTED,
    flag,
    review_output,
    revised_output,
    v6_confirmed,
    v6_output,
)

from fact_checker.contracts import Edit
from fact_checker.corpus import load_corpus
from fact_checker.index import build_index
from fact_checker.llm.base import LLMError
from fact_checker.llm.config import Settings
from fact_checker.llm.fake import FakeClient
from fact_checker.services.confirm import Issue
from fact_checker.services.pipeline import CheckResult, run_check
from fact_checker.services.schemas import (
    DecomposedStatement,
    DecomposeOutput,
    FalsifiabilityOutput,
)
from fact_checker.services.session import confirm_claim, start_claim, verify_claim
from fact_checker.store import get_run, init_store, list_spans

CLAIM = v6_confirmed().claim


@pytest.fixture(scope="module")
def corpus_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "f.sqlite"
    build_index(load_corpus(COMMITTED), path)
    return path


@pytest.fixture
def db(corpus_db, tmp_path):
    path = tmp_path / "f.sqlite"
    path.write_bytes(corpus_db.read_bytes())
    init_store(path)
    return path


def settings():
    return Settings(decompose_model="opus", verify_model="sonnet", verify_effort="high", review_model="sol")


def decompose_output():
    return DecomposeOutput(
        statements=[
            DecomposedStatement(
                text=s.text, kind="explicit", load_bearing=True, implied_by=s.implied_by, query=s.query
            )
            for s in v6_confirmed().statements
        ]
    )


def names(spans):
    return [(s.kind, s.name) for s in spans]


def test_no_revision_path(db):
    result = run_check(
        v6_confirmed(), db, FakeClient([v6_output()]), FakeClient([review_output()]), settings()
    )
    assert result.revised is False and result.first_scores is None and result.first_final == result.final
    assert not result.final_message.startswith("Revised after review")
    assert result.final_message.startswith("Claim:")


def test_revision_round_in_run_check(db):
    verify_client = FakeClient([v6_output(), revised_output()])
    review_client = FakeClient([review_output([flag()]), review_output()])
    result = run_check(v6_confirmed(), db, verify_client, review_client, settings())
    assert isinstance(result, CheckResult) and result.revised is True
    assert result.first_final.overall.verdict == "contradicted" and result.final.overall.verdict == "unknown"
    assert result.first_scores.needs_attention is True and result.scores.needs_attention is False
    assert result.final_message.startswith("Revised after review: 1 statement(s) changed.\n")
    assert "Overall: unknown" in result.final_message
    assert [e.step for e in result.events] == ["verify", "finalize", "review", "revise", "finalize", "review"]
    assert [sv.verdict for sv in result.verdicts.statements] == ["supported", "unknown"]


def test_only_one_revision_round(db):
    verify_client = FakeClient([v6_output(), revised_output()])
    review_client = FakeClient([review_output([flag()]), review_output([flag()])])
    result = run_check(v6_confirmed(), db, verify_client, review_client, settings())
    assert result.revised is True and result.scores.needs_attention is True
    assert len(verify_client.calls) == 2 and len(review_client.calls) == 2


def test_review_failure_skips_revision(db):
    result = run_check(
        v6_confirmed(), db, FakeClient([v6_output()]), FakeClient([LLMError("down")]), settings()
    )
    assert result.scores is None and "down" in result.review_error
    assert result.revised is False and result.first_scores is None


def test_failed_revision_keeps_the_first_answer(db):
    verify_client = FakeClient([v6_output(), LLMError("revise down")])
    review_client = FakeClient([review_output([flag()])])
    result = run_check(v6_confirmed(), db, verify_client, review_client, settings())
    assert result.revised is False and result.final == result.first_final
    assert result.scores.needs_attention is True and result.review_error is None
    assert result.events[-1].step == "revise" and result.events[-1].ok is False


def test_second_review_failure_keeps_revised_answer(db):
    verify_client = FakeClient([v6_output(), revised_output()])
    review_client = FakeClient([review_output([flag()]), LLMError("down")])
    result = run_check(v6_confirmed(), db, verify_client, review_client, settings())
    assert result.revised is True and result.scores is None and "down" in result.review_error
    assert result.first_scores.needs_attention is True


def test_full_session_with_revision_traces_every_step_in_order(db):
    run_id, proposed = start_claim(db, CLAIM, FakeClient([decompose_output()]), settings())
    assert [s.id for s in proposed] == [0, 1]
    assert get_run(db, run_id).status == "proposed"
    assert get_run(db, run_id).proposed[0]["text"] == proposed[0].text

    edits = [Edit(op="feedback", id=None, value="fine")]
    confirmed = confirm_claim(db, run_id, edits, FakeClient([]), settings())
    assert [s.id for s in confirmed.statements] == [0, 1]
    assert get_run(db, run_id).status == "confirmed"
    assert get_run(db, run_id).confirmed["claim"] == CLAIM

    verify_client = FakeClient([v6_output(), revised_output()])
    review_client = FakeClient([review_output([flag()]), review_output()])
    verify_claim(db, run_id, verify_client, review_client, settings())
    run = get_run(db, run_id)
    assert run.status == "done" and run.error is None
    assert run.result["revised"] is True
    assert run.result["final_message"].startswith("Revised after review")

    spans = list_spans(db, run_id)
    assert [s.seq for s in spans] == list(range(len(spans)))
    assert names(spans) == [
        ("user", "claim"),
        ("llm", "decompose"),
        ("user", "edits"),
        ("user", "approval"),
        *[("tool", "retrieve")] * 4,
        ("llm", "verify"),
        ("code", "finalize"),
        *[("tool", "retrieve")] * 4,
        ("code", "consistency"),
        ("llm", "review"),
        ("llm", "revise"),
        ("code", "finalize"),
        *[("tool", "retrieve")] * 4,
        ("llm", "review"),
        ("system", "final_message"),
    ]
    assert spans[0].input == {"claim": CLAIM}
    assert spans[1].input["schema"] == "DecomposeOutput" and spans[1].model == "opus"
    finalize_first, finalize_second = spans[9], spans[17]
    assert finalize_first.output["overall"] == {"verdict": "contradicted", "rule": 2}
    assert finalize_second.output["overall"] == {"verdict": "unknown", "rule": 3}
    statement = finalize_first.output["statements"][0]
    assert statement["downgrade_reason"] is None and statement["dropped_quotes"] == []
    assert statement["kept_quotes"][0]["quote"].startswith("LongAlign outperforms")
    assert finalize_first.input["verdicts"]["statements"][0]["id"] == 0
    for parent, children in ((finalize_first, spans[10:14]), (finalize_second, spans[18:22])):
        assert all(c.parent_id == parent.id for c in children)
        assert [c.input["query"] for c in children] == [
            q for s in v6_confirmed().statements for q in (f"{s.text} {s.query}", CLAIM)
        ]
        assert children[0].input["k"] == 5 and children[0].input["per_doc"] == 2
        assert children[0].output["hits"][0]["passage_id"]
    assert spans[-1].output["message"] == run.result["final_message"]


def test_session_without_revision(db):
    run_id, _ = start_claim(db, CLAIM, FakeClient([decompose_output()]), settings())
    confirm_claim(db, run_id, [], FakeClient([]), settings())
    verify_claim(db, run_id, FakeClient([v6_output()]), FakeClient([review_output()]), settings())
    run = get_run(db, run_id)
    assert run.status == "done" and run.result["revised"] is False
    kinds = names(list_spans(db, run_id))
    assert kinds.count(("llm", "revise")) == 0 and kinds.count(("llm", "review")) == 1
    assert kinds[-1] == ("system", "final_message")


def test_confirm_returns_issues_and_stays_proposed(db):
    run_id, _ = start_claim(db, CLAIM, FakeClient([decompose_output()]), settings())
    check = FakeClient([FalsifiabilityOutput(falsifiable=False, reason="hedge", query="")])
    issues = confirm_claim(db, run_id, [Edit(op="add", id=None, value="It is probably good.")], check, settings())
    assert issues == [Issue(statement_id=2, reason="hedge")]
    run = get_run(db, run_id)
    assert run.status == "proposed" and run.confirmed is None
    assert ("llm", "falsifiability") in names(list_spans(db, run_id))


def test_verify_failure_marks_the_run_failed(db):
    run_id, _ = start_claim(db, CLAIM, FakeClient([decompose_output()]), settings())
    confirm_claim(db, run_id, [], FakeClient([]), settings())
    verify_claim(db, run_id, FakeClient([LLMError("api down")]), FakeClient([]), settings())
    run = get_run(db, run_id)
    assert run.status == "failed" and "api down" in run.error and run.result is None


def test_start_claim_creates_the_store_tables_itself(corpus_db, tmp_path):
    path = tmp_path / "bare.sqlite"
    path.write_bytes(corpus_db.read_bytes())
    run_id, _ = start_claim(path, CLAIM, FakeClient([decompose_output()]), settings())
    assert get_run(path, run_id).status == "proposed"


def test_start_claim_failure_marks_the_run_failed(db):
    with pytest.raises(LLMError):
        start_claim(db, CLAIM, FakeClient([LLMError("nope")]), settings())
    from fact_checker.store import list_runs

    (summary,) = list_runs(db)
    assert summary.status == "failed"
