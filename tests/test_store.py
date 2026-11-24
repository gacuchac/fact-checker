import sqlite3

import pytest
from pipeline_helpers import COMMITTED

from fact_checker.corpus import load_corpus
from fact_checker.index import build_index
from fact_checker.store import (
    Span,
    add_span,
    count_runs_since,
    create_run,
    get_run,
    init_store,
    list_runs,
    list_spans,
    update_run,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "f.sqlite"
    init_store(path)
    return path


def span(run_id, seq, **kw):
    fields = {
        "id": f"s{seq}",
        "run_id": run_id,
        "parent_id": None,
        "seq": seq,
        "kind": "code",
        "name": f"n{seq}",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:00:01+00:00",
        "status": "ok",
        "model": None,
        "input": {"a": 1},
        "output": {"b": [1, 2]},
        "usage": None,
        "error": None,
    }
    return Span(**{**fields, **kw})


def test_create_and_get_run(db):
    run_id = create_run(db, "a claim")
    run = get_run(db, run_id)
    assert run.id == run_id and run.claim == "a claim" and run.status == "proposed"
    assert run.proposed is None and run.confirmed is None and run.result is None and run.error is None
    assert run.created_at == run.updated_at
    assert get_run(db, "missing") is None


def test_update_run_round_trips_json_and_touches_updated_at(db):
    run_id = create_run(db, "c")
    before = get_run(db, run_id)
    update_run(db, run_id, status="verifying", proposed=[{"id": 0}], result={"x": [1]}, error="boom")
    run = get_run(db, run_id)
    assert run.status == "verifying" and run.proposed == [{"id": 0}] and run.result == {"x": [1]}
    assert run.error == "boom"
    assert run.updated_at >= before.updated_at


def test_update_run_rejects_bad_status_field_and_unknown_run(db):
    run_id = create_run(db, "c")
    with pytest.raises(ValueError):
        update_run(db, run_id, status="nope")
    with pytest.raises(ValueError):
        update_run(db, run_id, claim="other")
    with pytest.raises(KeyError):
        update_run(db, "missing", status="done")


def test_list_runs_newest_first_with_limit(db):
    ids = [create_run(db, f"c{i}") for i in range(3)]
    update_run(db, ids[0], status="done")
    summaries = list_runs(db)
    assert [s.id for s in summaries] == ids[::-1]
    assert {s.id: s.status for s in summaries}[ids[0]] == "done"
    assert len(list_runs(db, limit=2)) == 2
    assert not hasattr(summaries[0], "result")


def test_spans_round_trip_ordered_by_seq(db):
    run_id = create_run(db, "c")
    other = create_run(db, "d")
    add_span(db, span(run_id, 2, parent_id="s0", model="m", usage={"input_tokens": 3}, error="e", status="error"))
    add_span(db, span(run_id, 0))
    add_span(db, span(run_id, 1))
    add_span(db, span(other, 0, id="other"))
    spans = list_spans(db, run_id)
    assert [s.seq for s in spans] == [0, 1, 2]
    last = spans[2]
    assert last.parent_id == "s0" and last.model == "m" and last.usage == {"input_tokens": 3}
    assert last.status == "error" and last.error == "e"
    assert spans[0].input == {"a": 1} and spans[0].output == {"b": [1, 2]}
    assert list_spans(db, "missing") == []


def test_count_runs_since(db):
    create_run(db, "c")
    assert count_runs_since(db, "2000-01-01T00:00:00+00:00") == 1
    assert count_runs_since(db, "2999-01-01T00:00:00+00:00") == 0


def test_init_store_is_idempotent_and_keeps_runs(db):
    run_id = create_run(db, "c")
    init_store(db)
    assert get_run(db, run_id) is not None


def test_init_store_does_not_touch_docs_and_passages(tmp_path):
    path = tmp_path / "f.sqlite"
    stats = build_index(load_corpus(COMMITTED), path)
    init_store(path)
    con = sqlite3.connect(path)
    docs = con.execute("SELECT count(*) FROM docs").fetchone()[0]
    passages = con.execute("SELECT count(*) FROM passages").fetchone()[0]
    con.close()
    assert (docs, passages) == (stats.docs, stats.passages)
    run_id = create_run(path, "c")
    build_index(load_corpus(COMMITTED), path)
    assert get_run(path, run_id) is not None


def test_transition_status_is_atomic(tmp_path):
    from fact_checker.store import transition_status

    db = tmp_path / "s.sqlite"
    init_store(db)
    run_id = create_run(db, "c")
    update_run(db, run_id, status="confirmed")
    assert transition_status(db, run_id, "confirmed", "verifying") is True
    assert transition_status(db, run_id, "confirmed", "verifying") is False
    assert get_run(db, run_id).status == "verifying"


def test_count_runs_since_can_filter_by_status(tmp_path):
    db = tmp_path / "s.sqlite"
    init_store(db)
    a, _ = create_run(db, "a"), create_run(db, "b")
    update_run(db, a, status="done")
    assert count_runs_since(db, "2000-01-01T00:00:00+00:00") == 2
    assert count_runs_since(db, "2000-01-01T00:00:00+00:00", statuses=("verifying", "done", "failed")) == 1
