from __future__ import annotations

from hashlib import sha256

import pytest
from pydantic import ValidationError

from research_agent.models import (
    Citation,
    Evidence,
    FinishAction,
    ObjectiveRequirement,
    Observation,
    ReportClaim,
    ResearchObjective,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
    RuntimeLimits,
    SourceChunk,
    SourceSnapshot,
    ToolCall,
    ToolCallAction,
    ToolCallStatus,
    ToolResult,
    TraceEvent,
    TraceEventType,
    agent_action_json_schema,
    parse_agent_action,
)


def make_objective() -> ResearchObjective:
    return ResearchObjective(
        original_query="Compare two unrelated approaches",
        goal="Compare the approaches using evidence",
        requirements=[
            ObjectiveRequirement(id="req_comparison", description="Compare both")
        ],
    )


def make_task(
    task_id: str = "task_a", *, depends_on: list[str] | None = None
) -> ResearchTask:
    return ResearchTask(
        id=task_id,
        description=f"Research {task_id}",
        rationale="The comparison requires evidence",
        expected_output="Relevant source-backed facts",
        objective_requirement_ids=["req_comparison"],
        depends_on=depends_on or [],
    )


def test_runtime_limits_are_bounded_and_strict() -> None:
    limits = RuntimeLimits(max_tool_calls=0, max_retries_per_tool=0)
    assert limits.max_iterations == 12
    assert limits.max_tool_calls == 0

    with pytest.raises(ValidationError):
        RuntimeLimits(max_iterations=0)
    with pytest.raises(ValidationError):
        RuntimeLimits(tool_timeout_seconds=0)
    with pytest.raises(ValidationError):
        RuntimeLimits(unexpected_limit=1)


def test_objective_rejects_empty_query_and_duplicate_requirements() -> None:
    objective = make_objective()
    assert objective.original_query == "Compare two unrelated approaches"

    with pytest.raises(ValidationError):
        ResearchObjective(
            original_query="   ",
            goal="Valid goal",
            requirements=[ObjectiveRequirement(id="r", description="Requirement")],
        )
    with pytest.raises(ValidationError, match="requirement IDs must be unique"):
        ResearchObjective(
            original_query="Question",
            goal="Goal",
            requirements=[
                ObjectiveRequirement(id="r", description="One"),
                ObjectiveRequirement(id="r", description="Two"),
            ],
        )


def test_research_plan_validates_task_references_and_cycles() -> None:
    plan = ResearchPlan(
        decision_summary="Independent research followed by synthesis",
        objective=make_objective(),
        tasks=[make_task(), make_task("task_b", depends_on=["task_a"])],
    )
    assert plan.tasks[1].depends_on == ["task_a"]

    with pytest.raises(ValidationError, match="unknown dependencies"):
        ResearchPlan(
            decision_summary="Invalid dependency",
            objective=make_objective(),
            tasks=[make_task(depends_on=["missing"])],
        )
    with pytest.raises(ValidationError, match="must be acyclic"):
        ResearchPlan(
            decision_summary="Cyclic dependency",
            objective=make_objective(),
            tasks=[
                make_task("task_a", depends_on=["task_b"]),
                make_task("task_b", depends_on=["task_a"]),
            ],
        )
    bad_requirement = make_task()
    bad_requirement.objective_requirement_ids = ["missing"]
    with pytest.raises(ValidationError, match="unknown objective requirements"):
        ResearchPlan(
            decision_summary="Invalid requirement mapping",
            objective=make_objective(),
            tasks=[bad_requirement],
        )


def test_agent_action_union_parses_valid_actions() -> None:
    tool_action = parse_agent_action(
        {
            "action": "tool_call",
            "decision_summary": "Find relevant primary sources",
            "task_id": "task_a",
            "tool_name": "search_web",
            "arguments": {"query": "an unseen research topic"},
        }
    )
    finish_action = parse_agent_action(
        {
            "action": "finish",
            "decision_summary": "Every required dimension is supported",
            "completion_summary": "Research is sufficient for synthesis",
            "is_partial": False,
        }
    )

    assert isinstance(tool_action, ToolCallAction)
    assert isinstance(finish_action, FinishAction)
    schema = agent_action_json_schema()
    assert schema["discriminator"]["propertyName"] == "action"


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "unknown", "decision_summary": "Invalid"},
        {
            "action": "finish",
            "decision_summary": "Missing completion summary",
        },
        {
            "action": "finish",
            "decision_summary": "Contains an extra field",
            "completion_summary": "Done",
            "invented": True,
        },
    ],
)
def test_agent_action_union_rejects_invalid_llm_output(payload: object) -> None:
    with pytest.raises(ValidationError):
        parse_agent_action(payload)


def test_tool_execution_records_are_strict_and_serializable() -> None:
    call = ToolCall(
        task_id="task_a",
        tool_name="search_web",
        tool_version="1",
        catalog_version="catalog_v1",
        arguments={"query": "topic"},
        status=ToolCallStatus.RUNNING,
    )
    result = ToolResult(
        tool_call_id=call.id,
        success=True,
        raw_output={"results": [{"title": "Source"}]},
        size_bytes=35,
    )
    observation = Observation(
        tool_result_id=result.id,
        success=True,
        summary="One candidate source was returned",
    )

    assert ToolCall.model_validate_json(call.model_dump_json()) == call
    assert ToolResult.model_validate_json(result.model_dump_json()) == result
    assert observation.tool_result_id == result.id

    with pytest.raises(ValidationError, match="failed tool result"):
        ToolResult(tool_call_id=call.id, success=False)
    with pytest.raises(ValidationError, match="successful tool result"):
        ToolResult(tool_call_id=call.id, success=True, error="not allowed")


def test_provenance_models_retain_lineage_identifiers() -> None:
    content = "A source-backed statement appears here."
    snapshot = SourceSnapshot(
        tool_result_id="tool_result_1",
        source_url="https://example.test/source",
        title="Example primary source",
        content=content,
        content_hash=sha256(content.encode()).hexdigest(),
    )
    excerpt = "source-backed statement"
    start = content.index(excerpt)
    chunk = SourceChunk(
        source_snapshot_id=snapshot.id,
        start_offset=start,
        end_offset=start + len(excerpt),
        text=excerpt,
        content_hash=sha256(excerpt.encode()).hexdigest(),
    )
    evidence = Evidence(
        task_id="task_a",
        claim="The source contains a source-backed statement.",
        source_chunk_ids=[chunk.id],
        verbatim_excerpt=excerpt,
        confidence=0.9,
    )
    report_claim = ReportClaim(
        text="The source contains a source-backed statement.",
        evidence_ids=[evidence.id],
    )
    citation = Citation(
        report_claim_id=report_claim.id,
        evidence_ids=[evidence.id],
        source_snapshot_ids=[snapshot.id],
        display_number=1,
    )

    assert chunk.source_snapshot_id == snapshot.id
    assert evidence.source_chunk_ids == [chunk.id]
    assert citation.report_claim_id == report_claim.id
    assert citation.evidence_ids == report_claim.evidence_ids

    with pytest.raises(ValidationError):
        SourceChunk(
            source_snapshot_id=snapshot.id,
            start_offset=4,
            end_offset=4,
            text="invalid",
            content_hash=sha256(b"invalid").hexdigest(),
        )
    with pytest.raises(ValidationError):
        Evidence(
            task_id="task_a",
            claim="Unsupported evidence",
            source_chunk_ids=[],
            verbatim_excerpt="none",
            confidence=0.5,
        )


def test_session_and_trace_round_trip_without_hidden_reasoning() -> None:
    session = ResearchSession(original_query="A generic question")
    session.plan = ResearchPlan(
        decision_summary="Research one source-backed dimension",
        objective=make_objective(),
        tasks=[make_task()],
    )
    session.trace.append(
        TraceEvent(
            event_type=TraceEventType.PLAN_CREATED,
            session_id=session.id,
            decision_summary="Created one task mapped to the objective",
            data={"task_count": 1},
        )
    )

    restored = ResearchSession.model_validate_json(session.model_dump_json())
    assert restored == session
    assert restored.trace[0].decision_summary is not None
    assert "reasoning" not in TraceEvent.model_fields
