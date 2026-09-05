"""OpenAI Responses API implementation of the provider-neutral LLM client."""

from __future__ import annotations

import json
from typing import Any, Optional

from openai import AsyncOpenAI

from research_agent.llm import LLMClientError, LLMRequest, LLMResponse


class OpenAIResponsesClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Optional[Any] = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model
        self._owns_client = client is None
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response_format = {
            "type": "json_schema",
            "name": f"{request.purpose}_response",
            "schema": request.response_schema,
            # Generic tool arguments contain an open-ended JSON object, which is not
            # accepted by the strict Structured Outputs subset. The deterministic
            # runtime still validates the complete response and tool arguments.
            "strict": False,
        }
        try:
            response = await self._client.responses.create(
                model=self.model,
                instructions=request.instructions,
                input=json.dumps(
                    request.context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                text={"format": response_format},
                max_output_tokens=request.max_output_tokens,
            )
        except Exception as exc:
            raise LLMClientError(
                f"OpenAI Responses request failed ({type(exc).__name__})"
            ) from exc

        status = getattr(response, "status", None)
        if status in {"failed", "cancelled", "incomplete"}:
            raise LLMClientError(f"OpenAI response ended with status {status}")
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise LLMClientError("OpenAI response did not contain structured text")
        try:
            output = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMClientError("OpenAI response was not valid JSON") from exc

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage else None
        output_tokens = getattr(usage, "output_tokens", None) if usage else None
        return LLMResponse(
            output=output,
            provider="openai",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()
