import pytest
from pipeline_helpers import (
    COMMITTED,
    flag,
    review_output,
    revised_output,
    v6_confirmed,
    v6_output,
)

from fact_checker.corpus import load_corpus
from fact_checker.finalize import _finalize_with_results
from fact_checker.index import build_index
from fact_checker.llm.base import LLMError
from fact_checker.llm.fake import FakeClient
from fact_checker.services.review import review
from fact_checker.services.revise import revise
from fact_checker.services.schemas import VerdictsOutput
from fact_checker.services.verify import verify
from fact_checker.store import create_run, init_store, list_spans
from fact_checker.tracing import Tracer


@pytest.fixture(scope="module")
def full_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "index.sqlite"
    build_index(load_corpus(COMMITTED), path)
    return path


def first_round(db):
    confirmed = v6_confirmed()
    verdicts, _ = verify(confirmed, db, FakeClient([v6_output()]), "m", None)
    final, results = _finalize_with_results(confirmed, verdicts, db)
    scores, _ = review(confirmed, verdicts, final, results, FakeClient([review_output([flag()])]), "sol")
    return confirmed, verdicts, final, results, scores


def test_revise_prompt_request_and_new_verdicts(full_db):
    confirmed, verdicts, final, results, scores = first_round(full_db)
    client = FakeClient([revised_output()])
    revised, usage = revise(confirmed, verdicts, final, results, scores, client, "sonnet", "high")
    call = client.calls[0]
    assert call.schema is VerdictsOutput and call.model == "sonnet" and call.effort == "high"
    assert "A reviewer flagged problems with your previous verdicts" in call.system
    assert "verbatim" in call.system and "each with its own passages" in call.system
    for s in confirmed.statements:
        assert f'<statement id="{s.id}" load_bearing="true">{s.text}</statement>' in call.user
        assert f'<passages statement="{s.id}">' in call.user
    assert '<passage id="2401.18058v1#7" doc_id="2401.18058v1"' in call.user
    assert verdicts.model_dump_json(indent=2) in call.user
    assert "overreach" in call.user and "the quote is about maintaining" in call.user
    assert "evidence_relevance" in call.user
    assert [sv.verdict for sv in revised.statements] == ["supported", "unknown"]
    assert [sv.queries for sv in revised.statements] == [sv.queries for sv in verdicts.statements]
    assert usage.model == "sonnet"


def test_revise_rejects_wrong_ids(full_db):
    confirmed, verdicts, final, results, scores = first_round(full_db)
    partial = VerdictsOutput(statements=v6_output().statements[:1])
    with pytest.raises(LLMError):
        revise(confirmed, verdicts, final, results, scores, FakeClient([partial]), "m", None)


def test_verify_records_one_tool_span_per_retrieve_with_hits(full_db, tmp_path):
    db = tmp_path / "t.sqlite"
    init_store(db)
    run_id = create_run(db, "c")
    confirmed = v6_confirmed()
    verify(confirmed, full_db, FakeClient([v6_output()]), "m", None, tracer=Tracer(db, run_id))
    spans = list_spans(db, run_id)
    assert [(s.kind, s.name) for s in spans] == [("tool", "retrieve")] * 2
    for s, statement in zip(spans, confirmed.statements, strict=True):
        assert s.input == {"query": f"{statement.text} {statement.query}", "k": 5, "per_doc": 2}
        hits = s.output["hits"]
        assert hits and set(hits[0]) == {"passage_id", "doc_id", "title", "score", "text"}
    assert any(h["passage_id"] == "2401.18058v1#7" for h in spans[0].output["hits"])
