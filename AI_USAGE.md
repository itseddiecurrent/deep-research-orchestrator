# AI Usage Disclosure

## Tool used

OpenAI Codex was used as a collaborative coding and writing assistant in this
workspace. It inspected the repository, read the project specification, drafted and
reviewed architecture/evaluation documents, managed a local conversation-history
export, and checked repository deliverables.

No separate AI-generated conversation transcript was created. The authentic filtered
Codex session export is in [`logs/codex-session-export.jsonl`](logs/codex-session-export.jsonl),
with its format and exclusions documented in [`logs/README.md`](logs/README.md).

## How the assistant was used

- Interpret the assignment and map explicit requirements to document sections.
- Explore architecture choices for multi-turn objectives, dynamic tools, task DAGs,
  context control, citation lineage, failure handling, security, and observability.
- Turn the evaluation requirements into measurable benchmark records, metrics,
  failure schedules, judge rubrics, invariants, and regression gates.
- Create and edit repository documentation.
- Inspect the local Codex history mechanism and export a reviewable subset without
  manually rewriting messages.

## Important human decisions and corrections

The human supplied and owns the authoritative specification and made the most
important scope correction in the session:

- The original direction led the assistant to create a prototype-first Python/FastAPI
  scaffold.
- The human replaced the specification with a system-design-focused assignment,
  explicitly directed the assistant to undo that implementation, and prioritized
  prompt history, `DESIGN.md`, and `EVALUATION.md` over coding volume.
- The human required four design questions to be answered explicitly, required
  concrete evaluation beyond manual QA, prohibited domain-specific workflows, and
  required incomplete implementation to be disclosed.

Codex followed that correction by moving its prior prototype artifacts to the system
Trash and returning the workspace to the new specification before creating the
current deliverables. This course correction is visible in the exported history; it
has not been edited out.

## Suggestions rejected or constrained

- The earlier code-first milestone was rejected after the assignment changed.
- A polished, manually reconstructed prompt history was not created because it would
  not be an authentic log.
- Significant prototype work was deferred until after the design and evaluation
  audit, in accordance with the human's priority order.
- Domain routers, fixed example-query pipelines, unbounded agents, and free-form
  citations were excluded by design.

## Human review still required

The documents reflect assistant-generated analysis and should receive normal human
review. In particular, proposed evaluation thresholds need calibration against an
initial labeled baseline; security and retention policies need organization-specific
approval; and any future prototype needs implementation and test evidence before it
is described as working.

## Log-export limitations

The local Codex session file contains internal records not suitable for a submission.
The exported JSONL retains actual user/assistant messages and tool calls/results, but
excludes system/developer instructions, encrypted reasoning records, aggregate token
telemetry, and session-internal metadata. JSON formatting is normalized by `jq`; the
message and tool-event values are not rewritten. Depending on when the final export
is refreshed, the final assistant handoff may not yet have been flushed to the local
source. See [`logs/README.md`](logs/README.md) for the exact filter.

`AI_USAGE.md` is a disclosure and summary. It is not a replacement for the prompt
history deliverable.
