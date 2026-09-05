from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from research_agent.llm import LLMClientError, LLMRequest
from research_agent.openai_adapter import OpenAIResponsesClient


class FakeResponses:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeOpenAIClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def make_request() -> LLMRequest:
    return LLMRequest(
        purpose="action",
        instructions="Choose one action",
        context={"query": "compare systems", "iteration": 1},
        response_schema={
            "type": "object",
            "properties": {"action": {"type": "string"}},
            "required": ["action"],
            "additionalProperties": False,
        },
        max_output_tokens=321,
    )


def test_openai_adapter_builds_responses_request_and_normalizes_usage() -> None:
    provider_response = SimpleNamespace(
        output_text='{"action":"finish"}',
        usage=SimpleNamespace(input_tokens=17, output_tokens=9),
    )
    responses = FakeResponses(provider_response)
    provider = FakeOpenAIClient(responses)
    client = OpenAIResponsesClient(
        api_key="must-not-enter-payload", model="configured-model", client=provider
    )

    result = asyncio.run(client.complete(make_request()))

    assert result.output == {"action": "finish"}
    assert result.provider == "openai"
    assert result.model == "configured-model"
    assert result.input_tokens == 17
    assert result.output_tokens == 9
    assert responses.calls == [
        {
            "model": "configured-model",
            "instructions": "Choose one action",
            "input": json.dumps(
                {"iteration": 1, "query": "compare systems"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "action_response",
                    "schema": make_request().response_schema,
                    "strict": False,
                }
            },
            "max_output_tokens": 321,
        }
    ]
    assert "must-not-enter-payload" not in repr(responses.calls)


@pytest.mark.parametrize(
    ("output_text", "message"),
    [
        (None, "did not contain structured text"),
        ("   ", "did not contain structured text"),
        ("not-json", "was not valid JSON"),
    ],
)
def test_openai_adapter_rejects_empty_or_malformed_output(
    output_text: object, message: str
) -> None:
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(
            FakeResponses(SimpleNamespace(output_text=output_text, usage=None))
        ),
    )

    with pytest.raises(LLMClientError, match=message):
        asyncio.run(client.complete(make_request()))


def test_openai_adapter_sanitizes_provider_failure() -> None:
    secret = "provider-secret"
    client = OpenAIResponsesClient(
        api_key=secret,
        model="configured-model",
        client=FakeOpenAIClient(
            FakeResponses(error=RuntimeError(f"request exposed {secret}"))
        ),
    )

    with pytest.raises(LLMClientError) as error:
        asyncio.run(client.complete(make_request()))

    assert "RuntimeError" in str(error.value)
    assert secret not in str(error.value)


@pytest.mark.parametrize("status", ["failed", "cancelled", "incomplete"])
def test_openai_adapter_rejects_noncompleted_provider_status(status: str) -> None:
    provider_response = SimpleNamespace(
        status=status,
        output_text='{"action":"finish"}',
        usage=None,
        error=SimpleNamespace(message="must-not-be-exposed"),
    )
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(FakeResponses(provider_response)),
    )

    with pytest.raises(LLMClientError) as error:
        asyncio.run(client.complete(make_request()))

    assert status in str(error.value)
    assert "must-not-be-exposed" not in str(error.value)


def test_openai_adapter_does_not_close_injected_client() -> None:
    provider = FakeOpenAIClient(FakeResponses())
    client = OpenAIResponsesClient(
        api_key="secret", model="configured-model", client=provider
    )

    asyncio.run(client.aclose())

    assert provider.closed is False
