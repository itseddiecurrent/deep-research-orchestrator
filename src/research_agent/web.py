"""Tiny local web UI for interactively exercising the live research agent."""

from __future__ import annotations

import argparse
import asyncio
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any, Awaitable, Callable, Optional, Sequence
from urllib.parse import urlparse

from research_agent.application import run_live_research
from research_agent.cli import _plain_report
from research_agent.config import ConfigurationError
from research_agent.models import ResearchSession


ResearchRunner = Callable[[str], Awaitable[ResearchSession]]
MAX_REQUEST_BYTES = 64 * 1024
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


def session_payload(session: ResearchSession) -> dict[str, Any]:
    """Return only the session details useful to the browser trace UI."""

    return {
        "session_id": session.id,
        "status": session.status.value,
        "query": session.original_query,
        "report": _plain_report(session),
        "unresolved_questions": session.unresolved_questions,
        "iteration_count": session.iteration_count,
        "plan": (
            session.plan.model_dump(mode="json") if session.plan is not None else None
        ),
        "tool_calls": [call.model_dump(mode="json") for call in session.tool_calls],
        "sources": [
            {
                "id": source.id,
                "title": source.title,
                "url": str(source.source_url),
                "retrieved_at": source.retrieved_at.isoformat(),
                "content_hash": source.content_hash,
            }
            for source in session.source_snapshots
        ],
        "evidence": [
            {
                "id": item.id,
                "task_id": item.task_id,
                "claim": item.claim,
                "confidence": item.confidence,
                "source_chunk_ids": item.source_chunk_ids,
            }
            for item in session.evidence
        ],
        "trace": [event.model_dump(mode="json") for event in session.trace],
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


class ResearchWebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        runner: ResearchRunner,
    ) -> None:
        self.runner = runner
        super().__init__(server_address, ResearchRequestHandler)


class ResearchRequestHandler(BaseHTTPRequestHandler):
    server: ResearchWebServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        asset = ASSETS.get(path)
        if asset is None:
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        filename, content_type = asset
        body = (
            resources.files("research_agent")
            .joinpath("web_assets", filename)
            .read_bytes()
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if urlparse(self.path).path != "/api/research":
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must be between 1 byte and 64 KB."},
            )
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json_response(
                HTTPStatus.BAD_REQUEST, {"error": "Request must be valid JSON."}
            )
            return
        query = payload.get("query") if isinstance(payload, dict) else None
        if not isinstance(query, str) or not query.strip():
            self._json_response(
                HTTPStatus.BAD_REQUEST, {"error": "A non-empty query is required."}
            )
            return

        try:
            session = asyncio.run(self.server.runner(query.strip()))
        except ConfigurationError as exc:
            self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": f"Configuration error: {exc}"},
            )
            return
        except Exception as exc:
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": (
                        "Research failed before completion "
                        f"({type(exc).__name__}). Check the server console."
                    )
                },
            )
            return

        self._json_response(HTTPStatus.OK, session_payload(session))

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the useful request line while avoiding default DNS/user lookups.
        print(f"[web] {self.command} {urlparse(self.path).path} - {args[1]}")

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    runner: ResearchRunner = run_live_research,
) -> ResearchWebServer:
    return ResearchWebServer((host, port), runner)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-agent-web",
        description="Run the local interactive UI for the research-agent MVP.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    server = create_server(args.host, args.port)
    address, port = server.server_address[:2]
    print(f"Research Agent UI: http://{address}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Research Agent UI.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
