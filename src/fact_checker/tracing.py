"""Tracing of one run: a Tracer writes spans to the store, and a TracingClient records each model call."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from fact_checker.llm.base import LLMClient, Usage
from fact_checker.store import Span, add_span, next_seq, now_iso


class SpanHandle:
    """What a span body sets: its output, its usage and, if known only afterwards, its model."""

    def __init__(self, span_id: str, model: str | None) -> None:
        """Start a handle for the span with this id; output and usage are None until set."""
        self.id = span_id
        self.model = model
        self.output: Any = None
        self.usage: Any = None


class Tracer:
    """Writes the spans of one run, numbering them in the order they start."""

    def __init__(self, db: Path, run_id: str) -> None:
        """Trace run_id into db; numbering continues after the spans the run already has."""
        self._db = db
        self._run_id = run_id
        self._seq = next_seq(db, run_id)

    def _take_seq(self) -> int:
        seq = self._seq
        self._seq += 1
        return seq

    @contextmanager
    def span(
        self, kind: str, name: str, input: Any, parent_id: str | None = None, model: str | None = None
    ) -> Iterator[SpanHandle]:
        """Record a span around the with-body; the body sets output, usage and model on the handle.

        The span is stored on exit with status ok, or with status error and the error text when the body
        raises; the exception is re-raised.
        """
        seq = self._take_seq()
        handle = SpanHandle(f"{self._run_id}-{seq}", model)
        started = now_iso()
        status, error = "ok", None
        try:
            yield handle
        except Exception as exc:
            status, error = "error", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            add_span(
                self._db,
                Span(
                    id=handle.id,
                    run_id=self._run_id,
                    parent_id=parent_id,
                    seq=seq,
                    kind=kind,
                    name=name,
                    started_at=started,
                    ended_at=now_iso(),
                    status=status,
                    model=handle.model,
                    input=input,
                    output=handle.output,
                    usage=handle.usage,
                    error=error,
                ),
            )

    def record(
        self,
        kind: str,
        name: str,
        input: Any,
        output: Any,
        parent_id: str | None = None,
        model: str | None = None,
        usage: Any = None,
    ) -> None:
        """Record an instant span that has no body."""
        with self.span(kind, name, input, parent_id, model) as handle:
            handle.output = output
            handle.usage = usage


class TracingClient:
    """An LLMClient that records one llm span per call and otherwise behaves as the client it wraps."""

    def __init__(self, inner: LLMClient, tracer: Tracer, name: str) -> None:
        """Wrap inner; every call becomes an llm span called name."""
        self._inner = inner
        self._tracer = tracer
        self._name = name

    def complete[T: BaseModel](
        self, system: str, user: str, schema: type[T], model: str, effort: str | None = None
    ) -> tuple[T, Usage]:
        """Call the wrapped client and record the span; errors are recorded and re-raised."""
        request = {"system": system, "user": user, "schema": schema.__name__, "model": model, "effort": effort}
        with self._tracer.span("llm", self._name, request, model=model) as handle:
            result, usage = self._inner.complete(system, user, schema, model, effort)
            handle.output = {"parsed": result.model_dump(), "raw": usage.raw_text or result.model_dump_json()}
            handle.usage = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "seconds": usage.seconds,
                "served_model": usage.model,
            }
        return result, usage
