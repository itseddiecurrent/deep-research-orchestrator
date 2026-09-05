"""Provider-neutral structured LLM boundary and deterministic test client."""

from __future__ import annotations

from collections import deque
from typing import (
    Any,
    Deque,
    Iterable,
    Literal,
    Optional,
    Protocol,
    Union,
    runtime_checkable,
)

from pydantic import Field

from research_agent.models import NonEmptyStr, StrictModel


class LLMRequest(StrictModel):
    purpose: Literal["plan", "action"]
    instructions: NonEmptyStr
    context: dict[str, Any]
    response_schema: dict[str, Any]
    max_output_tokens: int = Field(ge=1)


class LLMResponse(StrictModel):
    output: Any
    provider: NonEmptyStr
    model: NonEmptyStr
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)


class LLMClientError(Exception):
    """A provider/client failure at the LLM boundary."""


@runtime_checkable
class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return one provider-neutral structured response."""


ScriptedItem = Union[LLMResponse, object, Exception]


class ScriptedLLMClient:
    """FIFO response client for deterministic, offline runtime tests."""

    def __init__(self, responses: Iterable[ScriptedItem]) -> None:
        self._responses: Deque[ScriptedItem] = deque(responses)
        self.requests: list[LLMRequest] = []

    @property
    def remaining_responses(self) -> int:
        return len(self._responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request.model_copy(deep=True))
        if not self._responses:
            raise LLMClientError("scripted LLM response queue is exhausted")
        item = self._responses.popleft()
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(output=item, provider="scripted", model="scripted-v1")
