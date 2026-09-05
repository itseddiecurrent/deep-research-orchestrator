"""Composition root for one live, generic research-agent run."""

from __future__ import annotations

from typing import Optional

from research_agent.config import AppConfig
from research_agent.models import ResearchSession, RuntimeLimits
from research_agent.openai_adapter import OpenAIResponsesClient
from research_agent.provenance import EvidenceExtractor
from research_agent.runtime import AgentRuntime
from research_agent.synthesis import SynthesisService
from research_agent.tools import ToolRegistry
from research_agent.web_search import TavilySearchTool


async def run_live_research(
    query: str,
    *,
    config: Optional[AppConfig] = None,
    limits: Optional[RuntimeLimits] = None,
) -> ResearchSession:
    """Build the live adapters, run once, and close owned network clients."""

    settings = config or AppConfig.from_environment()
    effective_limits = limits or RuntimeLimits()
    llm_client = OpenAIResponsesClient(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )
    search_tool: Optional[TavilySearchTool] = None
    try:
        search_tool = TavilySearchTool(
            api_key=settings.tavily_api_key.get_secret_value(),
            timeout_seconds=effective_limits.tool_timeout_seconds,
            max_response_bytes=effective_limits.max_tool_result_bytes,
        )
        registry = ToolRegistry()
        registry.register(search_tool)
        evidence_extractor = EvidenceExtractor(llm_client=llm_client)
        runtime = AgentRuntime(
            llm_client=llm_client,
            tool_registry=registry,
            evidence_extractor=evidence_extractor,
            synthesis_service=SynthesisService(llm_client=llm_client),
        )
        return await runtime.run(query, limits=effective_limits)
    finally:
        try:
            if search_tool is not None:
                await search_tool.aclose()
        finally:
            await llm_client.aclose()
