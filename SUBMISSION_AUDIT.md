# Submission Audit

Status is based on repository evidence:

- **Complete** — required written artifact exists and was checked.
- **Verified** — implemented behavior has deterministic test evidence.
- **Implemented, live unverified** — adapter/code exists and is tested with fakes, but
  no real provider call succeeded in this environment.
- **Designed** — described in the architecture/evaluation plan but not implemented.
- **Not implemented** — neither code nor measured result exists.

## Required deliverables

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Prompt history | Complete, filtered export | `logs/codex-session-export.jsonl`; authentic user/assistant/tool records with exclusions in `logs/README.md` |
| Design document | Complete | `DESIGN.md`; four direct answers, 20 sections, five Mermaid diagrams, and an updated prototype boundary |
| Evaluation plan | Complete | `EVALUATION.md`; benchmark, metrics, judge rubric, invariants, faults, repetitions, and gates; it is not a results report |
| AI-use disclosure | Complete | `AI_USAGE.md`; includes the human scope correction and implementation/recovery work |
| Reviewer README | Complete | `README.md`; commands and verified/designed/unverified status |
| Prototype | Verified offline | Installable CLI and 100 passing deterministic tests; one live test skipped because opt-in/credentials are absent |

## 1. System Architecture

| Evaluation expectation | Status | Repository evidence / limitation |
|---|---|---|
| Explicit planner/execution loop | Verified | `runtime.py`; structured plan, action, tool, observation, finish loop |
| Session state | Verified, prototype subset | Strict in-memory `ResearchSession`; no durable or multi-turn session service |
| LLM-driven planning/tool choice | Verified offline | Scripted clients drive plans/actions; OpenAI adapter is offline-tested |
| User steering | Designed | `DESIGN.md` §§4 Q1 and 8; no runtime message reconciliation |
| Objective versioning | Designed | Schema has a version, but update/reconciliation behavior is not implemented |
| Task dependencies / DAG | Schema verified | References and cycles validate; no DAG scheduler/lifecycle execution |
| Parallelism | Designed | No concurrent task executor |
| Context-drift prevention | Partially verified | Original query/objective remain in prompts; no long-session compaction or re-grounding evaluator |
| Completion criteria | Partially verified | Structured finish and hard limits work; semantic coverage sufficiency is model-proposed, not independently evaluated |
| General-purpose behavior | Verified offline | Technology and conflicting-science cases use the same runtime and `search_web` definition |

## 2. Tool Use & Grounding

| Evaluation expectation | Status | Repository evidence / limitation |
|---|---|---|
| Dynamic registration/lookup | Verified | Versioned registry, catalog hashing, duplicates, ambiguity, and unknown tools tested |
| Dynamic semantic selection | Verified offline | Planner chooses among advertised fake tools; no domain router exists |
| Structured interfaces | Verified | Strict Pydantic plan/action/tool/evidence/synthesis schemas reject extra fields |
| Runtime validation | Verified subset | Tool/version, input/output, task reference, timeout, retry, and size checks; broader permission/URL policy is designed only |
| Real external research tool | Implemented, live unverified | Tavily `search_web` requests full cleaned Markdown and maps typed failures; HTTP is mocked in default tests |
| Retrieval/extraction separation | Verified | Snippets and failed results cannot create sources/evidence; extraction uses exact chunks |
| Evidence/provenance | Verified | Hashes, offsets, excerpts, atomic creation, and call/result/snapshot/chunk/evidence walks tested |
| Inline citation traceability | Verified | Synthesis accepts evidence IDs; renderer resolves stored sources and validates all edges |
| Semantic citation correctness | Not implemented | Exact containment is not entailment; no model/human entailment verifier has run |
| Unseen-query portability | Verified offline | Two unrelated cases require no application-code or catalog change |

## 3. Reliability & Error Handling

| Evaluation expectation | Status | Repository evidence / limitation |
|---|---|---|
| Malformed structured output | Verified | Invalid plan/action/evidence/synthesis output is rejected before unsafe mutation |
| Tool failure visibility | Verified | Typed failure observations return to the next planner request |
| Retries | Verified subset | Retryability, idempotency, and caps tested; exponential backoff/jitter is not implemented |
| Timeout/rate/auth/parse/empty/size faults | Verified offline | Runtime and Tavily injected-fault tests cover each class |
| Capability fallback | Partially verified | Failures are observable so the LLM can choose another catalog tool; broad fallback behavior is not benchmarked |
| Contradictory evidence | Designed | No conflict clustering/resolution implementation |
| Partial completion | Verified | Finish actions and hard limits preserve named unresolved questions |
| Planner-loop handling | Partially verified | Hard iteration/call caps terminate; repeated-action fingerprints are not implemented |
| Bounded autonomy | Verified subset | Iterations, logical calls, per-call retries/timeouts, output tokens, and result bytes; no cost/elapsed/concurrency ledger |
| Secret handling | Verified offline | Secret types, sanitized adapter errors, configuration messages, and payload tests; no production red-team claim |
| State preservation | Verified subset | Atomic evidence/report mutation tests; no persistence/interruption recovery |

## 4. Evaluation & Observability

| Evaluation expectation | Status | Repository evidence / limitation |
|---|---|---|
| Diverse synthetic benchmark | Complete plan, not implemented | `EVALUATION.md` §§2–4 |
| Ambiguity/steering/drift/conflict cases | Complete plan, not implemented | Detailed case families and metrics; no benchmark results |
| Failure injection | Verified prototype subset | Deterministic unit/integration-style tests; full matrix/property suite is future work |
| Citation invariants | Verified | Lineage, exact hashes/offsets, invalid IDs, unrelated sources, and URL provenance tested |
| Generality demonstration | Verified offline | Two unrelated deterministic cases through the same path |
| Structured observability | Verified prototype subset | Public trace events and parseable CLI output; no metrics dashboard/cost collector |
| Default offline isolation | Verified | 100 pass; guarded live test is collected and skipped |
| LLM-as-a-judge / human calibration | Not implemented | Rubric and protocol only |
| Measured research quality/cost/latency | Not implemented | No live credentials, benchmark execution, or calibrated results |

## Final checklist

- [x] Planning and semantic tool selection are LLM-driven at the application boundary.
- [x] Runtime schemas validate untrusted model and tool output.
- [x] Execution, retries, timeouts, and core budgets are deterministically bounded.
- [x] Evidence retains call/result/source/chunk provenance.
- [x] Final URLs and inline citations resolve from validated evidence IDs.
- [x] No domain-specific query workflow or hidden chain-of-thought dependency exists.
- [x] Two unrelated query categories traverse the same generic path offline.
- [x] Authentic filtered prompt/tool history is preserved with limitations disclosed.
- [x] Implemented, live-unverified, designed, and future work are separated.
- [ ] Live OpenAI/Tavily vertical slice verified (credentials/opt-in absent).
- [ ] Semantic citation entailment, contradiction handling, steering, persistence,
      full DAG execution, and the evaluation benchmark implemented.
- [ ] Research-quality, latency, token-cost, and judge/human metrics measured.

The unchecked items are explicit limitations, not implied capabilities.
