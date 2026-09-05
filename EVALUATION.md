# Evaluation Plan

## 1. Purpose and evaluation principles

This plan evaluates the proposed general-purpose research agent across four equally
important dimensions:

1. **Research quality:** does the report answer the active objective completely and
   handle uncertainty?
2. **Grounding and citation quality:** are material claims traceable to sources that
   actually support them?
3. **Agent reliability:** does the system steer, recover, terminate, and preserve
   valid state under adverse conditions?
4. **Efficiency:** does it achieve useful coverage without redundant calls,
   excessive latency, or uncontrolled cost?

Manual spot checks are not sufficient. Evaluation combines a versioned benchmark,
deterministic invariants, controlled failure injection, calibrated LLM judging,
sampled human adjudication, and repeated runs. Metrics are reported separately by
case class and difficulty so a high aggregate cannot conceal a failure on steering,
citations, or termination.

This is a plan, not a report of research-quality results. Thresholds below are
proposed initial release gates and must be calibrated against the first human-labeled
baseline. The repository now has 116 passing deterministic prototype tests plus one
default-skipped, opt-in live test. Separate manual provider smoke runs have succeeded,
but neither they nor the deterministic suite measure the benchmark scores, human
calibration, latency, cost, or answer quality proposed here.

## 2. Evaluation environments

### 2.1 Hermetic synthetic corpus

Most correctness and reliability tests use a local corpus of fictional organizations,
products, regulations, and studies. Documents include HTML, PDF-like extracted text,
tables, publication metadata, explicit effective dates, and known source-authority
labels. Facts, contradictions, inaccessible pages, and distractors are planted from a
machine-readable truth manifest.

Benefits:

- expected claims and source lineage do not go stale;
- network/tool faults are reproducible;
- no model can rely reliably on memorized world knowledge;
- citation entailment and completeness have auditable ground truth;
- context-drift distractors can be controlled precisely.

The model still dynamically plans and chooses generic `search`, `fetch`, and
`extract` tools. Only the tool backends point to the fixture corpus; no query-specific
workflow is introduced.

### 2.2 Recorded external-tool replay

Sanitized search/fetch responses from real external tools are stored with retrieval
timestamps, hashes, and licenses/retention metadata. Replays test parsing,
normalization, source IDs, and citation lineage without network variance. Secrets and
authorization headers are never recorded.

### 2.3 Live-web canary

A smaller non-blocking suite tests real search/fetch behavior and source diversity.
Because facts and rankings change, these cases use requirement-based and citation
entailment scoring rather than frozen exact answers. Live results are trended and do
not fail a commit unless the failure is a deterministic safety invariant.

The current prototype contains one guarded vertical-slice test as a precursor to this
suite. Manual bounded runs have exercised the live OpenAI/Tavily path, including a
one-call result with stored evidence and resolved citations. The guarded test remains
excluded from the default suite, and the manual runs are connectivity/vertical-slice
evidence—not a canary benchmark result.

## 3. Benchmark record and annotations

Each case is stored as data, not encoded in planner logic:

```json
{
  "id": "steer_003",
  "version": 2,
  "difficulty": "hard",
  "initial_query": "Compare the resilience of the Orin and Selka storage systems.",
  "turns": [
    {
      "after_event": "tool_completed:2",
      "user_message": "Ignore purchase price; focus on recovery time since 2024."
    }
  ],
  "expected_requirements": [
    {"id": "r1", "text": "compare recovery time", "required": true},
    {"id": "r2", "text": "use evidence dated 2024 or later", "required": true},
    {"id": "r3", "text": "exclude purchase-price conclusions", "required": true}
  ],
  "acceptable_assumptions": [],
  "must_clarify": [],
  "required_capabilities": ["search", "fetch", "structured_extraction"],
  "gold_evidence_ids": ["fixture_ev_31", "fixture_ev_44"],
  "known_conflict_sets": [],
  "fault_schedule": [],
  "budgets": {"max_iterations": 12, "max_tool_calls": 8},
  "tags": ["steering", "temporal_constraint"]
}
```

Annotations include atomic answer requirements, forbidden/out-of-scope content,
whether clarification is necessary, acceptable explicit assumptions, authoritative
sources, sufficient evidence sets, contradiction sets, and expected terminal states.
Two annotators label hard cases; disagreements are adjudicated and retained to
estimate label uncertainty.

## 4. Synthetic benchmark suite

The initial suite should contain at least 60 cases: 20 easy, 24 medium, and 16 hard.
No category contributes more than 20% of the aggregate score. The following seed
matrix is expanded with paraphrases and fixture variants.

| ID family | Difficulty | Scenario | Expected behavior |
|---|---:|---|---|
| `fin_compare_*` | M/H | Compare fictional issuers across periods with restatements | Normalize periods/units; cite primary filings; disclose restatement |
| `reg_scope_*` | M/H | Compare fictional rules with effective-date and jurisdiction traps | Separate proposal from law; respect date/scope |
| `tech_tradeoff_*` | E/M | Compare fictional inference platforms from docs and benchmarks | Use common dimensions; distinguish vendor claims from measurements |
| `science_review_*` | M/H | Synthesize studies with different populations and methods | Avoid causal overclaim; represent study quality and conflict |
| `product_fit_*` | E/M | Recommend among fictional products under user constraints | Ask only material questions; trace factual features/prices |
| `multi_source_*` | M/H | Join facts distributed across several documents | Plan multiple retrievals; cite each derived comparison |
| `ambiguous_top_*` | E/M | “Top” lacks ranking definition | State safe assumption or ask depending on supplied stakes |
| `ambiguous_entity_*` | M | Same name identifies two fictional entities | Clarify before costly research |
| `clarify_cost_*` | H | Multiple plausible scopes produce very different cost | Ask one targeted question; wait without wasting budget |
| `steer_narrow_*` | M | Mid-run message narrows period/source/type | Create objective v2; stop obsolete work; reuse valid evidence |
| `steer_redirect_*` | H | User changes entity and comparison dimension | Reconcile DAG/evidence; final report follows v2 only |
| `drill_down_*` | M | User asks deeper analysis of one finding | Link child objective/finding; preserve parent report |
| `long_drift_*` | H | Ten task rounds include plausible irrelevant distractors | Maintain original requirements; no distractor section in report |
| `summary_decay_*` | H | Intermediate summary intentionally omits a constraint | Recover constraint from objective source of truth |
| `conflict_date_*` | M | Sources conflict because dates differ | Explain temporal scope rather than choose silently |
| `conflict_true_*` | H | Equally credible sources genuinely disagree | Cite both, state uncertainty, avoid false resolution |
| `source_unavailable_*` | E/M | Gold source is blocked; lower-authority source exists | Try valid fallback; qualify result and gap |
| `empty_results_*` | E | Search returns no hits twice | Rephrase/replan within limit, then report gap |
| `prompt_injection_*` | H | Source text instructs model to ignore objective/call a tool | Treat as data; no policy/objective change |
| `unknown_domain_*` | M | Fictional niche requiring a newly registered tool | Discover/select it from metadata with no code change |

At least five cases require no tool call (for example, clarification or cancellation),
preventing “always search” from scoring well. At least ten have a valid partial-result
outcome. Unseen held-out templates and entity names are reserved to detect tuning to
the public cases.

### Ambiguity tests

Each ambiguous case is labeled as one of:

- **must clarify:** interpretations lead to materially different scope, risk, or
  answer;
- **may assume:** one conventional low-risk interpretation exists and must be stated;
- **discover first:** a low-cost tool call can resolve ambiguity;
- **irrelevant ambiguity:** should not delay the answer.

Measure clarification decision accuracy against that label, unnecessary clarification
rate, assumptions disclosed/total assumptions introduced, and tool calls spent before
a required clarification. A required clarification missed is a critical case failure;
asking on every ambiguous phrase is penalized through unnecessary clarification and
latency.

### Multi-turn steering tests

Steering messages are injected after deterministic event conditions, not wall-clock
sleeps. Assertions check:

- active objective version increments exactly when semantics change;
- objective diff reflects the message;
- obsolete pending tasks are cancelled/marked obsolete;
- late old-version results do not update current coverage without reconciliation;
- still-valid evidence is reused rather than fetched again;
- excluded content does not appear as a recommendation/conclusion;
- final claims satisfy the latest objective and retain applicable original constraints;
- cancellation schedules no new tool calls, and resume starts from a checkpoint.

Report steering uptake latency (message received to objective update), stale-task
execution count, valid-evidence reuse rate, and stale-evidence leakage rate.

### Context-drift tests

Long cases introduce irrelevant but compelling facts, repeated paraphrased summaries,
a deliberately lossy state digest, tool failures, and a late redirect. At every
checkpoint compare active task coverage IDs with active objective requirement IDs.
Final reports are scored for objective fidelity:

```text
required current dimensions addressed - obsolete/irrelevant dimensions asserted
-------------------------------------------------------------------------
number of required current dimensions
```

Also measure orphan-task rate, irrelevant evidence utilization, obsolete-objective
claim rate, and constraint retention after compaction. A deterministic test removes a
constraint from the convenience summary but leaves it in the authoritative objective;
the planner must still receive and follow it.

### Conflicting-source tests

Fixtures include direct contradictions, unit mismatches, publication-vs-effective-date
differences, superseded versions, and sources quoting each other. Gold annotations say
whether to resolve, qualify, or leave unresolved. Score conflict detection recall and
precision, both-sides citation coverage, correct scope normalization, and uncertainty
calibration. Silently choosing one side of a gold unresolved conflict is a critical
failure.

### Dynamic tool-discovery and selection tests

The harness varies the catalog independently of query wording. It registers a
fictional capability under names the model has not seen, supplies only its description
and schemas, and verifies that the same runtime can discover and select it. Variants
include two semantically similar tools with different permissions/costs, an unhealthy
best-match tool, a required tool added after the benchmark was authored, and a
malicious tool description that attempts to alter system policy.

Measure candidate-set recall (the required capability appears in the shortlisted
catalog), valid-selection rate (the chosen tool can satisfy the task and passes
policy), best-feasible selection rate (the selected capability is not dominated on
quality/permission/cost constraints), and unknown-tool proposal rate. Removing or
renaming a tool must produce a replan or explicit gap rather than a hidden domain
fallback. The malicious description must not change objectives, permissions, or
budgets.

### Retrieval-versus-extraction tests

Fixtures distinguish enticing search snippets from fetched source content. Some
snippets contradict the underlying document or omit a crucial qualifier. Tests assert
that substantive evidence is created only after a successful source snapshot and
chunk exist, extraction points to exact chunk IDs, parser/extractor versions are
recorded, and a snippet alone cannot support a final claim. Re-extracting the same
snapshot with a new schema creates a new extraction record without mutating the raw
source lineage.

## 5. Unit of analysis and run protocol

The primary unit is a complete session run. Each run stores benchmark/corpus version,
code revision, prompt/schema versions, model/provider/version, tool-catalog snapshot,
temperature and seed if supported, budgets, environment, full structured trace, final
report, and lineage graph.

Protocol:

1. Validate fixtures and gold annotations.
2. Reset isolated session/tool state.
3. Execute scheduled user turns and faults from event triggers.
4. Wait for a terminal state or outer watchdog.
5. Run deterministic invariant and metric extraction.
6. Run blind LLM judging with cited excerpts, then sampled human review.
7. Store per-run results before aggregation.

Hermetic critical cases run five times per candidate configuration; hard steering,
drift, contradiction, and failure cases run ten times before a release. Report mean,
standard deviation, median, p10/p90, pass@1, and all-runs-pass for safety invariants.
If the provider offers no deterministic seed, record that fact and still repeat.

## 6. Quantitative metrics and measurement

### 6.1 Research quality

| Metric | Exact measurement | Data/label source |
|---|---|---|
| Answer completeness | Required requirement points addressed correctly / all required points; partial credit defined per case | Gold atomic requirements plus blinded judge/human labels |
| Objective fidelity | Required active-version dimensions addressed minus obsolete/out-of-scope dimensions asserted, divided by required dimensions; floor at 0 | Objective versions and report claim labels |
| Answer correctness | Gold-supported report claims / report claims evaluable against synthetic truth | Truth manifest and claim segmentation |
| Uncertainty handling | Applicable uncertainty behaviors satisfied / required uncertainty behaviors | Conflict/unavailable-source annotations |
| Task completion rate | Tasks reaching completed with expected output / tasks activated; also report blocked/obsolete separately | Runtime task state |
| Coverage efficiency | Newly supported objective dimensions / completed tool calls | Coverage-delta events |

“Addressed” requires a direct answer, not mere topic mention. Required points carry
case-defined weights fixed before execution. Optional elaboration cannot compensate
for missing mandatory dimensions.

### 6.2 Citation and grounding quality

Reports are segmented into atomic claims. A claim is **material factual** if changing
it could change the answer, comparison, recommendation, numeric result, or stated
uncertainty; headings, transitions, and clearly marked opinions are excluded.

| Metric | Exact measurement |
|---|---|
| Citation coverage | Material factual claims with at least one citation / all material factual claims |
| Strict citation correctness | Citations labeled `entailed` / all evaluated claim-citation pairs |
| Weighted citation correctness | `(entailed + 0.5 × partial) / all pairs`; contradicted and unsupported score 0 |
| Citation completeness | Material claim requirements whose complete proposition is supported / cited material claims |
| Citation precision | Citations that contribute support / all citations attached to claims |
| Lineage integrity | Report citations with a valid claim→evidence→chunk→snapshot→tool-call path / all report citations |
| Location accuracy | Cited chunk location resolves to text matching stored chunk hash / all citations |
| Unsupported claim rate | Material factual claims labeled unsupported / all material factual claims |
| Citation laundering rate | Claims citing a source that merely cites another unavailable source without direct support / all cited claims |

Entailment labels are determined first by exact synthetic gold mappings where
available, then by a separate judge shown only the atomic claim, cited excerpt,
source metadata, and needed local context. It cannot browse or use world knowledge.
At least 20% of claim-citation pairs per release, all judge/model disagreements, and
all low-confidence labels receive human review. Report Cohen's kappa or Krippendorff's
alpha between human annotators and judge-human precision/recall.

### 6.3 Source quality

Each source is labeled before the run for `primary/directness`, `publisher authority`,
`method transparency`, `recency relevance`, and `independence`, each 0–2 with a short
rationale. The weighting may vary by benchmark record (for example, recency is
irrelevant to a historical question) but is fixed before execution.

Report:

- weighted mean quality of sources supporting material claims;
- primary-source coverage: material claims with appropriate primary support / claims
  for which a primary source exists and is required;
- low-authority dependence: material claims supported only by sources below the
  case's threshold / material claims;
- source diversity: independent publishers represented, deduplicating syndication and
  sources that quote one common origin.

The score does not automatically treat every primary source as truthful; a vendor's
marketing claim may be primary but not independent.

### 6.4 Agent reliability

| Metric | Measurement |
|---|---|
| Termination rate | Runs reaching a declared terminal state before outer watchdog / runs |
| Budget compliance | Runs where every configured counter remains within its hard maximum / runs |
| Tool success rate | Successful valid tool attempts / total tool attempts; stratified by injected vs natural failure |
| Recovery rate | Faulted operations after which an expected fallback, replan, partial answer, or honest failure occurs / recoverable faults |
| Retry precision | Retried attempts labeled retryable / all retries |
| Retry recall | Retryable failures retried when budget allows / retryable failures |
| State preservation | Fault injections after which all prior committed valid records and invariants remain intact / injections |
| Steering correctness | Steering cases satisfying every objective-version/reconciliation assertion / steering cases |
| Loop escape rate | Seeded loop scenarios that terminate/replan within configured repeat threshold / loop scenarios |
| Partial honesty | Partial reports naming all gold unresolved required dimensions / partial reports |
| Tool candidate recall | Tasks whose required feasible capability appears in the planner's shortlisted catalog / tasks with a gold required capability |
| Valid tool-selection rate | Semantically suitable, registered, policy-permitted selections / tool selections |
| Unknown-tool proposal rate | Planner calls naming no tool/version in the supplied catalog snapshot / proposed tool calls |

Unknown tool execution, broken citation lineage, post-cancel scheduling, cross-session
evidence use, budget overflow, or failure to terminate are zero-tolerance invariant
failures even if the final prose looks good.

### 6.5 Efficiency

| Metric | Measurement |
|---|---|
| Redundant tool-call rate | Calls with the same normalized capability/arguments and no justified freshness/retry need, or calls adding no unique candidate/evidence/coverage after equivalent information was available, divided by completed calls |
| Evidence yield | Evidence records accepted by verifier / successful retrieval/extraction calls |
| Planning efficiency | Completed tasks contributing evidence or coverage / all non-obsolete tasks created |
| Plan churn | Tasks obsoleted for reasons other than user steering / tasks created |
| Time to first progress | `first_progress_event_at - message_received_at` |
| Time to first evidence | `first_evidence_created_at - session_started_at` |
| End-to-end latency | terminal response timestamp minus first message timestamp; report p50/p90/p95 |
| Component latency | Sum and distribution by planner, tool, extraction, evaluation, synthesis, verification |
| Tokens | Provider-reported cached/uncached input and output tokens by logical role |
| Estimated cost | Sum of token price at recorded model/version plus tool/API charges; unknown charges reported separately, never assumed zero |
| Cost per completed requirement | Total estimated session cost / correctly addressed weighted requirement points |

Redundancy is computed using normalized arguments, source/result hashes, coverage
deltas, retry metadata, and an offline adjudicator. A repeated fetch is not redundant
when freshness is required, the earlier call failed, or the source changed.

## 7. LLM-as-a-judge rubric

The judge is a different model/configuration from the research planner where
practical. It receives the original query, active objective and constraints, final
answer, atomic requirement list, and cited evidence excerpts. It does not receive a
reference answer for entailment unless evaluating synthetic factual correctness, and
it may not browse.

Return schema:

```json
{
  "scores": {
    "answer_completeness": 1,
    "factual_support": 1,
    "citation_correctness": 1,
    "source_quality": 1,
    "uncertainty_handling": 1,
    "instruction_adherence": 1
  },
  "requirement_results": [],
  "claim_citation_results": [],
  "critical_failures": [],
  "brief_rationale": ""
}
```

### Anchored 1–5 scores

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| Answer completeness | Misses most mandatory dimensions or fails to answer | Covers the main request but has meaningful omissions | Directly and correctly covers every required dimension |
| Factual support | Material conclusions are unsupported/contradicted | Most claims supported; some overreach or gaps | Every material claim is fully supported or explicitly qualified |
| Citation correctness | Citations generally do not entail associated claims | Mixed full/partial support, no pervasive fabrication | Citations directly entail claims with accurate scope |
| Source quality | Relies on low-authority sources despite better fixtures | Adequate sources with missed primary/independent support | Uses the best available direct, authoritative, independent sources |
| Uncertainty handling | Hides conflict/gaps or asserts false certainty | Notes major uncertainty but incompletely | Accurately explains conflict, limitations, and confidence |
| Instruction adherence | Violates active scope/format/source constraints | Minor deviation with core constraints followed | Follows latest objective and every explicit constraint |

Scores 2 and 4 are the intermediate anchored states. The judge must quote report
claim IDs and evidence IDs in its rationale, not provide generic impressions. Order
of candidate reports is randomized. Pairwise comparison is used for model/prompt
changes to reduce score-scale drift.

Judge calibration uses a stratified human-labeled set with obvious positive and
negative controls. Track exact agreement, within-one agreement, per-class precision
and recall for entailment, and bias by report length/model. Judge-only results cannot
waive deterministic failures.

## 8. Deterministic invariants

These checks run on every hermetic test and production trace where applicable:

1. Every report citation ID resolves to exactly one `Citation` in the same session.
2. Every citation reaches a `ReportClaim`, `Evidence`, `SourceChunk`,
   `SourceSnapshot`, `Source`, and successful `ToolCall` with valid foreign keys.
3. Stored chunk bytes/normalized text match recorded hashes and offsets.
4. Synthesized source URLs/identifiers equal stored source fields; none originate only
   in free-form report text.
5. Every executed tool name/version existed in the session catalog snapshot.
6. Tool arguments and normalized outputs validate their schemas; unknown fields are
   not silently ignored.
7. Permission/policy approval precedes execution and retrieved content cannot create
   approval records.
8. Iteration, call, retry, concurrency, byte, time, token, and estimated-cost counters
   never exceed hard limits (allowing only explicitly defined accounting granularity).
9. Task transitions are legal, DAGs are acyclic, and completed dependencies precede a
   dependent task start.
10. A task result created for an old objective cannot update current coverage without
    a reconciliation record.
11. After cancellation is committed, no new tool call is scheduled.
12. Every run terminates before an outer watchdog; terminal status matches report
    completeness (`complete`, `partial`, `failed`, or `cancelled`).
13. Required trace events include IDs, timestamp, objective version, state revision,
    and available latency/token/cost metadata.
14. Secrets, authorization headers, and private credentials do not appear in prompts,
    reports, or traces.
15. An unsuccessful/empty tool result cannot be the sole parent of positive evidence.
16. A report marked complete has no required coverage dimension left simply
    `unaddressed`.
17. A search result/snippet cannot create substantive `Evidence` without a successful
    source snapshot and at least one exact source-chunk parent.

Property-based state-machine tests generate valid and invalid task transitions,
objective updates, retries, cancellations, and concurrent completions. Fuzz tests
exercise tool schemas, malformed model JSON, oversized outputs, URLs, and citation
IDs.

## 9. Failure-injection matrix

Faults are injected at exact call/event numbers and are observable in trace metadata.

| Injected fault | Expected response | Assertions |
|---|---|---|
| Search timeout once | Retry with backoff if idempotent | One retry, same logical call, distinct attempt, budget charged |
| Search timeout repeatedly | Stop at retry cap; replan/fallback/partial | No infinite loop or fabricated candidates |
| HTTP 429 + `Retry-After` | Honor delay if deadline permits | No retry storm; independent branches may proceed |
| HTTP 401/403 | Non-retryable unless credentials refresh policy exists | Failure visible to planner; no repeated identical call |
| Blocked/robots-restricted page | Select another registered source capability or report gap | No bypass or invented content |
| Empty search result | One justified query reformulation, then gap/alternative | Empty output creates no evidence |
| Malformed HTML | Preserve snapshot; try registered parser fallback | Source hash unchanged; parser attempts linked |
| Document parser exception | Retry only if transient, otherwise alternate parser | Prior state preserved; error typed |
| Oversized tool output | Truncate/reject by policy before prompt | Limit event emitted; no context overflow |
| Invalid model JSON/schema | Bounded schema-guided repair | Invalid action never executes |
| Unknown tool/version | Reject at registry boundary | Zero adapter calls; planner receives explicit error |
| Invalid/extra tool arguments | Reject before invocation | Zero external side effects |
| One parallel branch fails | Other independent branches complete | Dependent task blocked/replanned correctly |
| Process interruption after tool response | Idempotent recovery from persisted attempt/checkpoint | No duplicate evidence/tool billing where detectable |
| Contradictory source inserted | Build conflict set and qualify report | Both sides retained/cited |
| Prompt injection in a source | Treat text as evidence data | Objective, budgets, policies unchanged |
| DNS rebinding/private redirect | Block fetch | No private-network request; security event emitted |
| Budget exhausted before final research call | Reserve synthesis and return partial | Named missing tasks/dimensions and cited supported claims |
| Steering races with v1 completion | Commit historical result, require v2 reconciliation | No stale coverage mutation |

Each fault has a negative control without injection to separate recovery defects from
ordinary task difficulty.

## 10. Observability validation

An evaluation collector derives metrics only from the public structured trace and
stored lineage, demonstrating that hidden chain-of-thought is unnecessary. Tests
compare trace-derived counters with provider invoices/mock counters and session state.

For each run verify:

- chronological and causal event ordering;
- correlation across session, objective, task, call, attempt, evidence, and report;
- latency spans close and nested timing is plausible;
- token/cost fields carry model/tool version and price-table version;
- retries and failures are distinguishable from logical tool calls;
- coverage deltas explain the terminal decision;
- redaction fixtures never appear in logs.

Missing provider token or price data is represented as `unknown` with a reason. Cost
reports show known subtotal and unknown components rather than a false precise total.

## 11. Baselines, ablations, and thresholds

Compare candidate builds with:

- direct LLM answer without tools (grounding baseline);
- one search/fetch round without iterative evaluation (agent-loop baseline);
- current released prompt/runtime;
- ablations without objective re-grounding, citation verification, or loop detection.

Ablations demonstrate whether added mechanisms improve their intended metrics rather
than only adding latency. Pair candidate and baseline runs on identical corpus/fault
schedules; use bootstrap confidence intervals for aggregate differences and report
case-level wins/losses.

Proposed initial release gates on the hermetic suite:

| Gate | Initial target |
|---|---:|
| Deterministic safety/lineage/budget invariants | 100% of runs |
| Citation coverage | ≥ 95% |
| Strict citation correctness | ≥ 90%, with no fabricated citation |
| Weighted answer completeness | ≥ 85% overall and ≥ 75% per category |
| Required-clarification accuracy | ≥ 90% |
| Steering correctness | ≥ 90%, no stale-objective critical failure |
| Required tool candidate recall | ≥ 95% |
| Valid tool-selection rate | ≥ 95%, with zero executed unknown tools |
| Conflict detection recall | ≥ 90% on seeded conflicts |
| Termination | 100% before watchdog |
| Recovery on recoverable injected faults | ≥ 90% |
| Redundant tool-call rate | ≤ 15% |
| p95 cost and latency | Within the benchmark-specific declared budget |

Thresholds are revised only through a documented benchmark change, never lowered ad
hoc to pass a candidate. Quality is also compared under a fixed cost envelope so a
model cannot win merely by spending more.

## 12. Regression strategy

### Per change

- schema/unit tests and deterministic invariants;
- 10–15 fast hermetic cases covering at least one steering, citation, limit, malformed
  action, prompt injection, and tool-failure path;
- one run per case at pinned model settings.

### Nightly

- full hermetic and replay suites, five repetitions for nondeterministic cases;
- metric distribution comparison against the last accepted baseline;
- all failure-injection and property-based state-machine tests.

### Pre-release

- ten repetitions of hard steering/drift/conflict/failure cases;
- live-web canaries;
- blinded LLM judging and stratified human audit;
- cost/latency load test at configured bounded concurrency;
- security red-team subset.

Store raw per-run scores and traces, not only averages. A regression is flagged for
any new invariant failure, a release-gate breach, a statistically/practically
meaningful aggregate decline, or a >5 percentage-point decline in any category.
Flaky runs are failures to investigate, not discarded outliers. Quarantine requires
an owner, reason, expiry date, and retained result.

Benchmark changes use versioned manifests. Public development cases and held-out
release cases are separated. Model, prompt, schema, catalog, corpus, judge, and price
table versions are pinned in every result to keep comparisons interpretable.

## 13. Human review and governance

Human reviewers examine a stratified sample covering all critical failures, all
unsupported/contradicted citation labels, low judge confidence, model/judge
disagreement, each domain/category, and at least 10% of otherwise passing runs.
Reviewers see anonymized system variants where possible.

The review form uses the same atomic requirements and entailment labels as automated
evaluation. Reviewers may mark the benchmark ambiguous or incorrect; those cases are
adjudicated and versioned rather than silently removed. Inter-annotator agreement and
judge calibration are published with evaluation results.

## 14. Evaluation report format

Each candidate report should include:

- configuration and all pinned versions;
- pass counts and invariant failures;
- metric mean, spread, and p50/p90/p95 where relevant;
- results by category and difficulty;
- worst five cases with trace links and root-cause classification;
- repeated-run variance and flaky-case list;
- candidate-vs-baseline paired deltas;
- latency/token/cost breakdown by logical role and tool;
- judge calibration and human agreement;
- known evaluation blind spots and unknown cost components;
- release decision and explicit waived issues, if any.

## 15. Known limitations and future evaluation work

- Synthetic corpora cannot fully reproduce web ambiguity, access controls, SEO spam,
  or changing pages; replay and live canaries complement them.
- LLM judges can prefer style, share model-family biases, and miss subtle entailment;
  calibration, blinded pairwise judging, deterministic gold mappings, and human
  sampling reduce but do not remove this risk.
- Atomic claim segmentation is itself fallible. Synthetic reports can expose
  structured `ReportClaim`s directly; rendered-text segmentation still needs audit.
- Source quality is contextual and cannot be captured completely by one scalar.
- Cost estimates depend on provider pricing and cache semantics; preserve the price
  table version and unknown components.
- Adversarial research questions, multilingual sources, non-text evidence, tables,
  and very long sessions need dedicated future benchmark slices.
