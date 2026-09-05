from __future__ import annotations

import asyncio
from typing import Any

from research_agent import application
from research_agent.config import AppConfig
from research_agent.llm import LLMRequest, LLMResponse
from research_agent.models import SessionStatus
from research_agent.provenance import ResearchToolOutput
from research_agent.tools import ToolDefinition
from research_agent.web_search import SearchWebInput


class ApplicationLLM:
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []
        self.action_count = 0
        self.closed = False

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if request.purpose == "plan":
            output: object = {
                "decision_summary": "Research one generic source",
                "objective": {
                    "original_query": request.context["original_query"],
                    "goal": "Answer with cited evidence",
                    "requirements": [
                        {"id": "req_answer", "description": "Answer the query"}
                    ],
                },
                "tasks": [
                    {
                        "id": "task_search",
                        "description": "Find relevant evidence",
                        "rationale": "The answer requires a source",
                        "expected_output": "A source-backed fact",
                        "objective_requirement_ids": ["req_answer"],
                    }
                ],
            }
        elif request.purpose == "action":
            self.action_count += 1
            output = (
                {
                    "action": "tool_call",
                    "decision_summary": "Use the registered search capability",
                    "task_id": "task_search",
                    "tool_name": "search_web",
                    "tool_version": "1",
                    "arguments": {"query": "generic topic"},
                }
                if self.action_count == 1
                else {
                    "action": "finish",
                    "decision_summary": "Evidence is sufficient",
                    "completion_summary": "Ready for cited synthesis",
                }
            )
        elif request.purpose == "evidence":
            chunk = request.context["source_chunks"][0]
            output = {
                "evidence": [
                    {
                        "task_id": "task_search",
                        "claim": "The source states a fact.",
                        "source_chunk_ids": [chunk["id"]],
                        "verbatim_excerpt": "Source fact.",
                        "confidence": 0.9,
                    }
                ]
            }
        else:
            evidence_id = request.context["evidence"][0]["evidence"]["id"]
            output = {
                "title": "Application report",
                "claims": [
                    {
                        "text": "The source states a fact.",
                        "evidence_ids": [evidence_id],
                    }
                ],
                "limitations": [],
            }
        return LLMResponse(output=output, provider="fake", model="fake-v1")

    async def aclose(self) -> None:
        self.closed = True


class ApplicationSearchTool:
    input_model = SearchWebInput
    output_model = ResearchToolOutput

    def __init__(self) -> None:
        self.definition = ToolDefinition.from_models(
            name="search_web",
            version="1",
            description="Search a deterministic fixture source",
            input_model=self.input_model,
            output_model=self.output_model,
            capabilities=["web_search", "source_retrieval"],
            provider="fake",
        )
        self.closed = False

    async def execute(self, arguments: SearchWebInput) -> object:
        return {
            "sources": [
                {
                    "source_url": "https://example.test/application",
                    "title": "Application source",
                    "content": "Source fact.",
                }
            ]
        }

    async def aclose(self) -> None:
        self.closed = True


def test_application_composes_live_adapters_and_closes_them(monkeypatch: Any) -> None:
    llm = ApplicationLLM()
    search = ApplicationSearchTool()
    seen: dict[str, str] = {}

    def make_llm(**kwargs: Any) -> ApplicationLLM:
        seen["openai_key"] = kwargs["api_key"]
        seen["model"] = kwargs["model"]
        return llm

    def make_search(**kwargs: Any) -> ApplicationSearchTool:
        seen["tavily_key"] = kwargs["api_key"]
        return search

    monkeypatch.setattr(application, "OpenAIResponsesClient", make_llm)
    monkeypatch.setattr(application, "TavilySearchTool", make_search)
    config = AppConfig(
        openai_api_key="test-openai-key",
        tavily_api_key="test-tavily-key",
        openai_model="test-model",
    )

    session = asyncio.run(
        application.run_live_research("Research a generic topic", config=config)
    )

    assert seen == {
        "openai_key": "test-openai-key",
        "model": "test-model",
        "tavily_key": "test-tavily-key",
    }
    assert session.status == SessionStatus.COMPLETED
    assert "https://example.test/application" in session.completion_summary
    assert [request.purpose for request in llm.requests] == [
        "plan",
        "action",
        "evidence",
        "action",
        "synthesis",
    ]
    assert llm.closed is True
    assert search.closed is True
