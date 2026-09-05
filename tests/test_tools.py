from __future__ import annotations

import asyncio
from typing import Any

import pytest

from research_agent.models import StrictModel
from research_agent.tools import (
    AmbiguousToolVersionError,
    ToolDefinition,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    ToolRegistrationError,
    ToolRegistry,
)


class QueryInput(StrictModel):
    query: str


class TextOutput(StrictModel):
    text: str


class RecordingTool:
    input_model = QueryInput
    output_model = TextOutput

    def __init__(self, name: str, version: str = "1") -> None:
        self.definition = ToolDefinition.from_models(
            name=name,
            version=version,
            description=f"Return a recorded response from {name}",
            input_model=self.input_model,
            output_model=self.output_model,
            capabilities=["lookup"],
        )
        self.calls: list[QueryInput] = []
        self.output: Any = {"text": name}

    async def execute(self, arguments: QueryInput) -> object:
        self.calls.append(arguments)
        return self.output


def test_registry_registration_catalog_lookup_and_versioning() -> None:
    registry = ToolRegistry()
    first = RecordingTool("lookup_alpha")
    second = RecordingTool("lookup_beta", "2")
    registry.register(second)
    registry.register(first)

    assert registry.get("lookup_alpha") is first
    assert registry.get("lookup_beta", "2") is second
    assert [item.name for item in registry.definitions()] == [
        "lookup_alpha",
        "lookup_beta",
    ]
    assert registry.definitions()[0].input_schema == QueryInput.model_json_schema()
    assert registry.catalog_version.startswith("catalog_")

    with pytest.raises(ToolRegistrationError, match="already registered"):
        registry.register(RecordingTool("lookup_alpha"))
    with pytest.raises(ToolNotFoundError, match="unknown tool"):
        registry.get("missing")


def test_registry_requires_version_when_a_name_is_ambiguous() -> None:
    registry = ToolRegistry()
    registry.register(RecordingTool("lookup", "1"))
    registry.register(RecordingTool("lookup", "2"))

    with pytest.raises(AmbiguousToolVersionError, match="multiple versions"):
        registry.get("lookup")
    assert registry.get("lookup", "2").definition.version == "2"


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": ["wrong", "type"]},
        {"query": "valid", "invented": True},
    ],
)
def test_registry_rejects_invalid_arguments_before_adapter_call(
    arguments: object,
) -> None:
    registry = ToolRegistry()
    tool = RecordingTool("lookup")
    registry.register(tool)

    with pytest.raises(ToolInputValidationError):
        asyncio.run(registry.execute("lookup", arguments))
    assert tool.calls == []


def test_registry_validates_output_and_returns_normalized_data() -> None:
    registry = ToolRegistry()
    tool = RecordingTool("lookup")
    registry.register(tool)

    result = asyncio.run(registry.execute("lookup", {"query": "topic"}))
    assert result == {"text": "lookup"}
    assert tool.calls[0].query == "topic"

    tool.output = {"not_text": "invalid"}
    with pytest.raises(ToolOutputValidationError):
        asyncio.run(registry.execute("lookup", {"query": "topic"}))


def test_registry_rejects_adapters_whose_models_allow_unknown_fields() -> None:
    class LooseInput(StrictModel):
        model_config = {"extra": "ignore"}
        query: str

    tool = RecordingTool("lookup")
    tool.input_model = LooseInput

    with pytest.raises(ToolRegistrationError, match="reject unknown fields"):
        ToolRegistry().register(tool)
