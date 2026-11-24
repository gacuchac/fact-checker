import json
from pathlib import Path

import pytest
import yaml

from fact_checker.cli import main
from fact_checker.contracts import ConfirmedStatements, FinalAnswer
from fact_checker.evals import case_to_confirmed, score_runs

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
    assert [f.stem for f in files] == ["V1", "V2", "V3", "V4", "V5", "V6"]
    for f in files:
        case = yaml.safe_load(f.read_text())
        assert case["id"] == f.stem
        assert case["mode"] == "statements"
        confirmed = case_to_confirmed(case)
        assert confirmed.source == "case"
        assert len(confirmed.statements) == len(case["factcheck"]["statements"])


def test_us14_duplicate_statement_ids_do_not_cover_a_missing_gold_statement():
    final = _final("contradicted", [_fstmt(0, "supported"), _fstmt(0, "supported")])
    assert score_runs([CASE_A], {"A": final}).rows[0].statements_correct == 1


def test_us14_eval_prepare_clears_stale_run_outputs(tmp_path):
    cases, out = tmp_path / "cases", tmp_path / "out"
    _write_cases(cases)
    stale = ("verdicts.json", "final.json", "scores.json", "transcript.md", "trace.jsonl", "checks.json", "events.jsonl")
    (out / "A").mkdir(parents=True)
    for name in stale:
        (out / "A" / name).write_text("old")
    assert main(["eval", "prepare", str(cases), str(out)]) == 0
    assert sorted(p.name for p in (out / "A").iterdir()) == ["confirmed.json"]
