# AI Usage Disclosure

This project used AI assistance during development. This document records how, so
the work can be cited and acknowledged transparently.

## Tools & models

- **Claude Code** (Anthropic) — CLI coding agent. Models in the Claude Opus / Sonnet
  family. Update the specific model(s) here as they change.

## What AI was used for

<!-- Edit to reflect reality. Examples: -->
- Scaffolding and boilerplate
- Refactoring and code review
- Writing tests
- Documentation
- Debugging assistance

All AI-generated code was reviewed by a human before being committed.

## How usage is recorded

Three complementary, auditable records:

1. **Per-commit attribution** — commits made with AI assistance carry a
   `Co-Authored-By: Claude <noreply@anthropic.com>` trailer. Audit with:
   ```bash
   git log --grep="Co-Authored-By: Claude" --oneline
   ```
2. **Activity log** — [`AI_USAGE_LOG.jsonl`](AI_USAGE_LOG.jsonl) is an append-only
   record (one JSON object per line) of prompts submitted and files/commands the
   agent touched, written automatically by a Claude Code hook
   (`.claude/hooks/ai-log.sh`).
3. **Session transcripts** *(local, not committed)* — full session transcripts are
   archived under `.ai-sessions/` at session end. These are **gitignored by default**
   because transcripts can contain secrets and this is a public repo. To include them
   as citable evidence, remove `.ai-sessions/` from `.gitignore` and review each file
   for sensitive content before committing.

## Reproducing / reading the logs

- The JSONL log is greppable with `jq`, e.g. list every prompt:
  ```bash
  jq -r 'select(.kind=="prompt") | "\(.ts)\t\(.prompt)"' AI_USAGE_LOG.jsonl
  ```
- Render archived transcripts to HTML/Markdown with community tools such as
  [`daaain/claude-code-log`](https://github.com/daaain/claude-code-log).
