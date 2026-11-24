"""Tests of the LLM clients, with every SDK client mocked: no network."""

from types import SimpleNamespace

import anthropic
import openai
import pytest
from pydantic import BaseModel

from fact_checker.contracts import Verdicts
from fact_checker.llm.base import LLMError, LLMRefusal, Usage, strict_json_schema
from fact_checker.llm.claude import ClaudeClient
from fact_checker.llm.config import load_settings
from fact_checker.llm.fake import FakeClient
from fact_checker.llm.openai_client import OpenAIClient


class Inner(BaseModel):
    name: str
    count: int = 3


class Outer(BaseModel):
    """Outer."""

    inner: Inner
    items: list[Inner]
    note: str | None = None


def _objects(node: object) -> list[dict]:
    if isinstance(node, dict):
        found = [node] if node.get("type") == "object" else []
        return found + [o for v in node.values() for o in _objects(v)]
    if isinstance(node, list):
        return [o for v in node for o in _objects(v)]
    return []


def _keys(node: object) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _keys(v)}
    return set()


@pytest.mark.parametrize("model", [Outer, Verdicts])
def test_strict_json_schema_is_structured_output_safe(model):
    schema = strict_json_schema(model)
    objects = _objects(schema)
    assert objects
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])
    assert not {"default", "title", "$defs", "$ref"} & _keys(schema)


def test_strict_json_schema_keeps_optional_as_required_nullable():
    schema = strict_json_schema(Outer)
    assert "note" in schema["required"]
    assert {"type": "null"} in schema["properties"]["note"]["anyOf"]


class Answer(BaseModel):
    value: int


def _claude_response(text="{\"value\": 7}", stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(
        model="claude-served",
        stop_reason=stop_reason,
        stop_details=stop_details,
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=11, output_tokens=5),
    )


def _claude(response):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    client = ClaudeClient(api_key="k")
    client._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return client, calls


def test_claude_request_shape_and_success():
    client, calls = _claude(_claude_response())
    result, usage = client.complete("sys", "usr", Answer, "claude-x", "high")
    assert result == Answer(value=7)
    assert (usage.model, usage.input_tokens, usage.output_tokens) == ("claude-served", 11, 5)
    assert usage.seconds >= 0
    assert calls == [
        {
            "model": "claude-x",
            "max_tokens": 16000,
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
            "system": "sys",
            "messages": [{"role": "user", "content": "usr"}],
            "output_config": {
                "effort": "high",
                "format": {"type": "json_schema", "schema": strict_json_schema(Answer)},
            },
        }
    ]


def test_claude_omits_effort_when_none():
    client, calls = _claude(_claude_response())
    client.complete("s", "u", Answer, "m")
    assert "effort" not in calls[0]["output_config"]


def test_claude_refusal():
    client, _ = _claude(_claude_response(stop_reason="refusal", stop_details="policy"))
    with pytest.raises(LLMRefusal, match="policy"):
        client.complete("s", "u", Answer, "m")


def test_claude_max_tokens():
    client, _ = _claude(_claude_response(stop_reason="max_tokens"))
    with pytest.raises(LLMError):
        client.complete("s", "u", Answer, "m")


@pytest.mark.parametrize("text", ["not json", "{\"value\": \"x\"}"])
def test_claude_bad_output(text):
    client, _ = _claude(_claude_response(text=text))
    with pytest.raises(LLMError):
        client.complete("s", "u", Answer, "m")


def test_claude_no_text_block():
    response = _claude_response()
    response.content = [SimpleNamespace(type="thinking")]
    client, _ = _claude(response)
    with pytest.raises(LLMError):
        client.complete("s", "u", Answer, "m")


def _openai_response(text="{\"value\": 7}", output=()):
    return SimpleNamespace(
        model="gpt-served",
        output=list(output),
        output_text=text,
        usage=SimpleNamespace(input_tokens=21, output_tokens=9),
    )


def _openai(response):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    client = OpenAIClient(api_key="k")
    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    return client, calls


def test_openai_request_shape_and_success():
    client, calls = _openai(_openai_response())
    result, usage = client.complete("sys", "usr", Answer, "gpt-x", "high")
    assert result == Answer(value=7)
    assert (usage.model, usage.input_tokens, usage.output_tokens) == ("gpt-served", 21, 9)
    assert calls == [
        {
            "model": "gpt-x",
            "instructions": "sys",
            "input": "usr",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "Answer",
                    "schema": strict_json_schema(Answer),
                    "strict": True,
                }
            },
            "reasoning": {"effort": "high"},
        }
    ]


def test_openai_omits_reasoning_when_no_effort():
    client, calls = _openai(_openai_response())
    client.complete("s", "u", Answer, "m")
    assert "reasoning" not in calls[0]


def test_openai_refusal():
    refusal = SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal", refusal="no")])
    client, _ = _openai(_openai_response(text="", output=[refusal]))
    with pytest.raises(LLMRefusal, match="no"):
        client.complete("s", "u", Answer, "m")


@pytest.mark.parametrize("text", ["not json", "{\"value\": \"x\"}"])
def test_openai_bad_output(text):
    client, _ = _openai(_openai_response(text=text))
    with pytest.raises(LLMError):
        client.complete("s", "u", Answer, "m")


def test_load_settings_defaults():
    settings = load_settings({})
    assert settings.anthropic_api_key is None
    assert settings.openai_api_key is None
    assert settings.decompose_model == "claude-opus-5-5"
    assert settings.decompose_effort == "high"
    assert settings.verify_model == "claude-sonnet-5-5"
    assert settings.verify_effort == "high"
    assert settings.review_model == "gpt-6-sol"
    assert settings.access_code is None
    assert settings.daily_run_cap == 50


def test_load_settings_overrides():
    settings = load_settings(
        {
            "ANTHROPIC_API_KEY": "a",
            "OPENAI_API_KEY": "o",
            "FC_DECOMPOSE_MODEL": "dm",
            "FC_DECOMPOSE_EFFORT": "low",
            "FC_VERIFY_MODEL": "vm",
            "FC_VERIFY_EFFORT": "medium",
            "FC_REVIEW_MODEL": "rm",
            "FC_ACCESS_CODE": "code",
            "FC_DAILY_RUN_CAP": "7",
        }
    )
    assert (settings.anthropic_api_key, settings.openai_api_key) == ("a", "o")
    assert (settings.decompose_model, settings.decompose_effort) == ("dm", "low")
    assert (settings.verify_model, settings.verify_effort) == ("vm", "medium")
    assert settings.review_model == "rm"
    assert settings.access_code == "code"
    assert settings.daily_run_cap == 7


def test_fake_client_returns_in_order_and_records():
    first, second = Answer(value=1), Answer(value=2)
    fake = FakeClient([first, RuntimeError("boom"), second])
    out, usage = fake.complete("s1", "u1", Answer, "m1", "high")
    assert out is first
    assert isinstance(usage, Usage)
    with pytest.raises(RuntimeError):
        fake.complete("s2", "u2", Answer, "m2")
    assert fake.complete("s3", "u3", Answer, "m3")[0] is second
    assert [c.system for c in fake.calls] == ["s1", "s2", "s3"]
    assert fake.calls[0].effort == "high" and fake.calls[1].effort is None
    assert fake.calls[0].schema is Answer and fake.calls[0].model == "m1" and fake.calls[0].user == "u1"


def test_fake_client_exhausted():
    with pytest.raises(LLMError):
        FakeClient([]).complete("s", "u", Answer, "m")


def _api_error(module):
    return module.APIError("down", request=SimpleNamespace(headers={}), body=None)


def test_claude_sdk_error_becomes_llm_error():
    client, _ = _claude(None)
    client._client.beta.messages.create = lambda **_: (_ for _ in ()).throw(_api_error(anthropic))
    with pytest.raises(LLMError) as raised:
        client.complete("s", "u", Answer, "m")
    assert isinstance(raised.value.__cause__, anthropic.APIError)


def test_claude_unrelated_error_escapes():
    client, _ = _claude(None)
    client._client.beta.messages.create = lambda **_: (_ for _ in ()).throw(KeyError("x"))
    with pytest.raises(KeyError):
        client.complete("s", "u", Answer, "m")


def test_openai_sdk_error_becomes_llm_error():
    client, _ = _openai(None)
    client._client.responses.create = lambda **_: (_ for _ in ()).throw(_api_error(openai))
    with pytest.raises(LLMError) as raised:
        client.complete("s", "u", Answer, "m")
    assert isinstance(raised.value.__cause__, openai.APIError)


def test_openai_unrelated_error_escapes():
    client, _ = _openai(None)
    client._client.responses.create = lambda **_: (_ for _ in ()).throw(KeyError("x"))
    with pytest.raises(KeyError):
        client.complete("s", "u", Answer, "m")


def test_fake_client_rejects_wrong_schema_instance():
    with pytest.raises(LLMError):
        FakeClient([Inner(name="a")]).complete("s", "u", Answer, "m")
