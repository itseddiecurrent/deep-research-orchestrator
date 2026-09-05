from __future__ import annotations

import asyncio

import pytest

from research_agent.llm import LLMResponse, ScriptedLLMClient
from research_agent.models import Citation, SessionStatus, TraceEventType
from research_agent.provenance import (
    EvidenceCandidate,
    LineageValidationError,
    ProvenanceManager,
)
from research_agent.synthesis import (
    CitationLineageValidator,
    CitationRenderer,
    SynthesisError,
    SynthesisService,
)
from test_provenance import make_session


def make_evidence_session():  # type: ignore[no-untyped-def]
    raw_output = {
        "sources": [
            {
                "source_url": "https://example.test/shared",
                "title": "Shared [primary] source",
                "content": "Alpha supports fact one. Alpha also supports fact two.",
            },
            {
                "source_url": "https://example.test/second",
                "title": "Second source",
                "content": "Beta supports fact three.",
            },
        ]
    }
    session = make_session(raw_output=raw_output)
    manager = ProvenanceManager(chunk_size=1_000)
    manager.ingest_tool_result(session, session.tool_results[0].id)
    first, second = session.source_chunks
    evidence = manager.create_evidence(
        session,
        [
            EvidenceCandidate(
                task_id="task_sources",
                claim="Fact one",
                source_chunk_ids=[first.id],
                verbatim_excerpt="Alpha supports fact one.",
                confidence=0.95,
            ),
            EvidenceCandidate(
                task_id="task_sources",
                claim="Fact two",
                source_chunk_ids=[first.id],
                verbatim_excerpt="Alpha also supports fact two.",
                confidence=0.9,
            ),
            EvidenceCandidate(
                task_id="task_sources",
                claim="Fact three",
                source_chunk_ids=[second.id],
                verbatim_excerpt="Beta supports fact three.",
                confidence=0.85,
            ),
        ],
    )
    return session, evidence


def valid_draft(evidence):  # type: ignore[no-untyped-def]
    return {
        "title": "Evidence-backed comparison",
        "claims": [
            {"text": "Fact one is supported.", "evidence_ids": [evidence[0].id]},
            {"text": "Fact two is supported.", "evidence_ids": [evidence[1].id]},
            {
                "text": "Fact three is independently supported.",
                "evidence_ids": [evidence[2].id],
            },
        ],
        "limitations": [],
    }


def test_synthesis_uses_known_ids_and_renders_stable_deduplicated_sources() -> None:
    session, evidence = make_evidence_session()
    client = ScriptedLLMClient([valid_draft(evidence)])
    rendered = asyncio.run(SynthesisService(llm_client=client).synthesize(session))

    assert session.status == SessionStatus.COMPLETED
    assert client.requests[0].purpose == "synthesis"
    assert all(
        "source_url" not in item["evidence"]
        for item in client.requests[0].context["evidence"]
    )
    assert "Fact one is supported. [1]" in rendered.markdown
    assert "Fact two is supported. [1]" in rendered.markdown
    assert "Fact three is independently supported. [2]" in rendered.markdown
    assert rendered.markdown.count("https://example.test/shared") == 1
    assert rendered.markdown.count("https://example.test/second") == 1
    assert "Shared \\[primary\\] source" in rendered.markdown
    assert [citation.display_number for citation in session.citations] == [1, 1, 2]
    CitationLineageValidator().validate_report(session)
    assert session.trace[-1].event_type == TraceEventType.SESSION_COMPLETED


@pytest.mark.parametrize(
    "bad_draft",
    [
        {
            "title": "Fabricated evidence",
            "claims": [{"text": "Bad", "evidence_ids": ["evidence_invented"]}],
            "limitations": [],
        },
        {
            "title": "Invented URL",
            "claims": [{"text": "Bad", "evidence_ids": ["placeholder"]}],
            "limitations": [],
            "source_url": "https://invented.test",
        },
        {
            "title": "URL hidden in prose",
            "claims": [
                {
                    "text": "See https://invented.test for support.",
                    "evidence_ids": ["placeholder"],
                }
            ],
            "limitations": [],
        },
    ],
)
def test_synthesis_rejects_fabricated_ids_or_fields_before_report_mutation(
    bad_draft: object,
) -> None:
    session, evidence = make_evidence_session()
    if isinstance(bad_draft, dict):
        claims = bad_draft.get("claims")
        if isinstance(claims, list) and claims[0]["evidence_ids"] == ["placeholder"]:
            claims[0]["evidence_ids"] = [evidence[0].id]
    with pytest.raises(SynthesisError):
        asyncio.run(
            SynthesisService(llm_client=ScriptedLLMClient([bad_draft])).synthesize(
                session
            )
        )
    assert session.report_claims == []
    assert session.citations == []


def test_synthesis_rejects_reported_model_output_overflow() -> None:
    session, evidence = make_evidence_session()
    response = LLMResponse(
        output=valid_draft(evidence),
        provider="scripted",
        model="scripted-v1",
        output_tokens=session.limits.max_model_output_tokens + 1,
    )
    with pytest.raises(SynthesisError, match="max_model_output_tokens"):
        asyncio.run(
            SynthesisService(llm_client=ScriptedLLMClient([response])).synthesize(
                session
            )
        )
    assert session.report_claims == []


def test_partial_synthesis_renders_limitations_and_partial_state() -> None:
    session, evidence = make_evidence_session()
    draft = valid_draft(evidence)
    draft["limitations"] = ["A fourth comparison dimension lacks evidence."]
    rendered = asyncio.run(
        SynthesisService(llm_client=ScriptedLLMClient([draft])).synthesize(session)
    )

    assert session.status == SessionStatus.PARTIAL
    assert session.unresolved_questions == draft["limitations"]
    assert "## Limitations" in rendered.markdown
    assert "A fourth comparison dimension lacks evidence." in rendered.markdown
    assert session.trace[-1].event_type == TraceEventType.SESSION_PARTIAL


def test_citation_validator_rejects_cross_linked_and_missing_sources() -> None:
    session, evidence = make_evidence_session()
    asyncio.run(
        SynthesisService(
            llm_client=ScriptedLLMClient([valid_draft(evidence)])
        ).synthesize(session)
    )
    first_citation = session.citations[0]
    unrelated_snapshot_id = session.source_snapshots[1].id
    first_citation.source_snapshot_ids = [unrelated_snapshot_id]

    with pytest.raises(LineageValidationError, match="cross-links"):
        CitationLineageValidator().validate_report(session)

    first_citation.source_snapshot_ids = [session.source_snapshots[0].id]
    session.citations = [
        citation
        for citation in session.citations
        if citation.report_claim_id != session.report_claims[0].id
    ]
    with pytest.raises(LineageValidationError, match="has no citation"):
        CitationRenderer().render(session, title="Invalid", limitations=[])


def test_citation_validator_rejects_fabricated_evidence_and_duplicate_ids() -> None:
    session, evidence = make_evidence_session()
    asyncio.run(
        SynthesisService(
            llm_client=ScriptedLLMClient([valid_draft(evidence)])
        ).synthesize(session)
    )
    session.citations[0].evidence_ids = ["evidence_fabricated"]
    with pytest.raises(LineageValidationError):
        CitationLineageValidator().validate_report(session)

    session, evidence = make_evidence_session()
    asyncio.run(
        SynthesisService(
            llm_client=ScriptedLLMClient([valid_draft(evidence)])
        ).synthesize(session)
    )
    duplicate = session.citations[0].model_copy(deep=True)
    session.citations.append(duplicate)
    with pytest.raises(LineageValidationError, match="duplicate citation ID"):
        CitationLineageValidator().validate_report(session)


def test_renderer_never_uses_free_form_or_tampered_source_data() -> None:
    session, evidence = make_evidence_session()
    asyncio.run(
        SynthesisService(
            llm_client=ScriptedLLMClient([valid_draft(evidence)])
        ).synthesize(session)
    )
    session.source_snapshots[0].content_hash = "0" * 64
    with pytest.raises(LineageValidationError, match="hash does not match"):
        CitationRenderer().render(session, title="Invalid", limitations=[])
