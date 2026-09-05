"""Strict domain and boundary schemas for the research-agent MVP.

These models contain no research-domain routing. They are the validation boundary
between model proposals, deterministic runtime state, tool results, and citations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    TypeAdapter,
    model_validator,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SessionStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    RESEARCHING = "researching"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    OBSOLETE = "obsolete"
    CANCELLED = "cancelled"


class ToolCallStatus(str, Enum):
    REQUESTED = "requested"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TraceEventType(str, Enum):
    SESSION_STARTED = "session_started"
    OBJECTIVE_CREATED = "objective_created"
    PLAN_CREATED = "plan_created"
    PLANNER_DECISION = "planner_decision"
    TOOL_REQUESTED = "tool_requested"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    EVIDENCE_CREATED = "evidence_created"
    EVALUATION_COMPLETED = "evaluation_completed"
    SYNTHESIS_STARTED = "synthesis_started"
    CITATION_VALIDATED = "citation_validated"
    LIMIT_REACHED = "limit_reached"
    SESSION_COMPLETED = "session_completed"
    SESSION_PARTIAL = "session_partial"
    SESSION_FAILED = "session_failed"


class RuntimeLimits(StrictModel):
    max_iterations: int = Field(default=12, ge=1)
    max_tool_calls: int = Field(default=8, ge=0)
    max_retries_per_tool: int = Field(default=1, ge=0)
    tool_timeout_seconds: float = Field(default=20.0, gt=0)
    max_model_output_tokens: int = Field(default=2_000, ge=128)
    max_tool_result_bytes: int = Field(default=2_000_000, ge=1_024)


class ObjectiveRequirement(StrictModel):
    id: NonEmptyStr
    description: NonEmptyStr
    required: bool = True


class ResearchObjective(StrictModel):
    original_query: NonEmptyStr
    goal: NonEmptyStr
    requirements: list[ObjectiveRequirement] = Field(min_length=1)
    constraints: list[NonEmptyStr] = Field(default_factory=list)
    assumptions: list[NonEmptyStr] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def requirement_ids_are_unique(self) -> "ResearchObjective":
        ids = [requirement.id for requirement in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("objective requirement IDs must be unique")
        return self


class ResearchTask(StrictModel):
    id: NonEmptyStr
    description: NonEmptyStr
    rationale: NonEmptyStr
    expected_output: NonEmptyStr
    objective_requirement_ids: list[NonEmptyStr] = Field(min_length=1)
    depends_on: list[NonEmptyStr] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING

    @model_validator(mode="after")
    def dependencies_are_well_formed(self) -> "ResearchTask":
        if self.id in self.depends_on:
            raise ValueError("a task cannot depend on itself")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("task dependencies must be unique")
        return self


class ResearchPlan(StrictModel):
    decision_summary: NonEmptyStr
    objective: ResearchObjective
    tasks: list[ResearchTask] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references_and_cycles(self) -> "ResearchPlan":
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("research task IDs must be unique")

        known_tasks = set(task_ids)
        known_requirements = {
            requirement.id for requirement in self.objective.requirements
        }
        dependencies: dict[str, list[str]] = {}
        for task in self.tasks:
            unknown_dependencies = set(task.depends_on) - known_tasks
            if unknown_dependencies:
                raise ValueError(
                    f"task {task.id} has unknown dependencies: "
                    f"{sorted(unknown_dependencies)}"
                )
            unknown_requirements = (
                set(task.objective_requirement_ids) - known_requirements
            )
            if unknown_requirements:
                raise ValueError(
                    f"task {task.id} has unknown objective requirements: "
                    f"{sorted(unknown_requirements)}"
                )
            dependencies[task.id] = task.depends_on

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("research task dependencies must be acyclic")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in dependencies[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)
        return self


class ToolCallAction(StrictModel):
    action: Literal["tool_call"]
    decision_summary: NonEmptyStr
    task_id: NonEmptyStr
    tool_name: NonEmptyStr
    tool_version: Optional[NonEmptyStr] = None
    arguments: dict[str, Any]


class FinishAction(StrictModel):
    action: Literal["finish"]
    decision_summary: NonEmptyStr
    completion_summary: NonEmptyStr
    is_partial: bool = False
    unresolved_questions: list[NonEmptyStr] = Field(default_factory=list)


AgentAction = Annotated[
    Union[ToolCallAction, FinishAction], Field(discriminator="action")
]
agent_action_adapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)


def parse_agent_action(value: object) -> AgentAction:
    """Validate an untrusted planner response as a supported action."""

    return agent_action_adapter.validate_python(value)


def agent_action_json_schema() -> dict[str, Any]:
    """Return the provider-neutral JSON Schema supplied to structured LLM calls."""

    return agent_action_adapter.json_schema()


class ToolAttempt(StrictModel):
    id: str = Field(default_factory=lambda: new_id("attempt"))
    tool_call_id: NonEmptyStr
    attempt_number: int = Field(ge=1)
    status: ToolCallStatus
    started_at: AwareDatetime = Field(default_factory=utc_now)
    completed_at: Optional[AwareDatetime] = None
    latency_ms: Optional[float] = Field(default=None, ge=0)
    error_type: Optional[NonEmptyStr] = None
    error_message: Optional[NonEmptyStr] = None
    retryable: bool = False


class ToolCall(StrictModel):
    id: str = Field(default_factory=lambda: new_id("tool_call"))
    task_id: NonEmptyStr
    tool_name: NonEmptyStr
    tool_version: NonEmptyStr
    catalog_version: NonEmptyStr
    arguments: dict[str, Any]
    status: ToolCallStatus = ToolCallStatus.REQUESTED
    requested_at: AwareDatetime = Field(default_factory=utc_now)
    completed_at: Optional[AwareDatetime] = None
    attempts: list[ToolAttempt] = Field(default_factory=list)


class ToolResult(StrictModel):
    id: str = Field(default_factory=lambda: new_id("tool_result"))
    tool_call_id: NonEmptyStr
    success: bool
    raw_output: Any = None
    error: Optional[NonEmptyStr] = None
    retryable: bool = False
    received_at: AwareDatetime = Field(default_factory=utc_now)
    size_bytes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def failed_results_have_an_error(self) -> "ToolResult":
        if not self.success and self.error is None:
            raise ValueError("a failed tool result must include an error")
        if self.success and self.error is not None:
            raise ValueError("a successful tool result cannot include an error")
        return self


class Observation(StrictModel):
    id: str = Field(default_factory=lambda: new_id("observation"))
    tool_result_id: NonEmptyStr
    success: bool
    summary: NonEmptyStr
    created_at: AwareDatetime = Field(default_factory=utc_now)


class SourceSnapshot(StrictModel):
    id: str = Field(default_factory=lambda: new_id("source"))
    tool_result_id: NonEmptyStr
    source_url: HttpUrl
    title: NonEmptyStr
    retrieved_at: AwareDatetime = Field(default_factory=utc_now)
    media_type: NonEmptyStr = "text/markdown"
    content: NonEmptyStr
    content_hash: Sha256Hex


class SourceChunk(StrictModel):
    id: str = Field(default_factory=lambda: new_id("chunk"))
    source_snapshot_id: NonEmptyStr
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    text: NonEmptyStr
    content_hash: Sha256Hex

    @model_validator(mode="after")
    def offsets_are_ordered(self) -> "SourceChunk":
        if self.end_offset <= self.start_offset:
            raise ValueError("chunk end_offset must be greater than start_offset")
        return self


class Evidence(StrictModel):
    id: str = Field(default_factory=lambda: new_id("evidence"))
    task_id: NonEmptyStr
    claim: NonEmptyStr
    source_chunk_ids: list[NonEmptyStr] = Field(min_length=1)
    verbatim_excerpt: NonEmptyStr
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: AwareDatetime = Field(default_factory=utc_now)


class ReportClaim(StrictModel):
    id: str = Field(default_factory=lambda: new_id("report_claim"))
    text: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)
    material: bool = True


class Citation(StrictModel):
    id: str = Field(default_factory=lambda: new_id("citation"))
    report_claim_id: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)
    source_snapshot_ids: list[NonEmptyStr] = Field(min_length=1)
    display_number: int = Field(ge=1)


class TraceEvent(StrictModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    event_type: TraceEventType
    timestamp: AwareDatetime = Field(default_factory=utc_now)
    session_id: NonEmptyStr
    objective_version: int = Field(default=1, ge=1)
    task_id: Optional[NonEmptyStr] = None
    tool_call_id: Optional[NonEmptyStr] = None
    decision_summary: Optional[NonEmptyStr] = None
    data: dict[str, Any] = Field(default_factory=dict)


class ResearchSession(StrictModel):
    id: str = Field(default_factory=lambda: new_id("session"))
    original_query: NonEmptyStr
    status: SessionStatus = SessionStatus.CREATED
    limits: RuntimeLimits = Field(default_factory=RuntimeLimits)
    plan: Optional[ResearchPlan] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    source_snapshots: list[SourceSnapshot] = Field(default_factory=list)
    source_chunks: list[SourceChunk] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    report_claims: list[ReportClaim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    iteration_count: int = Field(default=0, ge=0)
    completion_summary: Optional[NonEmptyStr] = None
    unresolved_questions: list[NonEmptyStr] = Field(default_factory=list)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)
