"""OpenAI Responses API implementation of the provider-neutral LLM client."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

import httpx
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from research_agent.llm import LLMClientError, LLMRequest, LLMResponse


class OpenAIResponsesClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Optional[Any] = None,
        timeout_seconds: float = 60.0,
        max_transport_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        if max_transport_retries < 0:
            raise ValueError("max_transport_retries must be non-negative")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        self.model = model
        self.max_transport_retries = max_transport_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        provider_schema, unwrap_result = _provider_schema(request.response_schema)
        response_format = {
            "type": "json_schema",
            "name": f"{request.purpose}_response",
            "schema": provider_schema,
            # Generic tool arguments contain an open-ended JSON object, which is not
            # accepted by the strict Structured Outputs subset. The deterministic
            # runtime still validates the complete response and tool arguments.
            "strict": False,
        }
        create_arguments = {
            "model": self.model,
            "instructions": request.instructions,
            "input": json.dumps(
                request.context,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "text": {"format": response_format},
            "max_output_tokens": request.max_output_tokens,
            "stream": True,
        }
        if self.model.startswith("gpt-5"):
            # These are bounded, schema-constrained orchestration calls. Low effort
            # leaves more of max_output_tokens available for the required JSON.
            create_arguments["reasoning"] = {"effort": "low"}
        response: Any = None
        output_parts: list[str] = []
        response_id: Optional[str] = None
        last_sequence_number: Optional[int] = None
        completed_stream = False

        for attempt in range(self.max_transport_retries + 1):
            resuming = response_id is not None
            try:
                if not resuming:
                    # With no response ID there is nothing to resume, so a retry starts
                    # a fresh side-effect-free model request.
                    output_parts.clear()
                    last_sequence_number = None
                    stream = await self._client.responses.create(**create_arguments)
                else:
                    retrieve_arguments: dict[str, Any] = {"stream": True}
                    if last_sequence_number is not None:
                        retrieve_arguments["starting_after"] = last_sequence_number
                    stream = await self._client.responses.retrieve(
                        response_id, **retrieve_arguments
                    )

                if hasattr(stream, "__aiter__"):
                    async for event in stream:
                        sequence_number = getattr(event, "sequence_number", None)
                        if isinstance(sequence_number, int):
                            last_sequence_number = sequence_number
                        event_response = getattr(event, "response", None)
                        event_response_id = getattr(event_response, "id", None)
                        if isinstance(event_response_id, str) and event_response_id:
                            response_id = event_response_id

                        event_type = getattr(event, "type", None)
                        if event_type == "response.output_text.delta":
                            delta = getattr(event, "delta", None)
                            if isinstance(delta, str):
                                output_parts.append(delta)
                        elif event_type in {
                            "response.completed",
                            "response.failed",
                            "response.incomplete",
                        }:
                            response = event_response
                        elif event_type == "error":
                            raise LLMClientError(
                                "OpenAI response stream emitted an error"
                            )
                else:
                    # Preserve support for small injected clients used by embedders/tests.
                    response = stream
                completed_stream = True
                break
            except LLMClientError:
                raise
            except Exception as exc:
                resume_rejected = resuming and isinstance(exc, BadRequestError)
                can_retry = (
                    (_is_transport_error(exc) or resume_rejected)
                    and attempt < self.max_transport_retries
                )
                if not can_retry:
                    phase = "request" if last_sequence_number is None else "stream"
                    raise LLMClientError(
                        f"OpenAI response {phase} failed ({_safe_error_label(exc)})"
                    ) from exc
                if resume_rejected:
                    # Some model/account combinations reject retrieval while the
                    # original response is still in progress. Fall back to a fresh,
                    # bounded request rather than repeatedly retrying that resume.
                    response_id = None
                    last_sequence_number = None
                    output_parts.clear()
                await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))

        if not completed_stream:
            raise LLMClientError("OpenAI response stream did not complete")

        status = getattr(response, "status", None)
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None)
            suffix = (
                f" ({reason})"
                if isinstance(reason, str)
                and re.fullmatch(r"[a-z0-9_-]{1,64}", reason)
                else ""
            )
            raise LLMClientError(f"OpenAI response incomplete{suffix}")
        if status in {"failed", "cancelled"}:
            raise LLMClientError(f"OpenAI response ended with status {status}")
        output_text = "".join(output_parts) or getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise LLMClientError("OpenAI response did not contain structured text")
        try:
            output = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMClientError("OpenAI response was not valid JSON") from exc
        if unwrap_result:
            if not isinstance(output, dict):
                raise LLMClientError("OpenAI response omitted the structured result")
            # Some non-strict model responses follow the inner action schema directly
            # instead of the provider-only root wrapper. The deterministic runtime
            # still validates every field against the original discriminated union.
            if "result" in output:
                output = output["result"]

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


def _provider_schema(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Wrap root unions because Responses structured outputs require an object root."""

    if schema.get("type") == "object":
        return schema, False
    return (
        {
            "type": "object",
            "properties": {"result": schema},
            "required": ["result"],
            "additionalProperties": False,
        },
        True,
    )


def _is_transport_error(error: Exception) -> bool:
    """Recognize retryable transport failures through wrapped exception chains."""

    current: Optional[BaseException] = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current,
            (
                httpx.TimeoutException,
                httpx.TransportError,
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            ),
        ):
            return True
        if isinstance(current, APIError) and not isinstance(current, APIStatusError):
            return getattr(current, "code", None) in {
                "server_error",
                "internal_error",
                "temporarily_unavailable",
            }
        current = current.__cause__ or current.__context__
    return False


def _safe_error_label(error: Exception) -> str:
    """Expose a provider error code only when it is a short, non-secret identifier."""

    current: Optional[BaseException] = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, str) and re.fullmatch(r"[a-z0-9_-]{1,64}", code):
            return code
        current = current.__cause__ or current.__context__
    return type(error).__name__
