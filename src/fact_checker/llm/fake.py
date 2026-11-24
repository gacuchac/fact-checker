"""A scripted LLMClient for tests."""

from collections.abc import Sequence
from typing import NamedTuple

from pydantic import BaseModel

from fact_checker.llm.base import LLMError, Usage


class Call(NamedTuple):
    """One recorded call to the fake client."""

    system: str
    user: str
    schema: type[BaseModel]
    model: str
    effort: str | None


class FakeClient:
    """LLMClient that returns or raises queued items in order and records every call."""

    def __init__(self, responses: Sequence[BaseModel | Exception]) -> None:
        """Queue `responses`: models are returned, exceptions are raised, one per call."""
        self._queue = list(responses)
        self.calls: list[Call] = []

    def complete[T: BaseModel](
        self, system: str, user: str, schema: type[T], model: str, effort: str | None = None
    ) -> tuple[T, Usage]:
        """Record the call, then return or raise the next queued item; LLMError when none is left."""
        self.calls.append(Call(system, user, schema, model, effort))
        if not self._queue:
            raise LLMError("FakeClient has no queued response left")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, schema):
            raise LLMError(f"queued {type(item).__name__} is not a {schema.__name__}")
        return item, Usage(model=model, input_tokens=0, output_tokens=0, seconds=0.0)
