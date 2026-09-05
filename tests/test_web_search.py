from __future__ import annotations

import asyncio
import json
from typing import Callable

import httpx
import pytest

from research_agent.tools import ToolExecutionError
from research_agent.web_search import SearchWebInput, TavilySearchTool


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run_tool(tool: TavilySearchTool, **overrides: object):  # type: ignore[no-untyped-def]
    values = {"query": "generic research topic", **overrides}
    return asyncio.run(tool.execute(SearchWebInput(**values)))


def test_tavily_search_sends_bounded_raw_content_request_and_normalizes() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.test/source",
                        "title": "Primary source",
                        "content": "Snippet must not become evidence",
                        "raw_content": "Full cleaned source content.",
                    }
                ]
            },
        )

    client = make_client(handler)
    tool = TavilySearchTool(
        api_key="tavily-secret", client=client, timeout_seconds=7.5
    )

    output = run_tool(
        tool,
        max_results=3,
        include_domains=["example.test"],
        exclude_domains=["noise.test"],
    )

    assert len(output.sources) == 1
    assert output.sources[0].content == "Full cleaned source content."
    assert output.sources[0].content != "Snippet must not become evidence"
    request = seen[0]
    assert request.url == httpx.URL("https://api.tavily.com/search")
    assert request.headers["Authorization"] == "Bearer tavily-secret"
    payload = json.loads(request.content)
    assert payload == {
        "query": "generic research topic",
        "search_depth": "advanced",
        "max_results": 3,
        "include_answer": False,
        "include_raw_content": "markdown",
        "include_images": False,
        "include_domains": ["example.test"],
        "exclude_domains": ["noise.test"],
    }


@pytest.mark.parametrize(
    ("status", "error_type", "retryable"),
    [
        (400, "tavily_http_error", False),
        (401, "tavily_authentication", False),
        (403, "tavily_authentication", False),
        (429, "tavily_rate_limit", True),
        (500, "tavily_server_error", True),
    ],
)
def test_tavily_search_classifies_http_failures(
    status: int, error_type: str, retryable: bool
) -> None:
    tool = TavilySearchTool(
        api_key="secret",
        client=make_client(lambda request: httpx.Response(status, json={})),
    )

    with pytest.raises(ToolExecutionError) as error:
        run_tool(tool)

    assert error.value.error_type == error_type
    assert error.value.retryable is retryable
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    ("exception", "error_type"),
    [
        (httpx.ReadTimeout("late"), "tavily_timeout"),
        (httpx.ConnectError("offline"), "tavily_transport"),
    ],
)
def test_tavily_search_classifies_network_failures(
    exception: Exception, error_type: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    tool = TavilySearchTool(api_key="secret", client=make_client(handler))

    with pytest.raises(ToolExecutionError) as error:
        run_tool(tool)

    assert error.value.error_type == error_type
    assert error.value.retryable is True


@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (httpx.Response(200, content=b"not-json"), "invalid_tavily_response"),
        (httpx.Response(200, json={"other": []}), "invalid_tavily_response"),
        (httpx.Response(200, json={"results": []}), "tavily_empty_results"),
        (
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.test",
                            "title": "Snippet only",
                            "content": "Not full source content",
                            "raw_content": None,
                        }
                    ]
                },
            ),
            "tavily_empty_results",
        ),
    ],
)
def test_tavily_search_rejects_malformed_or_empty_responses(
    response: httpx.Response, error_type: str
) -> None:
    tool = TavilySearchTool(
        api_key="secret", client=make_client(lambda request: response)
    )

    with pytest.raises(ToolExecutionError) as error:
        run_tool(tool)

    assert error.value.error_type == error_type
    assert error.value.retryable is False


def test_tavily_search_rejects_oversized_response() -> None:
    body = {"results": [], "padding": "x" * 2_000}
    tool = TavilySearchTool(
        api_key="secret",
        client=make_client(lambda request: httpx.Response(200, json=body)),
        max_response_bytes=1_024,
    )

    with pytest.raises(ToolExecutionError) as error:
        run_tool(tool)

    assert error.value.error_type == "tavily_response_too_large"
    assert error.value.retryable is False


def test_tavily_search_stops_streaming_when_response_crosses_byte_limit() -> None:
    class TrackingStream(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.yield_count = 0

        async def __aiter__(self):  # type: ignore[no-untyped-def]
            for chunk in (b"x" * 600, b"y" * 600, b"must-not-be-read"):
                self.yield_count += 1
                yield chunk

    stream = TrackingStream()
    tool = TavilySearchTool(
        api_key="secret",
        client=make_client(
            lambda request: httpx.Response(200, stream=stream, request=request)
        ),
        max_response_bytes=1_024,
    )

    with pytest.raises(ToolExecutionError) as error:
        run_tool(tool)

    assert error.value.error_type == "tavily_response_too_large"
    assert stream.yield_count == 2


def test_search_input_bounds_result_and_domain_counts() -> None:
    with pytest.raises(ValueError):
        SearchWebInput(query="topic", max_results=11)
    with pytest.raises(ValueError):
        SearchWebInput(query="topic", include_domains=["x.test"] * 21)
