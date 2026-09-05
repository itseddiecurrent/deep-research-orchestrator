# Submission Deliverables

## Required

| Deliverable | Location |
|---|---|
| Prompt history / conversation logs | [`logs/codex-session-export.jsonl`](logs/codex-session-export.jsonl) |
| Conversation-log format and exclusions | [`logs/README.md`](logs/README.md) |
| Design document | [`DESIGN.md`](DESIGN.md) |
| Evaluation plan | [`EVALUATION.md`](EVALUATION.md) |

## Supporting material

| Item | Location |
|---|---|
| Requirement-by-requirement submission audit | [`SUBMISSION_AUDIT.md`](SUBMISSION_AUDIT.md) |
| AI usage disclosure | [`AI_USAGE.md`](AI_USAGE.md) |
| Original assignment | [`research-agent-init.md`](research-agent-init.md) |

## Nice-to-have prototype

The runnable prototype is in [`src/research_agent/`](src/research_agent/), with tests
in [`tests/`](tests/) and setup/entry-point definitions in
[`pyproject.toml`](pyproject.toml).

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q -W error
.venv/bin/research-agent "Your research question"
.venv/bin/research-agent-web
```
