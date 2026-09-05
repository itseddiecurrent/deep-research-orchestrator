"""Deterministic source ingestion, evidence validation, and lineage walking."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Iterable, Optional, Sequence, TypeVar

from pydantic import Field, HttpUrl, ValidationError, field_validator, model_validator

from research_agent.llm import LLMClient, LLMRequest
from research_agent.models import (
    Evidence,
    NonEmptyStr,
    Observation,
    ResearchSession,
    SourceChunk,
    SourceSnapshot,
    StrictModel,
    ToolCall,
    ToolCallStatus,
    ToolResult,
    TraceEvent,
    TraceEventType,
    utc_now,
)


class RetrievedSource(StrictModel):
    """Canonical full-content record returned by a read-only research tool."""

    source_url: HttpUrl
    title: NonEmptyStr
    content: str = Field(min_length=1)
    media_type: NonEmptyStr = "text/markdown"

    @field_validator("content")
    @classmethod
    def content_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("retrieved source content cannot be blank")
        return value


class ResearchToolOutput(StrictModel):
    """Canonical retrieval output; snippets alone deliberately do not satisfy it."""

    sources: list[RetrievedSource] = Field(default_factory=list)


class EvidenceCandidate(StrictModel):
    task_id: NonEmptyStr
    claim: NonEmptyStr
    source_chunk_ids: list[NonEmptyStr] = Field(min_length=1)
    verbatim_excerpt: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("verbatim_excerpt")
    @classmethod
    def excerpt_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence excerpt cannot be blank")
        return value

    @model_validator(mode="after")
    def chunk_ids_are_unique(self) -> "EvidenceCandidate":
        if len(self.source_chunk_ids) != len(set(self.source_chunk_ids)):
            raise ValueError("evidence source chunk IDs must be unique")
        return self


class EvidenceBatch(StrictModel):
    evidence: list[EvidenceCandidate] = Field(min_length=1)


class ProvenanceError(ValueError):
    """Base failure for malformed or broken provenance state."""


class SourceNormalizationError(ProvenanceError):
    pass


class EvidenceValidationError(ProvenanceError):
    pass


class LineageValidationError(ProvenanceError):
    pass


RecordT = TypeVar("RecordT")


def _index_by_id(records: Iterable[RecordT], label: str) -> dict[str, RecordT]:
    index: dict[str, RecordT] = {}
    for record in records:
        record_id = getattr(record, "id", None)
        if not isinstance(record_id, str) or not record_id:
            raise LineageValidationError(f"{label} contains a record without an ID")
        if record_id in index:
            raise LineageValidationError(f"duplicate {label} ID {record_id!r}")
        index[record_id] = record
    return index


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def emit_trace(
    session: ResearchSession,
    event_type: TraceEventType,
    *,
    task_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    decision_summary: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> None:
    objective_version = session.plan.objective.version if session.plan else 1
    session.trace.append(
        TraceEvent(
            event_type=event_type,
            session_id=session.id,
            objective_version=objective_version,
            task_id=task_id,
            tool_call_id=tool_call_id,
            decision_summary=decision_summary,
            data=data or {},
        )
    )
    session.updated_at = utc_now()


class ProvenanceManager:
    """Creates immutable snapshots/chunks/evidence after deterministic checks."""

    def __init__(self, *, chunk_size: int = 1_200) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self.chunk_size = chunk_size

    def ingest_tool_result(
        self, session: ResearchSession, tool_result_id: str
    ) -> list[SourceSnapshot]:
        results = _index_by_id(session.tool_results, "tool result")
        calls = _index_by_id(session.tool_calls, "tool call")
        try:
            result = results[tool_result_id]
        except KeyError as exc:
            raise SourceNormalizationError(
                f"unknown tool result {tool_result_id!r}"
            ) from exc
        self._require_successful_call(result, calls)

        try:
            output = ResearchToolOutput.model_validate(result.raw_output)
        except ValidationError as exc:
            raise SourceNormalizationError(
                "tool result does not match canonical full-content output"
            ) from exc

        canonical_sources: list[RetrievedSource] = []
        seen_source_keys: set[tuple[str, str]] = set()
        for source in output.sources:
            key = (str(source.source_url), _sha256_text(source.content))
            if key not in seen_source_keys:
                canonical_sources.append(source)
                seen_source_keys.add(key)

        existing = [
            snapshot
            for snapshot in session.source_snapshots
            if snapshot.tool_result_id == tool_result_id
        ]
        if existing:
            existing_keys = {
                (str(snapshot.source_url), snapshot.content_hash)
                for snapshot in existing
            }
            if existing_keys != seen_source_keys:
                raise SourceNormalizationError(
                    "tool result was already ingested with different source content"
                )
            LineageValidator().validate_sources_for_result(session, tool_result_id)
            return existing

        snapshots: list[SourceSnapshot] = []
        chunks: list[SourceChunk] = []
        for source in canonical_sources:
            snapshot = SourceSnapshot(
                tool_result_id=result.id,
                source_url=source.source_url,
                title=source.title,
                media_type=source.media_type,
                content=source.content,
                content_hash=_sha256_text(source.content),
            )
            source_chunks = self._chunk(snapshot)
            snapshots.append(snapshot)
            chunks.extend(source_chunks)

        session.source_snapshots.extend(snapshots)
        session.source_chunks.extend(chunks)
        chunks_by_snapshot: dict[str, list[str]] = {}
        for chunk in chunks:
            chunks_by_snapshot.setdefault(chunk.source_snapshot_id, []).append(chunk.id)
        call = calls[result.tool_call_id]
        for snapshot in snapshots:
            emit_trace(
                session,
                TraceEventType.SOURCE_CREATED,
                task_id=call.task_id,
                tool_call_id=call.id,
                data={
                    "source_snapshot_id": snapshot.id,
                    "source_url": str(snapshot.source_url),
                    "content_hash": snapshot.content_hash,
                    "chunk_ids": chunks_by_snapshot[snapshot.id],
                },
            )
        return snapshots

    def create_evidence(
        self,
        session: ResearchSession,
        candidates: Sequence[EvidenceCandidate],
    ) -> list[Evidence]:
        if not candidates:
            raise EvidenceValidationError("at least one evidence candidate is required")
        validator = LineageValidator()
        existing_ids = {evidence.id for evidence in session.evidence}
        if len(existing_ids) != len(session.evidence):
            raise LineageValidationError("duplicate evidence ID in session")

        created = [
            Evidence(
                task_id=candidate.task_id,
                claim=candidate.claim,
                source_chunk_ids=list(candidate.source_chunk_ids),
                verbatim_excerpt=candidate.verbatim_excerpt,
                confidence=candidate.confidence,
            )
            for candidate in candidates
        ]
        candidate_session = session.model_copy(deep=True)
        candidate_session.evidence.extend(created)
        for evidence in created:
            validator.resolve_evidence(candidate_session, evidence.id)

        session.evidence.extend(created)
        chunks = _index_by_id(session.source_chunks, "source chunk")
        snapshots = _index_by_id(session.source_snapshots, "source snapshot")
        results = _index_by_id(session.tool_results, "tool result")
        for evidence in created:
            first_chunk = chunks[evidence.source_chunk_ids[0]]
            snapshot = snapshots[first_chunk.source_snapshot_id]
            result = results[snapshot.tool_result_id]
            emit_trace(
                session,
                TraceEventType.EVIDENCE_CREATED,
                task_id=evidence.task_id,
                tool_call_id=result.tool_call_id,
                data={
                    "evidence_id": evidence.id,
                    "source_chunk_ids": evidence.source_chunk_ids,
                },
            )
        return created

    def _chunk(self, snapshot: SourceSnapshot) -> list[SourceChunk]:
        chunks: list[SourceChunk] = []
        for start in range(0, len(snapshot.content), self.chunk_size):
            end = min(start + self.chunk_size, len(snapshot.content))
            text = snapshot.content[start:end]
            chunks.append(
                SourceChunk(
                    source_snapshot_id=snapshot.id,
                    start_offset=start,
                    end_offset=end,
                    text=text,
                    content_hash=_sha256_text(text),
                )
            )
        return chunks

    def _require_successful_call(
        self, result: ToolResult, calls: dict[str, ToolCall]
    ) -> None:
        if not result.success:
            raise SourceNormalizationError("failed tool results cannot create sources")
        try:
            call = calls[result.tool_call_id]
        except KeyError as exc:
            raise SourceNormalizationError(
                f"tool result references unknown call {result.tool_call_id!r}"
            ) from exc
        if call.status != ToolCallStatus.SUCCEEDED:
            raise SourceNormalizationError(
                "source lineage requires a successful tool call"
            )


class LineageValidator:
    """Walks and verifies deterministic in-session provenance edges."""

    def resolve_chunk(
        self, session: ResearchSession, chunk_id: str
    ) -> SourceSnapshot:
        chunks = _index_by_id(session.source_chunks, "source chunk")
        snapshots = _index_by_id(session.source_snapshots, "source snapshot")
        results = _index_by_id(session.tool_results, "tool result")
        calls = _index_by_id(session.tool_calls, "tool call")
        try:
            chunk = chunks[chunk_id]
        except KeyError as exc:
            raise LineageValidationError(f"unknown source chunk {chunk_id!r}") from exc
        try:
            snapshot = snapshots[chunk.source_snapshot_id]
        except KeyError as exc:
            raise LineageValidationError(
                f"chunk {chunk.id!r} references an unknown snapshot"
            ) from exc
        self._validate_snapshot(snapshot, results, calls)
        if chunk.end_offset > len(snapshot.content):
            raise LineageValidationError(f"chunk {chunk.id!r} exceeds source content")
        if snapshot.content[chunk.start_offset : chunk.end_offset] != chunk.text:
            raise LineageValidationError(f"chunk {chunk.id!r} offsets/text do not match")
        if _sha256_text(chunk.text) != chunk.content_hash:
            raise LineageValidationError(f"chunk {chunk.id!r} hash does not match")
        return snapshot

    def resolve_evidence(
        self, session: ResearchSession, evidence_id: str
    ) -> list[SourceSnapshot]:
        evidence_index = _index_by_id(session.evidence, "evidence")
        try:
            evidence = evidence_index[evidence_id]
        except KeyError as exc:
            raise LineageValidationError(f"unknown evidence {evidence_id!r}") from exc
        if session.plan is None:
            raise LineageValidationError("evidence requires an active research plan")
        task_ids = [task.id for task in session.plan.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise LineageValidationError("duplicate task ID in research plan")
        if evidence.task_id not in set(task_ids):
            raise LineageValidationError(
                f"evidence {evidence.id!r} references unknown task {evidence.task_id!r}"
            )
        if len(evidence.source_chunk_ids) != len(set(evidence.source_chunk_ids)):
            raise LineageValidationError(
                f"evidence {evidence.id!r} repeats a source chunk ID"
            )

        chunks = _index_by_id(session.source_chunks, "source chunk")
        snapshots: list[SourceSnapshot] = []
        excerpt_found = False
        for chunk_id in evidence.source_chunk_ids:
            snapshot = self.resolve_chunk(session, chunk_id)
            snapshots.append(snapshot)
            if evidence.verbatim_excerpt in chunks[chunk_id].text:
                excerpt_found = True
        if not excerpt_found:
            raise LineageValidationError(
                f"evidence {evidence.id!r} excerpt is not contained in a cited chunk"
            )
        return _unique_records(snapshots)

    def validate_sources_for_result(
        self, session: ResearchSession, tool_result_id: str
    ) -> None:
        snapshots = _index_by_id(session.source_snapshots, "source snapshot")
        results = _index_by_id(session.tool_results, "tool result")
        calls = _index_by_id(session.tool_calls, "tool call")
        chunks = _index_by_id(session.source_chunks, "source chunk")
        matching = [
            snapshot
            for snapshot in snapshots.values()
            if snapshot.tool_result_id == tool_result_id
        ]
        for snapshot in matching:
            self._validate_snapshot(snapshot, results, calls)
            snapshot_chunks = [
                chunk
                for chunk in chunks.values()
                if chunk.source_snapshot_id == snapshot.id
            ]
            if not snapshot_chunks:
                raise LineageValidationError(
                    f"snapshot {snapshot.id!r} has no source chunks"
                )
            ordered = sorted(snapshot_chunks, key=lambda item: item.start_offset)
            if ordered[0].start_offset != 0:
                raise LineageValidationError("source chunks do not begin at offset zero")
            for previous, current in zip(ordered, ordered[1:]):
                if previous.end_offset != current.start_offset:
                    raise LineageValidationError("source chunks contain a gap or overlap")
            if ordered[-1].end_offset != len(snapshot.content):
                raise LineageValidationError("source chunks do not cover the snapshot")
            for chunk in ordered:
                self.resolve_chunk(session, chunk.id)

    def _validate_snapshot(
        self,
        snapshot: SourceSnapshot,
        results: dict[str, ToolResult],
        calls: dict[str, ToolCall],
    ) -> None:
        if _sha256_text(snapshot.content) != snapshot.content_hash:
            raise LineageValidationError(
                f"snapshot {snapshot.id!r} hash does not match"
            )
        try:
            result = results[snapshot.tool_result_id]
        except KeyError as exc:
            raise LineageValidationError(
                f"snapshot {snapshot.id!r} references an unknown tool result"
            ) from exc
        if not result.success:
            raise LineageValidationError(
                f"snapshot {snapshot.id!r} references a failed tool result"
            )
        try:
            call = calls[result.tool_call_id]
        except KeyError as exc:
            raise LineageValidationError(
                f"tool result {result.id!r} references an unknown tool call"
            ) from exc
        if call.status != ToolCallStatus.SUCCEEDED:
            raise LineageValidationError(
                f"tool call {call.id!r} is not successful"
            )


class EvidenceExtractor:
    """Requests structured evidence and applies deterministic acceptance checks."""

    def __init__(
        self, *, llm_client: LLMClient, provenance: Optional[ProvenanceManager] = None
    ) -> None:
        self.llm_client = llm_client
        self.provenance = provenance or ProvenanceManager()

    async def ingest_and_extract(
        self,
        session: ResearchSession,
        *,
        task_id: str,
        tool_result_id: str,
    ) -> list[Evidence]:
        """Normalize one successful result, then extract from its exact chunks."""

        snapshots = self.provenance.ingest_tool_result(session, tool_result_id)
        snapshot_ids = {snapshot.id for snapshot in snapshots}
        chunk_ids = [
            chunk.id
            for chunk in session.source_chunks
            if chunk.source_snapshot_id in snapshot_ids
        ]
        if not chunk_ids:
            raise EvidenceValidationError(
                "tool result did not produce any full-content source chunks"
            )
        return await self.extract(
            session,
            task_id=task_id,
            source_chunk_ids=chunk_ids,
        )

    async def extract(
        self,
        session: ResearchSession,
        *,
        task_id: str,
        source_chunk_ids: Sequence[str],
    ) -> list[Evidence]:
        if not source_chunk_ids or len(source_chunk_ids) != len(set(source_chunk_ids)):
            raise EvidenceValidationError(
                "source_chunk_ids must be a non-empty unique list"
            )
        if session.plan is None or task_id not in {task.id for task in session.plan.tasks}:
            raise EvidenceValidationError(f"unknown research task {task_id!r}")
        validator = LineageValidator()
        chunk_index = _index_by_id(session.source_chunks, "source chunk")
        snapshot_context: dict[str, dict[str, Any]] = {}
        chunk_context: list[dict[str, Any]] = []
        for chunk_id in source_chunk_ids:
            snapshot = validator.resolve_chunk(session, chunk_id)
            chunk_context.append(chunk_index[chunk_id].model_dump(mode="json"))
            snapshot_context[snapshot.id] = {
                "id": snapshot.id,
                "source_url": str(snapshot.source_url),
                "title": snapshot.title,
                "content_hash": snapshot.content_hash,
            }

        request = LLMRequest(
            purpose="evidence",
            instructions=(
                "Extract only source-supported evidence. Each verbatim_excerpt must "
                "be copied exactly from one supplied chunk and every chunk ID must "
                "come from the supplied list. Return only the structured schema."
            ),
            context={
                "original_query": session.original_query,
                "objective": session.plan.objective.model_dump(mode="json"),
                "task_id": task_id,
                "source_chunks": chunk_context,
                "source_snapshots": list(snapshot_context.values()),
            },
            response_schema=EvidenceBatch.model_json_schema(),
            max_output_tokens=session.limits.max_model_output_tokens,
        )
        try:
            response = await self.llm_client.complete(request)
            if (
                response.output_tokens is not None
                and response.output_tokens > session.limits.max_model_output_tokens
            ):
                raise EvidenceValidationError(
                    "evidence response exceeded max_model_output_tokens"
                )
            batch = EvidenceBatch.model_validate(response.output)
        except EvidenceValidationError:
            raise
        except Exception as exc:
            raise EvidenceValidationError(f"invalid evidence response: {exc}") from exc

        allowed_chunks = set(source_chunk_ids)
        for candidate in batch.evidence:
            if candidate.task_id != task_id:
                raise EvidenceValidationError(
                    "evidence response references a different task"
                )
            if not set(candidate.source_chunk_ids).issubset(allowed_chunks):
                raise EvidenceValidationError(
                    "evidence response references a chunk not supplied to extraction"
                )
        return self.provenance.create_evidence(session, batch.evidence)


def _unique_records(records: Sequence[RecordT]) -> list[RecordT]:
    seen: set[str] = set()
    unique: list[RecordT] = []
    for record in records:
        record_id = getattr(record, "id")
        if record_id not in seen:
            unique.append(record)
            seen.add(record_id)
    return unique
