"""Claude client on the official anthropic SDK."""

import os
import time
from typing import Any

import anthropic
from pydantic import BaseModel

from fact_checker.llm.base import (
    LLMError,
    LLMRefusal,
    Usage,
    parse_output,
    strict_json_schema,
)

MAX_TOKENS = 16000
BETAS = ["server-side-fallback-2026-07-01"]


class ClaudeClient:
    """LLMClient backed by the Anthropic Messages API with JSON-schema output."""

    def __init__(self, api_key: str | None = None) -> None:
        """Remember the API key (default: ANTHROPIC_API_KEY); the SDK client is built on first use."""
        self._api_key = api_key
        self._client: Any = None

    def complete[T: BaseModel](
        self, system: str, user: str, schema: type[T], model: str, effort: str | None = None
    ) -> tuple[T, Usage]:
        """Ask `model` for an instance of `schema`; raise LLMRefusal on refusal, LLMError otherwise."""
        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": strict_json_schema(schema)}
        }
        if effort is not None:
            output_config = {"effort": effort, **output_config}
        started = time.monotonic()
        response = self._sdk().beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            betas=BETAS,
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config=output_config,
        )
        seconds = time.monotonic() - started
        result = parse_output(_answer_text(response), schema)
        usage = Usage(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            seconds=seconds,
        )
        return result, usage

    def _sdk(self) -> Any:
        """Return the SDK client, creating it on first use."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key or os.environ.get("ANTHROPIC_API_KEY"))
        return self._client


def _answer_text(response: Any) -> str:
    """Return the first text block of a response; raise on refusal, truncation or no text."""
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise LLMRefusal(f"model refused: {details}" if details else "model refused")
    if response.stop_reason == "max_tokens":
        raise LLMError("model output hit max_tokens")
    for block in response.content:
        if block.type == "text":
            return block.text
    raise LLMError("model returned no text block")
