#!/usr/bin/env python3
"""Redact captured hook payloads into committable fixtures, and scan fixtures for leaks (AC-3).

  redact.py payload [--workspace DIR]                 stdin: one payload; stdout: {"redactions", "payload"}
  redact.py capture --raw-dir DIR --dest DIR --host H --host-version V --case C --install I
                    [--variant X] [--workspace DIR]   one capture's out/raw/*.jsonl -> <dest>/<event>-<n>.json
  redact.py scan PATH...                              leak scan; exit 1 with one line per finding

Rules (applied at any depth, key order kept):
  - prompt text, assistant messages and tool contents (TEXT_RULES keys, e.g. prompt, last_assistant_message,
    tool_input.content / new_string / old_string) -> "<REDACTED:<rule>>";
  - every string under tool_response (and similar output keys) -> "<REDACTED:tool-response>", shape kept;
  - command text after its first word -> "<first word> <REDACTED:command-args>";
  - the workspace path -> <WORKSPACE>, home directories -> <HOME>, macOS temp roots -> <TMP>,
    encoded project folders (.claude/projects/<x>) -> <PROJECT>, emails -> <EMAIL>;
  - session, conversation, agent (and other) ids -> stable placeholders such as <SESSION-1>, <AGENT-2>. One
    Redactor serves a whole capture, so equal ids stay equal across events (A2's concurrency check still works),
    and an id embedded in a path gets the same placeholder. Any other UUID becomes <ID-n>.
Every replacement is listed in the fixture's `redactions` as {"path", "rule"}. Findings never print matched text.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

FIXTURE_SCHEMA = "daedalus.probe-fixture/1"
MIN_KNOWN_ID_LENGTH = 6  # shorter ids are too likely to collide with ordinary text

TEXT_RULES = {
    "prompt": "prompt", "user_prompt": "prompt", "command_args": "prompt", "arguments": "prompt",
    "last_assistant_message": "assistant-message", "assistant_message": "assistant-message",
    "message": "message", "text": "message", "user_message": "message", "agent_message": "message",
    "error": "message", "_unparsed_text": "unparsed",
    "content": "tool-content", "new_string": "tool-content", "old_string": "tool-content",
    "description": "tool-content", "query": "tool-content", "url": "tool-content",
}
SUBTREE_RULES = {"tool_response": "tool-response", "tool_output": "tool-response", "output": "tool-response",
                 "stdout": "tool-response", "stderr": "tool-response"}
COMMAND_KEYS = ("command", "cmd")
ID_KEYS = {"session_id": "SESSION", "conversation_id": "CONVERSATION", "agent_id": "AGENT",
           "parent_agent_id": "AGENT", "generation_id": "GENERATION", "tool_use_id": "TOOL-USE",
           "turn_id": "TURN", "thread_id": "THREAD", "request_id": "REQUEST", "prompt_id": "PROMPT"}

HOME_RE = re.compile(r"(?:/Users|/home)/[^/\s\"'<>:]+")
WINDOWS_HOME_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"'<>]+")
TMP_RE = re.compile(r"/(?:private/)?var/folders/[^/\s]+/[^/\s]+/T")
PROJECT_SEGMENT_RE = re.compile(r"(\.(?:claude|cursor|codex)/projects/)[^/\s\"'<>]+")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
MARKER_RE = re.compile(r"^<REDACTED:[a-z-]+>$")
PLACEHOLDER_RE = re.compile(r"^<[A-Z][A-Z-]*-\d+>$")
COMMAND_MARKER = "<REDACTED:command-args>"
SCRUB_PATTERNS = (
    (TMP_RE, "<TMP>", "temp-path"),
    (HOME_RE, "<HOME>", "home-path"),
    (WINDOWS_HOME_RE, "<HOME>", "home-path"),
    (PROJECT_SEGMENT_RE, r"\1<PROJECT>", "project-folder"),
)
REDACTED_COMMAND_RE = re.compile(r"^\S*(?: " + re.escape(COMMAND_MARKER) + r")?$")

LEAK_PATTERNS = (
    ("home-path", re.compile(r"/Users/|/home/")),
    ("encoded-home", re.compile(r"-Users-|-home-")),
    ("windows-home", re.compile(r"[A-Za-z]:\\Users\\")),
    ("temp-path", re.compile(r"/var/folders/")),
    ("email", EMAIL_RE),
    ("uuid", UUID_RE),
)


class RedactionError(ValueError):
    """A capture can't be redacted (unreadable raw file, malformed record)."""


def marker(rule: str) -> str:
    return f"<REDACTED:{rule}>"


def join_path(base: str, key: object) -> str:
    if isinstance(key, int):
        return f"{base}[{key}]"
    return f"{base}.{key}" if base else str(key)


class Redactor:
    """Redacts the payloads of one capture; placeholders are stable for the Redactor's lifetime."""

    def __init__(self, workspace: Optional[str] = None, home: Optional[str] = None) -> None:
        self.ids: dict = {}
        self.counters: dict = {}
        literals = []
        for path in {workspace, os.path.realpath(workspace) if workspace else None}:
            if path and len(path) > 1:
                literals.append((path.rstrip("/"), "<WORKSPACE>"))
        home = home if home is not None else str(Path.home())
        if home and len(home) > 1:
            literals.append((home.rstrip("/"), "<HOME>"))
        self.literals = sorted(literals, key=lambda item: len(item[0]), reverse=True)

    def placeholder(self, value: str, label: str) -> str:
        if value not in self.ids:
            self.counters[label] = self.counters.get(label, 0) + 1
            self.ids[value] = f"<{label}-{self.counters[label]}>"
        return self.ids[value]

    def register_ids(self, node: object) -> None:
        """First pass: give id-keyed values their labelled placeholder before any string is scrubbed."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ID_KEYS and isinstance(value, str) and value:
                    self.placeholder(value, ID_KEYS[key])
                else:
                    self.register_ids(value)
        elif isinstance(node, list):
            for item in node:
                self.register_ids(item)

    def scrub(self, text: str, path: str, log: list) -> str:
        """Replace paths, ids and emails inside free text that is otherwise kept."""
        for literal, replacement in self.literals:
            if literal in text:
                text = text.replace(literal, replacement)
                log.append((path, "workspace-path" if replacement == "<WORKSPACE>" else "home-path"))
        for pattern, replacement, rule in SCRUB_PATTERNS:
            text, count = pattern.subn(replacement, text)
            if count:
                log.append((path, rule))
        for value, holder in sorted(self.ids.items(), key=lambda item: len(item[0]), reverse=True):
            if len(value) >= MIN_KNOWN_ID_LENGTH and value in text:
                text = text.replace(value, holder)
                log.append((path, "id"))
        text, count = UUID_RE.subn(lambda m: self.ids.get(m.group(0)) or self.placeholder(m.group(0), "ID"), text)
        if count:
            log.append((path, "id"))
        text, count = EMAIL_RE.subn("<EMAIL>", text)
        if count:
            log.append((path, "email"))
        return text

    def redact_command(self, value: object, path: str, log: list) -> object:
        if isinstance(value, str):
            parts = value.strip().split(None, 1)
            head = self.scrub(parts[0] if parts else "", path, log)
            if len(parts) > 1:
                log.append((path, "command-args"))
                return f"{head} {COMMAND_MARKER}"
            return head
        if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            head = self.scrub(value[0], path, log)
            if len(value) > 1:
                log.append((path, "command-args"))
                return [head, COMMAND_MARKER]
            return [head]
        return self.walk(value, path, log)

    def blank_strings(self, node: object, rule: str, path: str, log: list) -> object:
        if isinstance(node, str):
            if node:
                log.append((path, rule))
                return marker(rule)
            return node
        if isinstance(node, dict):
            return {key: self.blank_strings(value, rule, join_path(path, key), log) for key, value in node.items()}
        if isinstance(node, list):
            return [self.blank_strings(item, rule, join_path(path, i), log) for i, item in enumerate(node)]
        return node

    def walk(self, node: object, path: str, log: list) -> object:
        if isinstance(node, dict):
            return {key: self.redact_key(key, value, join_path(path, key), log) for key, value in node.items()}
        if isinstance(node, list):
            return [self.walk(item, join_path(path, i), log) for i, item in enumerate(node)]
        if isinstance(node, str):
            return self.scrub(node, path, log)
        return node

    def redact_key(self, key: str, value: object, path: str, log: list) -> object:
        if key in ID_KEYS and isinstance(value, str) and value:
            log.append((path, "id"))
            return self.placeholder(value, ID_KEYS[key])
        if key in TEXT_RULES and isinstance(value, (str, list, dict)):
            return self.blank_strings(value, TEXT_RULES[key], path, log)
        if key in SUBTREE_RULES:
            return self.blank_strings(value, SUBTREE_RULES[key], path, log)
        if key in COMMAND_KEYS:
            return self.redact_command(value, path, log)
        return self.walk(value, path, log)

    def redact(self, payload: dict) -> tuple:
        """Return (redacted payload, redactions[]) with the original key order."""
        self.register_ids(payload)
        log: list = []
        redacted = self.walk(payload, "", log)
        seen, redactions = set(), []
        for path, rule in log:
            if (path, rule) not in seen:
                seen.add((path, rule))
                redactions.append({"path": path, "rule": rule})
        return redacted, redactions


# ---- capture -> fixtures -------------------------------------------------------------------------------------

def load_raw_records(raw_dir: Path) -> list:
    """All recorder lines of one capture, in capture order (the recorder's global seq)."""
    records = []
    for file in sorted(raw_dir.glob("*.jsonl")):
        if file.name.startswith("_"):
            continue
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except OSError as err:
            raise RedactionError(f"cannot read raw capture {file.name}: {err}") from err
        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as err:
                raise RedactionError(f"{file.name}:{lineno} is not JSON: {err}") from err
            if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
                raise RedactionError(f"{file.name}:{lineno} has no payload object")
            records.append(record)
    return sorted(records, key=lambda r: int(r.get("seq") or 0))


def safe_event_name(event: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", event) or "unknown"


def build_fixtures(records: list, meta: dict, workspace: Optional[str] = None) -> list:
    """Return [(file name, fixture)] for one capture; names are <event>-<n>.json, n counted per event."""
    redactor = Redactor(workspace=workspace)
    for record in records:  # register every id first, so labels follow the ids' own keys, not first mention
        redactor.register_ids(record["payload"])
    per_event: dict = {}
    fixtures = []
    for position, record in enumerate(records, 1):
        event = safe_event_name(str(record.get("event") or record["payload"].get("hook_event_name") or "unknown"))
        per_event[event] = per_event.get(event, 0) + 1
        payload, redactions = redactor.redact(record["payload"])
        fixture = {"schema": FIXTURE_SCHEMA, "host": meta["host"], "host_version": meta["host_version"],
                   "install": meta["install"], "case": meta["case"], "variant": meta.get("variant"),
                   "event": event, "seq": position, "mode": record.get("mode"), "tag": record.get("tag"),
                   "redactions": redactions, "payload": payload}
        fixtures.append((f"{event}-{per_event[event]}.json", fixture))
    return fixtures


def write_fixtures(fixtures: list, dest: Path) -> list:
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name, fixture in fixtures:
        target = dest / name
        target.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(target)
    return written


# ---- leak scan ---------------------------------------------------------------------------------------------

def iter_strings(node: object, path: str = "") -> Iterable:
    if isinstance(node, dict):
        for key, value in node.items():
            yield join_path(path, key), str(key)
            yield from iter_strings(value, join_path(path, key))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from iter_strings(item, join_path(path, i))
    elif isinstance(node, str):
        yield path, node


def scan_value(node: object) -> list:
    """Pattern findings over every key and string value: [(path, kind)]; matched text is never returned."""
    findings = []
    for path, text in iter_strings(node):
        for kind, pattern in LEAK_PATTERNS:
            if pattern.search(text):
                findings.append((path or "$", kind))
    return findings


def structural_findings(node: object, path: str = "") -> list:
    """Fields that must hold placeholders or markers in a redacted payload."""
    findings = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = join_path(path, key)
            if key in ID_KEYS and isinstance(value, str) and value and not PLACEHOLDER_RE.match(value):
                findings.append((here, "id-not-placeholdered"))
            elif key in TEXT_RULES and isinstance(value, (str, list, dict)) and not only_markers(value):
                findings.append((here, "text-not-redacted"))
            elif key in SUBTREE_RULES and not only_markers(value):
                findings.append((here, "tool-response-not-redacted"))
            elif key in COMMAND_KEYS and not command_redacted(value):
                findings.append((here, "command-args-not-redacted"))
            else:
                findings.extend(structural_findings(value, here))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            findings.extend(structural_findings(item, join_path(path, i)))
    return findings


def only_markers(value: object) -> bool:
    if isinstance(value, str):
        return value == "" or bool(MARKER_RE.match(value))
    if isinstance(value, dict):
        return all(only_markers(item) for item in value.values())
    if isinstance(value, list):
        return all(only_markers(item) for item in value)
    return True


def command_redacted(value: object) -> bool:
    if isinstance(value, str):
        return bool(REDACTED_COMMAND_RE.match(value))
    if isinstance(value, list):
        return len(value) <= 1 or (len(value) == 2 and value[1] == COMMAND_MARKER)
    return True


def scan_file(file: Path) -> list:
    """Findings for one committed file: [(location, kind)]."""
    if file.suffix == ".jsonl":
        return [(str(file), "raw-capture-file")]
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        return [(str(file), f"unreadable-json ({type(err).__name__})")]
    findings = [(f"{file}:{path}", kind) for path, kind in scan_value(data)]
    if isinstance(data, dict) and data.get("schema") == FIXTURE_SCHEMA:
        findings += [(f"{file}:payload.{path}", kind) for path, kind in structural_findings(data.get("payload"))]
    return findings


def scan_paths(paths: Iterable) -> list:
    findings = []
    for root in paths:
        root = Path(root)
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix in (".json", ".jsonl"))
        for file in files:
            findings.extend(scan_file(file))
    return findings


# ---- CLI ---------------------------------------------------------------------------------------------------

def cmd_payload(args: argparse.Namespace) -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError as err:
        print(f"stdin is not JSON: {err}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("stdin must hold a JSON object", file=sys.stderr)
        return 1
    redacted, redactions = Redactor(workspace=args.workspace).redact(payload)
    print(json.dumps({"redactions": redactions, "payload": redacted}, indent=2, ensure_ascii=False))
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    meta = {"host": args.host, "host_version": args.host_version, "install": args.install, "case": args.case,
            "variant": args.variant}
    try:
        records = load_raw_records(Path(args.raw_dir))
    except RedactionError as err:
        print(f"capture failed: {err}", file=sys.stderr)
        return 1
    written = write_fixtures(build_fixtures(records, meta, args.workspace), Path(args.dest))
    leaks = scan_paths(written)
    for where, kind in leaks:
        print(f"LEAK {where} ({kind})", file=sys.stderr)
    print(f"{len(written)} fixture(s) written to {args.dest}")
    return 1 if leaks else 0


def cmd_scan(args: argparse.Namespace) -> int:
    findings = scan_paths(args.paths)
    for where, kind in findings:
        print(f"LEAK {where} ({kind})")
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("payload", help="redact one payload from stdin")
    p.add_argument("--workspace")
    c = sub.add_parser("capture", help="redact one capture into fixtures")
    c.add_argument("--raw-dir", required=True)
    c.add_argument("--dest", required=True)
    c.add_argument("--host", required=True, choices=("claude", "cursor", "codex"))
    c.add_argument("--host-version", required=True)
    c.add_argument("--case", required=True)
    c.add_argument("--install", required=True, choices=("script", "plugin"))
    c.add_argument("--variant")
    c.add_argument("--workspace")
    s = sub.add_parser("scan", help="leak-scan fixture files or folders")
    s.add_argument("paths", nargs="+")
    args = ap.parse_args(argv)
    return {"payload": cmd_payload, "capture": cmd_capture, "scan": cmd_scan}[args.command](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
