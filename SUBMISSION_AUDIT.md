# Submission Audit

Audit status is based on repository evidence, not intended future behavior:

- **Complete** — required document/export exists and was checked.
- **Designed** — architecture is specified but no prototype demonstrates it.
- **Not implemented** — no runnable code or measured result exists.

## Required deliverables

| Requirement | Status | Repository evidence / limitation |
|---|---|---|
| Prompt History / Conversation Logs | Complete, filtered export | `logs/codex-session-export.jsonl`; actual user/assistant/tool records, with exact exclusions in `logs/README.md`. Not a raw internal-session dump. |
| Design Document | Complete | `DESIGN.md`; four direct answers, 20 sections, and five Mermaid diagrams. |
| Evaluation Plan | Complete | `EVALUATION.md`; benchmark, metrics, judge rubric, invariants, failure injection, repetitions, and regression gates. |
| AI-use disclosure | Complete | `AI_USAGE.md`; includes human correction and prior prototype removal. |
| Reviewer README | Complete | `README.md`; separates implemented, proposed, and future work. |
| Prototype | Not implemented | Deliberately deferred; no run/test results are claimed. |

## Phase 4 document-review findings

The design and evaluation drafts were checked against the explicit requirements in
`research-agent-init.md`. The review confirmed coverage of the four required design
questions and found two areas worth making more explicit:

1. Dynamic tool discovery needed direct evaluation rather than only a benchmark-case
   mention. `EVALUATION.md` now defines catalog mutation/malicious-description tests,
   candidate recall, valid selection, and unknown-tool proposal metrics.
2. The retrieval/extraction separation needed an explicit invariant. The evaluation
   now prevents search snippets or unsuccessful tool output from becoming substantive
   evidence without a snapshot and exact chunk parent.

`DESIGN.md` explicitly includes future improvements, prototype boundaries, and
rejected alternatives. No significant prototype code was written before this review.

## 1. System Architecture

| Evaluation expectation | Status | Evidence |
|---|---|---|
| Explicit reasoning/execution loop | Designed | `DESIGN.md` §7, research-loop diagram and iteration contract |
| Session state | Designed | §6 `ResearchSession`, objective, task, and budget models |
| LLM-driven planning | Designed | §§4 Q2, 7, and 9; the runtime supplies goal/state/tools/budget and validates proposals |
| User steering | Designed | §§4 Q1 and 8; refinement, redirect, drill-down, cancellation, resume |
| Objective versioning | Designed | §§6 and 8; immutable versions and reconciliation |
| Task dependencies / DAG | Designed | §10; cycle/depth/node validation and readiness |
| Parallelism | Designed | §10; bounded concurrency, leases, isolated snapshots, late-result reconciliation |
| Context-drift prevention | Designed | §§4 Q3 and 11; immutable original objective, coverage matrix, re-grounding, safe compaction |
| Completion criteria | Designed | §7; semantic coverage plus deterministic lineage/limit gates |
| General-purpose behavior | Designed | §§1–2, 9, and 17; no domain/keyword router |

Audit conclusion: architecture addresses the assignment, but none of these mechanisms
has runtime evidence yet.

## 2. Tool Use & Grounding

| Evaluation expectation | Status | Evidence |
|---|---|---|
| Dynamic tool registration/discovery | Designed | `DESIGN.md` §9; versioned `ToolDefinition`, MCP/local adapters, catalog retrieval |
| Dynamic semantic selection | Designed | §§4 Q2 and 9; model chooses from supplied schemas, runtime does not route by domain |
| Structured interfaces | Designed | §§7 and 9; discriminated actions, input/output JSON Schemas, extra-field rejection |
| Runtime validation | Designed | §9 invocation boundary; catalog, objective, schema, policy, URL, budget, retry checks |
| External evidence | Designed | §§5 and 12; source ingestion and immutable snapshots |
| Retrieval/extraction separation | Designed and evaluated | `DESIGN.md` §12; `EVALUATION.md` §4 and invariant 17 |
| Evidence as structured data | Designed | `DESIGN.md` §12 entity table |
| Inline citation traceability | Designed | §§4 Q4 and 12; claim → finding → evidence → chunk → snapshot → source → tool call |
| Citation verification | Designed | §12; referential, numeric, entailment, bounded repair, renderer |
| Real external research tool | Not implemented | No prototype exists. |
| Unseen queries require no new workflow | Designed, not demonstrated | Catalog-driven architecture and `unknown_domain_*` evaluation cases |

Audit conclusion: the lineage and trust boundaries are explicit; an end-to-end real
tool demonstration remains future work.

## 3. Reliability & Error Handling

| Evaluation expectation | Status | Evidence |
|---|---|---|
| Malformed structured output | Designed | `DESIGN.md` §13; bounded schema-guided repair then explicit failure |
| Tool failure visibility | Designed | §13; typed failure observation returned to planner |
| Retries/backoff | Designed | §13; typed retryability, idempotency, cap, jitter, attempt lineage |
| Timeouts/rate limits/access/parse/empty result | Designed | §13 and evaluation failure matrix |
| Fallbacks | Designed | Capability-based replanning through healthy registered tools |
| Contradictory evidence | Designed | §12; conflict sets, scope/date resolution, both sides retained |
| Partial completion | Designed | §§7 and 13; reserved synthesis budget and named unresolved gaps |
| Planner-loop detection | Designed | §13; normalized fingerprints and coverage-progress windows |
| Bounded autonomy | Designed | §§6 and 14; calls, iterations, retries, parallelism, time, tokens, cost, bytes |
| Security/tool policy | Designed | §§9 and 14; least privilege, SSRF/redirect controls, prompt-injection isolation, secret handling |
| Fault-recovery behavior | Designed, not demonstrated | `EVALUATION.md` §9; no executed tests yet |

Audit conclusion: failure semantics and hard limits are detailed, but reliability
claims remain proposals until a prototype and fault-injection harness run.

## 4. Evaluation & Observability

| Evaluation expectation | Status | Evidence |
|---|---|---|
| Diverse synthetic benchmark | Complete plan | `EVALUATION.md` §§2–4; ≥60 cases across all requested categories/difficulties |
| Ambiguous-query tests | Complete plan | §4 decision classes and measured clarification behavior |
| Multi-turn steering tests | Complete plan | §4 event-triggered messages and state/output assertions |
| Context-drift tests | Complete plan | §4 lossy summaries, distractors, redirects, objective-fidelity formula |
| Conflicting-source tests | Complete plan | §4 conflict types and resolution/qualification labels |
| Tool-failure/failure injection | Complete plan | §9 fault schedule and expected assertions |
| Citation coverage/correctness | Complete plan | §6 exact claim-level formulas and labeling procedure |
| Source quality | Complete plan | §6 contextual five-factor annotations and formulas |
| Answer completeness | Complete plan | §6 weighted atomic requirements |
| Task completion / redundant calls | Complete plan | §6 formulas, trace inputs, and exceptions |
| Latency/token/estimated cost | Complete plan | §6 timestamps, percentiles, provider counters, versioned price tables |
| LLM-as-a-judge | Complete plan | §7 input boundary, output schema, anchored rubric, calibration |
| Deterministic invariants | Complete plan | §8; 17 state, lineage, policy, budget, and termination checks |
| Regression/repeated runs | Complete plan | §§5 and 12; 5×/10× runs, distribution reporting, held-out cases |
| Structured observability | Designed | `DESIGN.md` §15 and `EVALUATION.md` §10; events, correlation, metrics, redaction |
| Measured evaluation results | Not implemented | Thresholds are explicitly proposals, not observed scores. |

Audit conclusion: the plan goes beyond manual QA and specifies how metrics are
derived. The next implementation milestone should build the trace/lineage substrate
before attempting prose-quality evaluations.

## Final verification checklist

- [x] Planning is LLM-driven in the design.
- [x] Tool selection is dynamic and catalog-driven in the design.
- [x] Tools and agent actions use structured interfaces in the design.
- [x] No domain-specific or example-specific workflow is introduced.
- [x] User steering and objective versioning are explicit.
- [x] Context drift is explicitly addressed and tested by the evaluation plan.
- [x] Final citations are designed to resolve to specific tool results and source
      bytes.
- [x] Failures, contradictions, retries, limits, and partial completion are explicit.
- [x] Observability avoids private chain-of-thought and includes cost/latency fields.
- [x] Authentic prompt/tool history is exported with limitations disclosed.
- [x] Implemented versus proposed work is clearly distinguished.
- [ ] A working LLM/tool/evidence/citation prototype exists.
- [ ] Focused runtime tests have executed.
- [ ] Benchmark metrics have been measured and calibrated.

The unchecked items are intentionally disclosed future work, not submission claims.
