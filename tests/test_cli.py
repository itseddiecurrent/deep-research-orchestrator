from __future__ import annotations

import json

from research_agent import __version__
from research_agent.cli import main
from research_agent.config import ConfigurationError
from research_agent.models import (
    ResearchSession,
    SessionStatus,
    TraceEvent,
    TraceEventType,
)


def test_cli_without_query_prints_help(capsys: object) -> None:
    assert main([]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "usage: research-agent" in captured.out


def test_cli_version(capsys: object) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert f"research-agent {__version__}" in captured.out


def make_runner(
    status: SessionStatus,
    *,
    summary: str,
    unresolved: list[str] | None = None,
):  # type: ignore[no-untyped-def]
    async def run(query: str) -> ResearchSession:
        session = ResearchSession(original_query=query, status=status)
        session.completion_summary = summary
        session.unresolved_questions = unresolved or []
        session.trace.append(
            TraceEvent(
                event_type=TraceEventType.SESSION_COMPLETED,
                session_id=session.id,
                decision_summary="Finished the injected CLI run",
            )
        )
        return session

    return run


def test_cli_prints_complete_report(capsys: object) -> None:
    runner = make_runner(SessionStatus.COMPLETED, summary="# Final report")

    assert main(["Research an unseen topic"], runner=runner) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == "# Final report\n"
    assert captured.err == ""


def test_cli_prints_partial_report_and_limitations(capsys: object) -> None:
    runner = make_runner(
        SessionStatus.PARTIAL,
        summary="Supported partial answer",
        unresolved=["One source remained unavailable."],
    )

    assert main(["Research a partially available topic"], runner=runner) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Supported partial answer" in captured.out
    assert "## Limitations" in captured.out
    assert "One source remained unavailable." in captured.out
    assert captured.err == ""


def test_cli_trace_mode_emits_one_parseable_structured_result(capsys: object) -> None:
    runner = make_runner(SessionStatus.COMPLETED, summary="# Final report")

    assert main(["--trace", "Research an unseen topic"], runner=runner) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["status"] == "completed"
    assert payload["report"] == "# Final report"
    assert payload["unresolved_questions"] == []
    assert payload["trace"][0]["event_type"] == "session_completed"
    assert "reasoning" not in captured.out
    assert captured.err == ""


def test_cli_reports_configuration_failure_without_a_traceback(capsys: object) -> None:
    async def fail(query: str) -> ResearchSession:
        raise ConfigurationError("Missing required environment variables: SAFE_KEY")

    assert main(["Research an unseen topic"], runner=fail) == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert "Configuration error" in captured.err
    assert "SAFE_KEY" in captured.err
    assert "Traceback" not in captured.err


def test_cli_reports_terminal_runtime_failure(capsys: object) -> None:
    runner = make_runner(
        SessionStatus.FAILED,
        summary="Research failed: invalid_plan.",
        unresolved=["The structured plan was invalid."],
    )

    assert main(["Research a failing topic"], runner=runner) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert "Research failed: invalid_plan." in captured.err
    assert "The structured plan was invalid." in captured.err


def test_cli_sanitizes_unexpected_runner_exception(capsys: object) -> None:
    async def fail(query: str) -> ResearchSession:
        raise RuntimeError("must-not-be-printed")

    assert main(["Research an unseen topic"], runner=fail) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "RuntimeError" in captured.err
    assert "must-not-be-printed" not in captured.err
