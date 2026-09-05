from __future__ import annotations

import asyncio
import os

import pytest

from research_agent.application import run_live_research
from research_agent.config import AppConfig, ConfigurationError
from research_agent.models import RuntimeLimits, SessionStatus


def live_config() -> AppConfig | None:
    if os.environ.get("RUN_LIVE_TESTS") != "1":
        return None
    try:
        return AppConfig.from_environment()
    except ConfigurationError:
        return None


LIVE_CONFIG = live_config()


@pytest.mark.live
@pytest.mark.skipif(
    LIVE_CONFIG is None,
    reason="requires RUN_LIVE_TESTS=1 plus OpenAI and Tavily credentials",
)
def test_live_research_vertical_slice() -> None:
    assert LIVE_CONFIG is not None
    session = asyncio.run(
        run_live_research(
            "Use one web search to identify one current official OpenAI API guide, "
            "then finish with one cited factual sentence.",
            config=LIVE_CONFIG,
            limits=RuntimeLimits(
                max_iterations=3,
                max_tool_calls=1,
                max_retries_per_tool=0,
                max_model_output_tokens=1_200,
            ),
        )
    )

    assert session.status in {SessionStatus.COMPLETED, SessionStatus.PARTIAL}
    assert session.tool_calls
    assert session.source_snapshots
    assert session.evidence
    assert session.report_claims
    assert session.citations
