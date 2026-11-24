import pytest
from pydantic import BaseModel

from fact_checker.llm.base import LLMError, Usage
from fact_checker.llm.fake import FakeClient
from fact_checker.store import create_run, init_store, list_spans
from fact_checker.tracing import Tracer, TracingClient


class Answer(BaseModel):
    value: int


@pytest.fixture
def traced(tmp_path):
    db = tmp_path / "f.sqlite"
    init_store(db)
    run_id = create_run(db, "c")
    return db, run_id, Tracer(db, run_id)


def test_span_records_ok_with_handle_fields(traced):
    db, run_id, tracer = traced
    with tracer.span("code", "step", {"in": 1}, model="m") as handle:
        handle.output = {"out": 2}
        handle.usage = {"input_tokens": 4}
    (recorded,) = list_spans(db, run_id)
    assert (recorded.kind, recorded.name, recorded.status, recorded.model) == ("code", "step", "ok", "m")
    assert recorded.input == {"in": 1} and recorded.output == {"out": 2} and recorded.usage == {"input_tokens": 4}
    assert recorded.started_at <= recorded.ended_at and recorded.error is None and recorded.seq == 0


def test_span_records_error_and_reraises(traced):
    db, run_id, tracer = traced
    with pytest.raises(LLMError), tracer.span("llm", "boom", {}):
        raise LLMError("down")
    (recorded,) = list_spans(db, run_id)
    assert recorded.status == "error" and "down" in recorded.error


def test_nesting_and_seq_follow_start_order(traced):
    db, run_id, tracer = traced
    with tracer.span("code", "outer", {}) as outer:
        with tracer.span("tool", "inner", {}, parent_id=outer.id):
            pass
        tracer.record("system", "instant", {"a": 1}, {"b": 2}, parent_id=outer.id)
    spans = list_spans(db, run_id)
    assert [s.name for s in spans] == ["outer", "inner", "instant"]
    assert spans[1].parent_id == spans[0].id == spans[2].parent_id
    assert spans[2].input == {"a": 1} and spans[2].output == {"b": 2} and spans[2].status == "ok"


def test_new_tracer_continues_the_run_sequence(traced):
    db, run_id, tracer = traced
    tracer.record("user", "a", {}, {})
    Tracer(db, run_id).record("user", "b", {}, {})
    assert [s.seq for s in list_spans(db, run_id)] == [0, 1]


def test_tracing_client_records_system_user_raw_and_usage(traced):
    db, run_id, tracer = traced
    inner = FakeClient([Answer(value=3)])
    client = TracingClient(inner, tracer, "ask")
    result, usage = client.complete("SYS", "USR", Answer, "m1", "high")
    assert result == Answer(value=3) and isinstance(usage, Usage)
    (recorded,) = list_spans(db, run_id)
    assert (recorded.kind, recorded.name, recorded.model, recorded.status) == ("llm", "ask", "m1", "ok")
    assert recorded.input == {"system": "SYS", "user": "USR", "schema": "Answer", "model": "m1", "effort": "high"}
    assert recorded.output["parsed"] == {"value": 3}
    assert recorded.output["raw"] == '{"value":3}'
    assert recorded.usage == {"input_tokens": 0, "output_tokens": 0, "seconds": 0.0, "served_model": "m1"}


def test_tracing_client_uses_raw_text_when_the_client_exposes_it(traced):
    db, run_id, tracer = traced

    class Raw:
        def complete(self, system, user, schema, model, effort=None):
            return Answer(value=1), Usage(model="served", input_tokens=5, output_tokens=6, seconds=1.5, raw_text="RAW")

    TracingClient(Raw(), tracer, "ask").complete("s", "u", Answer, "m")
    (recorded,) = list_spans(db, run_id)
    assert recorded.output["raw"] == "RAW"
    assert recorded.usage == {"input_tokens": 5, "output_tokens": 6, "seconds": 1.5, "served_model": "served"}


def test_tracing_client_records_failures_and_reraises(traced):
    db, run_id, tracer = traced
    client = TracingClient(FakeClient([LLMError("down")]), tracer, "ask")
    with pytest.raises(LLMError):
        client.complete("s", "u", Answer, "m")
    (recorded,) = list_spans(db, run_id)
    assert recorded.status == "error" and "down" in recorded.error and recorded.output is None
