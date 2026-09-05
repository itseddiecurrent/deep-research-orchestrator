from __future__ import annotations

import asyncio
from typing import Any

import pytest

from research_agent.llm import LLMRequest, LLMResponse
from research_agent.models import SessionStatus
from research_agent.provenance import EvidenceExtractor, ResearchToolOutput
from research_agent.runtime import AgentRuntime
from research_agent.synthesis import SynthesisService
from research_agent.tools import ToolDefinition, ToolRegistry
from research_agent.web_search import SearchWebInput


class FixtureSearchTool:
    input_model = SearchWebInput
    output_model = ResearchToolOutput

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[SearchWebInput] = []
        self.definition = ToolDefinition.from_models(
            name="search_web",
            version="1",
            description="Search full-content sources for any natural-language query",
            input_model=self.input_model,
            output_model=self.output_model,
            capabilities=["web_search", "source_retrieval"],
            provider="fixture",
        )

    async def execute(self, arguments: SearchWebInput) -> object:
        self.calls.append(arguments)
        return {
            "sources": [
                {
                    "source_url": "https://example.test/generic-source",
                    "title": "Generic fixture source",
                    "content": self.content,
                }
            ]
        }


class GenericResearchClient:
    def __init__(self, query: str) -> None:
        self.query = query
        self.requests: list[LLMRequest] = []
        self.action_count = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request.model_copy(deep=True))
        if request.purpose == "plan":
            output: object = {
                "decision_summary": "Create one source-backed research task",
                "objective": {
                    "original_query": self.query,
                    "goal": self.query,
                    "requirements": [
                        {"id": "req_answer", "description": "Answer the query"}
                    ],
                },
                "tasks": [
                    {
                        "id": "task_research",
                        "description": "Find source-backed information",
                        "rationale": "The query requires external evidence",
                        "expected_output": "Relevant source-backed facts",
                        "objective_requirement_ids": ["req_answer"],
                    }
                ],
            }
        elif request.purpose == "action":
            self.action_count += 1
            output = (
                {
                    "action": "tool_call",
                    "decision_summary": "Use the advertised generic search tool",
                    "task_id": "task_research",
                    "tool_name": "search_web",
                    "tool_version": "1",
                    "arguments": {"query": self.query},
                }
                if self.action_count == 1
                else {
                    "action": "finish",
                    "decision_summary": "The requested dimension has evidence",
                    "completion_summary": "Proceed to cited synthesis",
                }
            )
        elif request.purpose == "evidence":
            chunk = request.context["source_chunks"][0]
            output = {
                "evidence": [
                    {
                        "task_id": "task_research",
                        "claim": chunk["text"],
                        "source_chunk_ids": [chunk["id"]],
                        "verbatim_excerpt": chunk["text"],
                        "confidence": 0.9,
                    }
                ]
            }
        else:
            evidence = request.context["evidence"][0]["evidence"]
            output = {
                "title": "Generic cited result",
                "claims": [
                    {"text": evidence["claim"], "evidence_ids": [evidence["id"]]}
                ],
                "limitations": [],
            }
        return LLMResponse(output=output, provider="fixture", model="fixture-v1")


@pytest.mark.parametrize(
    ("query", "source_content"),
    [
        (
            "Compare two serverless inference approaches on latency and portability.",
            "Approach A has lower cold-start latency; approach B is more portable.",
        ),
        (
            "Summarize conflicting findings on whether intervention X improves sleep.",
            "Trial A reports improved sleep, while Trial B reports no measurable effect.",
        ),
    ],
)
def test_unrelated_queries_use_the_same_generic_runtime_and_registry(
    query: str, source_content: str
) -> None:
    client = GenericResearchClient(query)
    tool = FixtureSearchTool(source_content)
    registry = ToolRegistry()
    registry.register(tool)
    catalog_version = registry.catalog_version
    runtime = AgentRuntime(
        llm_client=client,
        tool_registry=registry,
        evidence_extractor=EvidenceExtractor(llm_client=client),
        synthesis_service=SynthesisService(llm_client=client),
    )

    session = asyncio.run(runtime.run(query))

    assert registry.catalog_version == catalog_version
    assert [call.query for call in tool.calls] == [query]
    assert [call.tool_name for call in session.tool_calls] == ["search_web"]
    assert [request.purpose for request in client.requests] == [
        "plan",
        "action",
        "evidence",
        "action",
        "synthesis",
    ]
    assert client.requests[3].context["original_query"] == query
    assert session.status == SessionStatus.COMPLETED
    assert source_content in session.completion_summary
    assert session.evidence and session.report_claims and session.citations
