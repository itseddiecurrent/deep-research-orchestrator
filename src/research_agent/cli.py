"""CLI boundary for the incrementally implemented MVP."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Awaitable, Callable, Optional, Sequence

from research_agent import __version__
from research_agent.application import run_live_research
from research_agent.config import ConfigurationError
from research_agent.models import ResearchSession, SessionStatus


ResearchRunner = Callable[[str], Awaitable[ResearchSession]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-agent",
        description="Run the general-purpose research-agent MVP.",
    )
    parser.add_argument("query", nargs="?", help="Natural-language research query")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Emit one JSON result containing the report and structured trace",
    )
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    runner: ResearchRunner = run_live_research,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.query:
        parser.print_help()
        return 0

    try:
        session = asyncio.run(runner(args.query))
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Research failed before completion ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1

    report = _plain_report(session)
    if args.trace:
        print(
            json.dumps(
                {
                    "status": session.status.value,
                    "report": report,
                    "unresolved_questions": session.unresolved_questions,
                    "trace": [
                        event.model_dump(mode="json") for event in session.trace
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    elif session.status == SessionStatus.FAILED:
        print(report, file=sys.stderr)
    else:
        print(report)

    if session.status in {SessionStatus.COMPLETED, SessionStatus.PARTIAL}:
        return 0
    return 1


def _plain_report(session: ResearchSession) -> str:
    report = session.completion_summary or (
        f"Research ended with status {session.status.value}."
    )
    if session.unresolved_questions and "## Limitations" not in report:
        limitations = "\n".join(
            f"- {question}" for question in session.unresolved_questions
        )
        report = f"{report}\n\n## Limitations\n\n{limitations}"
    return report
