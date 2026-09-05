from __future__ import annotations

import asyncio
from hashlib import sha256

import pytest

from research_agent.llm import LLMResponse, ScriptedLLMClient
from research_agent.models import (
    ObjectiveRequirement,
    ResearchObjective,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
    ToolCall,
    ToolCallStatus,
    ToolResult,
    TraceEventType,
)
from research_agent.provenance import (
    EvidenceCandidate,
    EvidenceExtractor,
    EvidenceValidationError,
    LineageValidationError,
    LineageValidator,
    ProvenanceManager,
    SourceNormalizationError,
)


def make_session(
    *,
    raw_output: object | None = None,
    call_status: ToolCallStatus = ToolCallStatus.SUCCEEDED,
    result_success: bool = True,
) -> ResearchSession:
    query = "Compare two fictional systems"
    session = ResearchSession(original_query=query)
    session.plan = ResearchPlan(
        decision_summary="Research both systems",
        objective=ResearchObjective(
            original_query=query,
            goal="Compare both systems using retrieved sources",
            requirements=[
                ObjectiveRequirement(id="req_compare", description="Compare systems")
            ],
        ),
        tasks=[
            ResearchTask(
                id="task_sources",
                description="Find comparison evidence",
                rationale="The comparison requires source content",
                expected_output="Source-backed facts",
                objective_requirement_ids=["req_compare"],
            )
        ],
    )
    call = ToolCall(
        task_id="task_sources",
        tool_name="generic_retrieval",
        tool_version="1",
        catalog_version="catalog_test",
        arguments={"query": query},
        status=call_status,
    )
    session.tool_calls.append(call)
    if raw_output is None:
        raw_output = {
            "sources": [
                {
                    "source_url": "https://example.test/alpha",
                    "title": "Alpha source",
                    "content": "  Alpha retains leading spaces.\nBeta follows.",
                }
            ]
        }
    session.tool_results.append(
        ToolResult(
            tool_call_id=call.id,
            success=result_success,
            raw_output=raw_output if result_success else None,
            error=None if result_success else "retrieval failed",
        )
    )
    return session


def ingest_default(
    session: ResearchSession, *, chunk_size: int = 16
) -> ProvenanceManager:
    manager = ProvenanceManager(chunk_size=chunk_size)
    manager.ingest_tool_result(session, session.tool_results[0].id)
    return manager


def test_normalization_preserves_exact_content_hashes_offsets_and_trace() -> None:
    session = make_session()
    manager = ingest_default(session, chunk_size=11)

    snapshot = session.source_snapshots[0]
    chunks = [
        chunk
        for chunk in session.source_chunks
        if chunk.source_snapshot_id == snapshot.id
    ]
    assert snapshot.content.startswith("  Alpha")
    assert snapshot.content_hash == sha256(snapshot.content.encode("utf-8")).hexdigest()
    assert "".join(chunk.text for chunk in chunks) == snapshot.content
    assert [(chunk.start_offset, chunk.end_offset) for chunk in chunks] == [
        (0, 11),
        (11, 22),
        (22, 33),
        (33, 44),
        (44, 45),
    ]
    assert all(
        chunk.content_hash == sha256(chunk.text.encode("utf-8")).hexdigest()
        for chunk in chunks
    )
    assert session.trace[-1].event_type == TraceEventType.SOURCE_CREATED
    assert session.trace[-1].data["chunk_ids"] == [chunk.id for chunk in chunks]
    LineageValidator().validate_sources_for_result(
        session, session.tool_results[0].id
    )

    repeated = manager.ingest_tool_result(session, session.tool_results[0].id)
    assert repeated == [snapshot]
    assert len(session.source_snapshots) == 1
    assert len(session.source_chunks) == len(chunks)


def test_identical_sources_in_one_result_are_normalized_once() -> None:
    source = {
        "source_url": "https://example.test/duplicate",
        "title": "Duplicate source",
        "content": "Exact full content",
    }
    session = make_session(raw_output={"sources": [source, source]})
    ingest_default(session)

    assert len(session.source_snapshots) == 1


@pytest.mark.parametrize(
    ("session", "message"),
    [
        (make_session(result_success=False), "failed tool results"),
        (
            make_session(call_status=ToolCallStatus.FAILED),
            "successful tool call",
        ),
        (
            make_session(raw_output={"results": [{"snippet": "Only a snippet"}]}),
            "canonical full-content output",
        ),
    ],
)
def test_normalization_rejects_failed_lineage_and_snippet_only_output(
    session: ResearchSession, message: str
) -> None:
    with pytest.raises(SourceNormalizationError, match=message):
        ProvenanceManager().ingest_tool_result(session, session.tool_results[0].id)
    assert session.source_snapshots == []
    assert session.source_chunks == []


def test_normalization_rejects_missing_result_and_duplicate_record_ids() -> None:
    session = make_session()
    manager = ProvenanceManager()

    with pytest.raises(SourceNormalizationError, match="unknown tool result"):
        manager.ingest_tool_result(session, "tool_result_missing")

    session.tool_calls.append(session.tool_calls[0].model_copy(deep=True))
    with pytest.raises(LineageValidationError, match="duplicate tool call ID"):
        manager.ingest_tool_result(session, session.tool_results[0].id)


def test_evidence_creation_requires_exact_known_lineage_and_is_atomic() -> None:
    session = make_session()
    manager = ingest_default(session, chunk_size=100)
    chunk = session.source_chunks[0]
    valid = EvidenceCandidate(
        task_id="task_sources",
        claim="Alpha retains leading spaces.",
        source_chunk_ids=[chunk.id],
        verbatim_excerpt="  Alpha retains leading spaces.",
        confidence=0.95,
    )
    created = manager.create_evidence(session, [valid])

    assert created[0].verbatim_excerpt.startswith("  Alpha")
    assert session.trace[-1].event_type == TraceEventType.EVIDENCE_CREATED
    snapshots = LineageValidator().resolve_evidence(session, created[0].id)
    assert snapshots == session.source_snapshots

    starting_count = len(session.evidence)
    invalid = EvidenceCandidate(
        task_id="task_sources",
        claim="An unsupported exact quote",
        source_chunk_ids=[chunk.id],
        verbatim_excerpt="This text is absent",
        confidence=0.2,
    )
    with pytest.raises(LineageValidationError, match="not contained"):
        manager.create_evidence(session, [valid, invalid])
    assert len(session.evidence) == starting_count


@pytest.mark.parametrize(
    "candidate",
    [
        EvidenceCandidate(
            task_id="missing_task",
            claim="Unknown task",
            source_chunk_ids=["chunk_placeholder"],
            verbatim_excerpt="excerpt",
            confidence=0.5,
        ),
        EvidenceCandidate(
            task_id="task_sources",
            claim="Unknown chunk",
            source_chunk_ids=["chunk_missing"],
            verbatim_excerpt="excerpt",
            confidence=0.5,
        ),
    ],
)
def test_evidence_rejects_unknown_task_or_chunk(candidate: EvidenceCandidate) -> None:
    session = make_session()
    manager = ingest_default(session)
    with pytest.raises(LineageValidationError):
        manager.create_evidence(session, [candidate])
    assert session.evidence == []


def test_lineage_validator_detects_tampered_hash_and_offsets() -> None:
    session = make_session()
    ingest_default(session, chunk_size=100)
    chunk = session.source_chunks[0]
    evidence = ProvenanceManager().create_evidence(
        session,
        [
            EvidenceCandidate(
                task_id="task_sources",
                claim="Alpha fact",
                source_chunk_ids=[chunk.id],
                verbatim_excerpt="Alpha retains",
                confidence=0.9,
            )
        ],
    )[0]

    chunk.content_hash = "0" * 64
    with pytest.raises(LineageValidationError, match="hash does not match"):
        LineageValidator().resolve_evidence(session, evidence.id)

    chunk.content_hash = sha256(chunk.text.encode("utf-8")).hexdigest()
    chunk.start_offset = 1
    with pytest.raises(LineageValidationError, match="offsets/text do not match"):
        LineageValidator().resolve_evidence(session, evidence.id)


def test_structured_extractor_receives_exact_chunks_and_creates_evidence() -> None:
    session = make_session()
    manager = ingest_default(session, chunk_size=100)
    chunk = session.source_chunks[0]
    response = {
        "evidence": [
            {
                "task_id": "task_sources",
                "claim": "Alpha retains leading spaces.",
                "source_chunk_ids": [chunk.id],
                "verbatim_excerpt": "  Alpha retains leading spaces.",
                "confidence": 0.9,
            }
        ]
    }
    client = ScriptedLLMClient([response])
    extractor = EvidenceExtractor(llm_client=client, provenance=manager)
    created = asyncio.run(
        extractor.extract(
            session, task_id="task_sources", source_chunk_ids=[chunk.id]
        )
    )

    assert len(created) == 1
    assert client.requests[0].purpose == "evidence"
    assert client.requests[0].context["source_chunks"] == [
        chunk.model_dump(mode="json")
    ]
    assert created[0] in session.evidence


def test_extractor_rejects_unsupplied_chunk_and_reported_token_overflow() -> None:
    raw_output = {
        "sources": [
            {
                "source_url": "https://example.test/one",
                "title": "One",
                "content": "First exact source",
            },
            {
                "source_url": "https://example.test/two",
                "title": "Two",
                "content": "Second exact source",
            },
        ]
    }
    session = make_session(raw_output=raw_output)
    manager = ingest_default(session, chunk_size=100)
    first, second = session.source_chunks
    client = ScriptedLLMClient(
        [
            {
                "evidence": [
                    {
                        "task_id": "task_sources",
                        "claim": "Second source claim",
                        "source_chunk_ids": [second.id],
                        "verbatim_excerpt": "Second exact source",
                        "confidence": 0.8,
                    }
                ]
            }
        ]
    )
    with pytest.raises(EvidenceValidationError, match="not supplied"):
        asyncio.run(
            EvidenceExtractor(llm_client=client, provenance=manager).extract(
                session, task_id="task_sources", source_chunk_ids=[first.id]
            )
        )
    assert session.evidence == []

    overflow_client = ScriptedLLMClient(
        [
            LLMResponse(
                output={"evidence": []},
                provider="scripted",
                model="scripted-v1",
                output_tokens=session.limits.max_model_output_tokens + 1,
            )
        ]
    )
    with pytest.raises(EvidenceValidationError, match="max_model_output_tokens"):
        asyncio.run(
            EvidenceExtractor(llm_client=overflow_client).extract(
                session, task_id="task_sources", source_chunk_ids=[first.id]
            )
        )


def test_extractor_recovers_source_exact_whitespace_from_model_excerpt() -> None:
    source_text = "Revenue grew  \n\t10% this quarter despite constraints."
    session = make_session(
        raw_output={
            "sources": [
                {
                    "source_url": "https://example.test/earnings",
                    "title": "Earnings transcript",
                    "content": source_text,
                }
            ]
        }
    )
    manager = ingest_default(session, chunk_size=200)
    chunk = session.source_chunks[0]
    client = ScriptedLLMClient(
        [
            {
                "evidence": [
                    {
                        "task_id": "task_sources",
                        "claim": "Revenue grew ten percent.",
                        "source_chunk_ids": [chunk.id],
                        "verbatim_excerpt": (
                            '"Revenue grew 10% this quarter despite constraints."'
                        ),
                        "confidence": 0.9,
                    }
                ]
            }
        ]
    )

    created = asyncio.run(
        EvidenceExtractor(llm_client=client, provenance=manager).extract(
            session,
            task_id="task_sources",
            source_chunk_ids=[chunk.id],
        )
    )

    assert created[0].verbatim_excerpt == source_text
    assert created[0].verbatim_excerpt in chunk.text


def test_extractor_recovers_exact_excerpt_across_adjacent_chunks() -> None:
    excerpt = "Revenue grew ten percent despite constrained component supply."
    source_text = f"Short prefix. {excerpt} Short suffix."
    session = make_session(
        raw_output={
            "sources": [
                {
                    "source_url": "https://example.test/cross-chunk",
                    "title": "Cross-chunk transcript",
                    "content": source_text,
                }
            ]
        }
    )
    manager = ingest_default(session, chunk_size=32)
    first_relevant_chunk = next(
        chunk for chunk in session.source_chunks if "Revenue grew" in chunk.text
    )
    client = ScriptedLLMClient(
        [
            {
                "evidence": [
                    {
                        "task_id": "task_sources",
                        "claim": "Revenue grew despite supply constraints.",
                        "source_chunk_ids": [first_relevant_chunk.id],
                        "verbatim_excerpt": excerpt,
                        "confidence": 0.9,
                    }
                ]
            }
        ]
    )

    created = asyncio.run(
        EvidenceExtractor(llm_client=client, provenance=manager).extract(
            session,
            task_id="task_sources",
            source_chunk_ids=[chunk.id for chunk in session.source_chunks],
        )
    )

    assert created[0].verbatim_excerpt == excerpt
    assert len(created[0].source_chunk_ids) > 1
    LineageValidator().resolve_evidence(session, created[0].id)


def test_extractor_commits_valid_subset_when_another_candidate_is_invalid() -> None:
    session = make_session()
    manager = ingest_default(session, chunk_size=200)
    chunk = session.source_chunks[0]
    client = ScriptedLLMClient(
        [
            {
                "evidence": [
                    {
                        "task_id": "task_sources",
                        "claim": "The source supports this claim.",
                        "source_chunk_ids": [chunk.id],
                        "verbatim_excerpt": chunk.text,
                        "confidence": 0.9,
                    },
                    {
                        "task_id": "task_sources",
                        "claim": "This candidate is not source-exact.",
                        "source_chunk_ids": [chunk.id],
                        "verbatim_excerpt": "words that do not occur in the source",
                        "confidence": 0.4,
                    },
                ]
            }
        ]
    )

    created = asyncio.run(
        EvidenceExtractor(llm_client=client, provenance=manager).extract(
            session,
            task_id="task_sources",
            source_chunk_ids=[chunk.id],
        )
    )

    assert len(created) == 1
    assert created[0].claim == "The source supports this claim."
    assert session.evidence == created
