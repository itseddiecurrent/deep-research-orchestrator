from __future__ import annotations

import asyncio

import pytest

from research_agent.llm import LLMClientError, LLMRequest, ScriptedLLMClient


def make_request() -> LLMRequest:
    return LLMRequest(
        purpose="action",
        instructions="Choose one structured action",
        context={"iteration": 1},
        response_schema={"type": "object"},
        max_output_tokens=128,
    )


def test_scripted_client_returns_fifo_outputs_and_captures_requests() -> None:
    client = ScriptedLLMClient([{"action": "first"}, {"action": "second"}])

    first = asyncio.run(client.complete(make_request()))
    second = asyncio.run(client.complete(make_request()))

    assert first.output == {"action": "first"}
    assert second.output == {"action": "second"}
    assert len(client.requests) == 2
    assert client.requests[0].context == {"iteration": 1}
    assert client.remaining_responses == 0


def test_scripted_client_exhaustion_is_explicit() -> None:
    client = ScriptedLLMClient([])

    with pytest.raises(LLMClientError, match="exhausted"):
        asyncio.run(client.complete(make_request()))
