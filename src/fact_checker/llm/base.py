"""The LLM client protocol, its errors and usage record, and the strict JSON Schema builder."""

import json
import re
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

_DROPPED_KEYS = frozenset({"default", "title"})
_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_*-]*")


class Usage(BaseModel):
    """Tokens and wall-clock seconds of one model call, with the raw answer text when the client has it."""

    model: str
    input_tokens: int
    output_tokens: int
    seconds: float
    raw_text: str | None = None


def redact_secrets(text: str) -> str:
    """Return `text` with each `sk-` key-like token replaced by `[redacted key]`."""
    return _KEY_PATTERN.sub("[redacted key]", text)


class LLMError(Exception):
    """A model call failed or returned unusable output; its message never holds a key fragment."""

    def __init__(self, message: str = "") -> None:
        """Store `message` with key-like tokens redacted."""
        super().__init__(redact_secrets(message))


class LLMRefusal(LLMError):
    """The model refused to answer."""


class LLMClient(Protocol):
    """A client that returns one validated structured answer per call."""

    def complete[T: BaseModel](
        self, system: str, user: str, schema: type[T], model: str, effort: str | None = None
    ) -> tuple[T, Usage]:
        """Ask `model` for an instance of `schema`; return it with its usage, or raise LLMError."""
        ...


def parse_output[T: BaseModel](text: str, schema: type[T]) -> T:
    """Parse model text as JSON and validate it against `schema`; raise LLMError when it is not."""
    try:
        return schema.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as error:
        raise LLMError(f"model output does not match {schema.__name__}: {error}") from error


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return `model`'s JSON Schema made structured-output safe.

    References are inlined, `default` and `title` are removed, and every object has
    `additionalProperties: false` with all its properties listed in `required`.
    """
    schema = model.model_json_schema()
    return _strictify(schema, schema.get("$defs", {}))


def _strictify(node: Any, defs: dict[str, Any]) -> Any:
    """Return a copy of a schema node with references inlined and objects closed."""
    if isinstance(node, list):
        return [_strictify(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _strictify(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
    out = {k: _strictify(v, defs) for k, v in node.items() if k not in _DROPPED_KEYS | {"$defs"}}
    if "properties" in node:
        out["properties"] = {name: _strictify(sub, defs) for name, sub in node["properties"].items()}
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    return out
