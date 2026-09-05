from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIError, BadRequestError

from research_agent.llm import LLMClientError, LLMRequest
from research_agent.openai_adapter import (
    OpenAIResponsesClient,
    _is_transport_error,
    _safe_error_label,
)


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
            "stream": True,
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


def test_openai_adapter_reports_safe_incomplete_reason() -> None:
    provider_response = SimpleNamespace(
        status="incomplete",
        output_text="",
        usage=None,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(FakeResponses(provider_response)),
    )

    with pytest.raises(LLMClientError, match=r"incomplete \(max_output_tokens\)"):
        asyncio.run(client.complete(make_request()))


def test_openai_adapter_does_not_close_injected_client() -> None:
    provider = FakeOpenAIClient(FakeResponses())
    client = OpenAIResponsesClient(
        api_key="secret", model="configured-model", client=provider
    )

    asyncio.run(client.aclose())

    assert provider.closed is False


def test_openai_adapter_assembles_streamed_text_and_terminal_usage() -> None:
    terminal_response = SimpleNamespace(
        status="completed",
        output_text="",
        usage=SimpleNamespace(input_tokens=12, output_tokens=4),
    )

    class FakeStream:
        def __init__(self) -> None:
            self.events = iter(
                [
                    SimpleNamespace(
                        type="response.output_text.delta", delta='{"action":'
                    ),
                    SimpleNamespace(
                        type="response.output_text.delta", delta='"finish"}'
                    ),
                    SimpleNamespace(
                        type="response.completed", response=terminal_response
                    ),
                ]
            )

        def __aiter__(self) -> "FakeStream":
            return self

        async def __anext__(self) -> object:
            try:
                return next(self.events)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(FakeResponses(FakeStream())),
    )

    result = asyncio.run(client.complete(make_request()))

    assert result.output == {"action": "finish"}
    assert result.input_tokens == 12
    assert result.output_tokens == 4


def test_openai_adapter_wraps_and_unwraps_a_root_union_schema() -> None:
    request = make_request().model_copy(
        update={
            "response_schema": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {"action": {"const": "finish"}},
                        "required": ["action"],
                        "additionalProperties": False,
                    }
                ]
            }
        }
    )
    responses = FakeResponses(
        SimpleNamespace(
            status="completed",
            output_text='{"result":{"action":"finish"}}',
            usage=None,
        )
    )
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(responses),
    )

    result = asyncio.run(client.complete(request))

    assert result.output == {"action": "finish"}
    assert responses.calls[0]["text"]["format"]["schema"] == {
        "type": "object",
        "properties": {"result": request.response_schema},
        "required": ["result"],
        "additionalProperties": False,
    }


def test_openai_adapter_accepts_direct_output_for_wrapped_root_union() -> None:
    request = make_request().model_copy(
        update={
            "response_schema": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {"action": {"const": "finish"}},
                        "required": ["action"],
                        "additionalProperties": False,
                    }
                ]
            }
        }
    )
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(
            FakeResponses(
                SimpleNamespace(
                    status="completed",
                    output_text='{"action":"finish"}',
                    usage=None,
                )
            )
        ),
    )

    result = asyncio.run(client.complete(request))

    assert result.output == {"action": "finish"}


def test_openai_adapter_resumes_a_disconnected_stream() -> None:
    in_progress = SimpleNamespace(id="resp_test", status="in_progress")
    completed = SimpleNamespace(
        id="resp_test",
        status="completed",
        output_text="",
        usage=SimpleNamespace(input_tokens=8, output_tokens=3),
    )

    class EventStream:
        def __init__(self, events: list[object]) -> None:
            self.events = iter(events)

        def __aiter__(self) -> "EventStream":
            return self

        async def __anext__(self) -> object:
            try:
                event = next(self.events)
            except StopIteration as exc:
                raise StopAsyncIteration from exc
            if isinstance(event, Exception):
                raise event
            return event

    class ResumableResponses:
        def __init__(self) -> None:
            self.create_calls: list[dict[str, Any]] = []
            self.retrieve_calls: list[tuple[str, dict[str, Any]]] = []

        async def create(self, **kwargs: Any) -> object:
            self.create_calls.append(kwargs)
            return EventStream(
                [
                    SimpleNamespace(
                        type="response.created",
                        sequence_number=0,
                        response=in_progress,
                    ),
                    httpx.RemoteProtocolError("connection dropped"),
                ]
            )

        async def retrieve(self, response_id: str, **kwargs: Any) -> object:
            self.retrieve_calls.append((response_id, kwargs))
            return EventStream(
                [
                    SimpleNamespace(
                        type="response.output_text.delta",
                        sequence_number=1,
                        delta='{"action":"finish"}',
                        response=None,
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        sequence_number=2,
                        response=completed,
                    ),
                ]
            )

    responses = ResumableResponses()
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(responses),
        retry_backoff_seconds=0,
    )

    result = asyncio.run(client.complete(make_request()))

    assert result.output == {"action": "finish"}
    assert len(responses.create_calls) == 1
    assert responses.retrieve_calls == [
        ("resp_test", {"stream": True, "starting_after": 0})
    ]


def test_openai_adapter_caps_transport_retries_before_response_creation() -> None:
    class DisconnectingResponses:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **kwargs: Any) -> object:
            self.calls += 1
            raise httpx.ConnectError("offline")

    responses = DisconnectingResponses()
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(responses),
        max_transport_retries=2,
        retry_backoff_seconds=0,
    )

    with pytest.raises(LLMClientError, match="request failed"):
        asyncio.run(client.complete(make_request()))

    assert responses.calls == 3


def test_generic_non_status_openai_error_is_not_assumed_retryable() -> None:
    error = APIError(
        "stream interrupted",
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        body=None,
    )

    assert _is_transport_error(error) is False


def test_rejected_stream_resume_falls_back_to_one_fresh_request() -> None:
    in_progress = SimpleNamespace(id="resp_interrupted", status="in_progress")
    completed = SimpleNamespace(
        id="resp_retried",
        status="completed",
        output_text="",
        usage=None,
    )

    async def interrupted_stream() -> object:
        yield SimpleNamespace(
            type="response.created",
            sequence_number=0,
            response=in_progress,
        )
        raise httpx.RemoteProtocolError("connection dropped")

    async def successful_stream() -> object:
        yield SimpleNamespace(
            type="response.output_text.delta",
            sequence_number=0,
            delta='{"action":"finish"}',
            response=None,
        )
        yield SimpleNamespace(
            type="response.completed",
            sequence_number=1,
            response=completed,
        )

    class ResumeRejectingResponses:
        def __init__(self) -> None:
            self.create_calls = 0
            self.retrieve_calls = 0

        async def create(self, **kwargs: Any) -> object:
            self.create_calls += 1
            if self.create_calls == 1:
                return interrupted_stream()
            return successful_stream()

        async def retrieve(self, response_id: str, **kwargs: Any) -> object:
            self.retrieve_calls += 1
            request = httpx.Request("GET", f"https://api.openai.com/v1/responses/{response_id}")
            raise BadRequestError(
                "response is not ready",
                response=httpx.Response(400, request=request),
                body=None,
            )

    responses = ResumeRejectingResponses()
    client = OpenAIResponsesClient(
        api_key="secret",
        model="configured-model",
        client=FakeOpenAIClient(responses),
        max_transport_retries=2,
        retry_backoff_seconds=0,
    )

    result = asyncio.run(client.complete(make_request()))

    assert result.output == {"action": "finish"}
    assert responses.create_calls == 2
    assert responses.retrieve_calls == 1


def test_provider_error_code_is_safely_exposed_without_retrying() -> None:
    error = APIError(
        "account details must not be copied",
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        body={"code": "billing_not_active"},
    )

    assert _is_transport_error(error) is False
    assert _safe_error_label(error) == "billing_not_active"


def test_gpt5_family_requests_use_low_reasoning_effort() -> None:
    responses = FakeResponses(
        SimpleNamespace(
            status="completed",
            output_text='{"action":"finish"}',
            usage=None,
        )
    )
    client = OpenAIResponsesClient(
        api_key="secret",
        model="gpt-5-mini",
        client=FakeOpenAIClient(responses),
    )

    asyncio.run(client.complete(make_request()))

    assert responses.calls[0]["reasoning"] == {"effort": "low"}
