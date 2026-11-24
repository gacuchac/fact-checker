import hashlib
import json
import shutil
from pathlib import Path

import pytest

from fact_checker.cli import main
from fact_checker.contracts import FinalAnswer, JudgeScores
from fact_checker.index import build_index
from fact_checker.report import render_answer

ROOT = Path(__file__).parent
SPIKE6 = ROOT / "fixtures" / "spike6"
REPORT = ROOT / "fixtures" / "report"
COMMITTED = ROOT.parent / "data" / "corpus.json"
QUERY = "relevant information in the middle of long contexts"

pytestmark = pytest.mark.integration


@pytest.fixture
def full_db(tmp_path):
    from fact_checker.corpus import load_corpus

    path = tmp_path / "index.sqlite"
    build_index(load_corpus(COMMITTED), path)
    return path


def make_run(tmp_path, case="V1"):
    run = tmp_path / "run"
    run.mkdir()
    for name in ("confirmed.json", "verdicts.json"):
        shutil.copy(SPIKE6 / case / name, run / name)
    return run


def events(run):
    path = run / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_us11_validate_appends_one_line_with_rounds_edits_model(tmp_path):
    run = make_run(tmp_path)
    assert main(["validate", str(run), "confirmed", "--model", "sonnet-5.5"]) == 0
    lines = events(run)
    assert len(lines) == 1
    assert {"ts", "cmd", "ok", "rounds", "edits", "model"} <= set(lines[0])
    assert lines[0]["cmd"] == "validate"
    assert lines[0]["ok"] is True
    assert lines[0]["model"] == "sonnet-5.5"
    assert lines[0]["rounds"] == 1
    assert lines[0]["edits"] == 0


def test_us11_validate_without_model_logs_null(tmp_path):
    run = make_run(tmp_path)
    assert main(["validate", str(run), "confirmed"]) == 0
    assert events(run)[0]["model"] is None


def test_us11_validate_invalid_logs_ok_false_exit_1(tmp_path):
    run = make_run(tmp_path)
    data = json.loads((run / "confirmed.json").read_text())
    data["statements"][0]["implied_by"] = "text that is not in the claim"
    (run / "confirmed.json").write_text(json.dumps(data))
    assert main(["validate", str(run), "confirmed"]) == 1
    lines = events(run)
    assert len(lines) == 1
    assert lines[0]["ok"] is False


def test_us11_retrieve_run_appends_doc_ids(tmp_path, full_db, capsys):
    run = make_run(tmp_path)
    assert main(["retrieve", QUERY, "--json", "--db", str(full_db), "--run", str(run)]) == 0
    printed = json.loads(capsys.readouterr().out)
    lines = events(run)
    assert len(lines) == 1
    assert lines[0]["cmd"] == "retrieve"
    assert lines[0]["doc_ids"] == [h["doc_id"] for h in printed["hits"]]


def test_us11_retrieve_run_missing_index_logs_ok_false(tmp_path):
    run = make_run(tmp_path)
    assert main(["retrieve", QUERY, "--db", str(tmp_path / "none.sqlite"), "--run", str(run)]) == 1
    assert [e["ok"] for e in events(run)] == [False]


def test_us11_retrieve_without_run_writes_no_events(tmp_path, full_db):
    run = make_run(tmp_path)
    assert main(["retrieve", QUERY, "--db", str(full_db)]) == 0
    assert not (run / "events.jsonl").exists()
    assert not list(tmp_path.rglob("events.jsonl"))


def test_us11_finalize_writes_files_and_sha_matches(tmp_path, full_db):
    run = make_run(tmp_path)
    assert main(["finalize", str(run), "--db", str(full_db)]) == 0
    for name in ("final.json", "transcript.md", "trace.jsonl", "checks.json"):
        assert (run / name).exists(), name
    FinalAnswer.model_validate_json((run / "final.json").read_text())
    lines = events(run)
    assert len(lines) == 1
    assert lines[0]["cmd"] == "finalize"
    assert lines[0]["ok"] is True
    assert lines[0]["final_sha256"] == sha(run / "final.json")


def test_us11_finalize_bad_verdicts_exit_1_no_final(tmp_path, full_db):
    run = make_run(tmp_path, "V6")
    data = json.loads((run / "verdicts.json").read_text())
    data["statements"].pop()
    (run / "verdicts.json").write_text(json.dumps(data))
    assert main(["finalize", str(run), "--db", str(full_db)]) == 1
    assert not (run / "final.json").exists()
    lines = events(run)
    assert len(lines) == 1
    assert lines[0]["ok"] is False
    assert "final_sha256" not in lines[0]


def test_us11_finalize_missing_index_exit_1_no_final(tmp_path, capsys):
    run = make_run(tmp_path)
    assert main(["finalize", str(run), "--db", str(tmp_path / "none.sqlite")]) == 1
    assert "index not found" in capsys.readouterr().err
    assert not (run / "final.json").exists()
    assert [e["ok"] for e in events(run)] == [False]


def test_us11_show_prints_render_and_sha_matches(tmp_path, full_db, capsys):
    run = make_run(tmp_path)
    main(["finalize", str(run), "--db", str(full_db)])
    capsys.readouterr()
    assert main(["show", str(run)]) == 0
    out = capsys.readouterr().out
    final = FinalAnswer.model_validate_json((run / "final.json").read_text())
    assert out == render_answer(final, None)
    assert "not judged" in out
    lines = events(run)
    assert lines[-1]["cmd"] == "show"
    assert lines[-1]["final_sha256"] == lines[0]["final_sha256"] == sha(run / "final.json")


def test_us11_show_with_scores_json(tmp_path, full_db, capsys):
    run = make_run(tmp_path)
    main(["finalize", str(run), "--db", str(full_db)])
    shutil.copy(REPORT / "scores.json", run / "scores.json")
    capsys.readouterr()
    assert main(["show", str(run)]) == 0
    out = capsys.readouterr().out
    assert "not judged" not in out
    final = FinalAnswer.model_validate_json((run / "final.json").read_text())
    scores = JudgeScores.model_validate_json((run / "scores.json").read_text())
    assert out == render_answer(final, scores)


def test_us11_show_invalid_scores_exit_1(tmp_path, full_db):
    run = make_run(tmp_path)
    main(["finalize", str(run), "--db", str(full_db)])
    (run / "scores.json").write_text('{"schema_version": 1}')
    assert main(["show", str(run)]) == 1
    assert events(run)[-1]["ok"] is False


def test_us11_show_missing_final_exit_1(tmp_path):
    run = make_run(tmp_path)
    assert main(["show", str(run)]) == 1
    lines = events(run)
    assert len(lines) == 1
    assert lines[0]["ok"] is False


def test_us11_each_command_appends_exactly_one_line(tmp_path, full_db):
    run = make_run(tmp_path)
    assert main(["validate", str(run), "confirmed"]) == 0
    assert main(["retrieve", QUERY, "--db", str(full_db), "--run", str(run)]) == 0
    assert main(["finalize", str(run), "--db", str(full_db)]) == 0
    assert main(["show", str(run)]) == 0
    assert [e["cmd"] for e in events(run)] == ["validate", "retrieve", "finalize", "show"]


def test_us11_event_ts_is_utc_iso(tmp_path):
    run = make_run(tmp_path)
    main(["validate", str(run), "confirmed"])
    assert events(run)[0]["ts"].endswith("Z")
    assert len(events(run)[0]["ts"]) == len("2026-11-24T00:00:00Z")


def test_us11_missing_run_dir_exit_1_no_file(tmp_path):
    run = tmp_path / "nope"
    assert main(["show", str(run)]) == 1
    assert not run.exists()


def test_us11_run_files_trace_one_line_per_query(tmp_path, full_db):
    run = make_run(tmp_path, "V6")
    assert main(["finalize", str(run), "--db", str(full_db)]) == 0
    trace = [json.loads(line) for line in (run / "trace.jsonl").read_text().splitlines()]
    assert len(trace) == 2
    assert {"statement_id", "query", "passage_ids", "doc_ids"} <= set(trace[0])
    assert [t["statement_id"] for t in trace] == [0, 1]
    checks = json.loads((run / "checks.json").read_text())
    assert len(checks["statements"]) == 2
    assert all("kept" in q for st in checks["statements"] for q in st["quotes"])
    assert all(q["kept"] is True for st in checks["statements"] for q in st["quotes"])
    assert checks["overall"]["verdict"] == "contradicted"


def test_fc02_failed_refinalize_leaves_no_stale_files_and_show_fails(tmp_path, full_db):
    run = make_run(tmp_path)
    assert main(["finalize", str(run), "--db", str(full_db)]) == 0
    (run / "verdicts.json").write_text("{}")
    assert main(["finalize", str(run), "--db", str(full_db)]) == 1
    for name in ("final.json", "scores.json", "transcript.md", "trace.jsonl", "checks.json"):
        assert not (run / name).exists(), name
    assert main(["show", str(run)]) == 1


def test_fc02_refinalize_drops_older_scores(tmp_path, full_db, capsys):
    run = make_run(tmp_path)
    assert main(["finalize", str(run), "--db", str(full_db)]) == 0
    shutil.copy(REPORT / "scores.json", run / "scores.json")
    assert main(["finalize", str(run), "--db", str(full_db)]) == 0
    assert not (run / "scores.json").exists()
    capsys.readouterr()
    assert main(["show", str(run)]) == 0
    assert "not judged" in capsys.readouterr().out


def test_fc02_finalize_retrieves_each_query_once_and_trace_matches(tmp_path, full_db, monkeypatch):
    from fact_checker import finalize as finalize_module

    calls = []
    real = finalize_module.retrieve

    def counting(db, query, *args, **kwargs):
        calls.append(query)
        return real(db, query, *args, **kwargs)

    monkeypatch.setattr(finalize_module, "retrieve", counting)
    run = make_run(tmp_path, "V6")
    assert main(["finalize", str(run), "--db", str(full_db)]) == 0
    trace = [json.loads(line) for line in (run / "trace.jsonl").read_text().splitlines()]
    assert sorted(calls) == sorted(t["query"] for t in trace)
