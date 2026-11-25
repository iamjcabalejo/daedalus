#!/usr/bin/env python3
"""Probe recorder hook: capture the hook payload, then answer from the control file.

Used only inside the throwaway probe projects that scripts/probes/run-probes.sh creates; never wired into the hub.

  recorder.py [--ctrl PATH] [--out DIR] [--event NAME] [--tag TAG] [--dialect claude|cursor|codex]

--ctrl defaults to $PROBE_CTRL; --out defaults to $PROBE_OUT, else <ctrl dir>/out/raw.
Every call appends one line to <out>/<event>.jsonl:
  {"seq", "received_at", "event", "tool", "tag", "key", "mode", "dialect", "payload"}
(seq is global across events, so the capture keeps its order), then answers per the control file:

  {"<event>[:<tool>]": {"mode": "...", "after": 0, "limit": null, "agent": null, "reason": "...", "sleep_s": null}}

Modes:
  record        exit 0, no output
  allow|deny|ask  hookSpecificOutput.permissionDecision plus a reason (Cursor dialect: "permission"; verify in T0)
  exit2         reason on stderr, exit 2
  crash         exit 1
  timeout       sleep sleep_s (default 90 s, past the hosts' 60 s default), then exit 0
  invalid-json  malformed JSON on stdout, exit 0
missing-interpreter is not a recorder mode: the template's hook command names a binary that does not exist.

`after: n` answers `record` for the first n matching calls; `limit: n` applies the mode at most n times;
`agent` restricts the rule to payloads whose agent_type equals it or ends with ":<agent>" (plugin agents).
The tool part of a key is a full-match regex (`PreToolUse:mcp__.*`, `PreToolUse:Edit|Write`). Precedence: the
exact `<event>:<tool>` key, then regex keys in sorted order, then the bare `<event>`; counters are per key. Recorder errors (unreadable or invalid control file, unknown mode) go to
<out>/_errors.jsonl and are answered with `record`, so a harness bug shows up in the results instead of silently
changing a decision.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TextIO

try:
    import fcntl
except ImportError:  # Windows has no advisory locks; the probes target macOS and Linux
    fcntl = None  # type: ignore[assignment]

MODES = ("record", "allow", "deny", "ask", "exit2", "crash", "timeout", "invalid-json")
DECISION_MODES = ("allow", "deny", "ask")
DIALECTS = ("claude", "cursor", "codex")
DEFAULT_TIMEOUT_SLEEP_S = 90.0
DEFAULT_REASON = "daedalus probe recorder"
CRASH_MESSAGE = "daedalus probe recorder: simulated crash"
INVALID_JSON = '{"hookSpecificOutput": {"permissionDecision": '
EXIT_OK, EXIT_CRASH, EXIT_BLOCK = 0, 1, 2
UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
ERRORS_FILE = "_errors.jsonl"
STATE_FILE = "state.json"
LOCK_FILE = "recorder.lock"


class ControlError(ValueError):
    """The control file is unreadable or holds a rule the recorder can't apply."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_args(argv: list) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Record a hook payload and answer from the probe control file.")
    ap.add_argument("--ctrl", default=os.environ.get("PROBE_CTRL"), help="control file (default: $PROBE_CTRL)")
    ap.add_argument("--out", default=os.environ.get("PROBE_OUT"), help="raw capture dir (default: $PROBE_OUT)")
    ap.add_argument("--event", help="event name (default: the payload's hook_event_name)")
    ap.add_argument("--tag", help="label stored with each record (for example frontmatter or claude-import)")
    ap.add_argument("--dialect", choices=DIALECTS, default="claude", help="decision output format")
    return ap.parse_args(argv)


def read_payload(text: str) -> dict:
    """Parse stdin; anything that isn't a JSON object is kept verbatim so it can still be inspected."""
    try:
        value = json.loads(text) if text.strip() else {}
    except ValueError:
        return {"_unparsed_text": text}
    return value if isinstance(value, dict) else {"_unparsed_text": text}


def resolve_out_dir(ctrl: Optional[str], out: Optional[str]) -> Path:
    if out:
        return Path(out)
    if ctrl:
        return Path(ctrl).resolve().parent / "out" / "raw"
    return Path.cwd() / "out" / "raw"


def load_ctrl(path: Optional[str]) -> dict:
    if not path or not Path(path).is_file():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise ControlError(f"cannot read control file {path}: {err}") from err
    if not isinstance(data, dict):
        raise ControlError(f"control file {path} must hold a JSON object")
    for key, rule in data.items():
        if not isinstance(rule, dict) or rule.get("mode") not in MODES:
            raise ControlError(f"control rule {key!r} needs a mode in {MODES}")
        _, _, tool_pattern = key.partition(":")
        try:
            re.compile(tool_pattern)
        except re.error as err:
            raise ControlError(f"control rule {key!r} has an invalid tool pattern: {err}") from err
    return data


def agent_matches(wanted: Optional[str], agent_type: object) -> bool:
    if not wanted:
        return True
    return isinstance(agent_type, str) and (agent_type == wanted or agent_type.endswith(":" + wanted))


def candidate_keys(ctrl: dict, event: str, tool: Optional[str]) -> list:
    """Exact `<event>:<tool>` first, then `<event>:<regex>` keys whose regex fully matches the tool (sorted, for a
    stable order; e.g. `PreToolUse:mcp__.*` or `PreToolUse:Edit|Write`), then the bare `<event>`."""
    keys = []
    if tool:
        exact = f"{event}:{tool}"
        keys.append(exact)
        prefix = f"{event}:"
        for key in sorted(k for k in ctrl if k.startswith(prefix) and k != exact):
            if re.fullmatch(key[len(prefix):], tool):
                keys.append(key)
    keys.append(event)
    return keys


def match_rule(ctrl: dict, event: str, tool: Optional[str], agent_type: object) -> tuple:
    """Return (key, rule) for the most specific rule that applies, or (None, None)."""
    for key in candidate_keys(ctrl, event, tool):
        rule = ctrl.get(key)
        if rule is not None:
            return (key, rule) if agent_matches(rule.get("agent"), agent_type) else (None, None)
    return None, None


class StateLock:
    """Serialize recorder calls (background subagents fire hooks concurrently)."""

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / LOCK_FILE
        self.handle: Optional[TextIO] = None

    def __enter__(self) -> "StateLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a")
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc: object) -> None:
        if self.handle is not None:
            if fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def read_state(path: Path) -> dict:
    if not path.is_file():
        return {"seq": 0, "rules": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:
        raise ControlError(f"recorder state {path} is corrupt: {err}") from err


def decide(state: dict, key: Optional[str], rule: Optional[dict]) -> str:
    """Apply `after` and `limit` to the rule's counters (mutates state)."""
    if not key or not rule:
        return "record"
    counters = state["rules"].setdefault(key, {"seen": 0, "applied": 0})
    counters["seen"] += 1
    if counters["seen"] <= int(rule.get("after") or 0):
        return "record"
    limit = rule.get("limit")
    if limit is not None and counters["applied"] >= int(limit):
        return "record"
    counters["applied"] += 1
    return str(rule["mode"])


def append_line(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_error(out_dir: Path, message: str) -> None:
    """Keep recorder failures visible; never let them change a decision."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        append_line(out_dir / ERRORS_FILE, {"at": utc_now(), "error": message})
    except OSError as err:
        sys.stderr.write(f"daedalus probe recorder: cannot log error ({err}): {message}\n")


def capture(out_dir: Path, event: str, payload: dict, args: argparse.Namespace, ctrl: dict) -> tuple:
    """Record the payload and return (mode, rule) under one lock, so seq and counters stay consistent."""
    state_dir = out_dir.parent / "state"
    tool = payload.get("tool_name") if isinstance(payload.get("tool_name"), str) else None
    key, rule = match_rule(ctrl, event, tool, payload.get("agent_type"))
    out_dir.mkdir(parents=True, exist_ok=True)
    with StateLock(state_dir):
        state = read_state(state_dir / STATE_FILE)
        mode = decide(state, key, rule)
        state["seq"] += 1
        record = {"seq": state["seq"], "received_at": utc_now(), "event": event, "tool": tool, "tag": args.tag,
                  "key": key, "mode": mode, "dialect": args.dialect, "payload": payload}
        append_line(out_dir / f"{UNSAFE_NAME.sub('_', event) or 'unknown'}.jsonl", record)
        (state_dir / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
    return mode, rule


def decision_output(mode: str, event: str, reason: str, dialect: str) -> dict:
    if dialect == "cursor":  # Cursor hook response shape: verify in T0
        return {"permission": mode, "user_message": reason, "agent_message": reason}
    return {"hookSpecificOutput": {"hookEventName": event, "permissionDecision": mode,
                                   "permissionDecisionReason": reason}}


def respond(mode: str, rule: Optional[dict], event: str, dialect: str,
            out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
    rule = rule or {}
    reason = str(rule.get("reason") or DEFAULT_REASON)
    if mode in DECISION_MODES:
        out.write(json.dumps(decision_output(mode, event, reason, dialect)) + "\n")
        return EXIT_OK
    if mode == "exit2":
        err.write(reason + "\n")
        return EXIT_BLOCK
    if mode == "crash":
        err.write(CRASH_MESSAGE + "\n")
        return EXIT_CRASH
    if mode == "timeout":
        out.flush()
        time.sleep(float(rule.get("sleep_s") or DEFAULT_TIMEOUT_SLEEP_S))
        return EXIT_OK
    if mode == "invalid-json":
        out.write(INVALID_JSON)
        return EXIT_OK
    return EXIT_OK


def main(argv: list) -> int:
    args = parse_args(argv)
    out_dir = resolve_out_dir(args.ctrl, args.out)
    payload = read_payload(sys.stdin.read())
    event = args.event or str(payload.get("hook_event_name") or "unknown")
    try:
        ctrl = load_ctrl(args.ctrl)
    except ControlError as err:
        log_error(out_dir, str(err))
        ctrl = {}
    try:
        mode, rule = capture(out_dir, event, payload, args, ctrl)
    except (OSError, ControlError) as err:
        log_error(out_dir, f"capture failed for {event}: {err}")
        return EXIT_OK
    return respond(mode, rule, event, args.dialect)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
