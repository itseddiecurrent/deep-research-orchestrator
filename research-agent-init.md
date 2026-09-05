# General-Purpose LLM Research Agent — Project Initialization

## 1. Project Goal

Build a **general-purpose, LLM-powered research agent** that accepts natural-language research questions, decomposes them into sub-tasks, dynamically selects and calls tools, gathers evidence, iterates until sufficient information is available, and produces a **cited final report**.

Example user queries:

- "Compare the quarterly earnings of the top 5 semiconductor firms and highlight 3 supply-chain risks from their transcripts."
- "What are the regulatory risks for AI companies in the EU vs. the US?"
- "Compare the competitive positioning of three cloud providers for AI inference workloads."
- "Summarize the major arguments for and against a proposed regulation using primary sources."

The system must be **generic**. It must not contain hardcoded workflows for specific domains such as finance, regulation, semiconductors, or one particular API.

The LLM should drive:

- task decomposition
- planning
- tool selection
- iterative research
- synthesis

The application/runtime should drive:

- state management
- tool execution
- validation
- permissions
- retries
- budgets
- observability
- provenance/citations

---

# 2. Core Principle

Do **not** build this as a deterministic pipeline such as:

```text
query
  -> call one fixed API
  -> scrape one fixed site
  -> summarize
```

Instead, build an agent loop:

```text
USER QUERY
    |
    v
UNDERSTAND / PLAN
    |
    v
SELECT NEXT ACTION
    |
    v
CALL TOOL
    |
    v
OBSERVE RESULT
    |
    v
UPDATE RESEARCH STATE
    |
    v
EVALUATE: ENOUGH INFORMATION?
   / \
 no   yes
 |     |
 +-----+--> SYNTHESIZE
              |
              v
           VERIFY
              |
              v
       FINAL CITED REPORT
```

The workflow should be generated dynamically at runtime based on the user's goal.

---

# 3. High-Level Architecture

```text
                         User
                          |
                          v
                 +------------------+
                 | Conversation API |
                 +---------+--------+
                           |
                           v
                 +------------------+
                 |   Agent Runtime  |
                 |------------------|
                 | session state    |
                 | budgets          |
                 | retries          |
                 | tool execution   |
                 | observability    |
                 +---------+--------+
                           |
                           v
                 +------------------+
                 |   Planner LLM    |
                 |------------------|
                 | understand goal  |
                 | decompose task   |
                 | choose action    |
                 +---------+--------+
                           |
                           v
                 +------------------+
                 | Task Queue / DAG |
                 |     Executor     |
                 +---------+--------+
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   +-------------+   +-------------+   +-------------+
   | Web Search  |   | Documents   |   | Extraction  |
   | MCP / Tool  |   | MCP / Tool  |   | / Data Tool |
   +------+------+   +------+------+   +------+------+
          |                 |                 |
          +-----------------+-----------------+
                            |
                            v
                   +------------------+
                   |  Evidence Store  |
                   |------------------|
                   | claims           |
                   | source metadata  |
                   | extracted facts  |
                   | citations        |
                   | confidence       |
                   +---------+--------+
                             |
                             v
                   +------------------+
                   |    Evaluator     |
                   | enough evidence? |
                   +-------+----------+
                           |
                     no    |    yes
                     |     |     |
                     +-----+     v
                           |  +-------------+
                           |  | Synthesizer |
                           |  +------+------+
                           |         |
                           |         v
                           |  +-------------+
                           +->|  Verifier   |
                              +------+------+
                                     |
                                     v
                              Final cited report
```

---

# 4. Main Components

## 4.1 Conversation API

Responsibilities:

- accept natural-language user input
- create/reuse a research session
- stream progress events
- stream the final answer
- expose session status

Possible endpoints:

```text
POST /sessions
POST /sessions/{id}/messages
GET  /sessions/{id}
GET  /sessions/{id}/events
```

Do not over-design the API initially.

---

## 4.2 Agent Runtime

The runtime is the deterministic control layer.

Responsibilities:

- maintain session state
- invoke the planner/model
- execute validated tool calls
- enforce tool-call limits
- enforce token/time/cost budgets
- handle retries/timeouts
- persist intermediate results
- detect terminal states
- emit trace events

Conceptual loop:

```python
while not session.done:
    action = planner.next_action(session_state)

    validate(action)

    if action.type == "tool_call":
        result = tool_registry.execute(action)
        session_state.add_observation(result)

    elif action.type == "finish":
        session.done = True
```

The exact implementation may differ.

---

## 4.3 Planner / Orchestrator LLM

The planner receives:

- original user request
- conversation context
- available tool definitions
- current research plan
- completed tasks
- current evidence
- unresolved questions
- remaining budget

It should return structured output.

Example:

```json
{
  "reasoning_summary": "We need primary sources for the regulatory comparison.",
  "action": "tool_call",
  "tool": "search_web",
  "arguments": {
    "query": "EU AI Act official obligations general purpose AI"
  }
}
```

Or:

```json
{
  "action": "create_tasks",
  "tasks": [
    {
      "id": "task_1",
      "description": "Identify authoritative EU regulatory sources",
      "depends_on": []
    },
    {
      "id": "task_2",
      "description": "Identify authoritative US regulatory sources",
      "depends_on": []
    },
    {
      "id": "task_3",
      "description": "Compare obligations and risk categories",
      "depends_on": ["task_1", "task_2"]
    }
  ]
}
```

Use structured output / JSON Schema / Pydantic validation.

Do not rely on free-form model output where the runtime expects machine-readable actions.

---

# 5. Tool System

Tools should represent **generic capabilities**, not domain-specific workflows.

Initial tool interfaces could include:

```text
search_web(query, filters?)
fetch_url(url)
search_documents(query, filters?)
read_document(document_id)
extract_structured_data(content, schema)
```

Optional later tools:

```text
browser_navigate(...)
query_database(...)
execute_python(...)
search_arxiv(...)
search_sec(...)
search_github(...)
```

The planner should discover/select tools based on their descriptions and schemas.

Tool implementations may use:

- MCP servers
- function/tool calling APIs
- internal service adapters

Keep the planner decoupled from implementation details.

---

# 6. Tool Registry

Create a central registry abstraction.

Example:

```python
class Tool:
    name: str
    description: str
    input_schema: dict

    async def execute(self, arguments: dict):
        ...
```

```python
class ToolRegistry:
    def register(self, tool: Tool):
        ...

    def get_tool_descriptions(self):
        ...

    async def execute(self, name: str, arguments: dict):
        ...
```

The registry should support adding new tools without modifying planner logic.

---

# 7. Research Plan and Task Model

Represent research work explicitly.

Suggested model:

```text
ResearchTask
- id
- description
- status
- dependencies
- assigned_tool
- attempts
- result_summary
- created_at
- completed_at
```

Possible statuses:

```text
PENDING
READY
RUNNING
COMPLETED
FAILED
BLOCKED
```

Support a task DAG so independent branches may later execute in parallel.

Example:

```text
                  identify entities
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
       source A      source B      source C
          |             |             |
          +-------------+-------------+
                        |
                        v
                    compare
```

Do not require every query to create a large DAG. Small requests may use a simple iterative loop.

---

# 8. Evidence Model

Evidence must be first-class structured data.

Do not store only prose summaries.

Suggested schema:

```text
Evidence
- id
- claim
- source_url
- source_title
- source_type
- retrieved_at
- excerpt
- document_location
- tool_name
- task_id
- confidence
- metadata
```

Example:

```json
{
  "claim": "Advanced packaging capacity was identified as a supply constraint.",
  "source_url": "https://example.com/transcript",
  "source_title": "Company Q2 Earnings Call",
  "source_type": "earnings_transcript",
  "retrieved_at": "2026-09-05T00:00:00Z",
  "excerpt": "...",
  "document_location": "Supply Chain section",
  "task_id": "task_17",
  "confidence": 0.91
}
```

Important rule:

> Attach provenance/citation metadata when evidence is created, not after the report is already written.

---

# 9. Retrieval vs. Extraction

Keep these separate.

Typical flow:

```text
search
  |
  v
candidate source
  |
  v
fetch / parse
  |
  v
chunk / retrieve relevant sections
  |
  v
extract structured facts
  |
  v
evidence store
```

Avoid sending entire large documents into the LLM unless necessary.

Structured extraction should be schema-driven.

Example:

```json
{
  "revenue": {
    "value": 30.0,
    "unit": "USD billion",
    "evidence_id": "evidence_102"
  },
  "eps": {
    "value": 0.68,
    "evidence_id": "evidence_104"
  }
}
```

---

# 10. Evaluator / Research Completion

The agent must decide whether more research is necessary.

After one or more actions, evaluate:

```text
- What parts of the request are already answered?
- What remains unresolved?
- Which claims lack adequate evidence?
- Are important sources contradictory?
- Should another tool call be made?
- Is the marginal value of more research worth the cost?
```

Structured result example:

```json
{
  "status": "continue",
  "unresolved": [
    "Need authoritative US primary source",
    "One numerical claim has only a secondary source"
  ],
  "recommended_next_tasks": [
    "Search official US government guidance"
  ]
}
```

Terminal result:

```json
{
  "status": "complete",
  "reason": "All required comparison dimensions have at least one supporting source."
}
```

The LLM may decide research sufficiency, but the runtime must enforce hard limits.

---

# 11. Runtime Limits

Implement configurable safeguards:

```text
MAX_TOOL_CALLS
MAX_ITERATIONS
MAX_PARALLEL_TASKS
MAX_TOKENS
MAX_RESEARCH_TIME
MAX_RETRIES_PER_TOOL
MAX_COST
```

When limits are reached, the system should produce the best report possible and disclose unresolved gaps.

Never allow an unbounded research loop.

---

# 12. Synthesis

The synthesizer receives:

- original user question
- completed research plan
- structured findings
- evidence objects
- unresolved limitations

It produces a report that:

- directly answers the question
- organizes findings clearly
- distinguishes facts from interpretation
- cites material claims
- notes missing or conflicting evidence
- avoids unsupported conclusions

The synthesizer should not perform major new research.

---

# 13. Verification

Before returning the final report, run a verification pass.

Verifier responsibilities:

- check whether cited sources actually support the associated claims
- check numerical consistency
- detect unsupported statements
- detect contradictions between findings
- flag overly strong language
- identify citation gaps

Conceptual pipeline:

```text
Research
   |
   v
Draft
   |
   v
Verify
   |
   v
Revise
   |
   v
Final
```

Do not claim perfect hallucination prevention.

Treat model output as untrusted until validated.

---

# 14. Source Quality

Prefer higher-authority evidence when possible.

General ranking:

```text
Primary / official source
    >
High-quality reputable secondary source
    >
Industry analysis / specialist publication
    >
General blog / aggregator
```

The planner may use lower-quality sources for discovery but should try to support important conclusions with primary or authoritative sources.

---

# 15. Parallel Execution

Independent research tasks should eventually support concurrency.

Example:

```text
          compare companies
                 |
      +----------+----------+
      |          |          |
      v          v          v
   company A  company B  company C
      |          |          |
      +----------+----------+
                 |
                 v
             synthesis
```

Use bounded concurrency.

Do not introduce distributed complexity in the first version unless needed.

---

# 16. Memory and Persistence

Separate:

## Short-term session state

Required.

Store:

- user query
- conversation
- research plan
- tasks
- tool calls
- observations
- evidence
- report status

## Long-term memory

Optional / later.

Possible uses:

- user preferences
- organization-specific sources
- prior reports
- recurring research context

Do not make long-term memory necessary for MVP.

---

# 17. Observability

Every run should be traceable.

Record events such as:

```text
planner_called
task_created
tool_called
tool_succeeded
tool_failed
evidence_created
evaluation_completed
report_generated
verification_failed
verification_passed
```

Capture:

- latency
- token usage
- tool-call count
- errors
- retries
- total cost
- task completion rate

Provide a human-readable trace in development.

---

# 18. Error Handling

Handle:

- malformed LLM structured output
- unavailable tools
- HTTP failures
- parsing failures
- timeouts
- source access restrictions
- empty retrieval results
- contradictory evidence
- rate limits
- tool schema errors

Expected behavior:

```text
error
  |
  v
classify retryable?
  |
  +-- yes --> bounded retry
  |
  +-- no ---> report to planner / mark task failed
```

Do not silently hide tool failures from the planner.

---

# 19. Security / Tool Safety

The model must never directly execute arbitrary external actions.

Flow:

```text
LLM proposes tool call
        |
        v
schema validation
        |
        v
permission / policy check
        |
        v
runtime executes tool
```

Validate:

- tool exists
- arguments match schema
- URL/domain rules if configured
- timeout/cost limits
- tool permissions

Potentially dangerous tools such as shell/code/database writes should have stricter policies.

---

# 20. Suggested Initial Tech Shape

Keep the initial implementation simple.

Possible backend:

```text
Python
FastAPI
Pydantic
asyncio
Postgres or SQLite for state
LLM provider abstraction
MCP / function-calling tool adapters
```

Possible module layout:

```text
app/
  api/
    routes.py

  agent/
    runtime.py
    planner.py
    evaluator.py
    synthesizer.py
    verifier.py

  tools/
    base.py
    registry.py
    web_search.py
    web_fetch.py
    document_search.py
    extraction.py

  models/
    session.py
    task.py
    evidence.py
    tool_call.py

  storage/
    session_store.py
    evidence_store.py

  llm/
    client.py
    schemas.py
    prompts.py

  observability/
    tracing.py

tests/
```

This is a suggestion, not a hard requirement. Adjust if repository conventions suggest something better.

---

# 21. MVP Scope

The first working version should demonstrate the **agent architecture**, not maximum tool coverage.

MVP should support:

1. natural-language research query
2. LLM-generated research plan
3. dynamic tool selection
4. at least:
   - web search
   - page/document retrieval
   - structured extraction
5. iterative planner -> tool -> observation loop
6. evidence/provenance tracking
7. research completion evaluation
8. cited report synthesis
9. bounded execution
10. trace/debug output

A successful MVP should be able to answer two meaningfully different open-ended research questions **without changing application code**.

---

# 22. Non-Goals for MVP

Do not initially build:

- a finance-specific research pipeline
- a regulation-specific pipeline
- hardcoded company lists
- hardcoded APIs for one example
- complex multi-agent hierarchies
- autonomous shell access
- advanced browser automation unless required
- distributed queues
- elaborate long-term memory
- production billing system
- dozens of MCP integrations

Focus on the generic orchestration architecture.

---

# 23. Multi-Agent Design

Do not create many independent agents just for the sake of calling the system "multi-agent."

Start with logical roles:

```text
Planner
Executor
Evaluator
Synthesizer
Verifier
```

These may use the same underlying LLM with different prompts.

A future multi-agent implementation may introduce specialized workers when useful for:

- parallel research
- context isolation
- specialization
- fault isolation

The shared abstraction should remain:

```text
tasks + tools + evidence + state
```

---

# 24. Important Design Constraint

Avoid architecture like:

```python
if query_is_finance:
    run_finance_pipeline()

elif query_is_regulation:
    run_regulation_pipeline()
```

This violates the project goal.

The preferred pattern is conceptually:

```text
Here is the user's research goal.

Here are the tools available to you.

Here is the research already completed.

Here is the remaining budget.

Decide what action should happen next.
```

The LLM creates the workflow dynamically.

---

# 25. Development Phases

## Phase 1 — Foundation

Build:

- FastAPI service
- session model
- task model
- evidence model
- tool interface
- tool registry
- LLM client abstraction
- structured action schema

Add tests for schemas and tool registration.

---

## Phase 2 — Minimal Agent Loop

Implement:

```text
user query
  ->
planner
  ->
tool call
  ->
observation
  ->
planner
  ->
finish
```

Initially use mock tools where helpful.

Make the execution trace visible.

---

## Phase 3 — Real Research Tools

Add generic tools:

- web search
- URL fetch
- document text extraction
- structured information extraction

Normalize outputs into common result objects.

---

## Phase 4 — Evidence / Citation System

Implement:

- provenance
- evidence IDs
- source metadata
- claim/evidence relationships

Ensure synthesis receives evidence IDs rather than anonymous text blobs.

---

## Phase 5 — Planning / Task DAG

Support:

- generated sub-tasks
- dependencies
- task lifecycle
- bounded parallel execution

Avoid premature distributed infrastructure.

---

## Phase 6 — Evaluation Loop

Implement research sufficiency checks.

Agent should be capable of saying:

```text
I still need source X
```

and performing another research round automatically.

---

## Phase 7 — Synthesis + Verification

Add:

- cited report generation
- claim/citation verification
- revision pass

Produce human-readable reports.

---

## Phase 8 — Robustness

Add:

- retries
- timeouts
- malformed-output recovery
- cost/token/tool-call limits
- logging
- tracing
- failure-state handling

---

# 26. Testing Strategy

Tests should cover architecture, not one fixed query.

Unit tests:

```text
tool registry
schema validation
task transitions
evidence serialization
budget enforcement
retry logic
citation mapping
```

Agent tests with mocked LLM/tool responses:

```text
planner chooses correct registered tool
planner can perform multiple iterations
planner reacts to failed tool
runtime stops at limits
agent synthesizes after sufficient evidence
```

Integration tests:

Use several unrelated research queries.

Example categories:

```text
financial comparison
regulatory comparison
technology comparison
scientific literature research
company/product research
```

The same code path should handle all of them.

---

# 27. Evaluation Criteria

Track at minimum:

```text
answer completeness
citation coverage
citation correctness
tool-call success rate
research iterations
latency
token usage
cost
```

Useful future quality metrics:

- claim-level citation precision
- source authority
- answer factuality
- task completion rate
- redundant tool-call rate

---

# 28. Codex Working Instructions

When working on this repository:

1. Read this file before implementing major changes.
2. Inspect existing repository state before modifying anything.
3. Prefer small, coherent changes over large rewrites.
4. Keep the architecture generic.
5. Do not add domain-specific hardcoded workflows to make demos pass.
6. Use structured model outputs whenever application logic depends on LLM output.
7. Treat LLM output as untrusted input and validate it.
8. Preserve source provenance throughout the research pipeline.
9. Add tests for meaningful behavior.
10. Run relevant tests after changes.
11. Do not claim a milestone is complete until it is implemented and verified.
12. If implementation choices differ from this document, prefer the simpler design when it still satisfies the architecture.
13. Keep dependencies minimal.
14. Avoid premature distributed-system complexity.
15. Before large changes, briefly inspect the current design and continue from the existing architecture rather than starting over.

---

# 29. Original Prototype Milestone (Superseded by Section 46)

Begin by inspecting the repository.

If the repository is empty or contains only minimal scaffolding:

1. create the backend project structure
2. create the core domain models:
   - ResearchSession
   - ResearchTask
   - Evidence
   - ToolCall / AgentAction
3. implement:
   - base Tool abstraction
   - ToolRegistry
   - LLM client interface
   - structured planner action schemas
4. create a minimal AgentRuntime capable of:
   - accepting a user query
   - calling a planner abstraction
   - executing a registered mock tool
   - feeding the observation back to the planner
   - terminating on a structured finish action
5. add tests for the core loop
6. add a small README section explaining how to run the service/tests

Do not build all production tools immediately.

The first milestone is:

> A clean, generic, testable agent runtime where an LLM can dynamically choose among registered tools and iterate based on observations.

Once that is working and verified, continue to real research tools and evidence/citation handling.

---

# 30. Definition of Success

The architecture is successful when a user can submit an open-ended question the developers did not explicitly anticipate, and the system can:

```text
understand the goal
      |
      v
create research tasks
      |
      v
select appropriate tools dynamically
      |
      v
collect and structure evidence
      |
      v
identify missing information
      |
      v
perform additional research
      |
      v
synthesize findings
      |
      v
verify major claims
      |
      v
return a cited report
```

without adding a new hardcoded workflow for that query type.


---

# 31. Submission Requirements and Priority

This project is an evaluation of **system design judgment**, not primarily a coding-volume exercise.

The required deliverables are:

1. **Prompt History / Conversation Logs**
2. **Design Document**
3. **Evaluation Plan**

A working prototype is **nice to have**, not required.

Therefore, prioritize work in this order:

```text
Design clarity
    >
Evaluation depth
    >
Prompt/conversation history quality
    >
Minimal architecture prototype
    >
Additional implementation
```

Do not spend the entire time budget building features while leaving the design document or evaluation plan incomplete.

The final repository should make it easy for a reviewer to understand:

- how the reasoning loop works
- how the user can steer research
- how tools are discovered and invoked
- how grounding and citations work
- how context drift is prevented
- how failures are handled
- how the system is evaluated
- how cost, latency, and reliability are observed
- which assumptions were made
- which parts are implemented versus proposed

---

# 32. Required Design Question 01 — User Interaction and Mid-Research Steering

The system must support **multi-turn research**, not just:

```text
question -> long autonomous run -> final answer
```

A research session should remain interactive.

The user should be able to:

- refine the original question
- add constraints
- change scope
- redirect the research
- ask for deeper investigation into one finding
- exclude a source or topic
- request a different comparison dimension
- ask for clarification about intermediate findings
- stop/cancel the run
- continue from an existing report

Example:

```text
User:
Compare regulatory risks for AI companies in the EU and US.

Agent:
[researches and returns findings]

User:
Focus specifically on foundation-model providers.

Agent:
updates the research objective
reuses still-relevant evidence
invalidates irrelevant tasks
creates new tasks
continues research
```

Another example:

```text
User:
Compare the top semiconductor companies.

Agent:
begins research

User:
Actually, rank "top" by market capitalization and only use the latest reported quarter.

Agent:
updates constraints and replans.
```

## Interaction architecture

Represent the user's intent explicitly:

```text
ResearchObjective
- original_query
- current_goal
- constraints
- requested_output
- scope
- clarification_history
- version
```

Do not treat conversation history itself as the sole representation of intent.

When the user changes the goal:

```text
new user message
      |
      v
Intent / Goal Update
      |
      v
increment objective version
      |
      v
Reconciliation
      |
      +--> keep still-valid evidence
      |
      +--> invalidate obsolete tasks
      |
      +--> cancel unnecessary pending work
      |
      +--> create new tasks
      |
      v
continue agent loop
```

Evidence should not automatically be deleted when the user redirects. Instead, mark whether it is relevant to the current objective version.

For an MVP, it is acceptable to process steering messages between tool calls rather than interrupt an in-flight HTTP request.

## Clarifying questions

The LLM may ask the user a clarifying question when ambiguity would materially change the research.

However, avoid unnecessary clarification.

The planner may make a reasonable assumption when:

- the ambiguity has a conventional interpretation
- research can proceed safely
- the assumption can be stated explicitly

Example:

```text
"top 5 semiconductor firms"
```

Possible behavior:

```text
Assumption:
Interpret "top" as market capitalization as of the research date.

The agent records this assumption and proceeds.
```

If several interpretations would produce fundamentally different reports, the agent may ask the user.

---

# 33. Required Design Question 02 — LLM Planning and Dynamic Tool Selection

The LLM must perform task decomposition and tool selection.

The application must **not** encode domain workflows such as:

```python
if "earnings" in query:
    use_finance_pipeline()

if "regulation" in query:
    use_legal_pipeline()
```

Instead, the runtime supplies the model with:

```text
current research objective
current plan
available tools + schemas + descriptions
existing evidence
completed/failed tasks
remaining budget
```

The LLM decides:

```text
what needs to be learned
what can be done in parallel
what depends on previous results
which capability is appropriate
whether more research is needed
```

## Dynamic tool registration

Each tool exposes structured metadata:

```text
ToolDefinition
- name
- description
- input_schema
- output_schema
- capabilities/tags
- permissions
- cost metadata (optional)
- timeout metadata (optional)
```

Example:

```json
{
  "name": "search_web",
  "description": "Search the public web for sources relevant to a natural-language query.",
  "input_schema": {
    "query": "string",
    "domains": "optional list[string]",
    "date_range": "optional object"
  }
}
```

MCP servers or tool adapters register capabilities with the ToolRegistry.

The planner receives the available tool definitions at runtime.

Adding:

```text
search_arxiv
```

should not require modifying the planner's finance/legal/etc. routing logic.

The LLM selects it because its description/schema matches the current task.

## Tool selection validation

The LLM proposes actions; the runtime validates them.

```text
LLM
 |
 v
structured action
 |
 v
schema validation
 |
 v
policy / permission / budget checks
 |
 v
tool execution
```

The model owns semantic selection.

The runtime owns safe execution.

---

# 34. Required Design Question 03 — Preventing Context Drift

Long-running agents risk gradually optimizing for their own intermediate summaries instead of the user's actual request.

Do not solve this by continuously summarizing summaries.

Maintain an **immutable original objective** plus a structured current objective.

At every major planning/evaluation step, provide the model with:

```text
1. Original user query
2. Current objective + explicit constraints
3. Current objective version
4. Research plan
5. Evidence references
6. Unresolved questions
```

The original query must remain available even if older conversational messages are compacted.

## Source-of-truth hierarchy

Use:

```text
Original user request
        +
Current structured ResearchObjective
        |
        v
authoritative goal state
```

Intermediate summaries are convenience/context, not the source of truth.

## Objective versioning

When the user redirects research:

```text
objective v1
    |
user changes scope
    |
    v
objective v2
```

Tasks/evidence can record:

```text
created_for_objective_version
relevant_to_objective_versions
```

This prevents old tasks from silently driving a new research direction.

## Re-grounding checkpoints

At important boundaries, ask the evaluator to explicitly compare progress against the objective:

```text
Given the ORIGINAL REQUEST and CURRENT OBJECTIVE:

- Which requested dimensions are covered?
- Which are missing?
- Which current tasks are no longer relevant?
- Has the research introduced topics not required by the user?
- Does the current plan still answer the actual question?
```

Run this check:

- after major task batches
- before synthesis
- after a user redirect
- when the planner proposes a large plan expansion

## Context compaction

If context becomes too large:

```text
raw history
    |
    v
structured state + evidence IDs + task summaries
```

Compact old execution chatter, not authoritative goal/evidence data.

Never replace raw source provenance with an LLM-generated summary.

---

# 35. Required Design Question 04 — End-to-End Citation Provenance

Inline citations in the final answer must be traceable to **specific tool results**.

Citation provenance must survive:

```text
raw tool output
      |
      v
document / source record
      |
      v
source chunk
      |
      v
extracted evidence
      |
      v
derived finding
      |
      v
final claim
```

## Provenance entities

Suggested model:

```text
Source
- source_id
- tool_call_id
- URL / document identifier
- title
- retrieved_at
- raw-content hash
- metadata

SourceChunk
- chunk_id
- source_id
- location / offsets
- text

Evidence
- evidence_id
- chunk_ids
- extracted claim/fact
- extraction metadata

Finding
- finding_id
- statement
- supporting_evidence_ids
- conflicting_evidence_ids
```

The final report should cite `evidence_id` / source records, not arbitrary URLs invented during synthesis.

Example:

```text
Tool call tc_42
   |
   v
Source src_9
   |
   v
Chunk chunk_91
   |
   v
Evidence ev_31
   |
   v
Finding finding_8
   |
   v
"Company X identified packaging capacity as a constraint.[1]"
```

Citation `[1]` can then resolve back to:

```text
finding_8
 -> ev_31
 -> chunk_91
 -> src_9
 -> tc_42
```

## Citation verifier

Before final output:

1. identify each material factual claim
2. inspect its supporting evidence IDs
3. verify that cited excerpts support the wording
4. flag unsupported claims
5. flag citations that only weakly support the claim
6. revise or remove unsupported statements

Important:

> Citation generation is not a formatting problem. It is a data-lineage problem.

---

# 36. Failure Handling Strategy

The design document must explicitly discuss failure behavior.

## Tool failure

Examples:

```text
search API unavailable
page blocked
PDF parse failure
timeout
rate limit
empty search result
```

Response:

```text
tool failure
    |
    v
record failure in trace
    |
    v
retryable?
  /     \
yes      no
 |        |
bounded   return observation
retry     to planner
           |
           v
planner chooses alternative
```

Do not fabricate results when a tool fails.

## LLM structured-output failure

Use:

```text
JSON Schema / Pydantic validation
        |
        v
invalid?
        |
        v
bounded repair/retry
        |
        v
fallback error state
```

## Contradictory evidence

Do not silently pick one source.

Store both and allow the synthesizer to report uncertainty.

## Partial completion

If budget/time limits are reached:

```text
return best-supported partial report
+
explicit unresolved gaps
+
which tasks were incomplete
```

## Planner loops

Detect:

- repeated identical tool calls
- repeated failed actions
- no increase in evidence coverage
- excessive plan expansion

Terminate or ask the planner to replan.

---

# 37. Evaluation Plan — Required Deliverable

Create a dedicated `EVALUATION.md`.

The evaluation must go beyond manual QA.

The plan should evaluate four dimensions:

```text
1. Research quality
2. Grounding / citation quality
3. Agent reliability
4. Efficiency
```

## 37.1 Synthetic benchmark set

Create a diverse query suite.

Categories should include:

```text
financial comparison
regulatory research
technology comparison
scientific research
company/product research
multi-source synthesis
ambiguous queries
queries requiring clarification
queries with conflicting sources
queries where sources are unavailable
mid-conversation redirects
```

Avoid evaluating only the example prompts from the assignment.

Include easy, medium, and difficult tasks.

Example benchmark record:

```json
{
  "id": "eval_017",
  "query": "...",
  "expected_requirements": [
    "compare A and B",
    "include primary sources",
    "identify uncertainty"
  ],
  "required_capabilities": [
    "search",
    "document retrieval",
    "multi-source synthesis"
  ]
}
```

## 37.2 Quantitative metrics

Track:

### Task completion

```text
% of requested dimensions addressed
```

### Citation coverage

```text
material factual claims with citations
--------------------------------------
total material factual claims
```

### Citation correctness / entailment

```text
citations whose source supports the claim
-----------------------------------------
citations evaluated
```

### Source quality

Measure use of:

```text
primary sources
authoritative secondary sources
low-authority sources
```

### Tool success rate

```text
successful tool calls / total tool calls
```

### Redundant tool-call rate

Measure unnecessary repeated calls.

### Latency

Track:

```text
time to first progress event
total research time
tool latency
LLM latency
```

### Cost

Track:

```text
input tokens
output tokens
tool/API costs
estimated cost per completed research task
```

### Planning efficiency

Possible metrics:

```text
tasks completed / tasks created
useful evidence items / tool calls
replans per session
```

## 37.3 LLM-as-a-Judge

Use a separate evaluator prompt/model to score reports against a rubric.

Judge dimensions:

```text
answer completeness       1-5
factual support           1-5
citation correctness      1-5
source quality            1-5
handling of uncertainty   1-5
instruction adherence     1-5
```

The judge should receive:

- original query
- final answer
- cited evidence excerpts

Do not ask the judge to rely on unsupported world knowledge when citation entailment can be checked directly.

For higher confidence, combine automated checks with sampled human review.

## 37.4 Deterministic evaluation

Some checks should not use an LLM:

```text
every citation ID resolves
every cited evidence record resolves to a source
no unknown tool names were executed
budgets were respected
task state transitions are valid
agent terminates
required trace events exist
```

## 37.5 Failure-injection tests

Simulate:

```text
search timeout
malformed HTML
document parser exception
tool returns empty result
LLM returns invalid JSON
rate limit
one parallel branch fails
contradictory sources
```

Evaluate whether the system:

```text
retries appropriately
replans
preserves state
avoids fabricated evidence
returns partial results when necessary
```

## 37.6 Context-drift evaluation

Create long multi-step sessions where irrelevant findings are introduced.

Measure whether the final answer still satisfies the original objective.

Also test:

```text
initial question
 -> several research rounds
 -> user redirects scope
 -> agent must discard obsolete plan branches
 -> final report follows new objective
```

## 37.7 Regression suite

Store evaluation cases and run them after meaningful planner/runtime changes.

Because LLM behavior is nondeterministic:

- run important cases multiple times
- report mean and variance where practical
- pin model/version/settings for comparable experiments

---

# 38. Observability Requirements

A reviewer should be able to inspect the reasoning process without requiring hidden chain-of-thought.

Expose a **structured reasoning trace**, not private chain-of-thought.

Example:

```json
{
  "event": "planner_decision",
  "task_id": "task_4",
  "decision_summary": "Need an authoritative primary source for the US regulatory requirement.",
  "selected_tool": "search_web",
  "arguments": {
    "query": "..."
  }
}
```

Useful trace events:

```text
session_started
objective_created
objective_updated
plan_created
task_created
task_started
tool_requested
tool_completed
tool_failed
evidence_created
replan_requested
evaluation_completed
synthesis_started
verification_completed
session_completed
```

Each event should include:

```text
timestamp
session_id
objective_version
task_id when applicable
latency
token/cost metadata when available
```

Do not log secrets or unnecessary raw credentials.

---

# 39. Design Document — Required Deliverable

Create a dedicated `DESIGN.md`.

It should be concise enough to review quickly but deep enough to demonstrate architectural reasoning.

Recommended structure:

```text
1. Executive Summary
2. Goals and Non-Goals
3. Assumptions
4. Architecture Diagram
5. Agent Reasoning / Execution Loop
6. User Interaction and Steering
7. Planning and Dynamic Tool Selection
8. Research State and Task DAG
9. Context Drift Prevention
10. Evidence and Citation Provenance
11. Failure Handling
12. Reliability / Safety Controls
13. Observability
14. Evaluation Strategy
15. Trade-offs
16. Prototype Scope
17. Future Improvements
```

The document should explicitly answer the four required design questions rather than making reviewers infer the answers.

Include at least:

- one architecture diagram
- one research-loop sequence
- one user-redirection sequence
- one citation-lineage flow
- one failure-handling flow

Mermaid or ASCII diagrams are acceptable.

---

# 40. Prompt History / Conversation Logs — Required Deliverable

The full AI coding-assistant history is part of the submission and is explicitly evaluated.

Do not attempt to manufacture a polished fake history.

The conversation should naturally demonstrate:

```text
requirement interpretation
architecture decomposition
trade-off reasoning
implementation guidance
testing
identification of mistakes
course correction
scope management
```

Create a `PROMPT_HISTORY.md` or `logs/` directory only if there is a practical export mechanism.

Do not manually rewrite conversation history to make it look cleaner.

Instead, preserve/export the actual Codex session history where possible.

Also create a short `AI_USAGE.md` that explains:

- which AI tools were used
- what they were used for
- important decisions the human made
- places where AI suggestions were rejected or corrected
- any limitations in exported logs

This document is not a replacement for the required full logs.

---

# 41. Repository Deliverables

Target repository structure:

```text
README.md
DESIGN.md
EVALUATION.md
AI_USAGE.md
research-agent-init.md

logs/
  ... exported AI conversation history when available

app/
  ... prototype if implemented

tests/
  ... prototype/evaluation tests if implemented
```

If time is limited, required written deliverables take priority over adding prototype features.

---

# 42. Reviewer-Oriented README

Create a concise `README.md` that answers:

```text
What is this?
What is implemented?
What is proposed but not implemented?
How does the architecture work?
How do I run the prototype?
How do I run tests/evaluation?
Where are DESIGN.md and EVALUATION.md?
Where are the AI conversation logs?
What assumptions were made?
```

Do not oversell incomplete functionality.

Clearly label:

```text
Implemented
Designed / proposed
Future work
```

---

# 43. Updated MVP Scope

If implementing code, the prototype should demonstrate architecture rather than feature breadth.

Minimum useful prototype:

```text
natural-language query
        |
        v
LLM planner
        |
        v
structured action
        |
        v
ToolRegistry
        |
        v
at least one real external research tool
        |
        v
observation
        |
        v
LLM decides next action
        |
        v
evidence with provenance
        |
        v
cited response
```

Strong additions if time permits:

```text
second tool
multi-step research
user steering
research completion evaluator
citation verifier
failure/retry demo
structured trace
```

Do not build a large UI unless the core design and required deliverables are already strong.

A CLI or minimal API is sufficient to demonstrate the architecture.

---

# 44. Assignment Evaluation Alignment

The submission is evaluated equally across four dimensions.

## System Architecture

Demonstrate:

- explicit reasoning/execution loop
- session state
- dynamic planning
- user steering
- task dependencies
- bounded autonomy

## Tool Use & Grounding

Demonstrate:

- structured tool interfaces
- dynamic selection
- external evidence
- provenance
- citations

## Reliability & Error Handling

Demonstrate:

- schema validation
- bounded retries
- timeouts
- partial completion
- contradiction handling
- loop detection
- budget limits

## Evaluation & Observability

Demonstrate:

- structured traces
- metrics
- synthetic benchmark
- LLM-as-a-judge
- deterministic invariants
- failure injection
- regression testing

When choosing between implementing another feature and strengthening a weak evaluation dimension, prefer the latter.

---

# 45. Time-Budget Strategy

Assume the project should demonstrate thoughtful work within a couple of hours.

Suggested order:

```text
1. Lock architecture and assumptions
2. Write DESIGN.md
3. Write EVALUATION.md
4. Scaffold minimal prototype
5. Implement core planner -> tool -> observation loop
6. Demonstrate provenance/citation path
7. Add focused tests
8. Update README / AI_USAGE
9. Review deliverables against assignment
```

Do not allow Codex to spend the entire session polishing infrastructure.

If prototype work becomes expensive, stop at a coherent milestone and document:

```text
what works
what remains
what would be built next
why
```

---

# 46. Updated Initial Codex Task

Before making changes:

1. Read this entire specification.
2. Inspect the repository.
3. Restate, briefly, the assignment constraints you must preserve.
4. Identify any assumptions you need to make.
5. Do not begin with a large implementation.

Then work in this order.

## Step A — Required design artifacts first

Create:

```text
DESIGN.md
EVALUATION.md
AI_USAGE.md
README.md
```

`DESIGN.md` must explicitly answer:

```text
01 User interaction / steering
02 LLM decomposition + dynamic tool registration/selection
03 Context drift prevention
04 End-to-end citation provenance
```

It must also cover:

```text
architecture
agent loop
state model
failure handling
reliability
observability
trade-offs
prototype scope
```

`EVALUATION.md` must contain:

```text
synthetic benchmark strategy
quantitative metrics
citation evaluation
LLM-as-a-judge rubric
deterministic invariants
failure injection
context-drift tests
latency/cost measurements
regression strategy
```

## Step B — Review before implementation

After drafting the documents:

1. check them against every assignment requirement
2. identify weak/missing areas
3. improve them
4. summarize the resulting architecture

Only then begin prototype implementation.

## Step C — Minimal prototype

If time/tokens remain, implement the smallest useful generic prototype:

```text
LLM planner
   |
structured AgentAction
   |
ToolRegistry
   |
real research tool
   |
observation
   |
evidence/provenance
   |
next LLM decision
   |
cited final answer
```

Use structured schemas and bounded execution.

Do not hardcode example-specific behavior.

Add focused tests.

## Step D — Final submission audit

Before stopping, audit the repository against the assignment.

Produce a checklist covering:

```text
Prompt History / logs
Design Document
Evaluation Plan
Prototype (if any)
System Architecture
Tool Use & Grounding
Reliability & Error Handling
Evaluation & Observability
inline citation traceability
general-purpose behavior
LLM-driven planning/tool selection
```

Update README with current implementation status.

If anything remains incomplete, state it explicitly instead of pretending it is finished.
