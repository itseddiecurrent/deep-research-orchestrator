"""Evidence-ID-constrained synthesis, citation validation, and rendering."""

from __future__ import annotations

import re
from typing import Any, Optional, Sequence

from pydantic import Field, model_validator

from research_agent.llm import LLMClient, LLMRequest
from research_agent.models import (
    Citation,
    NonEmptyStr,
    ReportClaim,
    ResearchSession,
    SessionStatus,
    SourceSnapshot,
    StrictModel,
    TraceEventType,
)
from research_agent.provenance import (
    LineageValidationError,
    LineageValidator,
    _index_by_id,
    emit_trace,
)


class SynthesisClaim(StrictModel):
    text: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)
    material: bool = True

    @model_validator(mode="after")
    def evidence_ids_are_unique(self) -> "SynthesisClaim":
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("synthesis evidence IDs must be unique")
        return self


class SynthesisDraft(StrictModel):
    title: NonEmptyStr
    claims: list[SynthesisClaim] = Field(min_length=1)
    limitations: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def free_form_fields_do_not_supply_urls(self) -> "SynthesisDraft":
        values = [self.title, *[claim.text for claim in self.claims], *self.limitations]
        if any(re.search(r"https?://", value, flags=re.IGNORECASE) for value in values):
            raise ValueError(
                "synthesis free-form text cannot supply source URLs; use evidence IDs"
            )
        return self


class RenderedReport(StrictModel):
    markdown: NonEmptyStr
    report_claim_ids: list[NonEmptyStr] = Field(min_length=1)
    citation_ids: list[NonEmptyStr] = Field(min_length=1)


class SynthesisError(ValueError):
    pass


class CitationLineageValidator(LineageValidator):
    """Validates report-level referential integrity and display-number identity."""

    def validate_report(self, session: ResearchSession) -> None:
        claims = _index_by_id(session.report_claims, "report claim")
        citations = _index_by_id(session.citations, "citation")
        evidence = _index_by_id(session.evidence, "evidence")
        snapshots = _index_by_id(session.source_snapshots, "source snapshot")
        citations_by_claim: dict[str, list[Citation]] = {}
        number_urls: dict[int, str] = {}
        url_numbers: dict[str, int] = {}

        for citation in citations.values():
            try:
                claim = claims[citation.report_claim_id]
            except KeyError as exc:
                raise LineageValidationError(
                    f"citation {citation.id!r} references an unknown report claim"
                ) from exc
            if len(citation.evidence_ids) != len(set(citation.evidence_ids)):
                raise LineageValidationError(
                    f"citation {citation.id!r} repeats an evidence ID"
                )
            if len(citation.source_snapshot_ids) != len(
                set(citation.source_snapshot_ids)
            ):
                raise LineageValidationError(
                    f"citation {citation.id!r} repeats a source snapshot ID"
                )
            if not set(citation.evidence_ids).issubset(set(claim.evidence_ids)):
                raise LineageValidationError(
                    f"citation {citation.id!r} uses evidence outside its claim"
                )

            reachable_snapshot_ids: set[str] = set()
            for evidence_id in citation.evidence_ids:
                if evidence_id not in evidence:
                    raise LineageValidationError(
                        f"citation {citation.id!r} references unknown evidence"
                    )
                reachable_snapshot_ids.update(
                    snapshot.id
                    for snapshot in self.resolve_evidence(session, evidence_id)
                )
            if not set(citation.source_snapshot_ids).issubset(
                reachable_snapshot_ids
            ):
                raise LineageValidationError(
                    f"citation {citation.id!r} cross-links an unrelated source"
                )

            citation_urls: set[str] = set()
            for snapshot_id in citation.source_snapshot_ids:
                try:
                    citation_urls.add(str(snapshots[snapshot_id].source_url))
                except KeyError as exc:
                    raise LineageValidationError(
                        f"citation {citation.id!r} references an unknown source"
                    ) from exc
            if len(citation_urls) != 1:
                raise LineageValidationError(
                    "one citation display number must resolve to exactly one URL"
                )
            url = next(iter(citation_urls))
            previous_url = number_urls.setdefault(citation.display_number, url)
            if previous_url != url:
                raise LineageValidationError(
                    "one citation display number resolves to multiple URLs"
                )
            previous_number = url_numbers.setdefault(url, citation.display_number)
            if previous_number != citation.display_number:
                raise LineageValidationError(
                    "one source URL has multiple citation display numbers"
                )
            citations_by_claim.setdefault(claim.id, []).append(citation)

        for claim in claims.values():
            if len(claim.evidence_ids) != len(set(claim.evidence_ids)):
                raise LineageValidationError(
                    f"report claim {claim.id!r} repeats an evidence ID"
                )
            expected_snapshot_ids: set[str] = set()
            for evidence_id in claim.evidence_ids:
                expected_snapshot_ids.update(
                    snapshot.id
                    for snapshot in self.resolve_evidence(session, evidence_id)
                )
            claim_citations = citations_by_claim.get(claim.id, [])
            if not claim_citations:
                raise LineageValidationError(
                    f"report claim {claim.id!r} has no citation"
                )
            cited_evidence_ids = {
                evidence_id
                for citation in claim_citations
                for evidence_id in citation.evidence_ids
            }
            cited_snapshot_ids = {
                snapshot_id
                for citation in claim_citations
                for snapshot_id in citation.source_snapshot_ids
            }
            if cited_evidence_ids != set(claim.evidence_ids):
                raise LineageValidationError(
                    f"report claim {claim.id!r} does not cite all its evidence"
                )
            if cited_snapshot_ids != expected_snapshot_ids:
                raise LineageValidationError(
                    f"report claim {claim.id!r} does not cite all source snapshots"
                )


class CitationRenderer:
    """Renders report text using only validated claim and source records."""

    def __init__(
        self, *, validator: Optional[CitationLineageValidator] = None
    ) -> None:
        self.validator = validator or CitationLineageValidator()

    def render(
        self, session: ResearchSession, *, title: str, limitations: Sequence[str]
    ) -> RenderedReport:
        self.validator.validate_report(session)
        citations_by_claim: dict[str, list[Citation]] = {}
        for citation in session.citations:
            citations_by_claim.setdefault(citation.report_claim_id, []).append(citation)

        lines = [f"# {title}", ""]
        for claim in session.report_claims:
            numbers = sorted(
                {
                    citation.display_number
                    for citation in citations_by_claim[claim.id]
                }
            )
            markers = "".join(f"[{number}]" for number in numbers)
            lines.extend([f"{claim.text} {markers}", ""])

        if limitations:
            lines.extend(["## Limitations", ""])
            for limitation in limitations:
                lines.append(f"- {limitation}")
            lines.append("")

        lines.extend(["## Sources", ""])
        sources_by_number = self._sources_by_number(session)
        for number in sorted(sources_by_number):
            snapshot = sources_by_number[number]
            title_text = _escape_markdown_label(snapshot.title)
            lines.append(
                f"{number}. [{title_text}]({snapshot.source_url}) "
                f"(retrieved {snapshot.retrieved_at.isoformat()})"
            )
        markdown = "\n".join(lines).rstrip()
        return RenderedReport(
            markdown=markdown,
            report_claim_ids=[claim.id for claim in session.report_claims],
            citation_ids=[citation.id for citation in session.citations],
        )

    def _sources_by_number(
        self, session: ResearchSession
    ) -> dict[int, SourceSnapshot]:
        snapshots = _index_by_id(session.source_snapshots, "source snapshot")
        sources: dict[int, SourceSnapshot] = {}
        for citation in session.citations:
            snapshot = snapshots[citation.source_snapshot_ids[0]]
            sources.setdefault(citation.display_number, snapshot)
        return sources


class SynthesisService:
    """Requests ID-only structured claims and commits a validated cited report."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        renderer: Optional[CitationRenderer] = None,
    ) -> None:
        self.llm_client = llm_client
        self.renderer = renderer or CitationRenderer()

    async def synthesize(self, session: ResearchSession) -> RenderedReport:
        if session.plan is None:
            raise SynthesisError("synthesis requires an active research plan")
        if not session.evidence:
            raise SynthesisError("synthesis requires validated evidence")
        lineage = CitationLineageValidator()
        evidence_context: list[dict[str, Any]] = []
        for evidence in session.evidence:
            snapshots = lineage.resolve_evidence(session, evidence.id)
            evidence_context.append(
                {
                    "evidence": evidence.model_dump(mode="json"),
                    "sources": [
                        {
                            "source_snapshot_id": snapshot.id,
                            "title": snapshot.title,
                            "retrieved_at": snapshot.retrieved_at.isoformat(),
                        }
                        for snapshot in snapshots
                    ],
                }
            )

        emit_trace(session, TraceEventType.SYNTHESIS_STARTED)
        request = LLMRequest(
            purpose="synthesis",
            instructions=(
                "Draft material claims using only supplied evidence IDs. Do not emit "
                "URLs or citation numbers; the deterministic renderer supplies them. "
                "Return only the structured schema."
            ),
            context={
                "original_query": session.original_query,
                "objective": session.plan.objective.model_dump(mode="json"),
                "evidence": evidence_context,
            },
            response_schema=SynthesisDraft.model_json_schema(),
            max_output_tokens=session.limits.max_model_output_tokens,
        )
        try:
            response = await self.llm_client.complete(request)
            if (
                response.output_tokens is not None
                and response.output_tokens > session.limits.max_model_output_tokens
            ):
                raise SynthesisError(
                    "synthesis response exceeded max_model_output_tokens"
                )
            draft = SynthesisDraft.model_validate(response.output)
        except SynthesisError:
            raise
        except Exception as exc:
            raise SynthesisError(f"invalid synthesis response: {exc}") from exc

        known_evidence_ids = {evidence.id for evidence in session.evidence}
        for claim in draft.claims:
            unknown = set(claim.evidence_ids) - known_evidence_ids
            if unknown:
                raise SynthesisError(
                    f"synthesis referenced unknown evidence IDs: {sorted(unknown)}"
                )

        report_claims = [
            ReportClaim(
                text=claim.text,
                evidence_ids=list(claim.evidence_ids),
                material=claim.material,
            )
            for claim in draft.claims
        ]
        candidate_session = session.model_copy(deep=True)
        candidate_session.report_claims = report_claims
        candidate_session.citations = self._build_citations(
            candidate_session, report_claims
        )
        lineage.validate_report(candidate_session)
        rendered = self.renderer.render(
            candidate_session,
            title=draft.title,
            limitations=draft.limitations,
        )

        session.report_claims = candidate_session.report_claims
        session.citations = candidate_session.citations
        session.completion_summary = rendered.markdown
        session.unresolved_questions = list(draft.limitations)
        session.status = (
            SessionStatus.PARTIAL if draft.limitations else SessionStatus.COMPLETED
        )
        for citation in session.citations:
            emit_trace(
                session,
                TraceEventType.CITATION_VALIDATED,
                data={
                    "citation_id": citation.id,
                    "report_claim_id": citation.report_claim_id,
                    "display_number": citation.display_number,
                },
            )
        emit_trace(
            session,
            (
                TraceEventType.SESSION_PARTIAL
                if draft.limitations
                else TraceEventType.SESSION_COMPLETED
            ),
            decision_summary="Rendered a lineage-validated cited report",
            data={"citation_count": len(session.citations)},
        )
        return rendered

    def _build_citations(
        self,
        session: ResearchSession,
        report_claims: Sequence[ReportClaim],
    ) -> list[Citation]:
        lineage = LineageValidator()
        source_numbers: dict[str, int] = {}
        citations: list[Citation] = []
        for claim in report_claims:
            grouped: dict[str, dict[str, list[str]]] = {}
            for evidence_id in claim.evidence_ids:
                for snapshot in lineage.resolve_evidence(session, evidence_id):
                    url = str(snapshot.source_url)
                    group = grouped.setdefault(
                        url, {"evidence_ids": [], "snapshot_ids": []}
                    )
                    if evidence_id not in group["evidence_ids"]:
                        group["evidence_ids"].append(evidence_id)
                    if snapshot.id not in group["snapshot_ids"]:
                        group["snapshot_ids"].append(snapshot.id)
            for url, group in grouped.items():
                if url not in source_numbers:
                    source_numbers[url] = len(source_numbers) + 1
                citations.append(
                    Citation(
                        report_claim_id=claim.id,
                        evidence_ids=group["evidence_ids"],
                        source_snapshot_ids=group["snapshot_ids"],
                        display_number=source_numbers[url],
                    )
                )
        return citations


def _escape_markdown_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
