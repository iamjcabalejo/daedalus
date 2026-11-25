#!/bin/bash
# Log hook name + UTC time only. Do not log stdin (may contain secrets).
# Exit 0 with no decision JSON so tool calls are not blocked.
input=$(cat)
event=$(printf '%s' "$input" | sed -n 's/.*"hook_event_name":"\([^"]*\)".*/\1/p' | head -1)
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
root="${CLAUDE_PROJECT_DIR:-.}"
# Plugin installs must not write under the plugin root; they get a persistent data dir instead.
log_dir="${CLAUDE_PLUGIN_DATA:-$root/.claude/hooks}"
log_file="$log_dir/audit.log"
mkdir -p "$log_dir" 2>/dev/null
[ -w "$log_dir" ] 2>/dev/null && \
  echo "{\"event\":\"${event:-unknown}\",\"timestamp\":\"$timestamp\"}" >> "$log_file" 2>/dev/null || true
exit 0
