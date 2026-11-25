#!/bin/bash
# Session start for Claude Code (SessionStart) and Cursor (sessionStart, imported or native).
# 1. Refresh .workflow/profile.json when it is missing or a manifest changed (read-only detector, 5s budget).
# 2. Inject the workflow contract plus a short profile summary, in the calling tool's output format.
# Never blocks or fails the session: every error path still exits 0.

input="$(cat 2>/dev/null || true)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
scripts="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/scripts}"
scripts="${scripts:-$(cd "$here/../scripts" 2>/dev/null && pwd)}"

HOOK_INPUT="$input" SCRIPTS_DIR="$scripts" HUB_DIR="$(cd "$here/.." && pwd)" PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}" python3 - <<'PY' 2>/dev/null || exit 0
import json, os, re, subprocess, sys

raw = os.environ.get("HOOK_INPUT", "")
try:
    event = json.loads(raw) if raw.strip() else {}
except ValueError:
    event = {}
name = event.get("hook_event_name") or "SessionStart"
roots = event.get("workspace_roots") or []
project = os.environ.get("CLAUDE_PROJECT_DIR") or (roots[0] if roots else "") or event.get("cwd") or os.getcwd()

contract = (
    "Workflow: refine the request, then hand off (token-policy); Plan -> Code -> Review -> QA (compounding cycle). "
    "Stacks, commands and integrations come from .workflow/profile.json: read it before planning or coding, "
    "run only confirmed or script/derived commands, and run /setup to confirm or refresh it. "
    "Use graphify only when the profile shows a graph. /feature-plan or /apply-ticket write the plan; "
    "then /clear and /project-manager run Code, Review and QA. Modes: .claude/rules/claude-code.md."
)
if os.environ.get("PLUGIN_ROOT"):
    # Plugins can't ship always-on rules, so name the prefixes and point at the contract skill.
    contract = (
        "Workflow: installed as the daedalus plugin. Commands are /daedalus:<name> (for example /daedalus:feature-plan, "
        "/daedalus:project-manager); spawn roles as daedalus:implementer, daedalus:test-runner, daedalus:argus; "
        "browser QA is the companion plugin daedalus-qa (/daedalus-qa:manual-test, daedalus-qa:qa-tester). "
        "Load the daedalus:workflow-contract skill before planning, coding, reviewing or QA: refine then hand off; "
        "Plan -> Code -> Review -> QA; facts from .workflow/profile.json; run only safe profile commands; "
        "graphify only when a graph exists; never commit or push unless asked."
    )
summary = ""
detector = os.path.join(os.environ.get("SCRIPTS_DIR", ""), "detect-stack.py")
FAILED = "Project profile: detection failed; run /setup."
if os.path.isfile(detector) and os.path.isdir(project):
    # Budgets stay under the hook's 10s timeout: detector soft deadline 4s, its hard alarm 7s, this call 8s.
    try:
        res = subprocess.run([sys.executable, detector, "--ensure", "--summary", "--timeout", "4", "--root", project],
                             capture_output=True, text=True, timeout=8)
        summary = res.stdout.strip() if res.returncode == 0 else ""
        summary = summary or FAILED
    except (OSError, subprocess.SubprocessError):
        summary = "Project profile: detection timed out; run /setup."
extra = ""
def overlay_name():
    """`overlay:` from the nearest .workflow/config.yml (repo, then home); plugin installs keep overlays in ~/.claude."""
    for cfg in (os.path.join(project, ".workflow", "config.yml"), os.path.expanduser("~/.workflow/config.yml")):
        try:
            with open(cfg, encoding="utf-8") as fh:
                m = re.search(r"^overlay:\s*([A-Za-z0-9_-]+)", fh.read(), re.M)
        except OSError:
            continue
        if m and m.group(1) not in ("none", "null"):
            return m.group(1)
    return ""
candidates = [os.path.join(os.environ.get("HUB_DIR", ""), "hooks", "context.txt")]
name_ = overlay_name()
if name_:
    candidates.append(os.path.expanduser(os.path.join("~/.claude/overlays", name_, "hooks", "context.txt")))
for context_file in candidates:
    if os.path.isfile(context_file):
        with open(context_file, encoding="utf-8") as fh:
            extra = fh.read().strip()
        break
text = "\n".join(part for part in (contract, summary, extra) if part)

if name == "sessionStart":  # Cursor
    print(json.dumps({"continue": True, "additional_context": text}))
else:  # Claude Code
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
PY
exit 0
