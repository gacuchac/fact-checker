import hashlib
import json
from pathlib import Path

import pytest

from fact_checker.contracts import (
    ConfirmedStatements,
    Dimensions,
    DimensionScore,
    Edit,
    Evidence,
    Flag,
    Statement,
    Verdicts,
)
from fact_checker.corpus import load_corpus
from fact_checker.index import build_index
from fact_checker.llm.base import LLMError
from fact_checker.llm.config import Settings
from fact_checker.llm.fake import FakeClient
from fact_checker.services.confirm import Issue, apply_edits, check_statements
from fact_checker.services.decompose import decompose
from fact_checker.services.pipeline import run_check
from fact_checker.services.review import review
from fact_checker.services.schemas import (
    DecomposedStatement,
    DecomposeOutput,
    FalsifiabilityOutput,
    ReviewOutput,
    VerdictOutputItem,
    VerdictsOutput,
)
from fact_checker.services.verify import statement_queries, verify

ROOT = Path(__file__).parent
V6 = ROOT / "fixtures" / "spike6" / "V6"
COMMITTED = ROOT.parent / "data" / "corpus.json"
CLAIM = "A beats B on benchmarks. B is cheaper."


def decomposed(text, implied_by, kind="explicit", load_bearing=True, query="q words"):
    return DecomposedStatement(text=text, kind=kind, load_bearing=load_bearing, implied_by=implied_by, query=query)


def statement(id, text="A beats B on benchmarks.", mark="confirmed", query="a b", **kw):
    return Statement(
        id=id,
        text=text,
        load_bearing=kw.get("load_bearing", True),
        implied_by=kw.get("implied_by", "A beats B on benchmarks."),
        query=query,
        kind="explicit",
        mark=mark,
    )


def confirmed_of(*statements, claim=CLAIM, edits=()):
    return ConfirmedStatements(
        claim=claim, statements=list(statements), proposed=list(statements), edits=list(edits), rounds=1, source="chat"
    )


def dimensions(score=5):
    d = DimensionScore(score=score, evidence="e")
    return Dimensions(
        evidence_relevance=d,
        statement_verdicts=d,
        overreach=d,
        conflict_handling=d,
        aggregation=d,
        unknown_calibration=d,
    )


def test_decompose_ids_marks_and_request():
    out = DecomposeOutput(
        statements=[
            decomposed("A beats B.", CLAIM),
            decomposed("A beats B on benchmarks.", "A beats B on benchmarks."),
            decomposed("B is cheaper.", "B is cheaper.", kind="implicit_assumption", load_bearing=False),
        ]
    )
    client = FakeClient([out])
    statements, usage = decompose(CLAIM, client, "opus", "high")
    assert [s.id for s in statements] == [0, 1, 2]
    assert {s.mark for s in statements} == {"confirmed"}
    assert statements[2].kind == "implicit_assumption" and statements[2].load_bearing is False
    call = client.calls[0]
    assert call.user == f"<claim>{CLAIM}</claim>"
    assert call.model == "opus" and call.effort == "high"
    assert call.schema is DecomposeOutput
    assert "falsifiable statements" in call.system
    assert usage.model == "opus"


def test_decompose_caps_at_five():
    out = DecomposeOutput(statements=[decomposed(f"s{i}", CLAIM) for i in range(7)])
    statements, _ = decompose(CLAIM, FakeClient([out]), "m", None)
    assert [s.id for s in statements] == [0, 1, 2, 3, 4]


def test_decompose_drops_statement_failing_span_check():
    out = DecomposeOutput(
        statements=[decomposed("S0", CLAIM), decomposed("bad", "not in the claim"), decomposed("ok", "B is cheaper.")]
    )
    statements, _ = decompose(CLAIM, FakeClient([out]), "m", None)
    assert [(s.id, s.text) for s in statements] == [(0, "S0"), (1, "ok")]


def test_decompose_statement_zero_falls_back_to_whole_claim():
    out = DecomposeOutput(statements=[decomposed("S0", "paraphrase of claim")])
    statements, _ = decompose(CLAIM, FakeClient([out]), "m", None)
    assert statements[0].implied_by == CLAIM


def test_decompose_empty_output_raises():
    with pytest.raises(LLMError):
        decompose(CLAIM, FakeClient([DecomposeOutput(statements=[])]), "m", None)


def test_decomposed_statements_form_valid_confirmed():
    out = DecomposeOutput(statements=[decomposed("S0", "x"), decomposed("ok", "B is cheaper.")])
    statements, _ = decompose(CLAIM, FakeClient([out]), "m", None)
    assert confirmed_of(*statements).statements == statements


def test_apply_edits_drop_edit_flip():
    proposed = [statement(0), statement(1, text="B is cheaper.", implied_by="B is cheaper.")]
    edits = [
        Edit(op="edit", id=1, value="B costs less."),
        Edit(op="flip_load_bearing", id=1, value=None),
        Edit(op="feedback", id=None, value="shorter please"),
    ]
    result = apply_edits(CLAIM, proposed, edits)
    assert result.statements[1].text == "B costs less."
    assert result.statements[1].mark == "user_edited"
    assert result.statements[1].load_bearing is False
    assert result.statements[0].mark == "confirmed"
    assert result.proposed == proposed
    assert result.edits == edits
    assert (result.rounds, result.source) == (1, "chat")
    dropped = apply_edits(CLAIM, proposed, [Edit(op="drop", id=1, value=None)])
    assert [s.id for s in dropped.statements] == [0]


def test_apply_edits_add_takes_next_id_and_skips_span_check():
    proposed = [statement(0), statement(1, text="B is cheaper.", implied_by="B is cheaper.")]
    edits = [
        Edit(op="drop", id=1, value=None),
        Edit(op="add", id=None, value="C is open source."),
        Edit(op="add", id=None, value="D too."),
    ]
    result = apply_edits(CLAIM, proposed, edits)
    added = result.statements[1:]
    assert [s.id for s in added] == [2, 3]
    assert added[0].text == "C is open source."
    assert (added[0].mark, added[0].kind, added[0].implied_by) == ("user_added", "explicit", CLAIM)


def test_apply_edits_is_pure():
    proposed = [statement(0)]
    apply_edits(CLAIM, proposed, [Edit(op="edit", id=0, value="changed")])
    assert proposed[0].text == "A beats B on benchmarks." and proposed[0].mark == "confirmed"


def test_apply_edits_unknown_id_raises():
    with pytest.raises(ValueError):
        apply_edits(CLAIM, [statement(0)], [Edit(op="drop", id=9, value=None)])


def test_check_statements_pass_and_fail():
    confirmed = apply_edits(
        CLAIM,
        [statement(0), statement(1, text="B is cheaper.", implied_by="B is cheaper.")],
        [Edit(op="edit", id=1, value="B is probably cheaper."), Edit(op="add", id=None, value="C is open.")],
    )
    client = FakeClient(
        [
            FalsifiabilityOutput(falsifiable=False, reason="hedge word", query=""),
            FalsifiabilityOutput(falsifiable=True, reason="ok", query="C open source weights"),
        ]
    )
    result, issues, usages = check_statements(confirmed, client, "opus", "high")
    assert issues == [Issue(statement_id=1, reason="hedge word")]
    assert len(client.calls) == 2 and len(usages) == 2
    assert client.calls[0].user == "B is probably cheaper."
    assert client.calls[0].model == "opus" and client.calls[0].effort == "high"
    by_id = {s.id: s for s in result.statements}
    assert by_id[2].query == "C open source weights"
    assert by_id[1].query == confirmed.statements[1].query
    assert by_id[0].query == "a b"


def test_check_statements_skips_confirmed():
    client = FakeClient([])
    result, issues, usages = check_statements(confirmed_of(statement(0)), client, "m", None)
    assert (issues, usages, client.calls) == ([], [], [])
    assert result.statements[0].query == "a b"


@pytest.fixture(scope="module")
def full_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "index.sqlite"
    build_index(load_corpus(COMMITTED), path)
    return path


def v6_confirmed():
    return ConfirmedStatements.model_validate_json((V6 / "confirmed.json").read_text())


def v6_output():
    verdicts = json.loads((V6 / "verdicts.json").read_text())
    items = [
        VerdictOutputItem(
            id=s["id"],
            evidence=[Evidence(**e) for e in s["evidence"]],
            verdict=s["verdict"],
            reason=s["reason"],
        )
        for s in verdicts["statements"]
    ]
    return VerdictsOutput(statements=items)


def test_verify_one_call_with_each_statements_passages(full_db):
    confirmed = v6_confirmed()
    client = FakeClient([v6_output()])
    verdicts, usage = verify(confirmed, full_db, client, "sonnet", "high")
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call.model == "sonnet" and call.effort == "high" and call.schema is VerdictsOutput
    assert "each with its own passages" in call.system
    for s in confirmed.statements:
        assert f'<statement id="{s.id}" load_bearing="true">{s.text}</statement>' in call.user
        assert f'<passages statement="{s.id}">' in call.user
    assert '<passage id="2401.18058v1#7" doc_id="2401.18058v1"' in call.user
    assert isinstance(verdicts, Verdicts)
    assert [sv.verdict for sv in verdicts.statements] == ["supported", "contradicted"]
    s0 = confirmed.statements[0]
    assert verdicts.statements[0].queries == [f"{s0.text} {s0.query}", confirmed.claim]
    assert usage.model == "sonnet"


def test_statement_queries_add_the_claim_unless_it_is_the_same_text():
    s = v6_confirmed().statements[0]
    assert statement_queries(s, "the claim") == [f"{s.text} {s.query}", "the claim"]
    assert statement_queries(s, f" {s.text} {s.query} ") == [f"{s.text} {s.query}"]


def test_verify_shows_each_statement_the_passages_its_claim_search_finds(full_db):
    statement = Statement(
        id=0,
        text="Language model performance on tasks requiring use of a specific detail from a long input degrades "
        "when that detail is placed in the middle of the input rather than at its start or end.",
        load_bearing=True,
        implied_by="details get lost in the middle",
        query="U-shaped performance curve primacy recency bias long-context LLM multi-document question "
        "answering key-value retrieval",
        kind="explicit",
        mark="confirmed",
    )
    confirmed = ConfirmedStatements(
        claim="on long context, details get lost in the middle",
        statements=[statement],
        proposed=[statement],
        edits=[],
        rounds=1,
        source="chat",
    )
    output = VerdictsOutput(
        statements=[VerdictOutputItem(id=0, evidence=[], verdict="unknown", reason="r")]
    )
    client = FakeClient([output])
    verify(confirmed, full_db, client, "m", None)
    assert '<passage id="2307.03172v3#3"' in client.calls[0].user
    assert '<passage id="2406.16008v2#0"' in client.calls[0].user


def test_verify_rejects_missing_id(full_db):
    partial = VerdictsOutput(statements=v6_output().statements[:1])
    with pytest.raises(LLMError):
        verify(v6_confirmed(), full_db, FakeClient([partial]), "m", None)


def review_output(flagged=()):
    return ReviewOutput(dimensions=dimensions(), flagged=list(flagged))


def v6_pipeline_inputs(db):
    from fact_checker.finalize import _finalize_with_results

    confirmed = v6_confirmed()
    verdicts, _ = verify(confirmed, db, FakeClient([v6_output()]), "m", None)
    final, results = _finalize_with_results(confirmed, verdicts, db)
    return confirmed, verdicts, final, results


def test_review_uses_parse_scores(full_db):
    confirmed, verdicts, final, results = v6_pipeline_inputs(full_db)
    flag = Flag(statement_id=1, dimension="overreach", reason="r")
    client = FakeClient([review_output([flag])])
    scores, _ = review(confirmed, verdicts, final, results, client, "sol")
    assert scores.model == "sol" and scores.needs_attention is True and scores.flagged == [flag]
    call = client.calls[0]
    assert call.schema is ReviewOutput and call.model == "sol"
    assert "evidence_relevance" in call.system
    for marker in ("transcript.md", "trace.jsonl", "checks.json", "final.json"):
        assert marker in call.user
    assert "2401.18058v1#7" in call.user


def test_review_clean_scores_need_no_attention(full_db):
    args = v6_pipeline_inputs(full_db)
    scores, _ = review(*args, FakeClient([review_output()]), "sol")
    assert scores.needs_attention is False


def test_review_custom_rubric_path(full_db, tmp_path):
    rubric = tmp_path / "rubric.md"
    rubric.write_text("MY RUBRIC")
    client = FakeClient([review_output()])
    review(*v6_pipeline_inputs(full_db), client, "sol", rubric_path=rubric)
    assert client.calls[0].system == "MY RUBRIC"


def test_review_unknown_flag_id_is_llm_error(full_db):
    flag = Flag(statement_id=99, dimension="overreach", reason="r")
    with pytest.raises(LLMError):
        review(*v6_pipeline_inputs(full_db), FakeClient([review_output([flag])]), "sol")


def settings():
    return Settings(verify_model="sonnet", verify_effort="high", review_model="sol")


def test_run_check_happy_path(full_db):
    result = run_check(v6_confirmed(), full_db, FakeClient([v6_output()]), FakeClient([review_output()]), settings())
    assert result.final.overall.verdict == "contradicted"
    assert result.scores is not None and result.review_error is None
    assert [e.step for e in result.events] == ["verify", "finalize", "review"]
    assert all(e.ok for e in result.events)
    assert result.events[0].model == "sonnet" and result.events[2].model == "sol"
    digest = hashlib.sha256(result.final.model_dump_json().encode()).hexdigest()
    assert result.events[1].final_sha256 == digest
    assert "2401.18058v1" in result.events[1].doc_ids


def test_run_check_review_failure_keeps_verdicts(full_db):
    ok = run_check(v6_confirmed(), full_db, FakeClient([v6_output()]), FakeClient([review_output()]), settings())
    failed = run_check(v6_confirmed(), full_db, FakeClient([v6_output()]), FakeClient([LLMError("down")]), settings())
    assert failed.scores is None and "down" in failed.review_error
    assert failed.verdicts == ok.verdicts and failed.final == ok.final
    assert failed.events[-1].step == "review" and failed.events[-1].ok is False


def test_prompts_are_packaged():
    from fact_checker.services.loader import load_prompt

    runbook = (ROOT.parent / "docs" / "RUNBOOK.md").read_text()
    assert load_prompt("decompose").strip() in runbook
    for name in ("falsifiable", "verify"):
        assert load_prompt(name).strip()


def test_decompose_statement_zero_is_always_load_bearing():
    out = DecomposeOutput(statements=[decomposed("A beats B.", CLAIM, load_bearing=False)])
    statements, _ = decompose(CLAIM, FakeClient([out]), "opus", "high")
    assert statements[0].load_bearing is True


def test_review_rubric_is_packaged_and_matches_the_codex_rubric():
    from fact_checker.services.loader import load_prompt

    root = Path(__file__).resolve().parents[1]
    packaged = load_prompt("review")
    assert packaged == (root / ".claude" / "review-passes" / "judge.md").read_text()
