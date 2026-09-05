# General-Purpose LLM Research Agent

This repository is a system-design take-home submission for a generic LLM-powered
research agent. The proposed system lets an LLM dynamically plan research and choose
from registered tools while a deterministic runtime owns safe execution, state,
budgets, provenance, and observability.

The required written deliverables take priority over prototype breadth.

## Submission map

- [`DESIGN.md`](DESIGN.md) — architecture, interaction/steering, dynamic planning and
  tools, context-drift prevention, citation lineage, reliability, and trade-offs.
- [`EVALUATION.md`](EVALUATION.md) — benchmark design, concrete metrics, citation
  evaluation, failure injection, repeated-run policy, and regression gates.
- [`AI_USAGE.md`](AI_USAGE.md) — assistant usage, human decisions/corrections, and log
  limitations.
- [`SUBMISSION_AUDIT.md`](SUBMISSION_AUDIT.md) — requirement-by-requirement final
  audit with implemented/designed/not-implemented status.
- [`logs/codex-session-export.jsonl`](logs/codex-session-export.jsonl) — authentic,
  filtered Codex conversation/tool history; see [`logs/README.md`](logs/README.md).
- [`research-agent-init.md`](research-agent-init.md) — authoritative assignment
  specification.

## Implemented in this repository

- The required design document and evaluation plan.
- A reviewer-oriented project status and AI-use disclosure.
- A filtered export of the actual Codex session history.

There is currently **no runnable research-agent prototype and no claimed test or
evaluation result**. An earlier prototype-first scaffold was removed after the
assignment was clarified to prioritize system design.

## Designed / proposed

- Multi-turn `ResearchSession` state with immutable original intent and versioned
  `ResearchObjective`s.
- LLM-generated task DAGs and semantic selection from a dynamic ToolRegistry/MCP
  catalog.
- Runtime validation of structured actions, schemas, permissions, budgets, retries,
  timeouts, concurrency, and state transitions.
- Retrieval, snapshot, chunk, evidence, finding, report-claim, and inline-citation
  lineage.
- Coverage evaluation, context re-grounding, contradiction handling, cited
  synthesis, and verification.
- Structured traces and a reproducible synthetic/replay/live evaluation program.

These items are design commitments, not implemented features.

## Future work

The smallest useful prototype should demonstrate:

```text
user query
  -> LLM planner
  -> validated AgentAction
  -> dynamically selected real read-only research tool
  -> observation and immutable source snapshot
  -> chunk-linked Evidence
  -> next LLM decision
  -> verified cited response
```

It should add focused tests for invalid schemas, unknown tools, retry/timeout behavior,
hard limits, citation resolution, and at least two unrelated query types through the
same code path. Durable distributed workers, a large UI, long-term memory, and
write-capable tools remain later work.

## Architecture at a glance

The conversation API converts user messages into versioned objectives. A deterministic
runtime repeatedly provides the active objective, coverage gaps, evidence references,
available tool schemas, and remaining budget to an LLM planner. Validated actions run
through a bounded task scheduler and tool-policy boundary. Retrieved content becomes
immutable source/chunk/evidence records. An evaluator decides whether gaps justify
more work; a synthesizer drafts only from evidence IDs; a verifier checks lineage and
entailment before citations are rendered. See [`DESIGN.md`](DESIGN.md) for diagrams
and failure paths.

## Running the prototype and tests

There is no prototype or test harness yet, so there are no honest run/test commands to
provide. The proposed implementation and verification boundary is documented in
`DESIGN.md`; the planned automated evaluation harness is documented in
`EVALUATION.md`.

## Assumptions

- The initial system is a single service with read-only tools and one tenant.
- Steering is processed between tool calls in the MVP.
- Tool/model providers are replaceable behind structured interfaces.
- Source snapshots are retained where licensing permits.
- Evaluation thresholds are proposals until calibrated on human-labeled runs.
- The Codex history export is filtered rather than raw; its exact exclusions are
  documented and no conversation was manually fabricated.
