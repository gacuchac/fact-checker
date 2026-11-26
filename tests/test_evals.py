import json
from pathlib import Path

import pytest
import yaml
from pipeline_helpers import review_output, v6_confirmed, v6_output
from test_api import decompose_output

from fact_checker.api.app import Clients
from fact_checker.cli import main
from fact_checker.contracts import ConfirmedStatements, FinalAnswer
from fact_checker.docs import Doc
from fact_checker.evals import (
    ClaimOutcome,
    SecurityCheck,
    case_to_confirmed,
    score_claim_case,
    score_runs,
)
from fact_checker.llm.base import LLMError
from fact_checker.llm.fake import FakeClient

CASES_DIR = Path(__file__).resolve().parents[1] / "evals" / "cases"


def _case(case_id, label, statements, gold_doc_ids):
    return {
        "id": case_id,
        "mode": "statements",
        "factcheck": {
            "claim": " ".join(s["text"] for s in statements),
            "label": label,
            "statements": statements,
            "gold_doc_ids": gold_doc_ids,
        },
    }


def _stmt(text, gold, load_bearing=True):
    return {"text": text, "load_bearing": load_bearing, "query": text, "gold_verdict": gold}


CASE_A = _case(
    "A",
    "contradicted",
    [
        _stmt("Alpha improves recall by thirty percent.", "supported"),
        _stmt("Alpha has no cost at all.", "contradicted", False),
    ],
    ["d1", "d2"],
)
CASE_B = _case("B", "supported", [_stmt("Beta beats gamma on every benchmark.", "supported")], ["d3", "d5"])


def _ev(doc_id, stance="supports"):
    return {
        "doc_id": doc_id,
        "title": "T",
        "authors": ["X"],
        "published": "2024-01-02",
        "quote": "one two three four five six",
        "stance": stance,
    }


def _dropped():
    return {"passage_id": "p#1", "quote": "one two three four five six", "stance": "supports"}


def _fstmt(sid, verdict, evidence=(), dropped=()):
    return {
        "id": sid,
        "text": "t",
        "load_bearing": True,
        "mark": "confirmed",
        "model_verdict": verdict,
        "verdict": verdict,
        "downgrade_reason": None,
        "evidence": list(evidence),
        "dropped_quotes": list(dropped),
    }


def _final(overall, statements):
    return FinalAnswer.model_validate(
        {
            "claim": "c",
            "overall": {"verdict": overall, "rule": 1},
            "statements": statements,
            "counts": {"confirmed": len(statements), "user_edited": 0, "user_added": 0, "dropped": 0},
        }
    )


# A: overall right, both statements right, 3 kept + 1 dropped quote, cites gold d1 (1 of 2) and non-gold d9.
FINAL_A = _final(
    "contradicted",
    [_fstmt(0, "supported", [_ev("d1"), _ev("d1"), _ev("d9")], [_dropped()]), _fstmt(1, "contradicted")],
)
# B: overall wrong, statement wrong, 3 kept + 1 dropped quote, cites gold d3 (1 of 2).
FINAL_B = _final("unknown", [_fstmt(0, "unknown", [_ev("d3"), _ev("d3"), _ev("d3")], [_dropped()])])


def test_us14_case_to_confirmed_builds_case_sourced_statements():
    confirmed = case_to_confirmed(CASE_A)
    assert isinstance(confirmed, ConfirmedStatements)
    assert confirmed.source == "case"
    assert [s.text for s in confirmed.statements] == [
        "Alpha improves recall by thirty percent.",
        "Alpha has no cost at all.",
    ]
    assert [s.load_bearing for s in confirmed.statements] == [True, False]
    assert [s.query for s in confirmed.statements] == [
        "Alpha improves recall by thirty percent.",
        "Alpha has no cost at all.",
    ]
    assert len({s.id for s in confirmed.statements}) == 2
    assert all(s.mark == "confirmed" for s in confirmed.statements)
    for s in confirmed.statements:
        assert s.text in confirmed.claim


def test_us14_score_runs_reports_accuracy_quote_pass_rate_and_recall():
    report = score_runs([CASE_A, CASE_B], {"A": FINAL_A, "B": FINAL_B})
    assert report.accuracy == pytest.approx(1 / 2)
    assert report.statement_accuracy == pytest.approx(2 / 3)
    assert report.quote_pass_rate == pytest.approx(3 / 4)
    assert report.doc_recall == pytest.approx(1 / 2)
    assert len(report.rows) == 2


def test_us14_score_runs_counts_a_missing_final_as_wrong():
    report = score_runs([CASE_A, CASE_B], {"A": FINAL_A, "B": None})
    assert report.accuracy == pytest.approx(1 / 2)
    assert report.statement_accuracy == pytest.approx(2 / 3)
    assert len(report.rows) == 2


def test_us14_score_runs_all_missing_scores_zero_accuracy():
    report = score_runs([CASE_A, CASE_B], {"A": None, "B": None})
    assert report.accuracy == 0
    assert report.statement_accuracy == 0


def _write_cases(directory):
    directory.mkdir()
    for case in (CASE_A, CASE_B):
        (directory / f"{case['id']}.yaml").write_text(yaml.safe_dump(case))


def test_us14_eval_prepare_writes_one_valid_confirmed_per_case(tmp_path):
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_cases(cases)
    assert main(["eval", "prepare", str(cases), str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["A", "B"]
    for case_id, n in (("A", 2), ("B", 1)):
        confirmed = ConfirmedStatements.model_validate_json((out / case_id / "confirmed.json").read_text())
        assert confirmed.source == "case"
        assert len(confirmed.statements) == n


def test_us14_eval_score_prints_report_and_exits_0_with_a_missing_run(tmp_path, capsys):
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_cases(cases)
    (out / "A").mkdir(parents=True)
    (out / "A" / "final.json").write_text(FINAL_A.model_dump_json())
    assert main(["eval", "score", str(cases), str(out)]) == 0
    printed = capsys.readouterr().out
    report, _ = json.JSONDecoder().raw_decode(printed[printed.index("{") :])
    assert 0.5 in report.values()
    assert "A" in printed
    assert "B" in printed


def test_us14_committed_seed_cases_load_and_convert():
    files = sorted(CASES_DIR.glob("V*.yaml"))
    assert [f.stem for f in files] == ["V1", "V2", "V3", "V4", "V5", "V6", "V7"]
    for f in files:
        case = yaml.safe_load(f.read_text())
        assert case["id"] == f.stem
        assert case["mode"] == "statements"
        confirmed = case_to_confirmed(case)
        assert confirmed.source == "case"
        assert len(confirmed.statements) == len(case["factcheck"]["statements"])


def test_case_statement_may_give_its_implied_by_span():
    case = yaml.safe_load((CASES_DIR / "V7.yaml").read_text())
    confirmed = case_to_confirmed(case)
    assert confirmed.claim == "on long context, details get lost in the middle"
    assert [s.implied_by for s in confirmed.statements] == [
        "on long context, details get lost in the middle",
        "details get lost in the middle",
    ]


def test_us14_duplicate_statement_ids_do_not_cover_a_missing_gold_statement():
    final = _final("contradicted", [_fstmt(0, "supported"), _fstmt(0, "supported")])
    assert score_runs([CASE_A], {"A": final}).rows[0].statements_correct == 1


def test_us14_eval_prepare_clears_stale_run_outputs(tmp_path):
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_cases(cases)
    stale = (
        "verdicts.json",
        "final.json",
        "scores.json",
        "transcript.md",
        "trace.jsonl",
        "checks.json",
        "events.jsonl",
    )
    (out / "A").mkdir(parents=True)
    for name in stale:
        (out / "A" / name).write_text("old")
    assert main(["eval", "prepare", str(cases), str(out)]) == 0
    assert sorted(p.name for p in (out / "A").iterdir()) == ["confirmed.json"]


QUOTE = "one two three four five six"


def _claim_case(**security):
    return {"id": "S", "mode": "claim", "factcheck": {"claim": "c", "edits": []}, "security": security}


def _outcome(final=None, **kw):
    result = {"final": final.model_dump(mode="json")} if final is not None else None
    return ClaimOutcome(
        rejected=kw.get("rejected"),
        result=result,
        error=kw.get("error"),
        spans=kw.get("spans", []),
        abstracts=kw.get("abstracts", {}),
        prompts=kw.get("prompts", {}),
        secrets=kw.get("secrets", []),
    )


def _by_name(checks):
    return {c.name: c for c in checks}


def _added(verdict):
    stmt = _fstmt(0, verdict)
    stmt["mark"] = "user_added"
    return _final(verdict, [stmt])


def _kept_quote(doc_id, quote, stance="supports"):
    ev = _ev(doc_id, stance)
    ev["quote"] = quote
    return _fstmt(0, "supported", [ev])


VERDICT_KEY_CASES = {
    "allowed_overall": (
        ["unknown", "contradicted"],
        _outcome(_final("unknown", [_fstmt(0, "unknown")])),
        _outcome(_final("supported", [_fstmt(0, "supported")])),
    ),
    "forbidden_statement_verdicts": (
        ["supported"],
        _outcome(_final("unknown", [_fstmt(0, "unknown")])),
        _outcome(_final("unknown", [_fstmt(0, "unknown"), _fstmt(1, "supported")])),
    ),
    "forbidden_added_verdicts": (
        ["supported"],
        _outcome(_added("unknown")),
        _outcome(_added("supported")),
    ),
    "forbidden_kept_quotes": (
        ["FULLY SOLVED"],
        _outcome(_final("supported", [_kept_quote("d1", QUOTE)])),
        _outcome(_final("supported", [_kept_quote("d1", "the problem is Fully Solved today")])),
    ),
    "forbidden_evidence_docs": (
        ["9999"],
        _outcome(_final("supported", [_fstmt(0, "supported", [_ev("d1")])])),
        _outcome(_final("supported", [_fstmt(0, "supported", [_ev("d1"), _ev("9999")])])),
    ),
    "required_evidence_docs": (
        ["d1"],
        _outcome(_final("supported", [_fstmt(0, "supported", [_ev("d1")])])),
        _outcome(_final("supported", [_fstmt(0, "supported", [_ev("d2")])])),
    ),
    "evidence_doc_stances": (
        {"d9": "contradicts"},
        _outcome(_final("unknown", [_fstmt(0, "unknown", [_ev("d9", "contradicts"), _ev("d1", "supports")])])),
        _outcome(_final("unknown", [_fstmt(0, "unknown", [_ev("d9", "contradicts"), _ev("d9", "supports")])])),
    ),
    "quotes_verbatim": (
        True,
        _outcome(
            _final("supported", [_kept_quote("d1", QUOTE)]),
            abstracts={"d1": "intro " + QUOTE + " outro"},
        ),
        _outcome(
            _final("supported", [_kept_quote("d1", QUOTE)]),
            abstracts={"d1": "intro one two three four seven six outro"},
        ),
    ),
}


@pytest.mark.parametrize("key", sorted(VERDICT_KEY_CASES))
def test_score_claim_case_passes_and_fails_each_verdict_key(key):
    value, passing, failing = VERDICT_KEY_CASES[key]
    case = _claim_case(**{key: value})
    ok = _by_name(score_claim_case(case, passing))
    bad = _by_name(score_claim_case(case, failing))
    assert isinstance(ok[key], SecurityCheck)
    assert ok["completed"].passed and bad["completed"].passed
    assert ok[key].passed
    assert not bad[key].passed


def test_score_claim_case_has_completed_first_then_one_check_per_key():
    case = _claim_case(allowed_overall=["unknown"], forbidden_statement_verdicts=["supported"])
    checks = score_claim_case(case, _outcome(_final("unknown", [_fstmt(0, "unknown")])))
    assert [c.name for c in checks] == ["completed", "allowed_overall", "forbidden_statement_verdicts"]


def test_score_claim_case_rejected_at_confirm():
    outcome = _outcome(None, rejected=[{"issue": "forged passage"}])
    allowed = score_claim_case(_claim_case(confirm_may_reject=True, allowed_overall=["unknown"]), outcome)
    assert all(c.passed for c in allowed)
    refused = _by_name(score_claim_case(_claim_case(allowed_overall=["unknown"]), outcome))
    assert not refused["completed"].passed


def test_score_claim_case_missing_result_fails_completed():
    checks = _by_name(score_claim_case(_claim_case(allowed_overall=["unknown"]), _outcome(None, error="boom")))
    assert not checks["completed"].passed


def test_score_claim_case_rejects_unknown_security_key():
    with pytest.raises(ValueError):
        score_claim_case(_claim_case(allowed_overal=["unknown"]), _outcome(_final("unknown", [_fstmt(0, "unknown")])))


ROOT = Path(__file__).resolve().parents[1]
PROMPT = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
SECRET = "sk-ant-TOPSECRET123456"


def _llm(output=None, error=None, usage=None):
    return {"kind": "llm", "name": "verify", "output": output, "error": error, "usage": usage}


def _hit_span(kind, name, doc_ids):
    return {"kind": kind, "name": name, "output": {"hits": [{"doc_id": d} for d in doc_ids]}, "error": None}


def _with(outcome, **fields):
    data = {**outcome.__dict__, **fields}
    return ClaimOutcome(**data)


def _text_final(text):
    stmt = _fstmt(0, "unknown")
    stmt["text"] = text
    return _final("unknown", [stmt])


def _clean():
    return _outcome(_final("unknown", [_fstmt(0, "unknown")]))


def _with_result(outcome, **extra):
    return _with(outcome, result={**outcome.result, **extra})


LEAKAGE_CASES = {
    "forbidden_in_outputs/llm_output": (
        "forbidden_in_outputs",
        ["sk-[a-z]{3}-"],
        _clean(),
        _with(_clean(), spans=[_llm(output={"text": "key is sk-abc-123"})]),
    ),
    "forbidden_in_outputs/span_error": (
        "forbidden_in_outputs",
        ["leaky"],
        _clean(),
        _with(_clean(), spans=[{"kind": "llm", "name": "v", "output": None, "error": "a leaky failure"}]),
    ),
    "forbidden_in_outputs/result_json": (
        "forbidden_in_outputs",
        ["leaky"],
        _clean(),
        _with_result(_clean(), final_message="a leaky message"),
    ),
    "forbidden_in_outputs/rejected": (
        "forbidden_in_outputs",
        ["leaky"],
        _clean(),
        _with(_outcome(None, rejected=[{"issue": "a leaky issue"}]), result=None),
    ),
    "forbidden_in_outputs/error": (
        "forbidden_in_outputs",
        ["leaky"],
        _clean(),
        _outcome(None, error="a leaky error"),
    ),
    "forbid_secrets/llm_output": (
        "forbid_secrets",
        True,
        _with(_clean(), secrets=[SECRET], spans=[_llm(output={"text": "nothing here"})]),
        _with(_clean(), secrets=[SECRET], spans=[_llm(output={"text": f"echo {SECRET}"})]),
    ),
    "forbid_secrets/error": (
        "forbid_secrets",
        True,
        _with(_outcome(None, error="boom"), secrets=[SECRET]),
        _with(_outcome(None, error=f"boom {SECRET}"), secrets=[SECRET]),
    ),
    "no_prompt_overlap_words/statement": (
        "no_prompt_overlap_words",
        8,
        _with(_outcome(_text_final("alpha bravo charlie delta echo foxtrot golf then more")), prompts={"p": PROMPT}),
        _with(_outcome(_text_final("see: bravo charlie delta echo foxtrot golf hotel india x")), prompts={"p": PROMPT}),
    ),
    "no_prompt_overlap_words/final_message": (
        "no_prompt_overlap_words",
        8,
        _with(_with_result(_clean(), final_message="juliet kilo lima only"), prompts={"p": PROMPT}),
        _with(
            _with_result(_clean(), final_message="x charlie delta echo foxtrot golf hotel india juliet y"),
            prompts={"p": PROMPT},
        ),
    ),
    "no_prompt_overlap_words/llm_output": (
        "no_prompt_overlap_words",
        8,
        _with(_clean(), prompts={"p": PROMPT}, spans=[_llm(output={"t": "alpha bravo charlie delta"})]),
        _with(
            _clean(),
            prompts={"p": PROMPT},
            spans=[_llm(output={"t": "delta echo foxtrot golf hotel india juliet kilo"})],
        ),
    ),
    "required_hit_docs": (
        "required_hit_docs",
        ["d1", "d2"],
        _with(_clean(), spans=[_hit_span("tool", "retrieve", ["d1"]), _hit_span("tool", "retrieve", ["d2", "d3"])]),
        _with(_clean(), spans=[_hit_span("tool", "retrieve", ["d1"]), _hit_span("tool", "other", ["d2"])]),
    ),
}


@pytest.mark.parametrize("name", sorted(LEAKAGE_CASES))
def test_score_claim_case_leakage_keys(name):
    key, value, passing, failing = LEAKAGE_CASES[name]
    case = _claim_case(**{key: value})
    ok = _by_name(score_claim_case(case, passing))
    bad = _by_name(score_claim_case(case, failing))
    assert ok[key].passed
    assert not bad[key].passed


def test_forbid_secrets_detail_never_contains_the_secret():
    failing = _with(_clean(), secrets=[SECRET], spans=[_llm(output={"text": f"echo {SECRET}"})])
    check = _by_name(score_claim_case(_claim_case(forbid_secrets=True), failing))["forbid_secrets"]
    assert not check.passed
    assert SECRET not in check.detail


def _budget_outcome(spans):
    return _with(_clean(), spans=spans)


def test_budgets_count_llm_spans_and_tokens():
    usage = {"input_tokens": 100, "output_tokens": 50}
    spans = [_llm(usage=usage), _llm(usage=usage), {"kind": "tool", "name": "retrieve", "usage": usage, "output": {}}]
    outcome = _budget_outcome(spans)

    def passed(**budgets):
        case = {**_claim_case(allowed_overall=["unknown"]), "budgets": budgets}
        return all(c.passed for c in score_claim_case(case, outcome))

    assert passed(max_llm_calls=2)
    assert not passed(max_llm_calls=1)
    assert passed(max_total_tokens=300)
    assert not passed(max_total_tokens=299)


def test_committed_claim_cases_score_without_unknown_keys():
    empty = ClaimOutcome(rejected=None, result=None, error=None, spans=[], abstracts={}, prompts={}, secrets=[])
    files = sorted(CASES_DIR.glob("S*.yaml"))
    assert len(files) == 9
    for f in files:
        case = yaml.safe_load(f.read_text())
        assert case["mode"] == "claim"
        assert case["factcheck"]["claim"]
        assert score_claim_case(case, empty)
        extra = case["factcheck"].get("extra_docs")
        if extra:
            data = json.loads((ROOT / extra).read_text())
            assert [Doc.model_validate(d) for d in data["docs"]]
    for case_id in ("S01", "S02", "S04", "S09", "S10", "S11", "S12"):
        case = yaml.safe_load((CASES_DIR / f"{case_id}.yaml").read_text())
        assert case["security"]["allowed_overall"]


def _happy_clients(*_):
    return Clients(
        FakeClient([decompose_output()]), FakeClient([]), FakeClient([v6_output()]), FakeClient([review_output()])
    )


def _write_claim_case(directory, **security):
    directory.mkdir(exist_ok=True)
    case = {
        "id": "C1",
        "mode": "claim",
        "factcheck": {"claim": v6_confirmed().claim, "edits": []},
        "security": security,
    }
    (directory / "C1.yaml").write_text(yaml.safe_dump(case))


def test_eval_prepare_and_score_skip_claim_cases(tmp_path, capsys):
    cases, out = tmp_path / "cases", tmp_path / "out"
    cases.mkdir()
    (cases / "A.yaml").write_text(yaml.safe_dump(CASE_A))
    _write_claim_case(cases)
    assert main(["eval", "prepare", str(cases), str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["A"]
    assert main(["eval", "score", str(cases), str(out)]) == 0
    printed = capsys.readouterr().out
    report, _ = json.JSONDecoder().raw_decode(printed[printed.index("{") :])
    assert [row["id"] for row in report["rows"]] == ["A"]


@pytest.mark.parametrize(("security", "exit_code"), [({}, 0), ({"allowed_overall": ["no-such-verdict"]}, 1)])
def test_eval_run_claims_writes_outcome_and_checks_and_exit_code(tmp_path, monkeypatch, security, exit_code):
    monkeypatch.setattr("fact_checker.cli.real_clients", _happy_clients, raising=False)
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_claim_case(cases, **security)
    assert main(["eval", "run-claims", str(cases), str(out)]) == exit_code
    outcome = json.loads((out / "C1" / "outcome.json").read_text())
    assert "final" in outcome["result"]
    assert "secrets" not in outcome
    assert "prompts" not in outcome
    checks = json.loads((out / "C1" / "checks.json").read_text())
    assert checks[0]["name"] == "completed"
    assert all(c["passed"] for c in checks) == (exit_code == 0)


def test_eval_run_claims_never_writes_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr("fact_checker.cli.real_clients", _happy_clients, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-SECRETVALUE")
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_claim_case(cases, forbid_secrets=True)
    main(["eval", "run-claims", str(cases), str(out)])
    written = [p for p in out.rglob("*") if p.is_file()]
    assert written
    assert not any("SECRETVALUE" in p.read_text() for p in written)


def _two_run_clients(*_):
    return Clients(
        FakeClient([decompose_output()] * 2),
        FakeClient([]),
        FakeClient([v6_output()] * 2),
        FakeClient([review_output()] * 2),
    )


def _write_mixed_cases(directory):
    directory.mkdir()
    (directory / "A.yaml").write_text(yaml.safe_dump(CASE_A))
    for case_id in ("C1", "C2"):
        factcheck = {"claim": v6_confirmed().claim, "edits": []}
        case = {"id": case_id, "mode": "claim", "factcheck": factcheck, "security": {}}
        (directory / f"{case_id}.yaml").write_text(yaml.safe_dump(case))


def test_eval_run_claims_runs_only_claim_cases_and_honours_case_filter(tmp_path, monkeypatch):
    monkeypatch.setattr("fact_checker.cli.real_clients", _two_run_clients, raising=False)
    cases = tmp_path / "cases"
    _write_mixed_cases(cases)
    out_all, out_one = tmp_path / "all", tmp_path / "one"
    main(["eval", "run-claims", str(cases), str(out_all)])
    assert sorted(p.name for p in out_all.iterdir()) == ["C1", "C2"]
    main(["eval", "run-claims", str(cases), str(out_one), "--case", "C2"])
    assert sorted(p.name for p in out_one.iterdir()) == ["C2"]


def _leaking_clients(*_):
    leak = LLMError("provider said: letmein-CODE42 is not valid")
    return Clients(FakeClient([leak]), FakeClient([]), FakeClient([]), FakeClient([]))


def test_eval_run_claims_redacts_a_leaked_secret_in_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr("fact_checker.cli.real_clients", _leaking_clients, raising=False)
    monkeypatch.setenv("FC_ACCESS_CODE", "letmein-CODE42")
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_claim_case(cases, forbid_secrets=True)
    assert main(["eval", "run-claims", str(cases), str(out)]) == 1
    outcome = (out / "C1" / "outcome.json").read_text()
    assert "letmein-CODE42" not in outcome
    assert "[redacted secret]" in outcome
    checks = json.loads((out / "C1" / "checks.json").read_text())
    assert not next(c for c in checks if c["name"] == "forbid_secrets")["passed"]


def test_eval_run_claims_unknown_case_id_fails_without_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("fact_checker.cli.real_clients", _two_run_clients, raising=False)
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_mixed_cases(cases)
    assert main(["eval", "run-claims", str(cases), str(out), "--case", "C9"]) == 1
    assert not out.exists() or not any(out.iterdir())
    assert "C9" in capsys.readouterr().err


def test_quotes_verbatim_accepts_a_quote_that_matches_after_normalisation():
    abstract = "We find that Performance   is often HIGHEST when relevant information occurs at the beginning."
    quote = "performance is often highest when relevant information occurs"
    outcome = _outcome(_final("supported", [_kept_quote("d1", quote)]), abstracts={"d1": abstract})
    checks = _by_name(score_claim_case(_claim_case(quotes_verbatim=True), outcome))
    assert checks["quotes_verbatim"].passed


def test_eval_run_claims_redacts_a_leaked_secret_in_checks(tmp_path, monkeypatch):
    monkeypatch.setattr("fact_checker.cli.real_clients", _leaking_clients, raising=False)
    monkeypatch.setenv("FC_ACCESS_CODE", "letmein-CODE42")
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_claim_case(cases, forbid_secrets=True)
    main(["eval", "run-claims", str(cases), str(out)])
    assert "letmein-CODE42" not in (out / "C1" / "checks.json").read_text()
