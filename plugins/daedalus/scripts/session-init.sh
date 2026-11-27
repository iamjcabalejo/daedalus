#!/bin/bash
# Session start for Claude Code (SessionStart) and Cursor (sessionStart, imported or native).
# 1. Refresh .workflow/profile.json when it is missing or a manifest changed (read-only detector, 5s budget), at
#    the project's git top level (a folder without git is its own top), the profile `config commands` reads.
# 2. Inject the workflow contract plus a short profile summary, in the calling tool's output format, with
#    one line for a configuration error (file and line) and one for untrusted committed commands (count only).
#    The summary is rendered from the evaluated profile and shows a command's text only when the same fast-mode
#    check trusts that exact single-line command; every other command shows `(untrusted)`, and when the check
#    can't run (deadline, error) no command text is shown at all.
# Never blocks or fails the session: every error path still exits 0 (context hooks fail open, D9).
# Python runs isolated (`python3 -I`): the project folder never reaches sys.path, and only this install's own
# scripts folder is added (PF-2).

input="$(cat 2>/dev/null || true)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || exit 0
# This install's scripts folder, from the hook's own real location (never from the project or the environment):
# a plugin ships the hook in ${CLAUDE_PLUGIN_ROOT}/scripts/ next to workflow.py; a script install in <.claude>/hooks/.
if [ -f "$here/workflow.py" ]; then
    scripts="$here"
else
    scripts="$(cd "$here/../scripts" 2>/dev/null && pwd -P)"
fi

HOOK_INPUT="$input" SCRIPTS_DIR="$scripts" HUB_DIR="$(cd "$here/.." && pwd)" PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}" python3 -I - <<'PY' 2>/dev/null || exit 0
import json, os, re, shlex, subprocess, sys, time
from pathlib import Path

raw = os.environ.get("HOOK_INPUT", "")
try:
    event = json.loads(raw) if raw.strip() else {}
except ValueError:
    event = {}
name = event.get("hook_event_name") or "SessionStart"
roots = event.get("workspace_roots") or []
project = os.environ.get("CLAUDE_PROJECT_DIR") or (roots[0] if roots else "") or event.get("cwd") or os.getcwd()
scripts = os.path.realpath(os.environ["SCRIPTS_DIR"]) if os.environ.get("SCRIPTS_DIR") else ""
commands_cli = f"python3 -I {shlex.quote(os.path.join(scripts, 'workflow.py'))} config commands --json" if scripts \
    else "workflow.py config commands --json"
SETUP = "/daedalus:setup" if os.environ.get("PLUGIN_ROOT") else "/setup"

contract = (
    "Workflow: refine the request, then hand off (token-policy); Plan -> Code -> Review -> QA (compounding cycle). "
    "Stacks, commands and integrations come from .workflow/profile.json: read it before planning or coding. "
    f"Run only the commands `{commands_cli}` reports trusted and not unsafe; ask the user before any other, "
    "or run /setup to confirm or refresh them. "
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
        "Plan -> Code -> Review -> QA; facts from .workflow/profile.json; "
        f"run only the commands `{commands_cli}` reports trusted and not unsafe (ask before any other, "
        "or run /daedalus:setup); graphify only when a graph exists; never commit or push unless asked."
    )
summary = ""
started = time.monotonic()
detector = os.path.join(scripts, "detect-stack.py") if scripts else ""
FAILED = f"Project profile: detection failed; run {SETUP}."
TIMED_OUT = f"Project profile: detection timed out; run {SETUP}."
TRUST_DEADLINE = 5.0  # seconds since start; later, skip the trust count so the hook stays under its 10s timeout


rules = None  # lib/text.py: the hidden-character rule the trust library uses too (rework-3); set by load_lib


def load_lib():
    """(wfconfig, trust) from this install's own scripts folder, or (None, None) when it has none. Also sets `rules`;
    until it is set, no profile text counts as printable."""
    global rules
    lib = os.path.join(scripts, "lib", "wfconfig.py") if scripts else ""
    if not os.path.isfile(lib):
        return None, None
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from lib import text, trust, wfconfig
    rules = text
    return wfconfig, trust


def nearest_git_holder(folder: str) -> str:
    """`trust.top_level`'s usual answer, without git or the library: the nearest folder at or above `folder` that
    holds a `.git`, else the folder itself. Only a head start for the detector; `confirm_top` checks it."""
    real = os.path.realpath(folder)
    probe = real
    while not os.path.lexists(os.path.join(probe, ".git")):
        parent = os.path.dirname(probe)
        if parent == probe:
            return real
        probe = parent
    return probe


def start_detector(root: str):
    """Refresh and summarize `<root>/.workflow/profile.json` in the background; None when it can't start."""
    global summary
    # Budgets stay under the hook's 10s timeout: detector soft deadline 4s, its hard alarm 7s, this call 8s.
    # It runs while the configuration resolves below; the trust count waits for the refreshed profile.
    try:
        return subprocess.Popen([sys.executable, "-I", detector, "--ensure", "--summary", "--timeout", "4",
                                 "--root", root], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, text=True)
    except OSError:
        summary = TIMED_OUT
        return None


# The detector works on the project's top level, the folder `/setup`, `config commands` and the trust count read
# the profile from, so a session started in a subfolder sees that one profile. It starts on a guess so the
# library's import doesn't delay it; `confirm_top` checks the guess against `trust.top_level`.
top = nearest_git_holder(project) if os.path.isdir(project) else project
proc = start_detector(top) if os.path.isfile(detector) and os.path.isdir(top) else None


def confirm_top(trust) -> None:
    """`trust.top_level` decides the top level; when the guess was another folder (a `core.worktree` setting,
    an unreadable parent), restart the detector there so the summary and the count read the same profile.
    The stopped run may already have refreshed the guessed folder's profile; nothing reads that one."""
    global proc, top
    actual = str(trust.top_level(Path(project))[0])
    if actual == top:
        return
    if proc is not None:
        proc.kill()
        proc.communicate()
    top = actual
    proc = start_detector(top) if os.path.isfile(detector) else None


OVERLAY_NAME = re.compile(r"[A-Za-z0-9_-]+")  # an overlay is a folder name under ~/.claude/overlays, never a path
DETECTED = ("script", "derived")


def config_error_line(err) -> str:
    where = f", {err.file}:{err.line}" if err.file and err.line else (f", {err.file}" if err.file else "")
    return (f"Configuration error ({err.code}{where}): {err.message}; fix: {err.fix}. "
            "Configuration isn't applied this session; ask before running project commands.")


def needs_trust(record) -> bool:
    """Untrusted and claiming to run. Fast mode can't re-detect, so a `script` or `derived` entry is verified
    only when the trust store holds its digest (`trust record` stores the ones re-detection reproduced, and
    /setup runs it); one that isn't, or any entry with an unusable store, counts and its text is hidden."""
    if record.get("trusted"):
        return False
    if record.get("channel") == "config":
        return True
    declared = record.get("declared") or {}
    return declared.get("confidence") in DETECTED + ("user",) or declared.get("confirmed") is True


def resolve_configuration(notes):
    """(wfconfig, trust, resolved or None, overlay name); appends banner lines to `notes`."""
    if not os.path.isdir(project):
        return None, None, None, ""
    wfconfig, trust = load_lib()
    if wfconfig is None:
        return None, None, None, ""

    workspace = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        resolved = wfconfig.resolve(Path(project), Path(workspace) if workspace else None)
    except wfconfig.ConfigError as err:
        notes.append(config_error_line(err))
        return wfconfig, trust, None, ""
    value = resolved.get("overlay")
    overlay = value if isinstance(value, str) and OVERLAY_NAME.fullmatch(value) and value != "none" else ""
    return wfconfig, trust, resolved, overlay


# ---------- the profile summary (rework-2, finding 1ef278f-4) ----------
# The banner is model context, and a command's text there reads like one that may run. So the summary is rendered
# here, in the detector's `--summary` format, from the profile the trust check evaluated, and it shows a command's
# text only when that check trusts that exact single-line command (an allowlist); every other command bit is
# `(untrusted)`. The detector's own output only says whether detection worked. Free text (root names, layers, packs,
# gaps) stays free text, one line each with hidden characters (lib/text.py: control, format, line separators) removed.
SUMMARY_HEADER = "Project profile ("
PROFILE_REL = ".workflow/profile.json"
SUMMARY_COMMANDS = ("test", "lint", "build", "dev")  # the detector's summary shows these, in this order
SUMMARY_ROOTS, SUMMARY_FRAMEWORKS, SUMMARY_GAPS, SUMMARY_LINES = 8, 4, 3, 12  # and caps them like this
FREE_TEXT_LIMIT = 200  # characters per name, pack or gap, so a forged profile can't flood the banner
DEV_URL = re.compile(r"https?://[!-~]{1,200}")  # printable ASCII without spaces
UNTRUSTED = "(untrusted)"
NOT_SHOWN = f"Project profile: summary not shown (its commands couldn't be checked); run {SETUP}."


def is_printable(text: str) -> bool:
    return rules is not None and not rules.has_hidden(text)


def one_line(value) -> str:
    """Profile free text as the detector prints it, on one line and capped; a list or object never shows."""
    if value is None or isinstance(value, (bool, int, float)):
        return str(value)
    if not isinstance(value, str) or rules is None:
        return "?"
    text = rules.strip_hidden(value)
    return text if len(text) <= FREE_TEXT_LIMIT else text[:FREE_TEXT_LIMIT - 1] + "…"


def mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def texts(value) -> list:
    return [one_line(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def shown_commands(records) -> dict:
    """(root, name) → the text the summary may show: trusted records with single-line text only (the allowlist).
    The record is the effective one, so a trusted override shows its own text, never the entry it shadows."""
    shown = {}
    for record in records:
        cmd = record.get("cmd")
        if record.get("trusted") is True and isinstance(cmd, str) and cmd.strip() and is_printable(cmd):
            shown[(record.get("root"), record.get("name"))] = cmd
    return shown


def root_line(root, shown) -> str:
    """One root as the detector's summary prints it, with allowlisted command text only."""
    if not isinstance(root, dict):
        return "- (invalid root)"
    path = root.get("path")
    valid = isinstance(path, str) and is_printable(path)
    where = one_line(root.get("name") if path == "." else path) if valid else "(invalid path)"
    bits = [f"- {where} [{one_line(root.get('layer'))}]"]
    frameworks = texts(root.get("frameworks"))[:SUMMARY_FRAMEWORKS]
    if frameworks:
        bits.append(", ".join(frameworks))
    bits.append("packs: " + (", ".join(texts(root.get("packs"))) or "none (generic)"))
    commands = mapping(root.get("commands"))
    for name in SUMMARY_COMMANDS:
        if commands.get(name):
            bits.append(f"{name}: {shown.get((path, name), UNTRUSTED) if valid else UNTRUSTED}")
    url = mapping(root.get("ui")).get("dev_url")
    if isinstance(url, str) and DEV_URL.fullmatch(url):
        bits.append(url)
    return " · ".join(bits)


def render_summary(profile: dict, shown) -> str:
    """The detector's `--summary` lines for `profile` (header, roots, trailers, same caps), nothing else; the header
    names this install's setup command (`SETUP`)."""
    state = "confirmed" if profile.get("confirmed") else f"unconfirmed: run {SETUP} to confirm"
    lines = [f"{SUMMARY_HEADER}{PROFILE_REL}, {one_line(profile.get('generator'))}, {state}):"]
    roots = profile.get("roots") if isinstance(profile.get("roots"), list) else []
    lines += [root_line(root, shown) for root in roots[:SUMMARY_ROOTS]]
    if len(roots) > SUMMARY_ROOTS:
        lines.append(f"- …and {len(roots) - SUMMARY_ROOTS} more roots (see the profile)")
    integrations = mapping(profile.get("integrations"))
    tickets = mapping(integrations.get("tickets"))
    key = f" ({one_line(tickets.get('key'))})" if tickets.get("key") else ""
    graph = "graphify" if mapping(integrations.get("graph")).get("graphify") else "none"
    lines.append(f"Tickets: {one_line(tickets.get('system'))}{key} · Code host: "
                 f"{one_line(mapping(integrations.get('code_host')).get('kind'))} · Graph: {graph}")
    gaps = profile.get("gaps") if isinstance(profile.get("gaps"), list) else []
    if gaps:
        more = f" (+{len(gaps) - SUMMARY_GAPS} more)" if len(gaps) > SUMMARY_GAPS else ""
        lines.append("Gaps: " + "; ".join(one_line(gap) for gap in gaps[:SUMMARY_GAPS]) + more)
    return "\n".join(lines[:SUMMARY_LINES])


def banner_summary(detected: str, profile, shown) -> str:
    """The summary the banner shows. Detection's own outcome lines pass through; a profile summary is rendered from
    the evaluated `profile` with `shown` command text only; with no evaluated profile, none is shown."""
    if not detected.startswith(SUMMARY_HEADER):
        return detected if detected in ("", FAILED, TIMED_OUT) else FAILED
    if not isinstance(profile, dict):
        return NOT_SHOWN
    return render_summary(profile, shown)


def count_untrusted(wfconfig, trust, resolved, notes, view) -> None:
    """One banner line with the number of untrusted committed commands, malformed entries included (fast mode, no
    command text). Fills `view` with the profile it evaluated and the command text the summary may show."""
    try:
        top = resolved.repo
        view["profile"] = wfconfig.load_profile(top)
        found = trust.evaluate(top, view["profile"], resolved, rederive=False)
    except wfconfig.ConfigError as err:
        notes.append(config_error_line(err))
        return
    view["shown"] = shown_commands(found.records)
    store_error = (found.store or {}).get("error")
    untrusted = [record for record in found.records if needs_trust(record) or trust.is_malformed(record)]
    if untrusted:
        why = f" (trust store unusable: {store_error.get('code')})" if store_error else ""
        notes.append(f"Trust: {len(untrusted)} committed command(s) untrusted{why}: ask before running, "
                     f"or run {SETUP}.")


def check_configuration():
    """(overlay name, banner lines, view); never raises, and always collects the detector's summary. `view` gets
    the evaluated profile and the trusted command text only when the trust check ran: on every fail-open path
    (an exception, a configuration error, the deadline, a profile that can't be read) the summary shows no command
    text."""
    global summary
    notes, view = [], {}
    try:
        wfconfig, trust, resolved, overlay = resolve_configuration(notes)
        if trust is not None:
            confirm_top(trust)
    except Exception as err:  # noqa: BLE001 - fail open (D9): the session must start, so report and continue
        wfconfig, trust, resolved, overlay = None, None, None, ""
        notes.append(f"Configuration: couldn't be checked ({type(err).__name__}); "
                     f"ask before running project commands, or run {SETUP}.")
    if proc is not None:
        try:
            out, _ = proc.communicate(timeout=max(0.1, 8 - (time.monotonic() - started)))
            summary = (out.strip() if proc.returncode == 0 else "") or FAILED
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            summary = TIMED_OUT
    if wfconfig is None or resolved is None or not os.path.isdir(project):
        # No library, or a configuration that didn't resolve (its error line asks before running, and `config
        # commands` exits 3): which command wins is unknown, so neither a count nor any command text is shown.
        return overlay, notes, view
    if time.monotonic() - started > TRUST_DEADLINE:
        notes.append("Trust: not checked (session start ran long); "
                     f"ask before running project commands, or run {SETUP}.")
        return overlay, notes, view
    try:
        count_untrusted(wfconfig, trust, resolved, notes, view)
    except Exception as err:  # noqa: BLE001 - fail open (D9), as above
        notes.append(f"Trust: couldn't be checked ({type(err).__name__}); "
                     f"ask before running project commands, or run {SETUP}.")
    return overlay, notes, view


overlay, notes, view = check_configuration()
summary = banner_summary(summary, view.get("profile"), view.get("shown", {}))
extra = ""
candidates = [os.path.join(os.environ.get("HUB_DIR", ""), "hooks", "context.txt")]
if overlay:
    candidates.append(os.path.expanduser(os.path.join("~/.claude/overlays", overlay, "hooks", "context.txt")))
for context_file in candidates:
    if os.path.isfile(context_file):
        with open(context_file, encoding="utf-8") as fh:
            extra = fh.read().strip()
        break
text = "\n".join(part for part in [contract, summary] + notes + [extra] if part)

if name == "sessionStart":  # Cursor
    print(json.dumps({"continue": True, "additional_context": text}))
else:  # Claude Code
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
PY
exit 0
