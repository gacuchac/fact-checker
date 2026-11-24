"""OpenAI client on the official openai SDK Responses API."""

import os
import time
from typing import Any

import openai
from pydantic import BaseModel

from fact_checker.llm.base import (
    LLMError,
    LLMRefusal,
    Usage,
    parse_output,
    strict_json_schema,
)


class OpenAIClient:
    """LLMClient backed by the OpenAI Responses API with strict structured outputs."""

    def __init__(self, api_key: str | None = None) -> None:
        """Remember the API key (default: OPENAI_API_KEY); the SDK client is built on first use."""
        self._api_key = api_key
        self._client: Any = None

    def complete[T: BaseModel](
        self, system: str, user: str, schema: type[T], model: str, effort: str | None = None
    ) -> tuple[T, Usage]:
        """Ask `model` for an instance of `schema`; raise LLMRefusal on refusal, LLMError otherwise."""
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": user,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema.__name__,
                    "schema": strict_json_schema(schema),
                    "strict": True,
                }
            },
        }
        if effort is not None:
            kwargs["reasoning"] = {"effort": effort}
        started = time.monotonic()
        try:
            response = self._sdk().responses.create(**kwargs)
        except openai.APIError as error:
            raise LLMError(f"OpenAI API call failed: {error}") from error
        seconds = time.monotonic() - started
        _raise_on_refusal(response)
        result = parse_output(response.output_text, schema)
        usage = Usage(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            seconds=seconds,
            raw_text=response.output_text,
        )
        return result, usage

    def _sdk(self) -> Any:
        """Return the SDK client, creating it on first use."""
        if self._client is None:
            self._client = openai.OpenAI(api_key=self._api_key or os.environ.get("OPENAI_API_KEY"))
        return self._client


def _raise_on_refusal(response: Any) -> None:
    """Raise LLMRefusal when any output content item is a refusal."""
    for item in response.output:
        for part in getattr(item, "content", None) or []:
            if part.type == "refusal":
                raise LLMRefusal(f"model refused: {part.refusal}")
