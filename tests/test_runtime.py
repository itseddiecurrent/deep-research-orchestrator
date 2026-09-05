from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque

import pytest

from research_agent.llm import LLMRequest, LLMResponse, ScriptedLLMClient
from research_agent.models import (
    ObjectiveRequirement,
    ResearchObjective,
    ResearchPlan,
    ResearchTask,
    RuntimeLimits,
    SessionStatus,
    StrictModel,
    ToolCallStatus,
    TraceEventType,
)
from research_agent.runtime import AgentRuntime
from research_agent.provenance import EvidenceExtractor, ResearchToolOutput
from research_agent.synthesis import SynthesisService
from research_agent.tools import ToolDefinition, ToolExecutionError, ToolRegistry


class QueryInput(StrictModel):
    query: str


class TextOutput(StrictModel):
    text: str


class ScriptedTool:
    input_model = QueryInput
    output_model = TextOutput

    def __init__(
        self,
        name: str,
        responses: list[object] | None = None,
        *,
        version: str = "1",
        idempotent: bool = True,
        timeout_seconds: float | None = None,
    ) -> None:
        self.definition = ToolDefinition.from_models(
            name=name,
            version=version,
            description=f"Look up general information using {name}",
            input_model=self.input_model,
            output_model=self.output_model,
            capabilities=["lookup"],
            idempotent=idempotent,
            timeout_seconds=timeout_seconds,
        )
        self.responses: Deque[object] = deque(responses or [{"text": name}])
        self.calls: list[QueryInput] = []

    async def execute(self, arguments: QueryInput) -> object:
        self.calls.append(arguments)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class SlowTool(ScriptedTool):
    async def execute(self, arguments: QueryInput) -> object:
        self.calls.append(arguments)
        await asyncio.sleep(0.03)
        return {"text": "late"}


class ResearchSourceTool(ScriptedTool):
    output_model = ResearchToolOutput


class PipelineLLMClient:
    def __init__(
        self,
        query: str,
        *,
        partial_finish: bool = False,
        invalid_evidence: bool = False,
        invalid_synthesis: bool = False,
    ) -> None:
        self.query = query
        self.partial_finish = partial_finish
        self.invalid_evidence = invalid_evidence
        self.invalid_synthesis = invalid_synthesis
        self.requests: list[LLMRequest] = []
        self.action_count = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request.model_copy(deep=True))
        if request.purpose == "plan":
            output: object = make_plan(self.query)
        elif request.purpose == "action":
            self.action_count += 1
            if self.action_count == 1:
                output = tool_action("search_web")
            else:
                output = finish(partial=self.partial_finish)
        elif request.purpose == "evidence":
            chunk = request.context["source_chunks"][0]
            output = {
                "evidence": [
                    {
                        "task_id": "task_lookup",
                        "claim": "The source supports the researched fact.",
                        "source_chunk_ids": [
                            "chunk_invented" if self.invalid_evidence else chunk["id"]
                        ],
                        "verbatim_excerpt": "Source-backed fact.",
                        "confidence": 0.9,
                    }
                ]
            }
        else:
            assert request.purpose == "synthesis"
            evidence_id = request.context["evidence"][0]["evidence"]["id"]
            output = (
                {"invalid": True}
                if self.invalid_synthesis
                else {
                    "title": "Cited research",
                    "claims": [
                        {
                            "text": "The researched fact is supported.",
                            "evidence_ids": [evidence_id],
                        }
                    ],
                    "limitations": [],
                }
            )
        return LLMResponse(output=output, provider="scripted", model="scripted-v1")


def make_plan(query: str) -> ResearchPlan:
    return ResearchPlan(
        decision_summary="Research one generic requirement",
        objective=ResearchObjective(
            original_query=query,
            goal="Answer the query with a generic lookup",
            requirements=[
                ObjectiveRequirement(
                    id="req_answer", description="Answer the requested question"
                )
            ],
        ),
        tasks=[
            ResearchTask(
                id="task_lookup",
                description="Look up relevant information",
                rationale="The objective requires external information",
                expected_output="Relevant facts",
                objective_requirement_ids=["req_answer"],
            )
        ],
    )


def tool_action(name: str, *, version: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": "tool_call",
        "decision_summary": f"Use {name} for the task",
        "task_id": "task_lookup",
        "tool_name": name,
        "arguments": {"query": "generic topic"},
    }
    if version is not None:
        payload["tool_version"] = version
    return payload


def finish(*, partial: bool = False) -> dict[str, Any]:
    return {
        "action": "finish",
        "decision_summary": "The available observations are sufficient",
        "completion_summary": "Finished from structured observations",
        "is_partial": partial,
        "unresolved_questions": ["One gap remains"] if partial else [],
    }


def run_runtime(
    query: str,
    responses: list[object],
    registry: ToolRegistry,
    *,
    limits: RuntimeLimits | None = None,
) -> tuple[object, ScriptedLLMClient]:
    client = ScriptedLLMClient(responses)
    runtime = AgentRuntime(llm_client=client, tool_registry=registry)
    session = asyncio.run(runtime.run(query, limits=limits))
    return session, client


def test_planner_selects_one_of_two_advertised_tools_and_observes_result() -> None:
    query = "Research an unseen technology question"
    registry = ToolRegistry()
    irrelevant = ScriptedTool("lookup_documents")
    selected = ScriptedTool("lookup_benchmarks", [{"text": "measured result"}])
    registry.register(irrelevant)
    registry.register(selected)

    session, client = run_runtime(
        query,
        [make_plan(query), tool_action("lookup_benchmarks"), finish()],
        registry,
    )

    assert session.status == SessionStatus.COMPLETED
    assert irrelevant.calls == []
    assert [call.query for call in selected.calls] == ["generic topic"]
    assert len(client.requests[0].context["tool_catalog"]) == 2
    observation = session.observations[0].model_dump(mode="json")
    assert client.requests[2].context["observations"] == [observation]
    assert client.requests[2].context["tool_results"][0]["id"] == observation[
        "tool_result_id"
    ]
    assert client.requests[2].context["tool_calls"][0]["tool_name"] == (
        "lookup_benchmarks"
    )
    assert "measured result" in observation["summary"]
    assert session.tool_calls[0].status == ToolCallStatus.SUCCEEDED


def test_finish_action_terminates_without_consuming_later_script_items() -> None:
    query = "A question answerable without another call"
    registry = ToolRegistry()
    session, client = run_runtime(
        query,
        [make_plan(query), finish(), tool_action("never_called")],
        registry,
    )

    assert session.status == SessionStatus.COMPLETED
    assert session.completion_summary == "Finished from structured observations"
    assert session.tool_calls == []
    assert len(client.requests) == 2
    assert client.remaining_responses == 1


def test_unknown_tool_is_not_invoked_and_failure_observation_reaches_planner() -> None:
    query = "A generic lookup"
    registry = ToolRegistry()
    known = ScriptedTool("known_lookup")
    registry.register(known)
    session, client = run_runtime(
        query,
        [make_plan(query), tool_action("invented_lookup"), finish(partial=True)],
        registry,
    )

    assert known.calls == []
    assert session.status == SessionStatus.PARTIAL
    assert session.tool_calls[0].status == ToolCallStatus.FAILED
    assert session.tool_calls[0].attempts == []
    assert session.tool_results[0].success is False
    assert "unknown_tool" in session.observations[0].summary
    assert client.requests[2].context["observations"][0]["success"] is False


@pytest.mark.parametrize(
    ("limits", "expected_limit", "expected_calls"),
    [
        (RuntimeLimits(max_iterations=1), "max_iterations", 1),
        (RuntimeLimits(max_tool_calls=0), "max_tool_calls", 0),
    ],
)
def test_hard_limits_terminate_with_an_explicit_partial_result(
    limits: RuntimeLimits, expected_limit: str, expected_calls: int
) -> None:
    query = "Keep researching"
    registry = ToolRegistry()
    tool = ScriptedTool("lookup", [{"text": "first"}])
    registry.register(tool)
    session, _ = run_runtime(
        query,
        [make_plan(query), tool_action("lookup")],
        registry,
        limits=limits,
    )

    assert session.status == SessionStatus.PARTIAL
    assert len(tool.calls) == expected_calls
    limit_events = [
        event for event in session.trace if event.event_type == TraceEventType.LIMIT_REACHED
    ]
    assert limit_events[-1].data["limit"] == expected_limit
    assert session.unresolved_questions


@pytest.mark.parametrize(
    "bad_response",
    [
        {"action": "unsupported", "decision_summary": "Invalid"},
        {"action": "finish", "decision_summary": "Missing required field"},
    ],
)
def test_invalid_action_fails_without_tool_execution(bad_response: object) -> None:
    query = "Malformed planner output"
    registry = ToolRegistry()
    tool = ScriptedTool("lookup")
    registry.register(tool)
    session, _ = run_runtime(query, [make_plan(query), bad_response], registry)

    assert session.status == SessionStatus.FAILED
    assert tool.calls == []
    assert session.trace[-1].event_type == TraceEventType.SESSION_FAILED
    assert session.trace[-1].data["error_type"] == "invalid_planner_output"


def test_invalid_plan_fails_before_the_action_loop() -> None:
    registry = ToolRegistry()
    session, client = run_runtime(
        "Original query",
        [make_plan("Different rewritten query")],
        registry,
    )

    assert session.status == SessionStatus.FAILED
    assert session.iteration_count == 0
    assert len(client.requests) == 1
    assert session.trace[-1].data["error_type"] == "invalid_plan"


def test_retryable_idempotent_failure_retries_then_succeeds() -> None:
    query = "Retry a transient lookup"
    registry = ToolRegistry()
    tool = ScriptedTool(
        "lookup",
        [
            ToolExecutionError(
                "temporary outage", retryable=True, error_type="transient_transport"
            ),
            {"text": "recovered"},
        ],
    )
    registry.register(tool)
    session, _ = run_runtime(
        query,
        [make_plan(query), tool_action("lookup"), finish()],
        registry,
        limits=RuntimeLimits(max_retries_per_tool=1),
    )

    assert session.status == SessionStatus.COMPLETED
    assert len(tool.calls) == 2
    assert [attempt.status for attempt in session.tool_calls[0].attempts] == [
        ToolCallStatus.FAILED,
        ToolCallStatus.SUCCEEDED,
    ]
    retry_event = next(
        event
        for event in session.trace
        if event.event_type == TraceEventType.TOOL_FAILED
    )
    assert retry_event.data["will_retry"] is True


@pytest.mark.parametrize("idempotent", [True, False])
def test_permanent_or_non_idempotent_failure_does_not_retry(
    idempotent: bool,
) -> None:
    query = "Do not retry an unsafe failure"
    retryable = not idempotent
    registry = ToolRegistry()
    tool = ScriptedTool(
        "lookup",
        [
            ToolExecutionError(
                "cannot execute",
                retryable=retryable,
                error_type="permanent" if idempotent else "transient_transport",
            ),
            {"text": "must remain unused"},
        ],
        idempotent=idempotent,
    )
    registry.register(tool)
    session, _ = run_runtime(
        query,
        [make_plan(query), tool_action("lookup"), finish(partial=True)],
        registry,
        limits=RuntimeLimits(max_retries_per_tool=2),
    )

    assert len(tool.calls) == 1
    assert len(session.tool_calls[0].attempts) == 1
    assert session.tool_results[0].success is False


def test_repeated_retryable_failure_stops_at_retry_cap() -> None:
    query = "Bound repeated transient failures"
    failure = lambda: ToolExecutionError(  # noqa: E731
        "temporary outage", retryable=True, error_type="transient_transport"
    )
    registry = ToolRegistry()
    tool = ScriptedTool("lookup", [failure(), failure(), failure()])
    registry.register(tool)
    session, _ = run_runtime(
        query,
        [make_plan(query), tool_action("lookup"), finish(partial=True)],
        registry,
        limits=RuntimeLimits(max_retries_per_tool=1),
    )

    assert len(tool.calls) == 2
    assert len(session.tool_calls[0].attempts) == 2
    assert session.tool_calls[0].status == ToolCallStatus.FAILED
    assert session.tool_results[0].retryable is True


def test_timeout_is_retryable_but_stops_at_the_configured_cap() -> None:
    query = "Bound a slow tool"
    registry = ToolRegistry()
    tool = SlowTool("slow_lookup", timeout_seconds=0.001)
    registry.register(tool)
    session, _ = run_runtime(
        query,
        [make_plan(query), tool_action("slow_lookup"), finish(partial=True)],
        registry,
        limits=RuntimeLimits(max_retries_per_tool=1, tool_timeout_seconds=0.01),
    )

    assert len(tool.calls) == 2
    assert session.tool_calls[0].status == ToolCallStatus.FAILED
    assert all(
        attempt.error_type == "tool_timeout"
        for attempt in session.tool_calls[0].attempts
    )


def test_oversized_output_is_rejected_before_it_becomes_an_observation() -> None:
    query = "Bound tool output"
    registry = ToolRegistry()
    tool = ScriptedTool("lookup", [{"text": "x" * 2_000}])
    registry.register(tool)
    session, _ = run_runtime(
        query,
        [make_plan(query), tool_action("lookup"), finish(partial=True)],
        registry,
        limits=RuntimeLimits(max_tool_result_bytes=1_024),
    )

    assert session.tool_results[0].success is False
    assert session.tool_results[0].raw_output is None
    assert "tool_result_too_large" in session.observations[0].summary
    assert any(
        event.event_type == TraceEventType.LIMIT_REACHED
        and event.data["limit"] == "max_tool_result_bytes"
        for event in session.trace
    )


def test_reported_model_output_token_limit_is_enforced() -> None:
    query = "Reject an over-budget model response"
    client = ScriptedLLMClient(
        [
            LLMResponse(
                output=make_plan(query),
                provider="scripted",
                model="scripted-v1",
                output_tokens=129,
            )
        ]
    )
    runtime = AgentRuntime(llm_client=client, tool_registry=ToolRegistry())
    session = asyncio.run(
        runtime.run(query, limits=RuntimeLimits(max_model_output_tokens=128))
    )

    assert session.status == SessionStatus.FAILED
    assert session.trace[-1].data["error_type"] == "invalid_plan"


def test_trace_contains_required_lifecycle_events_without_reasoning_field() -> None:
    query = "Trace one successful call"
    registry = ToolRegistry()
    registry.register(ScriptedTool("lookup"))
    session, _ = run_runtime(
        query,
        [make_plan(query), tool_action("lookup"), finish()],
        registry,
    )

    event_types = [event.event_type for event in session.trace]
    assert event_types == [
        TraceEventType.SESSION_STARTED,
        TraceEventType.OBJECTIVE_CREATED,
        TraceEventType.PLAN_CREATED,
        TraceEventType.PLANNER_DECISION,
        TraceEventType.TOOL_REQUESTED,
        TraceEventType.TOOL_COMPLETED,
        TraceEventType.PLANNER_DECISION,
        TraceEventType.SESSION_COMPLETED,
    ]
    assert all(event.session_id == session.id for event in session.trace)
    assert all("reasoning" not in event.model_dump() for event in session.trace)


def make_pipeline_runtime(
    query: str, client: PipelineLLMClient
) -> tuple[AgentRuntime, ResearchSourceTool]:
    registry = ToolRegistry()
    tool = ResearchSourceTool(
        "search_web",
        [
            {
                "sources": [
                    {
                        "source_url": "https://example.test/research",
                        "title": "Research source",
                        "content": "Source-backed fact.",
                    }
                ]
            }
        ],
    )
    registry.register(tool)
    extractor = EvidenceExtractor(llm_client=client)
    return (
        AgentRuntime(
            llm_client=client,
            tool_registry=registry,
            evidence_extractor=extractor,
            synthesis_service=SynthesisService(llm_client=client),
        ),
        tool,
    )


def test_integrated_runtime_extracts_evidence_before_planning_and_synthesizes() -> None:
    query = "Research an unseen evidence-backed topic"
    client = PipelineLLMClient(query)
    runtime, tool = make_pipeline_runtime(query, client)

    session = asyncio.run(runtime.run(query))

    assert len(tool.calls) == 1
    assert [request.purpose for request in client.requests] == [
        "plan",
        "action",
        "evidence",
        "action",
        "synthesis",
    ]
    second_action = client.requests[3]
    assert second_action.context["evidence"] == [
        session.evidence[0].model_dump(mode="json")
    ]
    assert session.status == SessionStatus.COMPLETED
    assert "The researched fact is supported. [1]" in session.completion_summary
    assert "https://example.test/research" in session.completion_summary
    assert session.source_snapshots and session.source_chunks and session.evidence
    assert session.report_claims and session.citations


def test_evidence_processing_failure_is_a_safe_planner_observation() -> None:
    query = "Research a source whose extraction fails"
    client = PipelineLLMClient(query, partial_finish=True, invalid_evidence=True)
    registry = ToolRegistry()
    tool = ResearchSourceTool(
        "search_web",
        [
            {
                "sources": [
                    {
                        "source_url": "https://example.test/research",
                        "title": "Research source",
                        "content": "Source-backed fact.",
                    }
                ]
            }
        ],
    )
    registry.register(tool)
    runtime = AgentRuntime(
        llm_client=client,
        tool_registry=registry,
        evidence_extractor=EvidenceExtractor(llm_client=client),
    )

    session = asyncio.run(runtime.run(query))

    assert session.tool_calls[0].status == ToolCallStatus.SUCCEEDED
    assert session.evidence == []
    assert session.observations[-1].success is False
    assert session.observations[-1].summary == (
        "evidence_processing_failed: EvidenceValidationError"
    )
    assert client.requests[3].context["observations"][-1]["success"] is False
    assert any(
        event.event_type == TraceEventType.EVIDENCE_FAILED
        for event in session.trace
    )
    assert session.status == SessionStatus.PARTIAL


def test_integrated_synthesis_preserves_planner_declared_partial_status() -> None:
    query = "Research a topic with one unresolved gap"
    client = PipelineLLMClient(query, partial_finish=True)
    runtime, _ = make_pipeline_runtime(query, client)

    session = asyncio.run(runtime.run(query))

    assert session.status == SessionStatus.PARTIAL
    assert session.unresolved_questions == ["One gap remains"]
    assert "## Limitations" in session.completion_summary
    assert "One gap remains" in session.completion_summary


def test_integrated_synthesis_failure_terminates_without_unvalidated_report() -> None:
    query = "Research a topic whose synthesis fails"
    client = PipelineLLMClient(query, invalid_synthesis=True)
    runtime, _ = make_pipeline_runtime(query, client)

    session = asyncio.run(runtime.run(query))

    assert session.status == SessionStatus.FAILED
    assert session.report_claims == []
    assert session.citations == []
    assert session.trace[-1].event_type == TraceEventType.SESSION_FAILED
    assert session.trace[-1].data["error_type"] == "synthesis_failed"


def test_limit_after_evidence_returns_a_cited_partial_report() -> None:
    query = "Research a topic within one action iteration"
    client = PipelineLLMClient(query)
    runtime, _ = make_pipeline_runtime(query, client)

    session = asyncio.run(
        runtime.run(query, limits=RuntimeLimits(max_iterations=1))
    )

    assert [request.purpose for request in client.requests] == [
        "plan",
        "action",
        "evidence",
        "synthesis",
    ]
    assert session.status == SessionStatus.PARTIAL
    assert session.report_claims and session.citations
    assert "The researched fact is supported. [1]" in session.completion_summary
    assert "max_iterations" in session.unresolved_questions[0]
    assert any(
        event.event_type == TraceEventType.LIMIT_REACHED for event in session.trace
    )
