"""CLI boundary for the incrementally implemented MVP."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from research_agent import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-agent",
        description="Run the general-purpose research-agent MVP.",
    )
    parser.add_argument("query", nargs="?", help="Natural-language research query")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.query:
        parser.print_help()
        return 0

    print(
        "Live CLI research is not available yet; the deterministic runtime requires "
        "the Milestone 4 provider adapters.",
        file=sys.stderr,
    )
    return 2
