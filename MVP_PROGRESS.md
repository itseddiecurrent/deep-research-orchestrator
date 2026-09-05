# MVP Prototype Progress

## 1. Prototype Goal

Build the smallest runnable vertical slice that proves:

```text
User query
  -> LLM planner
  -> structured AgentAction
  -> ToolRegistry
  -> real external research tool
  -> raw ToolResult
  -> Evidence with provenance
  -> continue/finish decision
  -> cited final answer
```

The same runtime must handle at least two substantially different research questions
without application-code changes. Task decomposition and semantic tool selection
belong to the LLM; validation, execution, limits, provenance, citation resolution,
and trace recording belong to the deterministic runtime. No domain-specific routing
or hidden chain-of-thought is permitted.

## 2. Architecture Decisions

Status: **Approved as the prototype direction; implementation remains milestone-based.**

- **Interface:** a CLI and in-memory session state. FastAPI and durable storage do not
  strengthen the core proof enough to justify MVP complexity.
- **Orchestration:** one sequential planner → action → observation loop. The LLM first
  emits a structured objective/task plan, then chooses tool calls or a finish action.
- **Tools:** application-executed function tools registered at runtime. Use ordinary
  function/tool calling for the MVP; preserve MCP as a future adapter behind the same
  registry contract.
- **Real integration:** one generic `search_web` tool backed by Tavily Search with
  generated answers disabled and cleaned raw result content enabled. Evidence may use
  fetched result content, not search snippets alone. Requires `TAVILY_API_KEY`.
- **LLM boundary:** provider-neutral `LLMClient` request/response models with one
  OpenAI Responses API adapter. The model is configuration, not domain logic. Tests
  use a deterministic scripted client. Requires `OPENAI_API_KEY` for live runs.
- **Schemas:** strict Pydantic models with discriminated actions and rejected unknown
  fields. Provider-native calls are normalized and validated again by the runtime.
- **Evidence lineage:** `ToolCall -> ToolResult -> SourceSnapshot -> SourceChunk ->
  Evidence -> ReportClaim -> Citation`. Snapshots hash the exact cleaned content
  returned by the tool; this is not represented as original publisher bytes.
- **Citation behavior:** evidence candidates must reference an existing chunk and an
  exact excerpt. The runtime verifies containment/offsets. Synthesis cites only known
  evidence IDs; a deterministic renderer supplies URLs from source records.
- **Limits:** enforce maximum iterations, tool calls, per-call timeout, retry attempts,
  model output tokens, and tool-result size. A limit produces an honest partial result
  or explicit failure rather than continued research.
- **Retries:** bounded runtime retry only for adapter-declared retryable/idempotent
  failures. Every attempt is visible in the trace and charged to limits.
- **Trace:** append-only structured events with timestamps and IDs for objective,
  plan/tasks, planner decision summary, tool request/result/failure, evidence creation,
  continue/finish decision, synthesis, citation validation, limits, and terminal state.
- **Dependencies:** keep the set small: Python, Pydantic, OpenAI SDK, HTTPX, pytest,
  and pytest-asyncio. Use standard-library `argparse` for the CLI.
- **Intentionally proposed-only:** user steering/objective version reconciliation,
  persistence, DAG scheduling/parallelism, MCP transport, broad tool coverage,
  semantic entailment repair, contradiction clustering, and the full evaluation
  harness.

## 3. Implementation Plan

- [x] Establish prototype execution checkpoint
  - [x] Reconcile design-only repository state
  - [x] Record recommended scope, decisions, tests, and risks in this file
- [x] Milestone 1 — Project foundation and core schemas
  - [x] Create package/dependency structure and CLI entry point
  - [x] `ResearchSession` and bounded runtime configuration
  - [x] LLM-generated objective and `ResearchTask` plan
  - [x] Structured `AgentAction` union
  - [x] `ToolCall`, attempt, raw `ToolResult`, and observation models
  - [x] `SourceSnapshot`, `SourceChunk`, `Evidence`, `ReportClaim`, and citation models
  - [x] Trace-event model
  - [x] Focused schema/action tests
- [x] Milestone 2 — Tool abstraction and deterministic runtime
  - [x] Generic `Tool` protocol and `ToolDefinition`
  - [x] Dynamic registration, descriptions, lookup, and execution by name/version
  - [x] Argument/output validation and unknown-tool rejection
  - [x] Provider-neutral `LLMClient` abstraction and scripted test client
  - [x] Initial plan call and bounded planner/action loop
  - [x] Observation returned to the next planner turn
  - [x] Finish, limit, invalid-output, failure, and bounded-retry behavior
  - [x] Structured trace emission
  - [x] Deterministic runtime/registry/failure tests
- [x] Milestone 3 — Provenance and citations
  - [x] Normalize raw tool results into hashed source snapshots and chunks
  - [x] Structured evidence extraction with exact excerpt validation
  - [x] Reject evidence without successful source/tool lineage
  - [x] Structured synthesis using existing evidence IDs only
  - [x] Deterministic lineage validation and inline citation rendering
  - [x] Citation/provenance/fabricated-ID tests
- [ ] Milestone 4 — Real external integration and CLI
  - [ ] OpenAI Responses API adapter with configurable model
  - [ ] Tavily `search_web` adapter with timeout and output bounds
  - [ ] Environment/config validation without logging credentials
  - [ ] CLI output for final report, limitations, and optional structured trace
  - [ ] Opt-in live integration test that does not run in the default suite
- [ ] Milestone 5 — Generality demonstration
  - [ ] Run technology-comparison query without code changes
  - [ ] Run conflicting-science query without code changes
  - [ ] Optionally run current-policy comparison
  - [ ] Save sanitized, timestamped report and trace artifacts if licensing permits
  - [ ] Verify both required demos use the same runtime/tool registry
- [ ] Milestone 6 — Submission reconciliation
  - [ ] Update README implemented/designed/future status and commands
  - [ ] Reconcile DESIGN.md prototype-scope statements
  - [ ] Update SUBMISSION_AUDIT.md with only verified statuses
  - [ ] Update AI_USAGE.md and refresh authentic Codex history export
  - [ ] Run final repository, test, lineage, and disclosure audit

No implementation milestone is complete until its tests pass. Live-call success is
reported separately from deterministic test success.

## 4. Current Repository State

As of 2026-09-05 14:06 +08:00:

- Prototype package files now include `tools.py`, `llm.py`, `runtime.py`,
  `provenance.py`, and `synthesis.py` alongside `models.py`, `cli.py`, and
  `__init__.py`; `pyproject.toml` defines the package and `research-agent` entry point.
- Strict Pydantic schemas cover the session, limits, objective/task plan, actions,
  tool execution records, provenance/citations, and trace events.
- A generic versioned registry validates strict Pydantic input/output models, rejects
  duplicate/unknown/ambiguous tools, and executes registered async adapters.
- The provider-neutral LLM request/response protocol and scripted client feed a
  bounded plan/action runtime with catalog, state, observation, and remaining-budget
  context.
- Runtime tool attempts enforce timeout, idempotent retry, logical-call, iteration,
  model-output, and result-size limits; failures remain explicit observations.
- Canonical retrieval output can now be ingested into content-hashed snapshots and
  fixed-size exact-offset chunks without stripping source whitespace.
- Structured evidence extraction accepts candidates only when tasks, chunks,
  snapshots, successful results/calls, hashes, offsets, and verbatim excerpts form a
  valid in-session lineage chain.
- Structured synthesis accepts existing evidence IDs only; report claims/citations
  are built and validated atomically, then inline numbers and stored source URLs are
  rendered deterministically with repeated URLs deduplicated.
- Tests are now in seven files under `tests/`; 59 deterministic offline tests pass.
- The CLI exposes help/version and explicitly refuses live research because real LLM
  and search adapters remain Milestone 4 work.
- No semantic entailment verifier, real tool/provider adapter, live demo, or measured
  evaluation result exists yet.
- `README.md`, `DESIGN.md`, `SUBMISSION_AUDIT.md`, and `AI_USAGE.md` still describe
  the pre-prototype checkpoint; their final status reconciliation remains Milestone 6.
  This file is authoritative for incremental prototype progress meanwhile.
- A local `main` Git repository now targets
  `https://github.com/itseddiecurrent/deep-research-orchestrator.git`; `.env` and
  credential variants are ignored and never included in repository history.
- Milestone 1 requires no credentials. Future live execution will require
  `OPENAI_API_KEY`, `TAVILY_API_KEY`, and outbound network access; these have not been
  checked.
- The filtered prompt-history export is refreshed at verified milestone boundaries;
  the final assistant handoff may be absent because it is emitted afterward.

## 5. Completed Work

### Required written deliverables

Status: Complete before prototype planning

Implemented:

- architecture and four required design answers;
- concrete evaluation strategy;
- reviewer README, AI-use disclosure, and submission audit;
- filtered authentic Codex session export.

Verified by:

- prior repository audit confirmed required files and Markdown links;
- five required Mermaid diagrams were present;
- exported JSONL parsed and matched its documented filter.

### Prototype planning checkpoint

Status: Complete

Implemented:

- reconciled the design-only repository with the proposed minimal vertical slice;
- recorded implementation boundaries, ordered milestones, required tests, and risks.

Verified by:

- repository inventory showed no implementation/test files to reconcile;
- authoritative design/evaluation hashes matched the preceding checkpoint;
- this file contains exactly one current task and no unverified implementation claim.

### Milestone 1 — project foundation and core schemas

Status: Complete

Implemented:

- installable `src/` Python package and console entry-point shell;
- strict, provider-neutral schemas for runtime limits, session/objective/task plan,
  discriminated planner actions, tool execution, provenance/citations, and trace;
- validation for bounds, unknown fields/actions, task references/cycles, tool-result
  success/error consistency, provenance field shape, and timezone-aware timestamps;
- deterministic schema and CLI tests.

Relevant files:

- `pyproject.toml`, `src/research_agent/models.py`,
  `src/research_agent/cli.py`, `tests/test_models.py`, and `tests/test_cli.py`.

Verified by:

- `python -m compileall -q src tests`;
- `pytest -q`: 13 passed without warnings;
- installed `research-agent --version` and no-query help smoke checks.
- authentic Codex session export refreshed through this milestone checkpoint.

### Milestone 2 — tool abstraction and deterministic runtime

Status: Complete

Implemented:

- generic `Tool` protocol, strict `ToolDefinition`, deterministic catalog versions,
  and name/version registry lookup;
- registration checks that advertised schemas match strict Pydantic adapter models;
- pre-invocation argument rejection, post-invocation output normalization, explicit
  unknown/ambiguous tool errors, and adapter-declared execution failures;
- provider-neutral structured `LLMRequest`, `LLMResponse`, and `LLMClient`, plus a
  FIFO scripted client that captures exact requests;
- initial structured plan validation and sequential bounded action loop;
- full call/result/observation feedback to later planner turns;
- complete/partial/failed terminal state, iteration/logical-call/model-output/result-
  size limits, per-call timeout, idempotency-aware bounded retry, and structured
  lifecycle/attempt trace events;
- accurate CLI boundary message: deterministic runtime exists, live adapters do not.

Relevant files:

- `src/research_agent/tools.py`, `src/research_agent/llm.py`,
  `src/research_agent/runtime.py`, updates to `models.py` and `cli.py`, and
  `tests/test_tools.py`, `tests/test_llm.py`, `tests/test_runtime.py`.

Verified by:

- `python -m compileall -q src tests`;
- `pytest -q`: 38 passed without warnings;
- `python -m pip check`: no broken requirements;
- installed `research-agent --version` and no-query help smoke checks;
- no network or paid provider call was made.

### Milestone 3 — provenance and citations

Status: Complete

Implemented:

- strict canonical `ResearchToolOutput`/`RetrievedSource` boundary that requires full
  source content and rejects snippet-only payloads;
- exact UTF-8 SHA-256 source/chunk hashing, whitespace-preserving snapshot storage,
  deterministic fixed-size offsets, full-coverage reconstruction, duplicate-source
  normalization, and idempotent per-result ingestion;
- structured `EvidenceCandidate`/`EvidenceBatch` extraction requests with supplied-
  chunk restrictions, output-token enforcement, atomic creation, and exact excerpt
  containment;
- deterministic evidence walks through task → chunk → snapshot → successful tool
  result/call, including duplicate-ID, hash, offset, missing-link, and failed-lineage
  rejection;
- evidence-ID-only `SynthesisDraft`, with free-form URL rejection and atomic creation
  of `ReportClaim`/`Citation` records;
- report-level citation integrity checks, stable first-use display numbering,
  repeated-source URL deduplication, stored-metadata bibliography rendering, partial
  limitations, and citation/terminal trace events.

Relevant files:

- `src/research_agent/provenance.py`, `src/research_agent/synthesis.py`, updates to
  `models.py` and `llm.py`, and `tests/test_provenance.py`/
  `tests/test_synthesis.py`.

Verified by:

- `python -m compileall -q src tests`;
- `pytest -q -W error`: 59 passed without warnings;
- `python -m pip check`: no broken requirements;
- `git diff --check`: passed;
- no network or paid provider call was made.

## 6. Current Task

### Review Milestone 3 and authorize Milestone 4

Status: Ready — awaiting human direction

Objective:

- review the verified provenance/evidence/synthesis/citation boundary;
- confirm whether to begin Milestone 4: OpenAI Responses adapter, Tavily search tool,
  environment validation, live-capable CLI, and opt-in integration test.

Files expected to be modified:

- none until Milestone 4 is authorized; update this checkpoint first when it is.

Expected behavior:

- the repository remains at the verified, published Milestone 3 checkpoint;
- live calls remain opt-in and credentials must never enter prompts, trace data,
  command output, or Git history.

Tests that prove completion:

- none for this review gate. Milestone 4 tests will prove adapter request/response
  normalization, environment errors, Tavily bounds/timeouts, CLI report/trace output,
  and default-skipped live integration behavior.

## 7. Tests and Verification

Current status: 59 deterministic offline tests pass across schemas, CLI, registry,
scripted LLM client, bounded runtime, provenance, evidence, citation integrity,
synthesis rendering, failures, retries, timeouts, and trace behavior.

| Required coverage | Status | Planned proof |
|---|---|---|
| 1. Tool registration and lookup | Verified | Two generic tools, exact versions, deterministic catalog, duplicate/ambiguous cases |
| 2. Unknown tool rejection | Verified | Zero adapter calls and explicit failure observation reaches next planner turn |
| 3. Tool argument/schema validation | Verified | Valid, missing, wrong-type, extra input, and invalid output cases |
| 4. Planner structured-output parsing | Schema verified | Valid tool/finish actions parse through the discriminated union |
| 5. Invalid LLM output handling | Verified | Invalid plan/action yields failed terminal state and zero tool execution |
| 6. Model-selected tool execution | Verified | Scripted planner selects one of two advertised adapters; only it executes |
| 7. Observation returned to planner | Verified | Next context contains exact observation plus linked call/result records |
| 8. Finish action terminates | Verified | Complete/partial state; later scripted responses remain unused |
| 9. Iteration/tool-call limits | Verified | Each cap terminates deterministically; model/result-size limits also tested |
| 10. Tool failure and bounded retry | Verified | Retryable idempotent timeout/error retries to cap; permanent/non-idempotent does not |
| 11. Evidence keeps provenance | Verified | Exact hashes/offsets/excerpts and successful call→result→snapshot→chunk→evidence walk |
| 12. Citation IDs resolve | Verified | Claims render only after every evidence/chunk/snapshot/result/call edge validates |
| 13. Fabricated citation IDs rejected | Verified | Unknown evidence, unrelated source links, duplicate IDs, and free-form URLs fail |
| 14. Two unrelated queries, same runtime | Planned | Parameterized scripted test plus separate opt-in live demos |
| Real external tool | Planned | Tavily integration test skipped unless key/network explicitly enabled |
| Hidden chain-of-thought independence | Schema verified | Trace exposes `decision_summary`; no reasoning field exists |

Default tests must be deterministic, offline, and free of paid API calls. Live tests
must be opt-in and clearly labeled.

## 8. Known Issues / Risks

- OpenAI and Tavily credentials/availability are unknown.
- External search results are nondeterministic and may change between demo runs.
- Tavily cleaned raw content proves lineage to a tool result, not byte identity with
  the original publisher page.
- Exact excerpt containment proves referential provenance, not semantic entailment.
- One tool limits fallback and tool-selection breadth; two registered fake tools in
  tests can still prove dynamic selection mechanics.
- A weak or flaky live demo could reduce confidence relative to the design-only
  submission.
- The repository has only a new local history; Milestone 3 is published to the
  configured GitHub origin and future milestones must be pushed after verification.
- User steering, objective versioning, persistence, DAG concurrency, contradiction
  handling, and full evaluation remain unimplemented by deliberate scope choice.
- Saved external content may have retention/licensing constraints; prefer short
  excerpts and source hashes in committed demo artifacts.
- The prompt-history export must be refreshed after authorized milestones without
  fabricating or manually rewriting messages.

## 9. Remaining Work

1. Review/authorize Milestone 4 real provider/tool/CLI integration.
2. Add and exercise OpenAI and Tavily adapters behind existing interfaces.
3. Run at least two unrelated demos through the unchanged runtime.
4. Reconcile reviewer documents and refresh the authentic session export.
5. Complete the final submission audit without overstating results.

## 10. Last Verified Checkpoint

Last verified: 2026-09-05 14:09:34 +08:00

- Repository inventory: written deliverables plus verified Milestone 1–3 package/tests.
- Git status/diff: local `main` and `origin/main` resolve to the verified Milestone 3
  implementation commit; the worktree was clean immediately after publication.
- Python compilation: passed for `src` and `tests`.
- Prototype unit tests: 59 passed with warnings treated as errors; dependency and
  whitespace checks passed.
- Integration/demo runs: not present; not run.
- Working behavior: scripted structured planning, dynamic validated tool execution,
  bounded observation loop, provenance ingestion/evidence validation, ID-constrained
  synthesis, deterministic inline citations, retries/failures/limits, terminal state,
  and trace work; live providers and semantic entailment do not.
- Prompt history: filtered authentic export is refreshed at milestone boundaries;
  this publication-reconciliation turn may be absent until the next refresh.
- Commands used: `python -m compileall -q src tests`, `pytest -q -W error`,
  `python -m pip check`, and `git diff --check`.

## 11. Working Rules

1. Read the specification, design, evaluation plan, README, audit, and this checkpoint
   before significant implementation changes.
2. Inspect Git state when available, actual source files, and tests; repository code
   is authoritative for implemented behavior.
3. Keep exactly one current task and update it after each meaningful milestone.
4. Define expected behavior and focused tests before implementing a behavior.
5. Do not mark implementation complete until relevant tests pass.
6. Add or update deterministic tests whenever behavior changes; keep paid/live calls
   out of the default suite.
7. If repository state contradicts this file, correct this file without rewriting
   valid completed history.
8. Keep decisions, implementation facts, and verbose command logs separate.
9. Update this checkpoint and refresh the authentic conversation export before ending
   an authorized implementation session.
10. Preserve the generic architecture: no query-domain routing or hidden
    chain-of-thought dependency.
11. Commit and push after each verified milestone; keep `.env` ignored and never put
    credentials in repository content, logged commands, or remote URLs.
