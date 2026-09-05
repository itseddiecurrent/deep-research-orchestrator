# General-Purpose LLM Research Agent

This repository combines a system-design submission with a deliberately small,
runnable research-agent prototype. An LLM creates a structured research plan and
selects dynamically advertised tools; deterministic code validates and executes those
actions, enforces limits, records provenance, and renders citations.

## Submission map

- [`DESIGN.md`](DESIGN.md) — intended architecture, steering, dynamic tools, context
  control, provenance, reliability, trade-offs, and prototype boundary.
- [`EVALUATION.md`](EVALUATION.md) — proposed benchmark, metrics, failure injection,
  judging, observability validation, and regression gates.
- [`MVP_PROGRESS.md`](MVP_PROGRESS.md) — implementation checkpoints and verification.
- [`SUBMISSION_AUDIT.md`](SUBMISSION_AUDIT.md) — requirement-by-requirement status.
- [`AI_USAGE.md`](AI_USAGE.md) and [`logs/`](logs/) — AI-use disclosure and authentic
  filtered Codex history.
- [`research-agent-init.md`](research-agent-init.md) — authoritative assignment.

## Implemented and tested

- Strict Pydantic schemas for objectives, task plans, structured planner actions,
  tool execution, evidence lineage, report claims, citations, and trace events.
- A provider-neutral LLM boundary, deterministic scripted client, and injectable
  OpenAI Responses API adapter.
- A versioned `ToolRegistry` with runtime lookup plus strict input/output validation.
- A generic Tavily `search_web` adapter that requests cleaned full content, disables
  generated answers, and bounds results, response bytes, timeouts, and retries.
- A sequential bounded planner → tool → observation loop. Successful research output
  is normalized into exact hashed snapshots/chunks, then structured evidence is
  extracted before the next planner decision.
- Evidence-ID-only synthesis, deterministic lineage validation, URL resolution from
  source records, deduplicated inline citations, and explicit partial limitations.
- A live-capable CLI with plain report output or one parseable `--trace` JSON result.
- Deterministic demonstrations for unrelated technology-comparison and
  conflicting-science queries through the same runtime and tool definition.

The default offline suite currently has **100 passing tests and one skipped live
test**. It makes no paid API or internet calls.

## Implemented but not live-verified

The OpenAI and Tavily adapters and their composition are tested with injected clients.
The current development environment has no provider credentials and live opt-in is
off, so no live answer quality, availability, latency, or cost result is claimed.

## Designed, not implemented

- Multi-turn user steering and immutable objective-version reconciliation.
- Durable persistence, a full task-DAG scheduler, and bounded parallel execution.
- Capability search for very large catalogs and MCP transport.
- Coverage sufficiency evaluation, contradiction clustering, semantic entailment and
  numeric verification, repair passes, and planner-loop fingerprinting.
- The full synthetic/replay/live benchmark and measured research-quality gates in
  `EVALUATION.md`.

Exact excerpt containment and referential lineage are verified; semantic entailment
is not. The prototype is not a production security or reliability claim.

## Setup and commands

Python 3.9 or newer is required.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q -W error
```

For a live CLI run, copy `.env.example` to `.env` and supply
`OPENAI_API_KEY` and `TAVILY_API_KEY`; `OPENAI_MODEL` is optional.

```bash
.venv/bin/research-agent "Your research question"
.venv/bin/research-agent --trace "Your research question"
```

Normal mode writes a complete or useful partial report to stdout. `--trace` writes one
JSON object containing status, report, unresolved questions, and trace events.
Configuration errors exit 2; terminal runtime failures exit 1.

The paid/network smoke test is opt-in and remains skipped unless the flag and both
credentials are present:

```bash
RUN_LIVE_TESTS=1 .venv/bin/python -m pytest -q -m live
```

## Architecture at a glance

```text
query → structured LLM plan → structured action → ToolRegistry
      → validated tool result → snapshot/chunks → evidence
      → next LLM decision → ID-only synthesis → validated inline citations
```

The model owns semantic planning, tool choice, evidence extraction, and drafting. The
runtime owns schemas, execution, retry/timeout policy, limits, state, provenance, and
citation resolution. There are no finance-, regulation-, technology-, or science-
specific application workflows.

## Assumptions

- The prototype is one in-memory, single-tenant CLI process with one read-only search
  integration.
- Tavily cleaned raw content is the retained tool snapshot; it is not claimed to be
  byte-identical to the publisher's original page.
- Provider/model behavior is replaceable behind structured interfaces.
- Proposed evaluation thresholds require calibration on human-labeled runs.
- The Codex history is an authentic filtered export, not a reconstructed transcript;
  exclusions are documented in [`logs/README.md`](logs/README.md).
