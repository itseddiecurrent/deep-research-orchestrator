# Conversation log exports

For human review, open `codex-session-transcript.txt`. It contains the same retained
events as the JSONL, rendered with visible timestamps, role/tool labels, and readable
message, input, and result blocks.

`codex-session-export.jsonl` is a filtered export of all five actual local Codex
sessions whose recorded working directory is this repository. It was not manually
reconstructed, shortened for style, or rewritten to hide the prototype-first mistake,
subsequent course correction, interrupted-session recovery, or live debugging.

Each line is a JSON event. The export retains `response_item` records when they are:

- a user message;
- an assistant message; or
- a custom tool call or custom tool-call result.

It deliberately excludes system/developer instructions, encrypted reasoning payloads,
token/rate-limit telemetry, and other session-internal metadata. This protects private
reasoning and environment instructions while retaining the reviewable collaboration
record. `jq -c` normalizes JSON whitespace/key rendering but does not paraphrase event
values.

The `.txt` file is mechanically rendered from this JSONL without summarizing,
paraphrasing, or dropping events. For text-file portability, carriage returns and
trailing whitespace are normalized; original values remain in the JSONL. The JSONL
is the canonical machine-readable artifact, and the text file is its reviewer-friendly
presentation.

Completeness is checked before replacement by comparing the count of retained events
in every matching source session with the merged export, validating every JSON line,
and scanning for configured credentials and common token formats. Events are kept in
session chronology. The active session is exported through the refresh point; as with
any live transcript, the final handoff emitted afterward cannot be present yet.

The filter used was:

```jq
select(.type == "response_item")
| select(
    (.payload.type == "message"
      and (.payload.role == "user" or .payload.role == "assistant"))
    or .payload.type == "custom_tool_call"
    or .payload.type == "custom_tool_call_output"
  )
```

Limitations:

- This is a safe review export, not the raw internal session database.
- The final assistant message and any events after the refresh point are necessarily
  absent until a later refresh.
- Internal chain-of-thought is intentionally unavailable. Concise reasoning summaries
  communicated to the user remain in assistant messages.
- Local source paths and tool output may reveal development-environment structure;
  reviewers should treat the log as submission evidence, not application input.
