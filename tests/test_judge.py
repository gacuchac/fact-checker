import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fact_checker.cli import main
from fact_checker.contracts import JudgeScores

ROOT = Path(__file__).parent
PROJECT = ROOT.parent
REPORT = ROOT / "fixtures" / "report"
DIMENSIONS = (
    "evidence_relevance",
    "statement_verdicts",
    "overreach",
    "conflict_handling",
    "aggregation",
    "unknown_calibration",
)
HEADER = "<!-- pass: judge | model: gpt-6-sol | 2026-11-24 -->\n"


def sol_output(scores=None, flagged=(), header=True, fence=True):
    base = dict.fromkeys(DIMENSIONS, 4)
    base.update(scores or {})
    body = {
        "dimensions": {d: {"score": s, "evidence": f"{d} note"} for d, s in base.items()},
        "flagged": list(flagged),
    }
    text = json.dumps(body, indent=2)
    if fence:
        text = f"```json\n{text}\n```\n"
    return (HEADER if header else "") + text


@pytest.fixture
def run(tmp_path):
    path = tmp_path / "run"
    path.mkdir()
    shutil.copy(REPORT / "final.json", path / "final.json")
    (path / "transcript.md").write_text("transcript")
    (path / "trace.jsonl").write_text("{}\n")
    (path / "checks.json").write_text("{}")
    return path


@pytest.fixture
def codex(monkeypatch):
    calls = []
    state = {"stdout": sol_output(), "returncode": 0}

    def fake_run(cmd, *args, **kwargs):
        calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, state["returncode"], state["stdout"], "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.delenv("FC_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("FC_CODEX_REVIEW", raising=False)
    codex_state = state
    codex_state["calls"] = calls
    return codex_state


def events(run):
    path = run / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def judge_ok(run, codex, stdout):
    codex["stdout"] = stdout
    assert main(["judge", str(run)]) == 0
    return JudgeScores.model_validate_json((run / "scores.json").read_text())


def test_us12_header_and_fence_output_parses_into_scores(run, codex):
    flag = {"statement_id": 1, "dimension": "overreach", "reason": "too strong"}
    scores = judge_ok(run, codex, sol_output({"aggregation": 3}, [flag]))
    assert scores.model == "gpt-6-sol"
    assert scores.seconds >= 0
    assert scores.dimensions.aggregation.score == 3
    assert scores.dimensions.overreach.evidence == "overreach note"
    assert [(f.statement_id, f.dimension) for f in scores.flagged] == [(1, "overreach")]
    last = events(run)[-1]
    assert last["cmd"] == "judge"
    assert last["ok"] is True


def test_us12_plain_json_without_header_or_fence_parses(run, codex):
    scores = judge_ok(run, codex, sol_output(header=False, fence=False))
    assert scores.dimensions.evidence_relevance.score == 4


FLAG = {"statement_id": 0, "dimension": "conflict_handling", "reason": "r"}


@pytest.mark.parametrize(
    ("scores", "flagged", "expected"),
    [
        ({}, [FLAG], True),
        ({"statement_verdicts": 2}, [], True),
        ({"overreach": 2}, [], True),
        ({"evidence_relevance": 2}, [], True),
        ({"statement_verdicts": 1}, [], True),
        ({"statement_verdicts": 3, "overreach": 3, "evidence_relevance": 3}, [], False),
        ({}, [], False),
        ({"conflict_handling": 1}, [], False),
        ({"aggregation": 2, "unknown_calibration": 2}, [], False),
    ],
)
def test_us12_needs_attention_truth_table(run, codex, scores, flagged, expected):
    result = judge_ok(run, codex, sol_output(scores, flagged))
    assert result.needs_attention is expected


def bad_outputs():
    def with_dims(mutate):
        data = json.loads(sol_output(fence=False, header=False))
        mutate(data)
        return json.dumps(data)

    flag = {"statement_id": 99, "dimension": "overreach", "reason": "r"}
    bad_dim_flag = {"statement_id": 0, "dimension": "vibes", "reason": "r"}
    return {
        "score_0": sol_output({"overreach": 0}),
        "score_6": sol_output({"overreach": 6}),
        "unknown_dimension": with_dims(lambda d: d["dimensions"].update(vibes={"score": 3, "evidence": "e"})),
        "missing_dimension": with_dims(lambda d: d["dimensions"].pop("aggregation")),
        "unknown_statement_id": sol_output(flagged=[flag]),
        "unknown_flag_dimension": sol_output(flagged=[bad_dim_flag]),
        "not_json": "I could not decide, sorry.",
    }


@pytest.mark.parametrize("name", list(bad_outputs()))
def test_us12_invalid_output_exit_1_no_scores_event_not_ok(run, codex, name):
    codex["stdout"] = bad_outputs()[name]
    assert main(["judge", str(run)]) == 1
    assert not (run / "scores.json").exists()
    last = events(run)[-1]
    assert last["cmd"] == "judge"
    assert last["ok"] is False


def test_us12_nonzero_subprocess_exit_fails(run, codex):
    codex["returncode"] = 2
    assert main(["judge", str(run)]) == 1
    assert not (run / "scores.json").exists()
    assert events(run)[-1]["ok"] is False


def test_us12_missing_final_json_exit_1(run, codex):
    (run / "final.json").unlink()
    assert main(["judge", str(run)]) == 1
    assert not (run / "scores.json").exists()
    assert events(run)[-1]["ok"] is False
    assert codex["calls"] == []


def test_us12_codex_called_with_project_cwd_model_and_context_files(run, codex):
    judge_ok(run, codex, sol_output())
    assert len(codex["calls"]) == 1
    cmd, kwargs = codex["calls"][0]
    assert Path(kwargs["cwd"]).resolve() == PROJECT.resolve()
    assert cmd[cmd.index("--model") + 1] == "gpt-6-sol"
    assert "judge" in cmd
    context = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--context-file"]
    expected = [run / n for n in ("final.json", "transcript.md", "trace.jsonl", "checks.json")]
    assert [Path(c).resolve() for c in context] == [p.resolve() for p in expected]


def test_us12_success_event_carries_final_sha256_and_model(run, codex):
    judge_ok(run, codex, sol_output())
    last = events(run)[-1]
    assert last["final_sha256"] == hashlib.sha256((run / "final.json").read_bytes()).hexdigest()
    assert last["model"] == "gpt-6-sol"


def test_us12_model_env_override(run, codex, monkeypatch):
    monkeypatch.setenv("FC_JUDGE_MODEL", "other-model")
    scores = judge_ok(run, codex, sol_output())
    cmd = codex["calls"][0][0]
    assert cmd[cmd.index("--model") + 1] == "other-model"
    assert scores.model == "other-model"


def test_us12_failed_judge_removes_stale_scores(run, codex):
    shutil.copy(REPORT / "scores.json", run / "scores.json")
    codex["stdout"] = "not json"
    assert main(["judge", str(run)]) == 1
    assert not (run / "scores.json").exists()


def test_us12_failed_subprocess_removes_stale_scores(run, codex):
    shutil.copy(REPORT / "scores.json", run / "scores.json")
    codex["returncode"] = 1
    assert main(["judge", str(run)]) == 1
    assert not (run / "scores.json").exists()


def test_us12_successful_rejudge_replaces_stale_scores(run, codex):
    shutil.copy(REPORT / "scores.json", run / "scores.json")
    scores = judge_ok(run, codex, sol_output({"aggregation": 5}))
    assert scores.model == "gpt-6-sol"
    assert scores.flagged == []
