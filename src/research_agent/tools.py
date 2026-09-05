"""Generic, versioned tool registration and validated execution."""

from __future__ import annotations

from hashlib import sha256
import inspect
import json
from typing import Any, Optional, Protocol, Type, runtime_checkable

from pydantic import BaseModel, Field, ValidationError, model_validator

from research_agent.models import NonEmptyStr, StrictModel


class ToolDefinition(StrictModel):
    """Provider-neutral metadata advertised to the planner."""

    name: NonEmptyStr
    version: NonEmptyStr
    description: NonEmptyStr
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capabilities: list[NonEmptyStr] = Field(default_factory=list)
    provider: NonEmptyStr = "local"
    idempotent: bool = True
    timeout_seconds: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def schemas_are_objects(self) -> "ToolDefinition":
        for label, schema in (
            ("input", self.input_schema),
            ("output", self.output_schema),
        ):
            if schema.get("type") != "object":
                raise ValueError(f"tool {label} schema must describe an object")
        return self

    @classmethod
    def from_models(
        cls,
        *,
        name: str,
        version: str,
        description: str,
        input_model: Type[BaseModel],
        output_model: Type[BaseModel],
        capabilities: Optional[list[str]] = None,
        provider: str = "local",
        idempotent: bool = True,
        timeout_seconds: Optional[float] = None,
    ) -> "ToolDefinition":
        return cls(
            name=name,
            version=version,
            description=description,
            input_schema=input_model.model_json_schema(),
            output_schema=output_model.model_json_schema(),
            capabilities=capabilities or [],
            provider=provider,
            idempotent=idempotent,
            timeout_seconds=timeout_seconds,
        )


@runtime_checkable
class Tool(Protocol):
    """Runtime adapter contract; schemas and execution remain provider-neutral."""

    definition: ToolDefinition
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]

    async def execute(self, arguments: BaseModel) -> object:
        """Execute one already validated invocation."""


class ToolRegistryError(Exception):
    """Base error safe to turn into a planner-visible failure observation."""

    error_type = "tool_registry_error"
    retryable = False


class ToolRegistrationError(ToolRegistryError):
    error_type = "tool_registration_error"


class ToolNotFoundError(ToolRegistryError):
    error_type = "unknown_tool"


class AmbiguousToolVersionError(ToolRegistryError):
    error_type = "ambiguous_tool_version"


class ToolInputValidationError(ToolRegistryError):
    error_type = "invalid_tool_arguments"


class ToolOutputValidationError(ToolRegistryError):
    error_type = "invalid_tool_output"


class ToolExecutionError(ToolRegistryError):
    """An adapter-declared execution failure with explicit retryability."""

    error_type = "tool_execution_error"

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        error_type: str = "tool_execution_error",
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.error_type = error_type


class ToolRegistry:
    """Mutable startup catalog with deterministic versioned snapshots."""

    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], Tool] = {}

    def register(self, tool: Tool) -> None:
        self._validate_adapter(tool)
        key = (tool.definition.name, tool.definition.version)
        if key in self._tools:
            raise ToolRegistrationError(
                f"tool {key[0]!r} version {key[1]!r} is already registered"
            )
        self._tools[key] = tool

    def _validate_adapter(self, tool: Tool) -> None:
        if not isinstance(tool, Tool):
            raise ToolRegistrationError("tool does not satisfy the Tool protocol")
        for label, model in (
            ("input", tool.input_model),
            ("output", tool.output_model),
        ):
            if not inspect.isclass(model) or not issubclass(model, BaseModel):
                raise ToolRegistrationError(f"tool {label}_model must be a BaseModel")
            if model.model_config.get("extra") != "forbid":
                raise ToolRegistrationError(
                    f"tool {label}_model must reject unknown fields"
                )
        if tool.definition.input_schema != tool.input_model.model_json_schema():
            raise ToolRegistrationError("tool input schema does not match input_model")
        if tool.definition.output_schema != tool.output_model.model_json_schema():
            raise ToolRegistrationError("tool output schema does not match output_model")

    def definitions(self) -> list[ToolDefinition]:
        return [
            self._tools[key].definition.model_copy(deep=True)
            for key in sorted(self._tools)
        ]

    @property
    def catalog_version(self) -> str:
        payload = [
            definition.model_dump(mode="json") for definition in self.definitions()
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return f"catalog_{sha256(encoded).hexdigest()[:16]}"

    def get(self, name: str, version: Optional[str] = None) -> Tool:
        if version is not None:
            try:
                return self._tools[(name, version)]
            except KeyError as exc:
                raise ToolNotFoundError(
                    f"unknown tool {name!r} version {version!r}"
                ) from exc

        matches = [
            tool for (tool_name, _), tool in self._tools.items() if tool_name == name
        ]
        if not matches:
            raise ToolNotFoundError(f"unknown tool {name!r}")
        if len(matches) > 1:
            versions = sorted(tool.definition.version for tool in matches)
            raise AmbiguousToolVersionError(
                f"tool {name!r} has multiple versions; choose one of {versions}"
            )
        return matches[0]

    def validate_arguments(self, tool: Tool, arguments: object) -> BaseModel:
        try:
            return tool.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolInputValidationError(str(exc)) from exc

    async def execute_validated(self, tool: Tool, arguments: BaseModel) -> dict[str, Any]:
        try:
            raw_output = await tool.execute(arguments)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                f"{type(exc).__name__}: {exc}", error_type="unexpected_tool_error"
            ) from exc

        try:
            output = tool.output_model.model_validate(raw_output)
            return output.model_dump(mode="json")
        except Exception as exc:
            raise ToolOutputValidationError(str(exc)) from exc

    async def execute(
        self,
        name: str,
        arguments: object,
        *,
        version: Optional[str] = None,
    ) -> dict[str, Any]:
        tool = self.get(name, version)
        validated = self.validate_arguments(tool, arguments)
        return await self.execute_validated(tool, validated)
