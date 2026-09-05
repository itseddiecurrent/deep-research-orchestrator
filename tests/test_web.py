from __future__ import annotations

import json
import threading
from urllib.request import Request, urlopen

from research_agent.models import ResearchSession, SessionStatus
from research_agent.web import create_server, session_payload


async def fake_runner(query: str) -> ResearchSession:
    session = ResearchSession(original_query=query)
    session.status = SessionStatus.COMPLETED
    session.completion_summary = "# Test report\n\nA deterministic answer."
    return session


def test_session_payload_exposes_ui_state_without_full_source_content() -> None:
    session = ResearchSession(original_query="A safe query")
    session.status = SessionStatus.PARTIAL
    session.completion_summary = "Useful partial result"
    session.unresolved_questions = ["One question remains"]

    payload = session_payload(session)

    assert payload["status"] == "partial"
    assert payload["query"] == "A safe query"
    assert payload["report"].endswith("- One question remains")
    assert "source_chunks" not in payload
    assert "tool_results" not in payload


def test_web_server_serves_ui_and_runs_research() -> None:
    server = create_server(port=0, runner=fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base_url = f"http://{host}:{port}"
    try:
        with urlopen(f"{base_url}/", timeout=2) as response:
            assert response.status == 200
            assert b"Research Agent" in response.read()

        request = Request(
            f"{base_url}/api/research",
            data=json.dumps({"query": "Interactive test"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["status"] == "completed"
        assert payload["query"] == "Interactive test"
        assert "deterministic answer" in payload["report"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
