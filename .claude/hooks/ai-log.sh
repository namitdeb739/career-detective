#!/usr/bin/env bash
# Append-only AI-usage logger for Claude Code.
# Invoked by hooks in .claude/settings.json. Receives the hook JSON payload on stdin.
# Writes structured entries to AI_USAGE_LOG.jsonl and (on session end) archives the
# full session transcript into .ai-sessions/ for a complete audit trail.
set -euo pipefail

kind="${1:?usage: ai-log.sh <prompt|tool|session-end>}"
input="$(cat)"                                   # hook payload arrives on stdin
root="${CLAUDE_PROJECT_DIR:-$PWD}"
log="${root}/AI_USAGE_LOG.jsonl"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

case "$kind" in
  prompt)
    jq -c --arg ts "$ts" \
      '{ts: $ts, kind: "prompt", session: .session_id, prompt: .prompt}' \
      <<<"$input" >> "$log"
    ;;
  tool)
    jq -c --arg ts "$ts" \
      '{ts: $ts, kind: "tool", session: .session_id, tool: .tool_name,
        file: (.tool_input.file_path // null),
        cmd: (.tool_input.command // null)}' \
      <<<"$input" >> "$log"
    ;;
  session-end)
    tp="$(jq -r '.transcript_path // empty' <<<"$input")"
    sid="$(jq -r '.session_id // "unknown"' <<<"$input")"
    dir="${root}/.ai-sessions"
    mkdir -p "$dir"
    [ -n "$tp" ] && [ -f "$tp" ] && cp "$tp" "$dir/${sid}.jsonl"
    jq -c --arg ts "$ts" \
      '{ts: $ts, kind: "session-end", session: .session_id, reason: .reason}' \
      <<<"$input" >> "$log"
    ;;
  *)
    echo "ai-log.sh: unknown kind '$kind'" >&2; exit 1
    ;;
esac
exit 0
