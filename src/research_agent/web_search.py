"""Bounded Tavily Search adapter returning canonical full-content sources."""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

from research_agent.models import NonEmptyStr, StrictModel
from research_agent.provenance import ResearchToolOutput, RetrievedSource
from research_agent.tools import ToolDefinition, ToolExecutionError


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class SearchWebInput(StrictModel):
    query: NonEmptyStr
    max_results: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "advanced"
    include_domains: list[NonEmptyStr] = Field(default_factory=list, max_length=20)
    exclude_domains: list[NonEmptyStr] = Field(default_factory=list, max_length=20)


class TavilySearchTool:
    input_model = SearchWebInput
    output_model = ResearchToolOutput

    def __init__(
        self,
        *,
        api_key: str,
        client: Optional[httpx.AsyncClient] = None,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes < 1_024:
            raise ValueError("max_response_bytes must be at least 1024")
        self._api_key = SecretStr(api_key)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.definition = ToolDefinition.from_models(
            name="search_web",
            version="1",
            description=(
                "Search the public web for full cleaned source content relevant to a "
                "natural-language research query."
            ),
            input_model=self.input_model,
            output_model=self.output_model,
            capabilities=["web_search", "source_retrieval"],
            provider="tavily",
            idempotent=True,
            timeout_seconds=timeout_seconds,
        )

    async def execute(self, arguments: BaseModel) -> object:
        search = SearchWebInput.model_validate(arguments)
        payload = {
            "query": search.query,
            "search_depth": search.search_depth,
            "max_results": search.max_results,
            "include_answer": False,
            "include_raw_content": "markdown",
            "include_images": False,
            "include_domains": search.include_domains,
            "exclude_domains": search.exclude_domains,
        }
        try:
            async with self._client.stream(
                "POST",
                TAVILY_SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            ) as response:
                if response.status_code >= 400:
                    self._raise_for_status(response.status_code)
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > self.max_response_bytes:
                        raise ToolExecutionError(
                            "Tavily response exceeded the configured byte limit",
                            error_type="tavily_response_too_large",
                        )
                response_content = bytes(content)
        except httpx.TimeoutException as exc:
            raise ToolExecutionError(
                "Tavily request timed out",
                retryable=True,
                error_type="tavily_timeout",
            ) from exc
        except httpx.TransportError as exc:
            raise ToolExecutionError(
                "Tavily transport failed",
                retryable=True,
                error_type="tavily_transport",
            ) from exc

        try:
            body = json.loads(response_content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolExecutionError(
                "Tavily response was not valid JSON",
                error_type="invalid_tavily_response",
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise ToolExecutionError(
                "Tavily response did not contain a results list",
                error_type="invalid_tavily_response",
            )

        sources: list[RetrievedSource] = []
        try:
            for result in body["results"]:
                if not isinstance(result, dict):
                    raise ValueError("search result is not an object")
                raw_content = result.get("raw_content")
                if not isinstance(raw_content, str) or not raw_content.strip():
                    continue
                sources.append(
                    RetrievedSource(
                        source_url=result.get("url"),
                        title=result.get("title"),
                        content=raw_content,
                        media_type="text/markdown",
                    )
                )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ToolExecutionError(
                "Tavily returned a malformed search result",
                error_type="invalid_tavily_response",
            ) from exc
        if not sources:
            raise ToolExecutionError(
                "Tavily returned no results with full source content",
                error_type="tavily_empty_results",
            )
        return ResearchToolOutput(sources=sources)

    def _raise_for_status(self, status_code: int) -> None:
        retryable = status_code == 429 or status_code >= 500
        if status_code in (401, 403):
            error_type = "tavily_authentication"
        elif status_code == 429:
            error_type = "tavily_rate_limit"
        elif status_code >= 500:
            error_type = "tavily_server_error"
        else:
            error_type = "tavily_http_error"
        raise ToolExecutionError(
            f"Tavily returned HTTP {status_code}",
            retryable=retryable,
            error_type=error_type,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
