#!/usr/bin/env bash
# Offline tests for the capability-probe harness (plan P0: AC-1, AC-2, AC-3, AC-12). No credentials, no model calls.
#
#   scripts/test-probes.sh          run every test; exit 1 on any failure
#   scripts/test-probes.sh -v       verbose unittest output
#
# Covers:
#   - every recorder mode and control option (after, limit, agent, regex keys, concurrency);
#   - redaction rules and placeholder equality (with 2.1.325's dash-encoded scratchpad_dir), plus the leak scan over
#     scripts/probes/fixtures/, results/ and testdata/, and `redact.py rescan --fix` on published files;
#   - fixture, result and case schema validation (the 30 cases), and the probe-mcp JSON-RPC handshake and echo;
#   - the --dry-run action list (a fake `claude` on PATH proves no host call);
#   - the claude flag preflight: a flag missing from --help is confirmed by a parse check against a fake `claude`
#     (accepted and noted as hidden, or missing: a required one blocks, an optional one is dropped);
#   - the isolation and cleanup logic on a fake hub, home and workspace;
#   - the offline pipeline (workspace -> recorder -> observe -> redact -> cleanup) on a synthetic capture;
#   - attribution: a main-thread call can't decide C1-C4, F3, F4 or I1 (only the probe agent's agent_type counts),
#     and the `requires` gate keeps them undecided unless A1 is confirmed for the same host version and install;
#     A1 proves agent_type on the agent's PostToolUse as well as its PreToolUse (the event C1 and C2 decide on);
#   - permissions (T0, 2.1.325): every claude call carries the template's allow rules with --allowedTools; the
#     untrusted-workspace warning without them is inconclusive; denials are classified hook / permission / unknown,
#     and a permission or unknown denial of the probed call is inconclusive unless the case expects one (F1-F4),
#     checked on synthetic streams and end to end through a fake `claude`;
#   - publishing a rerun replaces the same (case, variant, install) entries and fixtures, all or nothing; a not-run
#     entry (budget exhausted, host skipped) keeps the earlier entry and fixtures.
# Synthetic paths, ids and emails below are made up; they exist only in memory or in temp dirs.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HUB PYTHONDONTWRITEBYTECODE=1
exec python3 -B - "$@" <<'PY'
from __future__ import annotations  # Python 3.8+
import json, os, shlex, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HUB = Path(os.environ["HUB"])
PROBES = HUB / "scripts" / "probes"
sys.path.insert(0, str(PROBES))
import isolation, observe, probelib as lib, redact  # noqa: E402

RECORDER = PROBES / "recorder.py"
MCP_SERVER = PROBES / "templates" / "script" / "mcp" / "probe_mcp.py"
RUNNER = PROBES / "run-probes.sh"
TESTDATA = PROBES / "testdata"
EXPECTED_CASES = {"A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "C4", "D1", "E1", "E2", "E3", "E4", "E5",
                  "F1", "F2", "F3", "F4", "G1", "H1", "H2", "I1", "J1", "L1", "M1", "M2", "N1", "K1", "K2"}
SCHEMA_KEYWORDS = {"$schema", "$id", "title", "description", "type", "enum", "required", "properties",
                   "additionalProperties", "items", "$ref", "definitions"}
FAKE_HOME = "/Users/synthetic-user"  # synthetic
FAKE_SESSION = "0b9e3c2a-1f4d-4e8a-9c3b-2d7f6a5e4b10"  # synthetic


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", *lib.GIT_ISOLATION, "-C", str(path), *args], capture_output=True, text=True,
                          check=True).stdout


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="test-probes-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---- recorder (AC-1 tooling) ----------------------------------------------------------------------------------

class RecorderTests(TempDirCase):
    def call(self, payload: object, ctrl: object = None, *extra: str, raw_stdin: str = None):
        ctrl_path = self.tmp / "ctrl.json"
        if ctrl is not None:
            ctrl_path.write_text(ctrl if isinstance(ctrl, str) else json.dumps(ctrl))
        stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
        return subprocess.run([sys.executable, str(RECORDER), "--ctrl", str(ctrl_path),
                               "--out", str(self.tmp / "out" / "raw"), *extra],
                              input=stdin, capture_output=True, text=True, timeout=30)

    def raw(self, event: str) -> list:
        path = self.tmp / "out" / "raw" / f"{event}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    @staticmethod
    def bash(command: str = "echo hi", **extra: object) -> dict:
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, **extra}

    def test_record_is_silent_and_captures_the_payload(self) -> None:
        done = self.call(self.bash(), {})
        self.assertEqual((done.returncode, done.stdout), (0, ""))
        lines = self.raw("PreToolUse")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["payload"]["tool_input"]["command"], "echo hi")
        self.assertEqual((lines[0]["seq"], lines[0]["mode"], lines[0]["tool"]), (1, "record", "Bash"))

    def test_decision_modes_emit_permission_decision_and_reason(self) -> None:
        for mode in ("allow", "deny", "ask"):
            done = self.call(self.bash(), {"PreToolUse:Bash": {"mode": mode, "reason": f"because {mode}"}})
            out = json.loads(done.stdout)["hookSpecificOutput"]
            self.assertEqual(done.returncode, 0)
            self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]), (mode, f"because {mode}"))
            self.assertEqual(out["hookEventName"], "PreToolUse")

    def test_exit2_blocks_with_the_reason_on_stderr(self) -> None:
        done = self.call({"hook_event_name": "Stop"}, {"Stop": {"mode": "exit2", "reason": "keep going"}})
        self.assertEqual((done.returncode, done.stdout), (2, ""))
        self.assertIn("keep going", done.stderr)

    def test_crash_exits_1(self) -> None:
        done = self.call(self.bash(), {"PreToolUse:Bash": {"mode": "crash"}})
        self.assertEqual((done.returncode, done.stdout), (1, ""))

    def test_timeout_sleeps_then_exits_0(self) -> None:
        start = time.monotonic()
        done = self.call(self.bash(), {"PreToolUse:Bash": {"mode": "timeout", "sleep_s": 0.4}})
        self.assertGreaterEqual(time.monotonic() - start, 0.4)
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_invalid_json_mode_prints_unparseable_output(self) -> None:
        done = self.call(self.bash(), {"PreToolUse:Bash": {"mode": "invalid-json"}})
        self.assertEqual(done.returncode, 0)
        with self.assertRaises(ValueError):
            json.loads(done.stdout)

    def test_after_answers_record_for_the_first_n_calls(self) -> None:
        ctrl = {"PreToolUse": {"mode": "deny", "after": 2}}
        modes = [self.call(self.bash(), ctrl).stdout for _ in range(4)]
        self.assertEqual([bool(m) for m in modes], [False, False, True, True])
        self.assertEqual([r["mode"] for r in self.raw("PreToolUse")], ["record", "record", "deny", "deny"])

    def test_limit_applies_the_mode_once(self) -> None:
        ctrl = {"Stop": {"mode": "exit2", "limit": 1}}
        codes = [self.call({"hook_event_name": "Stop"}, ctrl).returncode for _ in range(3)]
        self.assertEqual(codes, [2, 0, 0])

    def test_agent_filter_matches_the_plugin_prefix_only_for_that_agent(self) -> None:
        ctrl = {"PreToolUse": {"mode": "deny", "agent": "probe-reader"}}
        self.assertTrue(self.call(self.bash(agent_type="probe:probe-reader"), ctrl).stdout)
        self.assertTrue(self.call(self.bash(agent_type="probe-reader"), ctrl).stdout)
        self.assertFalse(self.call(self.bash(agent_type="probe-a"), ctrl).stdout)
        self.assertFalse(self.call(self.bash(), ctrl).stdout)

    def test_exact_key_beats_regex_key_beats_event_key(self) -> None:
        ctrl = {"PreToolUse": {"mode": "deny"}, "PreToolUse:Bash": {"mode": "allow"},
                "PreToolUse:mcp__.*": {"mode": "ask"}, "PreToolUse:Edit|Write": {"mode": "deny", "reason": "edit"}}
        decision = lambda payload: json.loads(self.call(payload, ctrl).stdout)["hookSpecificOutput"]  # noqa: E731
        self.assertEqual(decision(self.bash())["permissionDecision"], "allow")
        mcp = {"hook_event_name": "PreToolUse", "tool_name": "mcp__probe-mcp__echo"}
        self.assertEqual(decision(mcp)["permissionDecision"], "ask")
        write = {"hook_event_name": "PreToolUse", "tool_name": "Write"}
        self.assertEqual(decision(write)["permissionDecisionReason"], "edit")
        read = {"hook_event_name": "PreToolUse", "tool_name": "Read"}
        self.assertEqual(decision(read)["permissionDecision"], "deny")

    def test_regex_key_records_the_first_mcp_call_then_denies(self) -> None:
        ctrl = {"PreToolUse:mcp__.*": {"mode": "deny", "after": 1}}
        first = {"hook_event_name": "PreToolUse", "tool_name": "mcp__probe-mcp__echo"}
        second = {"hook_event_name": "PreToolUse", "tool_name": "mcp__plugin_probe_probe-mcp__echo"}
        self.assertEqual(self.call(first, ctrl).stdout, "")
        self.assertIn("deny", self.call(second, ctrl).stdout)

    def test_missing_control_file_records(self) -> None:
        done = self.call(self.bash(), None)
        self.assertEqual((done.returncode, done.stdout), (0, ""))
        self.assertEqual(len(self.raw("PreToolUse")), 1)

    def test_invalid_control_file_is_logged_and_answered_with_record(self) -> None:
        for ctrl in ("{not json", {"PreToolUse": {"mode": "explode"}}, {"PreToolUse:(": {"mode": "deny"}}):
            done = self.call(self.bash(), ctrl)
            self.assertEqual((done.returncode, done.stdout), (0, ""))
        self.assertEqual(len(self.raw("_errors")), 3)
        self.assertEqual(len(self.raw("PreToolUse")), 3)

    def test_non_json_stdin_is_kept_unparsed(self) -> None:
        done = self.call(None, {}, "--event", "PreToolUse", raw_stdin="not json at all")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(self.raw("PreToolUse")[0]["payload"], {"_unparsed_text": "not json at all"})

    def test_tag_and_cursor_dialect(self) -> None:
        payload = {"hook_event_name": "beforeShellExecution", "command": "touch x"}
        done = self.call(payload, {"beforeShellExecution": {"mode": "deny", "reason": "no"}},
                         "--dialect", "cursor", "--tag", "claude-import")
        self.assertEqual(json.loads(done.stdout), {"permission": "deny", "user_message": "no", "agent_message": "no"})
        self.assertEqual(self.raw("beforeShellExecution")[0]["tag"], "claude-import")

    def test_concurrent_calls_get_unique_ordered_seq(self) -> None:
        (self.tmp / "ctrl.json").write_text("{}")
        argv = [sys.executable, str(RECORDER), "--ctrl", str(self.tmp / "ctrl.json"),
                "--out", str(self.tmp / "out" / "raw")]
        procs = [subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                 for _ in range(12)]
        for i, proc in enumerate(procs):
            proc.communicate(json.dumps(self.bash(f"echo probe-{i}")), timeout=30)
        self.assertEqual(sorted(r["seq"] for r in self.raw("PreToolUse")), list(range(1, 13)))


# ---- redaction (AC-3) -----------------------------------------------------------------------------------------

def a2_payloads() -> list:
    """Synthetic A2 capture: two background agents, each with its own id."""
    base = {"session_id": FAKE_SESSION, "transcript_path": f"{FAKE_HOME}/.claude/projects/-Users-x/{FAKE_SESSION}.jsonl"}
    out = []
    for agent_id, name in (("a7f3c9e1aa", "probe-a"), ("b8e2d0f2bb", "probe-b")):
        out.append({**base, "hook_event_name": "SubagentStart", "agent_id": agent_id, "agent_type": name})
        for n in (1, 2, 3):
            out.append({**base, "hook_event_name": "PreToolUse", "agent_id": agent_id, "agent_type": name,
                        "tool_name": "Bash", "tool_input": {"command": f"echo {name}-{n}"}})
    return out


class RedactTests(unittest.TestCase):
    def redact_one(self, payload: dict, **kw: str) -> tuple:
        return redact.Redactor(home="/nonexistent-home", **kw).redact(payload)

    def test_text_fields_and_tool_contents_are_redacted(self) -> None:
        payload = {"prompt": "secret plan", "last_assistant_message": "done it",
                   "tool_input": {"content": "file body", "new_string": "new", "old_string": "old",
                                  "edits": [{"old_string": "a", "new_string": "b"}]},
                   "tool_response": {"stdout": "output", "stderr": "", "interrupted": False, "lines": ["x"]}}
        out, _ = self.redact_one(payload)
        self.assertEqual(out["prompt"], "<REDACTED:prompt>")
        self.assertEqual(out["last_assistant_message"], "<REDACTED:assistant-message>")
        self.assertEqual(out["tool_input"]["content"], "<REDACTED:tool-content>")
        self.assertEqual(out["tool_input"]["edits"][0]["new_string"], "<REDACTED:tool-content>")
        self.assertEqual(out["tool_response"], {"stdout": "<REDACTED:tool-response>", "stderr": "",
                                                "interrupted": False, "lines": ["<REDACTED:tool-response>"]})

    def test_command_keeps_only_its_first_word(self) -> None:
        out, _ = self.redact_one({"tool_input": {"command": "  curl -sI https://example.com  "}, "command": "ls",
                                  "cmd": ["bash", "-lc", "rm -rf x"]})
        self.assertEqual(out["tool_input"]["command"], "curl <REDACTED:command-args>")
        self.assertEqual(out["command"], "ls")
        self.assertEqual(out["cmd"], ["bash", "<REDACTED:command-args>"])

    def test_paths_and_emails(self) -> None:
        ws = "/private/var/folders/ab/cd123/T/daedalus-probes/x/A1/script"
        out, _ = self.redact_one({"cwd": f"{ws}/repo", "file_path": f"{FAKE_HOME}/notes.txt",
                                  "other": "/var/folders/zz/yy/T/elsewhere", "who": "write to someone@example.org",
                                  "win": "C:\\Users\\someone\\x"}, workspace=ws)
        self.assertEqual(out["cwd"], "<WORKSPACE>/repo")
        self.assertEqual(out["file_path"], "<HOME>/notes.txt")
        self.assertEqual(out["other"], "<TMP>/elsewhere")
        self.assertEqual(out["who"], "write to <EMAIL>")
        self.assertEqual(out["win"], "<HOME>\\x")

    def test_ids_get_stable_placeholders_that_keep_equality(self) -> None:
        redactor = redact.Redactor(home="/nonexistent-home")
        first, _ = redactor.redact({"session_id": FAKE_SESSION, "agent_id": "a7f3c9e1aa"})
        second, _ = redactor.redact({"session_id": FAKE_SESSION, "agent_id": "b8e2d0f2bb"})
        third, _ = redactor.redact({"agent_id": "a7f3c9e1aa", "conversation_id": FAKE_SESSION})
        self.assertEqual(first["session_id"], second["session_id"])
        self.assertEqual(first["session_id"], "<SESSION-1>")
        self.assertNotEqual(first["agent_id"], second["agent_id"])
        self.assertEqual(first["agent_id"], third["agent_id"])
        self.assertEqual(third["conversation_id"], "<SESSION-1>")

    def test_an_id_inside_a_path_gets_the_same_placeholder(self) -> None:
        path = f"{FAKE_HOME}/.claude/projects/-Users-synthetic-user-repo/{FAKE_SESSION}/subagents/agent-a7f3c9e1aa.jsonl"
        out, _ = self.redact_one({"agent_transcript_path": path, "session_id": FAKE_SESSION, "agent_id": "a7f3c9e1aa"})
        self.assertEqual(out["agent_transcript_path"],
                         "<HOME>/.claude/projects/<PROJECT>/<SESSION-1>/subagents/agent-<AGENT-1>.jsonl")

    def test_other_uuids_become_id_placeholders(self) -> None:
        out, _ = self.redact_one({"note": "see 123e4567-e89b-42d3-a456-426614174000"})
        self.assertEqual(out["note"], "see <ID-1>")

    def test_key_order_non_strings_and_identity_fields_are_kept(self) -> None:
        payload = {"z": 1, "agent_type": "probe-reader", "a": True, "hook_event_name": "PreToolUse", "m": None}
        out, redactions = self.redact_one(payload)
        self.assertEqual(list(out), list(payload))
        self.assertEqual(out, payload)
        self.assertEqual(redactions, [])

    def test_redactions_list_every_rule_applied(self) -> None:
        _, redactions = self.redact_one({"session_id": FAKE_SESSION, "prompt": "x",
                                         "tool_input": {"command": "echo hi"}})
        self.assertEqual(redactions, [{"path": "session_id", "rule": "id"}, {"path": "prompt", "rule": "prompt"},
                                      {"path": "tool_input.command", "rule": "command-args"}])

    def test_identity_consistency_survives_redaction(self) -> None:
        raw = a2_payloads()
        redactor = redact.Redactor(home="/nonexistent-home")
        redacted = [redactor.redact(p)[0] for p in raw]
        names = ["probe-a", "probe-b"]
        self.assertEqual(observe.identity_consistency(raw, names)[0], observe.PASS)
        self.assertEqual(observe.identity_consistency(redacted, names)[0], observe.PASS)
        mixed = [dict(p) for p in raw]
        mixed[-1]["agent_id"] = "a7f3c9e1aa"  # probe-b's last call carries probe-a's id
        redactor = redact.Redactor(home="/nonexistent-home")
        self.assertEqual(observe.identity_consistency(mixed, names)[0], observe.FAIL)
        self.assertEqual(observe.identity_consistency([redactor.redact(p)[0] for p in mixed], names)[0], observe.FAIL)

    def test_capture_writes_schema_valid_clean_fixtures(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="test-probes-capture-"))
        try:
            raw = tmp / "raw"
            raw.mkdir()
            for seq, payload in enumerate(a2_payloads(), 1):
                event = payload["hook_event_name"]
                with (raw / f"{event}.jsonl").open("a") as fh:
                    fh.write(json.dumps({"seq": seq, "event": event, "mode": "record", "tag": None,
                                         "payload": payload}) + "\n")
            (raw / "_errors.jsonl").write_text("")
            dest = tmp / "fixtures" / "claude-9.9.9" / "A2" / "script"
            done = subprocess.run([sys.executable, str(PROBES / "redact.py"), "capture", "--raw-dir", str(raw),
                                   "--dest", str(dest), "--host", "claude", "--host-version", "9.9.9",
                                   "--case", "A2", "--install", "script"], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            names = sorted(p.name for p in dest.glob("*.json"))
            self.assertEqual(names, ["PreToolUse-1.json", "PreToolUse-2.json", "PreToolUse-3.json",
                                     "PreToolUse-4.json", "PreToolUse-5.json", "PreToolUse-6.json",
                                     "SubagentStart-1.json", "SubagentStart-2.json"])
            fixtures = [json.loads(p.read_text()) for p in sorted(dest.glob("*.json"))]
            self.assertEqual(sorted(f["seq"] for f in fixtures), list(range(1, 9)))
            for fixture in fixtures:
                self.assertEqual(lib.schema_errors(fixture, "probe-fixture.schema.json"), [])
            self.assertEqual(redact.scan_paths([dest]), [])
            payloads = [f["payload"] for f in fixtures]
            self.assertEqual(observe.identity_consistency(payloads, ["probe-a", "probe-b"])[0], observe.PASS)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_encoded_scratchpad_dir_comes_out_clean(self) -> None:
        """Regression (39cf56d-1): 2.1.325's scratchpad_dir holds the per-user temp folder (dash-encoded) and uid."""
        macos_ws = "/private/var/folders/ab/cd123efg/T/daedalus-probes/20260101T000000Z/E1.default/script"
        macos = (f"/private/tmp/claude-1234/-private-var-folders-ab-cd123efg-T-daedalus-probes-20260101T000000Z-"
                 f"E1-default-script-repo/{FAKE_SESSION}/scratchpad")
        linux_ws = "/tmp/daedalus-probes/20260101T000000Z/E1/script"
        linux = f"/tmp/claude-1000/-tmp-daedalus-probes-20260101T000000Z-E1-script-repo/{FAKE_SESSION}/scratchpad"
        for label, workspace, scratchpad in (("macos", macos_ws, macos), ("macos, no workspace", None, macos),
                                             ("linux", linux_ws, linux)):
            with self.subTest(label):
                kw = {"workspace": workspace} if workspace else {}
                out, redactions = self.redact_one({"session_id": FAKE_SESSION, "scratchpad_dir": scratchpad}, **kw)
                self.assertEqual(out["scratchpad_dir"], "<TMP>/<PROJECT>/<SESSION-1>/scratchpad")
                rules = {r["rule"] for r in redactions if r["path"] == "scratchpad_dir"}
                self.assertTrue({"temp-path", "project-folder"} <= rules, rules)
                self.assertEqual(redact.scan_value(out), [])

    def test_encoded_home_and_project_folders(self) -> None:
        out, _ = self.redact_one({"a": "/x/-Users-some-one-Documents-proj/y", "b": "-home-someone-proj",
                                  "c": "C--Users-someone-proj", "d": "/tmp/claude-1234",
                                  "e": "/var/folders/ab/cd/T/claude-1234/-x/s"})
        self.assertEqual(out, {"a": "/x/<PROJECT>/y", "b": "<PROJECT>", "c": "C-<PROJECT>", "d": "<TMP>",
                               "e": "<TMP>/-x/s"})
        custom, _ = redact.Redactor(home="/srv/people/someone").redact({"p": "/q/-srv-people-someone-proj/r"})
        self.assertEqual(custom["p"], "/q/<PROJECT>/r")
        kept = {"fixture": "claude-2.1.325/A1/script/PreToolUse-1", "t": "<HOME>/.claude/projects/<PROJECT>/x.jsonl",
                "word": "x-root-y"}  # a one-component home (/root) gets no encoded pattern
        self.assertEqual(redact.Redactor(home="/root").redact(kept)[0], kept)


# ---- leak scan over committed fixtures (AC-3) -----------------------------------------------------------------

class LeakScanTests(TempDirCase):
    def fixture(self, payload: dict) -> Path:
        doc = {"schema": redact.FIXTURE_SCHEMA, "host": "claude", "host_version": "0", "install": "script",
               "case": "X", "event": "PreToolUse", "seq": 1, "redactions": [], "payload": payload}
        path = self.tmp / f"f{len(list(self.tmp.iterdir()))}.json"
        path.write_text(json.dumps(doc))
        return path

    def test_scanner_flags_every_leak_kind(self) -> None:
        cases = {
            "home-path": {"cwd": f"{FAKE_HOME}/repo"},
            "encoded-home": {"transcript_path": "<HOME>/.claude/projects/-Users-someone-repo/x.jsonl"},
            "temp-path": {"cwd": "/var/folders/ab/cd/T/x"},
            "encoded-temp-path": {"scratchpad_dir": "<TMP>/-private-var-folders-ab-cd-T-x/<SESSION-1>/scratchpad"},
            "claude-temp-root": {"scratchpad_dir": "/private/tmp/claude-1234/<PROJECT>/<SESSION-1>/scratchpad"},
            "email": {"note": "someone@example.org"},
            "uuid": {"note": FAKE_SESSION},
            "text-not-redacted": {"prompt": "the user's real words"},
            "command-args-not-redacted": {"tool_input": {"command": "echo the real args"}},
            "id-not-placeholdered": {"agent_id": "a7f3c9e1aa"},
            "tool-response-not-redacted": {"tool_response": {"stdout": "real output"}},
        }
        for kind, payload in cases.items():
            kinds = {k for _, k in redact.scan_file(self.fixture(payload))}
            self.assertIn(kind, kinds, f"{kind} not flagged")
        (self.tmp / "raw.jsonl").write_text("{}\n")
        self.assertIn("raw-capture-file", {k for _, k in redact.scan_paths([self.tmp])})

    def test_scan_cli_reports_location_but_never_the_matched_text(self) -> None:
        self.fixture({"prompt": "TOP-SECRET-WORDS", "note": "someone@example.org"})
        done = subprocess.run([sys.executable, str(PROBES / "redact.py"), "scan", str(self.tmp)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("TOP-SECRET-WORDS", done.stdout)
        self.assertNotIn("someone@example.org", done.stdout)
        self.assertIn("text-not-redacted", done.stdout)

    def test_the_scratchpad_dir_published_before_the_fix_fails_the_scan(self) -> None:
        """Regression (39cf56d-1): the raw form, and the form 39cf56d published (only the session id replaced)."""
        encoded = "-private-var-folders-ab-cd123efg-T-daedalus-probes-20260101T000000Z-E1-default-script-repo"
        for label, value in (("raw", f"/private/tmp/claude-1234/{encoded}/{FAKE_SESSION}/scratchpad"),
                             ("39cf56d", f"/private/tmp/claude-1234/{encoded}/<SESSION-1>/scratchpad")):
            with self.subTest(label):
                kinds = {k for _, k in redact.scan_file(self.fixture({"scratchpad_dir": value}))}
                self.assertTrue({"encoded-temp-path", "claude-temp-root"} <= kinds, kinds)
        clean = self.fixture({"scratchpad_dir": "<TMP>/<PROJECT>/<SESSION-1>/scratchpad",
                              "note": "claude-2.1.325/A1/script/PreToolUse-1"})
        self.assertEqual(redact.scan_file(clean), [])

    def test_committed_fixtures_results_and_testdata_have_no_leaks(self) -> None:
        findings = redact.scan_paths([lib.FIXTURES_DIR, lib.RESULTS_DIR, TESTDATA])
        self.assertEqual(findings, [], "redaction leak in committed probe data")

    def test_committed_fixtures_and_results_need_no_rescan(self) -> None:
        """The published files already follow the current path rules (redact.py rescan finds nothing to change)."""
        done = subprocess.run([sys.executable, str(PROBES / "redact.py"), "rescan", str(lib.FIXTURES_DIR),
                               str(lib.RESULTS_DIR)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("0 file(s) to rewrite", done.stdout)

    def test_committed_fixtures_and_results_match_their_schemas(self) -> None:
        checked = 0
        for root in (lib.FIXTURES_DIR, TESTDATA, lib.RESULTS_DIR):
            for path in sorted(root.rglob("*.json")) if root.is_dir() else []:
                doc = json.loads(path.read_text())
                schema = {redact.FIXTURE_SCHEMA: "probe-fixture.schema.json",
                          lib.RESULT_SCHEMA: "probe-result.schema.json"}.get(doc.get("schema"))
                self.assertIsNotNone(schema, f"{path.name}: unknown schema {doc.get('schema')!r}")
                self.assertEqual(lib.schema_errors(doc, schema), [], path.name)
                checked += 1
        self.assertGreater(checked, 0)

    def test_synthetic_result_lists_the_current_a1_checks(self) -> None:
        """The synthetic sample must follow A1's observations (it went stale when A1 gained agent-type-after)."""
        doc = json.loads((TESTDATA / "results" / "claude-0.0.0-synthetic.json").read_text())
        entry = next(e for e in doc["entries"] if (e["case"], e["install"]) == ("A1", "script"))
        observations = lib.load_cases("A1")[0]["observations"]
        self.assertEqual([(c["check"], c["role"], c["expected"]) for c in entry["observations"]],
                         [(o["id"], o["role"], observe.describe_expected(o, "script")) for o in observations])
        self.assertEqual(entry["status"], "confirmed")


class RescanTests(TempDirCase):
    """39cf56d-1: `redact.py rescan --fix` re-redacts published files in place, once, and touches nothing else."""

    ENCODED = "-private-var-folders-ab-cd123efg-T-daedalus-probes-20260101T000000Z-E1-default-script-repo"

    def published(self) -> tuple:
        """A fixture as 39cf56d published it, a results file and an unrelated JSON file; returns their paths."""
        fixture = {"schema": redact.FIXTURE_SCHEMA, "host": "claude", "host_version": "9.9.9", "install": "script",
                   "case": "E1", "variant": "default", "event": "PreToolUse", "seq": 3, "mode": "record", "tag": None,
                   "redactions": [{"path": "session_id", "rule": "id"}, {"path": "scratchpad_dir", "rule": "id"}],
                   "payload": {"session_id": "<SESSION-1>", "cwd": "<WORKSPACE>/repo",
                               "scratchpad_dir": f"/private/tmp/claude-1234/{self.ENCODED}/<SESSION-1>/scratchpad",
                               "agent_id": "<AGENT-2>", "tool_input": {"command": "touch <REDACTED:command-args>"}}}
        results = {"schema": lib.RESULT_SCHEMA, "host": "claude", "host_version": "9.9.9", "generated_at": "x",
                   "entries": [{"case": "E1", "fixture_ids": ["claude-9.9.9/E1.default/script/PreToolUse-1"]}]}
        paths = (self.tmp / "fixtures" / "E1.default" / "script" / "PreToolUse-1.json",
                 self.tmp / "results" / "claude-9.9.9.json", self.tmp / "fixtures" / "other.json")
        other = {"path": ".claude/projects/some-folder"}  # a path rule would change it, the leak scan doesn't flag it
        for path, doc in zip(paths, (fixture, results, other)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(redact.dump_document(doc))
        return paths

    def rescan(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(PROBES / "redact.py"), "rescan", *args, str(self.tmp / "fixtures"),
                               str(self.tmp / "results")], capture_output=True, text=True)

    def test_fix_cleans_the_fixture_and_appends_the_rules(self) -> None:
        fixture_path, results_path, other_path = self.published()
        before = json.loads(fixture_path.read_text())
        untouched = (results_path.read_text(), other_path.read_text())
        check = self.rescan()
        self.assertEqual(check.returncode, 1, check.stdout)
        self.assertIn("1 file(s) to rewrite", check.stdout)
        self.assertEqual(json.loads(fixture_path.read_text()), before, "rescan without --fix must not write")
        done = self.rescan("--fix")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        after = json.loads(fixture_path.read_text())
        self.assertEqual(after["payload"]["scratchpad_dir"], "<TMP>/<PROJECT>/<SESSION-1>/scratchpad")
        self.assertEqual(after["redactions"], before["redactions"] + [{"path": "scratchpad_dir", "rule": "temp-path"},
                                                                      {"path": "scratchpad_dir",
                                                                       "rule": "project-folder"}])
        self.assertEqual({k: v for k, v in after.items() if k not in ("payload", "redactions")},
                         {k: v for k, v in before.items() if k not in ("payload", "redactions")})  # seq, case, ...
        self.assertEqual(list(after["payload"]), list(before["payload"]))
        self.assertEqual(dict(after["payload"], scratchpad_dir=None), dict(before["payload"], scratchpad_dir=None))
        self.assertEqual(lib.schema_errors(after, "probe-fixture.schema.json"), [])
        self.assertEqual((results_path.read_text(), other_path.read_text()), untouched)
        self.assertEqual(redact.scan_paths([fixture_path, results_path]), [])

    def test_fix_is_idempotent_and_matches_a_fresh_capture(self) -> None:
        fixture_path, _, _ = self.published()
        self.assertEqual(self.rescan("--fix").returncode, 0)
        once = fixture_path.read_text()
        again = self.rescan("--fix")
        self.assertEqual(again.returncode, 0, again.stdout)
        self.assertIn("0 file(s) rewritten", again.stdout)
        self.assertEqual(fixture_path.read_text(), once)
        self.assertEqual(self.rescan().returncode, 0)
        raw = {"scratchpad_dir": f"/private/tmp/claude-1234/{self.ENCODED}/{FAKE_SESSION}/scratchpad",
               "session_id": FAKE_SESSION}
        fresh, _ = redact.Redactor(home="/nonexistent-home").redact(raw)
        self.assertEqual(fresh["scratchpad_dir"], json.loads(once)["payload"]["scratchpad_dir"])


# ---- cases and schemas (AC-2) ---------------------------------------------------------------------------------

class CaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = {c["id"]: c for c in lib.load_cases("all")}

    def test_all_30_cases_exist_and_validate(self) -> None:
        self.assertEqual(set(self.cases), EXPECTED_CASES)

    def test_case_files_pass_the_profile_validator_cli(self) -> None:
        for path in lib.case_paths():
            done = subprocess.run([sys.executable, str(lib.VALIDATOR), str(path), "--schema",
                                   str(lib.SCHEMA_DIR / "probe-case.schema.json")], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{path.name}: {done.stdout}")

    def test_install_and_host_applicability(self) -> None:
        for cid, case in self.cases.items():
            applies = case["applies_to"]
            if cid in ("K1", "K2"):
                self.assertEqual(applies["hosts"], ["cursor"] if cid == "K1" else ["codex"])
            elif cid == "N1":
                self.assertEqual(applies["installs"], ["plugin"])  # S+P together: one plugin run with both agents
            else:
                self.assertEqual(applies["installs"], ["script", "plugin"], cid)
                self.assertEqual(applies["hosts"], ["claude"], cid)
        self.assertEqual(self.cases["I1"]["applies_to"]["os"], ["darwin", "linux"])
        c4 = {o["id"]: o for o in self.cases["C4"]["observations"]}
        self.assertEqual(c4["frontmatter-hook"]["expect_by_install"], {"script": "present", "plugin": "absent"})

    def test_e_cases_map_failure_modes_with_and_without_on_failure(self) -> None:
        modes = {"E1": "crash", "E2": "timeout", "E3": "invalid-json", "E5": "exit2"}
        for cid, mode in modes.items():
            self.assertEqual(self.cases[cid]["ctrl"][0]["mode"], mode)
        self.assertEqual(self.cases["E4"]["ctrl"], [])
        self.assertTrue(self.cases["E4"]["vars"]["interpreter"].startswith("/nonexistent/"))
        root = Path(tempfile.gettempdir()) / "unused" / "daedalus-probes" / "ts"
        for cid in sorted(modes) + ["E4"]:
            runs, _ = lib.plan_runs([self.cases[cid]], ("script",), "claude", root)
            self.assertEqual([r.variant_id for r in runs], ["default", "on-failure-block"])
            for run in runs:
                settings = json.loads(next(a for a in lib.build_actions(run, "0", root) if a.kind == "render")
                                      .params["content"])
                hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
                self.assertEqual(hook.get("onFailure"), None if run.variant_id == "default" else "block")

    def test_every_run_renders_valid_files_without_leftover_tokens(self) -> None:
        root = Path(tempfile.gettempdir()) / "unused" / "daedalus-probes" / "ts"
        total = 0
        for host in lib.HOSTS:
            runs, _ = lib.plan_runs(list(self.cases.values()), lib.INSTALLS, host, root)
            for run in runs:
                for action in lib.build_actions(run, "0", root / "staged"):
                    if action.kind == "render":
                        if action.params["dest"].endswith(".json"):
                            json.loads(action.params["content"])
                        self.assertNotIn("{{", action.params["content"], f"{run.label} {action.params['dest']}")
                    if action.kind == "host":
                        self.assertNotIn("{{", " ".join(action.params["argv"]))
                total += 1
        self.assertEqual(total, 70)

    def test_validate_case_rejects_bad_definitions(self) -> None:
        good = json.loads((lib.CASES_DIR / "A1.json").read_text())
        path = lib.CASES_DIR / "A1.json"
        bad_mode = json.loads(json.dumps(good)); bad_mode["ctrl"] = [{"key": "PreToolUse", "mode": "explode"}]
        bad_dest = json.loads(json.dumps(good)); bad_dest["files"]["script"][0]["dest"] = "repo/../../escape.json"
        dup_obs = json.loads(json.dumps(good)); dup_obs["observations"].append(good["observations"][0])
        no_tpl = json.loads(json.dumps(good)); no_tpl["files"]["script"][0]["template"] = "script/missing.json"
        bad_kind = json.loads(json.dumps(good)); bad_kind["observations"][1].pop("field")
        extra = json.loads(json.dumps(good)); extra["surprise"] = 1
        for label, case in (("mode", bad_mode), ("dest", bad_dest), ("dup", dup_obs), ("template", no_tpl),
                            ("field", bad_kind), ("extra", extra)):
            self.assertTrue(lib.validate_case(case, path), f"{label} accepted")

    def test_validate_case_rejects_variant_ids_that_leave_the_workspace(self) -> None:
        """Variant ids become a path segment (<case>.<variant>) that mkdir and render write to."""
        path = lib.CASES_DIR / "E1.json"
        good = json.loads(path.read_text())
        self.assertEqual(lib.validate_case(good, path), [])
        for bad_id in ("../../escape", "a/b", "..", "a\\b", "x..y", ""):
            case = json.loads(json.dumps(good))
            case["variants"][1]["id"] = bad_id
            errors = lib.validate_case(case, path)
            self.assertTrue(any("variant id" in e for e in errors), f"{bad_id!r} accepted: {errors}")

    def test_schemas_stay_inside_the_validator_subset(self) -> None:
        def walk(node: dict, where: str) -> None:
            self.assertFalse(set(node) - SCHEMA_KEYWORDS, f"{where}: {set(node) - SCHEMA_KEYWORDS}")
            if "additionalProperties" in node:
                self.assertIsInstance(node["additionalProperties"], bool, where)
            if "$ref" in node:
                self.assertTrue(node["$ref"].startswith("#/definitions/"), where)
            for key, child in node.get("properties", {}).items():
                walk(child, f"{where}.properties.{key}")
            for key, child in node.get("definitions", {}).items():
                walk(child, f"{where}.definitions.{key}")
            if isinstance(node.get("items"), dict):
                walk(node["items"], f"{where}.items")
        for name in ("probe-case", "probe-fixture", "probe-result"):
            walk(json.loads((lib.SCHEMA_DIR / f"{name}.schema.json").read_text()), name)


# ---- probe-mcp server (M2) ------------------------------------------------------------------------------------

class McpServerTests(unittest.TestCase):
    def test_handshake_list_echo_and_errors(self) -> None:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "one"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
            {"jsonrpc": "2.0", "id": 6, "method": "ping"},
        ]
        stdin = "\n".join(json.dumps(m) for m in messages) + "\n{broken\n"
        done = subprocess.run([sys.executable, str(MCP_SERVER)], input=stdin, capture_output=True, text=True,
                              timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        replies = [json.loads(line) for line in done.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5, 6, None])  # no reply to the notification
        init = replies[0]["result"]
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        self.assertEqual(init["serverInfo"]["name"], "probe-mcp")
        self.assertIn("tools", init["capabilities"])
        self.assertEqual([t["name"] for t in replies[1]["result"]["tools"]], ["echo"])
        self.assertEqual(replies[2]["result"], {"content": [{"type": "text", "text": "one"}], "isError": False})
        self.assertEqual(replies[3]["error"]["code"], -32602)
        self.assertEqual(replies[4]["error"]["code"], -32601)
        self.assertEqual(replies[5]["result"], {})
        self.assertEqual(replies[6]["error"]["code"], -32700)

    def test_unknown_protocol_version_falls_back_to_the_latest(self) -> None:
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
        done = subprocess.run([sys.executable, str(MCP_SERVER)], input=json.dumps(msg) + "\n",
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(done.stdout)["result"]["protocolVersion"], "2025-06-18")


# ---- runner: --dry-run and the budget guard (AC-1) ------------------------------------------------------------

class DryRunTests(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.sentinel = self.tmp / "host-was-called"
        for name in ("claude", "agent", "codex"):
            fake = self.bin / name
            fake.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(self.sentinel))}\n")
            fake.chmod(0o755)
        self.tmpdir = self.tmp / "tmpdir"
        self.tmpdir.mkdir()

    def dry(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, TMPDIR=str(self.tmpdir), PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        return subprocess.run(["bash", str(RUNNER), "--dry-run", *args], capture_output=True, text=True, env=env,
                              timeout=120)

    def assert_no_side_effects(self) -> None:
        self.assertFalse(self.sentinel.exists(), "a host CLI was invoked during --dry-run")
        self.assertEqual(list(self.tmpdir.iterdir()), [], "--dry-run wrote into TMPDIR")

    def test_action_list_for_both_installs(self) -> None:
        done = self.dry("--case", "A1", "--install", "both")
        self.assertEqual(done.returncode, 0, done.stderr)
        out = done.stdout
        self.assertIn("plan: 2 run(s) from 1 case(s); host claude", out)
        for needle in ("run A1/script", "run A1/plugin", "mkdir: create", "git-init: git init", "copy: copy",
                       "render templates/script/settings.json", "render templates/plugin/hooks.json",
                       "--model haiku --max-turns 8 --max-budget-usd 0.25 --output-format stream-json",
                       "--plugin-dir", "ctrl: write", "observe: evaluate 5 observation(s)", "redact: redact",
                       "cleanup: remove repo/.claude", "isolation: would snapshot", "isolation: would compare",
                       "leak scan: would scan", "publish: would copy", "no model calls were made"):
            self.assertIn(needle, out)
        self.assertIn(str(self.tmpdir / "daedalus-probes"), out)
        host_lines = [line for line in out.splitlines() if ". host: run in" in line]
        self.assertEqual(len(host_lines), 2)
        self.assertNotIn("--plugin-dir", host_lines[0])  # script install
        self.assertIn("--plugin-dir", host_lines[1])  # plugin install
        self.assert_no_side_effects()

    def test_every_claude_host_line_passes_the_allow_rules(self) -> None:
        """T0 (2.1.325): the project allow rules are ignored in an untrusted folder, so the host call carries them."""
        done = self.dry("--case", "E1")
        self.assertEqual(done.returncode, 0, done.stderr)
        host_lines = [line for line in done.stdout.splitlines() if ". host: run in" in line]
        self.assertEqual(len(host_lines), 4)  # two variants, two installs
        rules = " ".join(shlex.quote(r) for r in json.loads(
            (lib.TEMPLATES_DIR / "script" / "settings.failure.json").read_text())["permissions"]["allow"])
        for line in host_lines:
            self.assertTrue(line.endswith(f"--allowedTools {rules}"), line)
        self.assertIn("optional, with fallbacks: --max-budget-usd, --plugin-dir, --permission-mode, --allowedTools",
                      done.stdout)
        every = [line for line in self.dry("--case", "all").stdout.splitlines() if ". host: run in" in line]
        self.assertEqual(sum("--allowedTools Read Grep Glob Edit Write" in line for line in every), 65)
        self.assert_no_side_effects()

    def test_a_case_without_its_required_case_is_flagged_in_the_plan(self) -> None:
        done = self.dry("--case", "C1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("note: C1 requires A1 confirmed in the same run; A1 isn't selected, so C1 will be "
                      "inconclusive", done.stdout)
        self.assertNotIn("note:", self.dry("--case", "all").stdout)
        self.assert_no_side_effects()

    def test_all_cases_plan_65_claude_runs_and_skip_k(self) -> None:
        done = self.dry("--case", "all")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("plan: 65 run(s) from 30 case(s)", done.stdout)
        self.assertIn("skip K1 (-): host claude not in cursor", done.stdout)
        self.assertIn("skip N1 (script): install type does not apply", done.stdout)
        self.assertEqual(done.stdout.count("\nrun "), 65)
        self.assert_no_side_effects()

    def test_cursor_and_codex_commands(self) -> None:
        cursor = self.dry("--case", "K1", "--host", "cursor")
        self.assertEqual(cursor.returncode, 0, cursor.stderr)
        self.assertIn("plan: 3 run(s)", cursor.stdout)
        self.assertIn("agent -p", cursor.stdout)
        self.assertIn("docs-only [D]", cursor.stdout)
        codex = self.dry("--case", "K2", "--host", "codex")
        self.assertIn("codex exec --json", codex.stdout)
        self.assert_no_side_effects()

    def test_unknown_case_is_refused(self) -> None:
        done = self.dry("--case", "Z9")
        self.assertEqual(done.returncode, 2)
        self.assertIn("unknown case", done.stderr)

    def test_budget_guard(self) -> None:
        with self.assertRaises(lib.GuardError):
            lib.check_budget(False, None, 1.0)
        with self.assertRaises(lib.GuardError):
            lib.check_budget(False, 0.5, 1.0)
        with self.assertRaises(lib.GuardError):
            lib.check_budget(False, 0, 0.0)
        lib.check_budget(False, 2.0, 1.0)
        lib.check_budget(True, None, 99.0)

    def test_budget_exhaustion_records_runs_without_starting_them(self) -> None:
        case = json.loads((lib.CASES_DIR / "A3.json").read_text())
        root = self.tmp / "daedalus-probes" / "ts"
        runs, _ = lib.plan_runs([case], lib.INSTALLS, "claude", root)
        entries, failures, lines = [], [], []
        lib.run_all(runs, "9.9.9", frozenset(), 0.05, root / "staged", None, entries, failures, lines.append)
        self.assertEqual([e["status"] for e in entries], ["inconclusive", "inconclusive"])
        self.assertTrue(all("not run: budget exhausted" in e["notes"] for e in entries))
        self.assertEqual((failures, lines), ([], []))
        self.assertFalse(root.exists(), "no workspace may be created for a run the budget can't cover")
        self.assertFalse(self.sentinel.exists())

    def test_finish_publishes_nothing_after_a_failure(self) -> None:
        staging = self.tmp / "daedalus-probes" / "ts" / "staged"
        before = sorted(p.name for p in lib.FIXTURES_DIR.rglob("*"))
        lines = []
        code = lib.finish(staging, "claude", "9.9.9", [], None, ["A1/script: cleanup left x"], lines.append)
        self.assertEqual(code, 1)
        self.assertIn("nothing published", lines[-1])
        self.assertEqual(sorted(p.name for p in lib.FIXTURES_DIR.rglob("*")), before)
        self.assertFalse((lib.RESULTS_DIR / "claude-9.9.9.json").exists())

    def test_enabled_plugins_never_names_other_plugins(self) -> None:
        text = "daedalus@daedalus enabled\nsecret-tool@private-market enabled\ndaedalus-qa@daedalus"
        self.assertEqual(lib.enabled_plugins(text), ["daedalus", "daedalus-qa", "other:1"])
        self.assertIsNone(lib.enabled_plugins(None))

    def test_dry_run_leaves_home_and_the_hub_untouched(self) -> None:
        """AC-1: no writes to the user scope or the hub, checked with the harness's own isolation snapshot."""
        home = self.tmp / "home"
        home.mkdir()
        before = isolation.snapshot(HUB, home)
        env = dict(os.environ, HOME=str(home), TMPDIR=str(self.tmpdir),
                   PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        for args in (("--case", "all", "--install", "both"), ("--case", "K1", "--host", "cursor"),
                     ("--case", "K2", "--host", "codex")):
            done = subprocess.run(["bash", str(RUNNER), "--dry-run", *args], capture_output=True, text=True,
                                  env=env, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(list(home.iterdir()), [], "--dry-run wrote into HOME")
        self.assertEqual(isolation.compare(before, isolation.snapshot(HUB, home)), [])
        self.assert_no_side_effects()


# ---- claude flag preflight: --help, then a parse check for flags it doesn't list (T0) --------------------------

CLAUDE_FLAGS = lib.REQUIRED_FLAGS["claude"] + tuple(lib.OPTIONAL_FLAGS["claude"])
# Fake `claude`: logs each call (argv, cwd, cwd contents, whether stdin is /dev/null) next to itself, then answers
# --version, --help, a host call (a free, empty stream) or a parse check, per spec.json's mode:
#   commander    like claude's parser: the first unknown `--` option fails with `error: unknown option '<flag>'`
#   exit0        exits 0 with no output (a parser that ignores unknown options)
#   other-error  fails with an error that names neither flag
#   lists-all    fails with an error that echoes every argument (names both flags)
#   sleep        hangs past the parse-check timeout
FAKE_CLAUDE = r'''
import json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "spec.json").read_text())
args = sys.argv[1:]
try:
    stdin_is_null = os.path.samestat(os.fstat(0), os.stat(os.devnull))
except OSError:
    stdin_is_null = False
with (HERE / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"argv": args, "cwd": os.getcwd(), "cwd_entries": os.listdir("."),
                          "stdin_is_null": stdin_is_null}) + "\n")
if args == ["--version"]:
    print("9.9.9 (Claude Code)")
elif args == ["--help"]:
    print(SPEC["help"])
elif SPEC["unknown"] not in args:
    print(json.dumps({"type": "result", "subtype": "success", "total_cost_usd": 0}))
elif SPEC["mode"] == "sleep":
    time.sleep(30)
elif SPEC["mode"] == "other-error":
    sys.exit("error: something else went wrong")
elif SPEC["mode"] == "lists-all":
    sys.exit("error: bad arguments: " + " ".join(args))
elif SPEC["mode"] == "commander":
    i = 0
    while i < len(args):
        if args[i].startswith("--") and args[i] not in SPEC["known"]:
            sys.exit(f"error: unknown option '{args[i]}'")
        i += 2 if args[i] in SPEC["known"] else 1
'''


class FlagPreflightTests(TempDirCase):
    """T0 (2.1.325): --max-turns works but `claude --help` doesn't list it. A flag missing from --help is confirmed
    by a parse check (`claude -p <flag> <value> --zz-daedalus-unknown-flag`) before it counts as missing.
    A fake `claude` first on PATH answers every call; the real CLI is never called."""

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        fake = self.bin / "claude"
        fake.write_text(f"#!{sys.executable}\n{FAKE_CLAUDE}")
        fake.chmod(0o755)
        self.fake()
        patcher = mock.patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"})
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def help_text(*left_out: str) -> str:
        return "Usage: claude [options] [command] [prompt]\n" + "".join(
            f"  {flag} <value>\n" for flag in CLAUDE_FLAGS if flag not in left_out)

    def fake(self, hidden: tuple = (), unknown: tuple = (), mode: str = "commander") -> None:
        """`hidden`: left out of --help but known to the parser; `unknown`: left out of both."""
        spec = {"help": self.help_text(*hidden, *unknown), "known": [f for f in CLAUDE_FLAGS if f not in unknown],
                "mode": mode, "unknown": lib.UNKNOWN_FLAG}
        (self.bin / "spec.json").write_text(json.dumps(spec))
        (self.bin / "calls.jsonl").unlink(missing_ok=True)

    def calls(self) -> list:
        log = self.bin / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def parse_checks(self) -> list:
        return [call["argv"] for call in self.calls() if lib.UNKNOWN_FLAG in call["argv"]]

    def test_a_flag_in_the_help_text_needs_no_parse_check(self) -> None:
        self.assertEqual(lib.check_flags("claude", self.help_text()), lib.FlagSupport())
        self.assertEqual(self.calls(), [])
        lines = []
        self.assertEqual(lib.preflight_flags("claude", lines.append), lib.FlagSupport())
        self.assertEqual(([c["argv"] for c in self.calls()], lines), ([["--help"]], []))

    def test_a_hidden_flag_the_parser_accepts_is_recorded_as_hidden(self) -> None:
        """The T0 finding: the parse check names only the fake flag, so --max-turns is accepted, not BLOCKED."""
        self.fake(hidden=("--max-turns",))
        lines = []
        support = lib.preflight_flags("claude", lines.append)
        self.assertEqual(support, lib.FlagSupport(hidden=frozenset({"--max-turns"})))
        self.assertEqual(lines, ["preflight: --max-turns is accepted but hidden from `claude --help` "
                                 "(verified by a parse check)"])
        check = next(call for call in self.calls() if lib.UNKNOWN_FLAG in call["argv"])
        self.assertEqual(self.parse_checks(), [["-p", "--max-turns", "1", lib.UNKNOWN_FLAG]])  # no prompt
        self.assertEqual((check["cwd_entries"], check["stdin_is_null"]), ([], True))
        self.assertFalse(isolation.is_within(Path(check["cwd"]), HUB), "the parse check ran inside the hub")
        self.assertFalse(Path(check["cwd"]).exists(), "the parse check's temp cwd was left behind")

    def test_every_checked_flag_has_a_placeholder_and_no_prompt(self) -> None:
        workdir = self.tmp / "work"
        values = {}
        for flag in CLAUDE_FLAGS:
            argv = lib.parse_check_argv("claude", flag, workdir)
            self.assertEqual(argv[:3] + argv[4:], ["claude", "-p", flag, lib.UNKNOWN_FLAG], flag)
            values[flag] = argv[3]
        self.assertEqual(int(values["--max-turns"]), 1)
        self.assertGreater(float(values["--max-budget-usd"]), 0)
        self.assertEqual((values["--model"], values["--plugin-dir"]), ("haiku", str(workdir)))
        self.assertIsNone(lib.parse_check_argv("claude", "--no-placeholder", workdir))
        self.assertFalse(lib.flag_accepted("claude", "--no-placeholder"))  # unverifiable: missing, CLI not called
        self.assertEqual(self.calls(), [])

    def test_a_required_flag_the_parser_names_blocks(self) -> None:
        self.fake(unknown=("--max-turns",))
        with self.assertRaises(lib.GuardError) as raised:
            lib.check_flags("claude", self.help_text("--max-turns"))
        self.assertIn("BLOCKED (env): `claude` lacks --max-turns", str(raised.exception))
        self.assertEqual(self.parse_checks(), [["-p", "--max-turns", "1", lib.UNKNOWN_FLAG]])

    def test_run_live_blocks_before_any_run_when_a_required_flag_is_missing(self) -> None:
        self.fake(unknown=("--max-turns",))
        lines, run_root = [], self.tmp / "daedalus-probes" / "ts"
        # The next live step after the preflight: if a regression lets the preflight pass, stop here rather than
        # snapshot, run and publish (which writes results/ into the hub).
        past_preflight = AssertionError("run_live got past the flag preflight")
        with mock.patch.object(lib, "plugin_list_text", side_effect=past_preflight):
            self.assertEqual(lib.run_live([], "claude", 1.0, run_root, lines.append), 2)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("BLOCKED (env): `claude` lacks --max-turns"), lines)
        self.assertEqual([c["argv"] for c in self.calls()],
                         [["--version"], ["--help"], ["-p", "--max-turns", "1", lib.UNKNOWN_FLAG]])
        self.assertFalse(run_root.exists())

    def test_an_optional_flag_the_parser_names_is_dropped(self) -> None:
        self.fake(hidden=("--max-turns",), unknown=("--plugin-dir", "--max-budget-usd"))
        support = lib.check_flags("claude", self.help_text("--max-turns", "--plugin-dir", "--max-budget-usd"))
        self.assertEqual(support, lib.FlagSupport(dropped=frozenset({"--plugin-dir", "--max-budget-usd"}),
                                                  hidden=frozenset({"--max-turns"})))
        self.assertEqual(sorted(argv[1] for argv in self.parse_checks()),
                         ["--max-budget-usd", "--max-turns", "--plugin-dir"])
        case = json.loads((lib.CASES_DIR / "A1.json").read_text())
        run = lib.Run(case, "plugin", "claude", self.tmp / "daedalus-probes" / "A1" / "plugin")
        argv = lib.host_command(run, support.dropped)
        self.assertNotIn("--plugin-dir", argv)
        self.assertNotIn("--max-budget-usd", argv)
        self.assertIn("--max-turns", argv)

    def test_unexpected_output_or_a_timeout_is_missing(self) -> None:
        for mode in ("exit0", "other-error", "lists-all", "sleep"):
            with self.subTest(mode=mode), mock.patch.object(lib, "PARSE_CHECK_TIMEOUT_S", 0.5):
                self.fake(hidden=("--max-turns", "--permission-mode"), mode=mode)
                start = time.monotonic()
                with self.assertRaises(lib.GuardError):
                    lib.check_flags("claude", self.help_text("--max-turns"))
                support = lib.check_flags("claude", self.help_text("--permission-mode"))
                self.assertEqual(support, lib.FlagSupport(dropped=frozenset({"--permission-mode"})))
                self.assertLess(time.monotonic() - start, 10, "the parse check outlived its timeout")
                self.assertEqual(len(self.parse_checks()), 2)

    def test_parse_check_verdicts(self) -> None:
        fake_error = f"error: unknown option '{lib.UNKNOWN_FLAG}'"
        accepted = [(1, fake_error), (1, f"{fake_error}\nnear --max-turns-total")]  # token boundaries
        missing = [None, (0, fake_error), (1, ""), (1, "error: unknown option '--max-turns'"),
                   (1, f"{fake_error}\n(Did you mean --max-turns?)"),
                   (1, "Unknown arguments: max-turns, zz-daedalus-unknown-flag")]  # a parser that drops dashes
        for outcome in accepted:
            self.assertTrue(lib.parse_check_accepts("--max-turns", outcome), outcome)
        for outcome in missing:
            self.assertFalse(lib.parse_check_accepts("--max-turns", outcome), outcome)

    def test_results_note_hidden_flags_once_on_the_runs_that_pass_them(self) -> None:
        case = json.loads((lib.CASES_DIR / "A3.json").read_text())
        root = self.tmp / "daedalus-probes"
        note = "accepted but hidden from `claude --help` (verified by a parse check): "
        scenarios = (({"--max-turns", "--plugin-dir"}, set(), {"script": "--max-turns",
                                                               "plugin": "--max-turns, --plugin-dir"}),
                     ({"--max-turns"}, {"--plugin-dir"}, {"script": "--max-turns", "plugin": None}))
        for number, (hidden, dropped, expected) in enumerate(scenarios):
            with self.subTest(hidden=sorted(hidden), dropped=sorted(dropped)):
                self.fake()
                run_root = root / f"ts{number}"
                runs, _ = lib.plan_runs([case], lib.INSTALLS, "claude", run_root)
                entries, failures = [], []
                with mock.patch.object(lib, "probe_root", return_value=root):
                    lib.run_all(runs, "9.9.9", frozenset(dropped), 10.0, run_root / "staged", None, entries,
                                failures, lambda line: None, frozenset(hidden))
                self.assertEqual(failures, [])
                for entry in entries:
                    want = expected[entry["install"]]
                    self.assertEqual([n for n in entry["notes"] if "hidden from" in n], [note + want] if want else [])
                host_calls = [c["argv"] for c in self.calls()
                              if c["argv"][:1] == ["-p"] and lib.UNKNOWN_FLAG not in c["argv"]]
                self.assertEqual(len(host_calls), 2 if not dropped else 1)  # plugin host call skipped when dropped
                self.assertTrue(all("--max-turns" in argv for argv in host_calls))
                doc = lib.result_document("claude", "9.9.9", entries)
                self.assertEqual(lib.schema_errors(doc, "probe-result.schema.json"), [])


# ---- the generated plugins never carry the probe harness (AC-12) ----------------------------------------------

class PluginBoundaryTests(unittest.TestCase):
    def test_probe_harness_never_reaches_the_plugins(self) -> None:
        names = {p.name for p in PROBES.iterdir() if p.is_file()} - {"README.md"}
        plugins = [p for p in (HUB / "plugins").iterdir() if p.is_dir()]
        self.assertTrue(plugins, "no generated plugins to check")
        for plugin in plugins:
            for path in plugin.rglob("*"):
                rel = path.relative_to(plugin)
                self.assertNotIn("probes", rel.parts[:-1], str(path))
                self.assertNotIn(path.name, names, str(path))


# ---- isolation, cleanup and the offline pipeline (AC-1) -------------------------------------------------------

class IsolationTests(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.hub = self.tmp / "hub"
        self.hub.mkdir()
        git(self.hub, "init", "-q")
        (self.hub / "tracked.txt").write_text("v1\n")
        (self.hub / "audit.log").write_text("a\n")
        git(self.hub, "add", "-A")
        git(self.hub, "commit", "-q", "-m", "init")
        self.home = self.tmp / "home"
        (self.home / ".claude" / "plugins").mkdir(parents=True)
        (self.home / ".claude" / "settings.json").write_text('{"x": 1}')
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text("{}")

    def snap(self, plugin_list: str = "daedalus@daedalus") -> dict:
        return isolation.snapshot(self.hub, self.home, plugin_list)

    def test_unchanged_state_has_no_difference(self) -> None:
        self.assertEqual(isolation.compare(self.snap(), self.snap()), [])

    def test_an_already_modified_file_changing_again_is_not_a_difference(self) -> None:
        (self.hub / "audit.log").write_text("a\nb\n")
        before = self.snap()
        (self.hub / "audit.log").write_text("a\nb\nc\n")
        self.assertEqual(isolation.compare(before, self.snap()), [])

    def test_hub_changes_are_differences(self) -> None:
        before = self.snap()
        (self.hub / "tracked.txt").write_text("v2\n")
        (self.hub / "new.txt").write_text("x")
        diffs = isolation.compare(before, self.snap())
        self.assertTrue(any("tracked.txt" in d for d in diffs))
        self.assertTrue(any("new.txt" in d for d in diffs))

    def test_user_scope_changes_are_differences(self) -> None:
        before = self.snap()
        (self.home / ".claude" / "settings.json").write_text('{"x": 2}')
        (self.home / ".claude" / "plugins" / "known_marketplaces.json").write_text("{}")
        diffs = isolation.compare(before, self.snap("daedalus@daedalus\nprobe@probe-market"))
        self.assertIn("user-scope file changed: ~/.claude/settings.json", diffs)
        self.assertIn("user-scope file created: ~/.claude/plugins/known_marketplaces.json", diffs)
        self.assertIn("user-scope plugin list changed", diffs)

    def test_snapshot_stores_digests_not_contents(self) -> None:
        text = json.dumps(self.snap())
        self.assertNotIn('{"x": 1}', text)
        self.assertIn("sha256:", text)

    def test_safe_remove_stays_inside_the_probe_root(self) -> None:
        root = self.tmp / "daedalus-probes"
        (root / "run" / "repo" / ".claude").mkdir(parents=True)
        outside = self.tmp / "keep.txt"
        outside.write_text("keep")
        (root / "run" / "link").symlink_to(outside)
        with self.assertRaises(isolation.IsolationError):
            isolation.safe_remove(outside, root)
        with self.assertRaises(isolation.IsolationError):
            isolation.safe_remove(root, root)
        with self.assertRaises(isolation.IsolationError):
            isolation.safe_remove(root / "run" / ".." / ".." / "keep.txt", root)
        # A trailing `..` survives parent-only resolution: these would rmtree the probe root and its parent.
        for target in (root / "run" / "..", root / "run" / ".." / "..", root / "run" / "repo" / ".." / ".claude"):
            with self.assertRaises(isolation.IsolationError, msg=str(target)):
                isolation.safe_remove(target, root)
        self.assertTrue((root / "run" / "repo" / ".claude").is_dir())
        self.assertTrue(outside.exists())
        with self.assertRaises(isolation.IsolationError):
            isolation.safe_remove(self.hub / "tracked.txt", self.hub)  # not a daedalus-probes root
        self.assertTrue(isolation.safe_remove(root / "run" / "link", root))
        self.assertTrue(outside.exists(), "removing a symlink must not touch its target")
        self.assertTrue(isolation.safe_remove(root / "run" / "repo" / ".claude", root))
        self.assertFalse(isolation.safe_remove(root / "run" / "missing", root))
        self.assertEqual(isolation.leftovers([root / "run" / "repo" / ".claude", root / "run" / "link"]), [])

    def test_offline_pipeline_on_a_fake_workspace(self) -> None:
        """Every A1/script action except the host call: real workspace, recorder, observe, redact and cleanup."""
        root = self.tmp / "daedalus-probes"
        case = json.loads((lib.CASES_DIR / "A1.json").read_text())
        runs, _ = lib.plan_runs([case], ("script",), "claude", root / "20260101T000000Z")
        run, staging = runs[0], root / "20260101T000000Z" / "staged"
        actions = lib.build_actions(run, "9.9.9", staging)
        state = lib.RunState(host_version="9.9.9")
        fixtures_before = sorted(p.name for p in lib.FIXTURES_DIR.rglob("*"))
        for action in actions:
            if action.kind == "host":
                self.simulate_host(run)
                state.host_ran = True
                continue
            lib.execute_action(action, run, root, state)
        self.assertEqual(state.failures, [])
        self.assertEqual(state.status, "confirmed", state.notes)
        self.assertEqual(len(state.fixture_ids), 4)
        self.assertTrue(all(i.startswith("claude-9.9.9/A1/script/") for i in state.fixture_ids))
        fixture_dir = staging / "fixtures" / "claude-9.9.9" / "A1" / "script"
        self.assertEqual(redact.scan_paths([fixture_dir]), [])
        for path in fixture_dir.glob("*.json"):
            self.assertEqual(lib.schema_errors(json.loads(path.read_text()), "probe-fixture.schema.json"), [])
        self.assertEqual(isolation.leftovers(run.workspace / rel for rel in lib.INSTALLED_PATHS), [])
        self.assertTrue((run.repo / "seed.txt").is_file(), "cleanup removes installs, not the throwaway repo")
        self.assertEqual(git(run.repo, "log", "--format=%s").strip(), "probe seed")
        self.assertEqual(sorted(p.name for p in lib.FIXTURES_DIR.rglob("*")), fixtures_before)
        entry = lib.result_entry(run, state, ["daedalus"])
        doc = lib.result_document("claude", "9.9.9", [entry])
        self.assertEqual(lib.schema_errors(doc, "probe-result.schema.json"), [])

    def simulate_host(self, run) -> None:
        """Feed synthetic payloads through the rendered hook command, exactly as the host would."""
        hooks = json.loads((run.repo / ".claude" / "settings.json").read_text())["hooks"]
        base = {"session_id": FAKE_SESSION, "cwd": str(run.repo),
                "transcript_path": f"{FAKE_HOME}/.claude/projects/-Users-synthetic/{FAKE_SESSION}.jsonl"}
        bash = {"tool_name": "Bash", "tool_input": {"command": "echo A1"}, "agent_id": "a7f3c9e1aa",
                "agent_type": "probe-reader"}
        spawn = {"tool_name": "Agent", "tool_input": {"subagent_type": "probe-reader", "prompt": "go"}}
        read = {"tool_name": "Read", "tool_input": {"file_path": str(run.repo / "seed.txt")},
                "agent_id": "a7f3c9e1aa", "agent_type": "probe-reader"}
        ran = dict(bash, tool_response={"stdout": "A1\n", "stderr": "", "interrupted": False})
        # A1 asserts agent_type on both the PreToolUse and the PostToolUse of the agent's `echo A1` (ac4232f-16).
        calls = [("PreToolUse", spawn), ("PreToolUse", read), ("PreToolUse", bash), ("PostToolUse", ran)]
        for event, call in calls:
            command = hooks[event][0]["hooks"][0]["command"]
            payload = {**base, "hook_event_name": event, **call}
            done = subprocess.run(command, shell=True, input=json.dumps(payload), capture_output=True,
                                  text=True, timeout=30)
            self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)

    def test_missing_interpreter_template_fails_to_start_the_hook(self) -> None:
        root = self.tmp / "daedalus-probes"
        case = json.loads((lib.CASES_DIR / "E4.json").read_text())
        run = lib.plan_runs([case], ("script",), "claude", root / "ts")[0][0]
        state = lib.RunState(host_version="0")
        for action in lib.build_actions(run, "0", root / "ts" / "staged"):
            if action.kind in ("mkdir", "git-init", "copy", "render", "ctrl"):
                lib.execute_action(action, run, root, state)
        command = json.loads((run.repo / ".claude" / "settings.json").read_text())["hooks"]["PreToolUse"][0][
            "hooks"][0]["command"]
        done = subprocess.run(command, shell=True, input="{}", capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 127)
        self.assertFalse((run.workspace / "out" / "raw" / "PreToolUse.jsonl").exists())

    def test_cleanup_reports_leftovers_as_failures(self) -> None:
        root = self.tmp / "daedalus-probes"
        case = json.loads((lib.CASES_DIR / "A3.json").read_text())
        run = lib.plan_runs([case], ("script",), "claude", root / "ts")[0][0]
        (run.repo / ".claude").mkdir(parents=True)
        state = lib.RunState(host_version="0")
        original = isolation.safe_remove
        isolation.safe_remove = lambda target, probe_root: False  # simulate a removal that silently did nothing
        try:
            lib.cleanup_run(run, root, state)
        finally:
            isolation.safe_remove = original
        self.assertTrue(any("cleanup left" in f for f in state.failures))


# ---- status guards: no verdict without an attempt (AC-2, §3.10) ------------------------------------------------

SETUP_ACTIONS = ("mkdir", "git-init", "copy", "render", "ctrl")
SPAWN = {"tool_name": "Agent", "tool_input": {"subagent_type": "probe-x", "prompt": "go"}}
# The probe agent each case spawns; its agent_type is the bare name on script installs, probe:<name> on plugin ones.
CASE_AGENTS = {"C1": "probe-tools", "C2": "probe-nobash", "C3": "probe-maxturns", "C4": "probe-frontmatter",
               "F3": "probe-reader", "F4": "probe-reader", "I1": "probe-reader"}
# The precondition proving the agent attempted the marker call in F3, F4 and I1.
CASE_SEEN = {"F3": "bash-seen", "F4": "bash-seen", "I1": "write-attempted"}


def agent_type(case_id: str, install: str = "script") -> str:
    name = CASE_AGENTS[case_id]
    return f"{lib.PLUGIN_NAME}:{name}" if install == "plugin" else name


class RunHelpers:
    """Build one run's workspace (everything before the host call) and feed the recorder by hand."""
    tmp: Path

    def plan(self, case_id: str, variant: str = None, case: dict = None, install: str = "script") -> tuple:
        root = self.tmp / "daedalus-probes"
        case = case or json.loads((lib.CASES_DIR / f"{case_id}.json").read_text())
        self.plans = getattr(self, "plans", 0) + 1  # a fresh run root per call: git-init can't run twice
        run_root = root / f"ts{self.plans}"
        runs, _ = lib.plan_runs([case], (install,), "claude", run_root)
        run = next(r for r in runs if r.variant_id == variant)
        return root, run, lib.build_actions(run, "0", run_root / "staged")

    def prepare(self, case_id: str, variant: str = None, case: dict = None, install: str = "script"):
        root, run, actions = self.plan(case_id, variant, case, install)
        state = lib.RunState(host_version="0")
        for action in actions:
            if action.kind in SETUP_ACTIONS:
                lib.execute_action(action, run, root, state)
        return run

    @staticmethod
    def record(run, event: str, payload: dict, tag: str = None) -> None:
        """One hook call through the recorder with the run's control file, as the host would make it."""
        tag_args = ["--tag", tag] if tag else []
        subprocess.run([sys.executable, str(RECORDER), "--ctrl", str(run.workspace / "ctrl.json"),
                        "--out", str(run.workspace / "out" / "raw"), "--event", event, *tag_args],
                       input=json.dumps({"hook_event_name": event, **payload}), capture_output=True, text=True,
                       timeout=30)

    @staticmethod
    def observed(run, **state_fields: object):
        state = lib.RunState(host_version="0", **state_fields)
        lib.observe_run(run, state)
        return state


class StatusGuardTests(RunHelpers, TempDirCase):
    """A run whose host didn't run, timed out, or never attempted the probed call is inconclusive."""

    def test_e1_on_failure_block_without_the_host_is_inconclusive(self) -> None:
        """Regression (ac4232f-1): with `host` skipped, the absent marker used to read as `confirmed`."""
        root, run, actions = self.plan("E1", "on-failure-block")
        state = lib.RunState(host_version="0")
        lib.execute_run(run, actions, root, state, skip=("host",))
        self.assertEqual(state.failures, [])
        self.assertTrue(state.cleaned)
        self.assertEqual(state.status, "inconclusive", state.notes)
        self.assertIn("host not run; inconclusive", state.notes)

    def test_host_not_run_or_timed_out_overrides_passing_checks(self) -> None:
        run = self.prepare("E1", "on-failure-block")
        self.record(run, "PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "touch marker-E1"}})
        self.assertEqual(self.observed(run, host_ran=True).status, "confirmed")  # the capture alone would confirm
        not_run = self.observed(run)
        self.assertEqual(not_run.status, "inconclusive")
        self.assertIn("host not run; inconclusive", not_run.notes)
        timed_out = self.observed(run, host_ran=True, timed_out=True)
        self.assertEqual(timed_out.status, "inconclusive")
        self.assertIn("host timed out; inconclusive", timed_out.notes)
        self.assertEqual({e["check"]: e["outcome"] for e in timed_out.evaluated}["marker"], "pass")  # facts kept

    def test_e_cases_need_the_hook_to_have_seen_the_call(self) -> None:
        """E1-E3 and E5: no PreToolUse record means the call was never attempted, whatever the marker says."""
        for cid in ("E1", "E2", "E3", "E5"):
            for variant in ("default", "on-failure-block"):
                with self.subTest(case=cid, variant=variant):
                    case = lib.load_cases(cid)[0]
                    observations = next(v for v in case["variants"] if v["id"] == variant)["observations"]
                    roles = {o["id"]: o["role"] for o in observations}
                    self.assertEqual(roles["hook-ran"], "precondition")
                    state = self.observed(self.prepare(cid, variant), host_ran=True)
                    self.assertEqual(state.status, "inconclusive", state.notes)
                    self.assertIn("precondition not met: hook-ran", state.notes)

    def test_c_cases_without_subagent_start_are_inconclusive(self) -> None:
        """Regression (ac4232f-1): `spawned` only proves the spawn was requested; a failed spawn passed C1-C3."""
        for cid in ("C1", "C2", "C3", "C4"):
            with self.subTest(case=cid):
                run = self.prepare(cid)
                self.record(run, "PreToolUse", SPAWN)
                state = self.observed(run, host_ran=True)
                self.assertEqual(state.status, "inconclusive", state.notes)
                self.assertTrue(any("subagent-started" in n for n in state.notes), state.notes)

    def test_c_cases_confirm_once_the_agent_started(self) -> None:
        for cid in ("C1", "C2", "C3"):
            with self.subTest(case=cid):
                run = self.prepare(cid)
                self.record(run, "PreToolUse", SPAWN)
                self.record(run, "SubagentStart", {"agent_id": "a1b2c3d4", "agent_type": agent_type(cid)})
                if cid == "C3":
                    no_read = self.observed(run, host_ran=True)
                    self.assertIn("precondition not met: step-read", no_read.notes)  # read nothing: not a pass
                    self.record(run, "PreToolUse", {"tool_name": "Read", "agent_type": agent_type(cid),
                                                    "tool_input": {"file_path": "steps/step1.txt"}})
                state = self.observed(run, host_ran=True)
                self.assertEqual(state.status, "confirmed", state.notes)

    def test_h2_needs_a_stop_before_it_can_contradict(self) -> None:
        run = self.prepare("H2")
        early_exit = self.observed(run, host_ran=True)
        self.assertEqual(early_exit.status, "inconclusive", early_exit.notes)  # was: contradicted on zero Stops
        self.assertIn("precondition not met: stop-seen", early_exit.notes)
        self.record(run, "Stop", {"stop_hook_active": False})
        self.assertEqual(self.observed(run, host_ran=True).status, "contradicted")  # one Stop: the block was ignored

    def test_l1_needs_edits_aimed_at_seed_txt(self) -> None:
        run = self.prepare("L1")
        for agent, name in ((None, "other.txt"), ("probe-reader", "other.txt")):
            payload = {"tool_name": "Edit", "tool_input": {"file_path": str(run.repo / name)}}
            self.record(run, "PreToolUse", dict(payload, agent_type=agent) if agent else payload)
        self.assertEqual(self.observed(run, host_ran=True).status, "inconclusive")
        for agent in (None, "probe-reader"):
            payload = {"tool_name": "Edit", "tool_input": {"file_path": str(run.repo / "seed.txt")}}
            self.record(run, "PreToolUse", dict(payload, agent_type=agent) if agent else payload)
        self.assertEqual(self.observed(run, host_ran=True).status, "confirmed")


class AttributionTests(RunHelpers, TempDirCase):
    """Regression (ac4232f-14): only the probe agent's own calls (agent_type, A1) decide C1-C4, F3, F4 and I1."""

    def started(self, cid: str, install: str = "script", agent: object = "default"):
        """A run where the main thread spawned the agent and a SubagentStart (with `agent` as agent_type) arrived."""
        run = self.prepare(cid, install=install)
        self.record(run, "PreToolUse", SPAWN)
        start = {"agent_id": "a1b2c3d4"}
        agent = agent_type(cid, install) if agent == "default" else agent
        self.record(run, "SubagentStart", dict(start, agent_type=agent) if agent else start)
        return run

    @staticmethod
    def by(payload: dict, agent: str = None) -> dict:
        """The payload as the agent (agent_type set) or the main thread (no agent fields, A3) sends it."""
        return dict(payload, agent_type=agent) if agent else payload

    @staticmethod
    def step(n: int) -> dict:
        return {"tool_name": "Read", "tool_input": {"file_path": f"steps/step{n}.txt"}}

    def status(self, run) -> tuple:
        state = self.observed(run, host_ran=True)
        return state.status, {e["check"]: e for e in state.evaluated}, state.notes

    def test_c_cases_need_their_own_agents_subagent_start(self) -> None:
        """Another agent's start, or a start without agent_type (a host without A1), proves nothing."""
        for cid in ("C1", "C2", "C3", "C4"):
            for agent in ("general-purpose", None):
                with self.subTest(case=cid, agent=agent):
                    status, checks, notes = self.status(self.started(cid, agent=agent))
                    self.assertEqual(status, "inconclusive", notes)
                    self.assertEqual(checks["subagent-started"]["outcome"], "fail")

    def test_c3_main_thread_step_read_is_inconclusive_not_confirmed(self) -> None:
        for install in lib.INSTALLS:
            with self.subTest(install=install):
                run = self.started("C3", install)
                self.record(run, "PreToolUse", self.step(1))  # the main thread, not the agent
                status, _, notes = self.status(run)
                self.assertEqual(status, "inconclusive", notes)  # was: confirmed (1 read < 5)
                self.assertIn("precondition not met: step-read", notes)
                self.record(run, "PreToolUse", self.by(self.step(1), agent_type("C3", install)))
                self.assertEqual(self.status(run)[0], "confirmed")

    def test_c3_main_thread_reads_after_the_agent_stops_dont_count(self) -> None:
        for install in lib.INSTALLS:
            with self.subTest(install=install):
                agent = agent_type("C3", install)
                run = self.started("C3", install)
                for n in (1, 2):
                    self.record(run, "PreToolUse", self.by(self.step(n), agent))
                self.record(run, "SubagentStop", {"agent_id": "a1b2c3d4", "agent_type": agent})
                for n in range(1, 6):
                    self.record(run, "PreToolUse", self.step(n))  # the main thread finishes the task
                status, checks, notes = self.status(run)
                self.assertEqual(status, "confirmed", notes)  # was: contradicted (7 step reads)
                self.assertEqual(checks["fewer-than-five"]["actual"], 2)
                run = self.started("C3", install)  # the agent's own five reads still contradict
                for n in range(1, 6):
                    self.record(run, "PreToolUse", self.by(self.step(n), agent))
                self.assertEqual(self.status(run)[0], "contradicted")

    def test_c1_c2_main_thread_echo_leaves_the_run_confirmed(self) -> None:
        for cid in ("C1", "C2"):
            for install in lib.INSTALLS:
                with self.subTest(case=cid, install=install):
                    run = self.started(cid, install)
                    bash = {"tool_name": "Bash", "tool_input": {"command": f"echo {cid}"}}
                    self.record(run, "PreToolUse", bash)
                    self.record(run, "PostToolUse", bash)  # the main thread ran it itself
                    status, checks, notes = self.status(run)
                    self.assertEqual(status, "confirmed", notes)  # was: contradicted
                    self.assertEqual(checks["bash-attempted"]["actual"], {"count": 0})
                    self.record(run, "PostToolUse", self.by(bash, agent_type(cid, install)))
                    self.assertEqual(self.status(run)[0], "contradicted")  # the agent itself ran Bash

    def test_c4_main_thread_edit_of_seed_is_inconclusive(self) -> None:
        for install in lib.INSTALLS:
            with self.subTest(install=install):
                run = self.started("C4", install)
                seed = run.repo / "seed.txt"
                edit = {"tool_name": "Edit", "tool_input": {"file_path": str(seed)}}
                self.record(run, "PreToolUse", self.by(edit, agent_type("C4", install)))  # blocked: seed unchanged
                if install == "script":
                    self.record(run, "PreToolUse", self.by(edit, agent_type("C4")), tag="frontmatter")
                status, _, notes = self.status(run)
                self.assertEqual(status, "confirmed" if install == "script" else "contradicted", notes)
                self.record(run, "PreToolUse", edit)  # the main thread edits seed.txt itself
                seed.write_text("C4\n", encoding="utf-8")
                status, _, notes = self.status(run)  # was: contradicted (script) or confirmed (plugin)
                self.assertEqual(status, "inconclusive", notes)
                self.assertIn("precondition not met: main-thread-no-edit", notes)

    def check_marker_case(self, cid: str, command: str, marker: str, guard: str) -> None:
        """F3, F4 and I1 assert a marker is absent: it must be the agent's attempt, with no main-thread one."""
        for install in lib.INSTALLS:
            with self.subTest(case=cid, install=install):
                bash = {"tool_name": "Bash", "tool_input": {"command": command}}
                agent = agent_type(cid, install)
                run = self.prepare(cid, install=install)
                self.record(run, "PreToolUse", bash)  # only the main thread tried, and was blocked
                status, checks, notes = self.status(run)
                self.assertEqual(status, "inconclusive", notes)  # was: confirmed
                self.assertEqual((checks[CASE_SEEN[cid]]["outcome"], checks[guard]["outcome"]), ("fail", "fail"))
                run = self.prepare(cid, install=install)
                self.record(run, "PreToolUse", self.by(bash, agent))
                self.assertEqual(self.status(run)[0], "confirmed")  # the agent tried and was blocked
                self.record(run, "PreToolUse", bash)
                (run.repo / marker).touch()  # the main thread's own attempt went through
                status, _, notes = self.status(run)
                self.assertEqual(status, "inconclusive", notes)  # was: contradicted
                self.assertIn(f"precondition not met: {guard}", notes)
                run = self.prepare(cid, install=install)
                self.record(run, "PreToolUse", self.by(bash, agent))
                (run.repo / marker).touch()
                self.assertEqual(self.status(run)[0], "contradicted")  # the agent's own call went through

    def test_f3_f4_main_thread_touch_cant_decide(self) -> None:
        for cid in ("F3", "F4"):
            self.check_marker_case(cid, f"touch marker-{cid}", f"marker-{cid}", "main-thread-no-touch")

    @unittest.skipUnless(sys.platform.startswith(("darwin", "linux")), "I1 applies to macOS and Linux only")
    def test_i1_main_thread_outside_write_cant_decide(self) -> None:
        self.check_marker_case("I1", "touch ../outside.txt", "../outside.txt", "main-thread-no-write")


class RequiresGateTests(unittest.TestCase):
    """`requires` (RW-26): an entry is only decided when its required case is confirmed for the same host version
    and install. Closes the C1/C2 gap where a host without agent_type on tool calls passes bash-not-run trivially."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = {c["id"]: c for c in lib.load_cases("all")}

    def entry(self, case_id: str, status: str, install: str = "script", version: str = "9.9.9") -> dict:
        run = lib.Run(self.cases[case_id], install, "claude", Path("/nonexistent"))
        return lib.result_entry(run, lib.RunState(host_version=version, status=status), None)

    @staticmethod
    def statuses(doc: dict) -> dict:
        return {(e["case"], e["install"]): (e["status"], e["notes"]) for e in doc["entries"]}

    def finalized(self, entries: list, existing: dict = None) -> dict:
        doc = lib.result_document("claude", "9.9.9", entries, existing)
        self.assertEqual(lib.schema_errors(doc, "probe-result.schema.json"), [])
        return self.statuses(doc)

    def test_attribution_cases_require_a1(self) -> None:
        for cid in CASE_AGENTS:
            self.assertEqual(self.cases[cid].get("requires"), ["A1"], cid)
        self.assertNotIn("requires", self.cases["A1"])

    def test_c1_confirmed_with_a1_contradicted_is_inconclusive(self) -> None:
        got = self.finalized([self.entry("C1", "confirmed"), self.entry("A1", "contradicted")])
        self.assertEqual(got[("C1", "script")], ("inconclusive", ["requires A1 confirmed (A1 contradicted)"]))
        self.assertEqual(got[("A1", "script")], ("contradicted", []))

    def test_a1_missing_from_the_run_is_inconclusive(self) -> None:
        staged = lib.result_document("claude", "9.9.9", [self.entry("C1", "confirmed")])
        self.assertEqual(self.statuses(staged)[("C1", "script")],
                         ("inconclusive", ["requires A1 confirmed (A1 not run)"]))
        older = {"entries": [self.entry("A1", "confirmed")]}  # an older A1 in the results file can't vouch for it
        self.assertEqual(self.finalized(staged["entries"], older)[("C1", "script")][0], "inconclusive")

    def test_a1_confirmed_keeps_c1_confirmed(self) -> None:
        got = self.finalized([self.entry("C1", "confirmed"), self.entry("A1", "confirmed")])
        self.assertEqual(got[("C1", "script")], ("confirmed", []))

    def test_the_gate_is_per_install_and_host_version(self) -> None:
        entries = [self.entry("C1", "confirmed"), self.entry("C1", "confirmed", "plugin"),
                   self.entry("A1", "confirmed"), self.entry("A1", "confirmed", "plugin", version="9.9.8")]
        got = self.finalized(entries)
        self.assertEqual(got[("C1", "script")][0], "confirmed")
        self.assertEqual(got[("C1", "plugin")], ("inconclusive", ["requires A1 confirmed (A1 not run)"]))

    def test_a_later_a1_that_isnt_confirmed_downgrades_published_dependents(self) -> None:
        published = lib.result_document("claude", "9.9.9", [self.entry("C3", "confirmed"),
                                                             self.entry("A1", "confirmed")])
        self.assertEqual(self.statuses(published)[("C3", "script")][0], "confirmed")
        got = self.finalized([self.entry("A1", "inconclusive")], published)
        self.assertEqual(got[("C3", "script")], ("inconclusive", ["requires A1 confirmed (A1 inconclusive)"]))

    def test_only_decided_entries_are_gated_and_inputs_are_untouched(self) -> None:
        entries = [self.entry("C2", "contradicted"), self.entry("F3", "inconclusive"),
                   self.entry("E1", "confirmed")]
        got = self.finalized(entries)
        self.assertEqual(got[("C2", "script")][0], "inconclusive")  # a finding needs attribution too
        self.assertEqual(got[("F3", "script")], ("inconclusive", []))
        self.assertEqual(got[("E1", "script")], ("confirmed", []))  # no requires
        self.assertEqual((entries[0]["status"], entries[0]["notes"]), ("contradicted", []))

    def test_a_chain_of_requirements_settles(self) -> None:
        entries = [self.entry("C1", "confirmed"), self.entry("C2", "confirmed"), self.entry("A1", "contradicted")]
        gated = lib.gate_requirements(entries, {"C1": ["C2"], "C2": ["A1"]})
        self.assertEqual([e["status"] for e in gated], ["inconclusive", "inconclusive", "contradicted"])
        self.assertEqual(gated[0]["notes"], ["requires C2 confirmed (C2 inconclusive)"])

    def test_validate_case_rejects_unknown_or_self_requirements(self) -> None:
        path = lib.CASES_DIR / "C1.json"
        self.assertEqual(lib.validate_case(self.cases["C1"], path), [])
        for required, needle in (("Z9", "no such case"), ("C1", "can't require itself")):
            case = dict(self.cases["C1"], requires=[required])
            self.assertTrue(any(needle in e for e in lib.validate_case(case, path)), required)
        wrong_type = dict(self.cases["C1"], requires="A1")
        self.assertTrue(lib.validate_case(wrong_type, path))


def a1_agent_type(install: str) -> str:
    return f"{lib.PLUGIN_NAME}:probe-reader" if install == "plugin" else "probe-reader"


class A1AfterCallAttributionTests(RunHelpers, TempDirCase):
    """Regression (ac4232f-16): A1 proves agent_type on the agent's PostToolUse too, the event C1 and C2 decide on.

    On a host that attributes PreToolUse but not PostToolUse, C1's bash-not-run absence holds trivially even when the
    agent's Bash ran, so C1 alone reads `confirmed`; A1 must then not be `confirmed`, so the gate holds C1 back.
    """

    BASH_A1 = {"tool_name": "Bash", "tool_input": {"command": "echo A1"}}
    RAN = {"tool_response": {"stdout": "", "stderr": "", "interrupted": False}}

    def a1(self, install: str, post: str) -> tuple:
        """An A1 run whose agent's `echo A1` PreToolUse is attributed. `post` is its PostToolUse: "attributed",
        "unattributed" (no agent fields), "other-agent", or "none" (no PostToolUse at all)."""
        agent = {"agent_id": "a7f3c9e1aa", "agent_type": a1_agent_type(install)}
        run = self.prepare("A1", install=install)
        self.record(run, "PreToolUse", {**self.BASH_A1, **agent})
        post_payloads = {"attributed": {**self.BASH_A1, **self.RAN, **agent},
                         "unattributed": {**self.BASH_A1, **self.RAN},
                         "other-agent": {**self.BASH_A1, **self.RAN, **agent, "agent_type": "general-purpose"}}
        if post in post_payloads:
            self.record(run, "PostToolUse", post_payloads[post])
        state = self.observed(run, host_ran=True)
        return run, state, {e["check"]: e for e in state.evaluated}

    def c_pre_only_host(self, cid: str, install: str) -> tuple:
        """C1 or C2 on a host that names the agent on PreToolUse but not PostToolUse: the agent's Bash ran."""
        run = self.prepare(cid, install=install)
        self.record(run, "PreToolUse", SPAWN)
        self.record(run, "SubagentStart", {"agent_id": "a1b2c3d4", "agent_type": agent_type(cid, install)})
        bash = {"tool_name": "Bash", "tool_input": {"command": f"echo {cid}"}}
        self.record(run, "PreToolUse", dict(bash, agent_id="a1b2c3d4", agent_type=agent_type(cid, install)))
        self.record(run, "PostToolUse", {**bash, **self.RAN})  # it ran, but the payload names no agent
        return run, self.observed(run, host_ran=True)

    def test_a1_asserts_agent_type_on_the_before_and_after_call_events(self) -> None:
        observations = {o["id"]: o for o in lib.load_cases("A1")[0]["observations"]}
        before, after = observations["agent-type"], observations["agent-type-after"]
        self.assertEqual((before["event"], after["event"]), ("PreToolUse", "PostToolUse"))
        for key in ("kind", "role", "where", "field", "expect", "value_by_install"):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after["role"], "assert")
        self.assertEqual(after["value_by_install"], {i: a1_agent_type(i) for i in lib.INSTALLS})

    def test_the_hooks_a1_renders_record_post_tool_use(self) -> None:
        hook_files = {"script": Path("repo/.claude/settings.json"), "plugin": Path("probe-plugin/hooks/hooks.json")}
        for install in lib.INSTALLS:
            with self.subTest(install=install):
                run = self.prepare("A1", install=install)
                hooks = json.loads((run.workspace / hook_files[install]).read_text())["hooks"]
                entries = hooks.get("PostToolUse") or []
                self.assertTrue(any(e.get("matcher") == "*" and any(h["command"].endswith("--event PostToolUse")
                                                                    for h in e["hooks"]) for e in entries), entries)

    def test_a1_unattributed_or_misattributed_post_tool_use_is_contradicted(self) -> None:
        for install in lib.INSTALLS:
            for post in ("unattributed", "other-agent"):
                with self.subTest(install=install, post=post):
                    _, state, checks = self.a1(install, post)
                    self.assertEqual(state.status, "contradicted", state.notes)
                    self.assertEqual((checks["agent-type"]["outcome"], checks["agent-type-after"]["outcome"]),
                                     ("pass", "fail"))
                    self.assertIn("failed: agent-type-after", state.notes)

    def test_a1_without_a_post_tool_use_is_inconclusive(self) -> None:
        """No PostToolUse is missing evidence, not a contradiction: the host may fire none inside subagents, or the
        call may have been cut short. Either way A1 isn't confirmed, so its dependents stay undecided."""
        for install in lib.INSTALLS:
            with self.subTest(install=install):
                _, state, checks = self.a1(install, "none")
                self.assertEqual(state.status, "inconclusive", state.notes)
                self.assertEqual(checks["agent-type-after"]["outcome"], "unknown")
                self.assertEqual(checks["agent-type-after"]["actual"], {"matched": 0})
                self.assertIn("no evidence: agent-type-after", state.notes)

    def test_a1_attributed_on_both_events_is_still_confirmed(self) -> None:
        for install in lib.INSTALLS:
            with self.subTest(install=install):
                _, state, checks = self.a1(install, "attributed")
                self.assertEqual(state.status, "confirmed", state.notes)
                self.assertEqual({checks[c]["outcome"] for c in ("agent-id", "agent-type", "agent-type-after")},
                                 {"pass"})

    def test_c1_c2_confirmed_on_a_pre_only_host_are_gated_inconclusive(self) -> None:
        for cid in ("C1", "C2"):
            for install in lib.INSTALLS:
                with self.subTest(case=cid, install=install):
                    c_run, c_state = self.c_pre_only_host(cid, install)
                    self.assertEqual(c_state.status, "confirmed", c_state.notes)  # the hazard: alone, it confirms
                    c_entry = lib.result_entry(c_run, c_state, None)
                    for post, a1_status in (("unattributed", "contradicted"), ("none", "inconclusive")):
                        a1_run, a1_state, _ = self.a1(install, post)
                        self.assertEqual(a1_state.status, a1_status, a1_state.notes)
                        doc = lib.result_document("claude", "0", [c_entry, lib.result_entry(a1_run, a1_state, None)])
                        self.assertEqual(lib.schema_errors(doc, "probe-result.schema.json"), [])
                        got = {(e["case"], e["install"]): e for e in doc["entries"]}[(cid, install)]
                        self.assertEqual(got["status"], "inconclusive")
                        self.assertIn(f"requires A1 confirmed (A1 {a1_status})", got["notes"])
                    a1_run, a1_state, _ = self.a1(install, "attributed")  # control: the gate is what changed
                    doc = lib.result_document("claude", "0", [c_entry, lib.result_entry(a1_run, a1_state, None)])
                    got = {(e["case"], e["install"]): e for e in doc["entries"]}[(cid, install)]
                    self.assertEqual(got["status"], "confirmed", got["notes"])


class StreamToolUseTests(RunHelpers, TempDirCase):
    """The `stream` `tool-use` check: a hook that can never record (E4) can't prove the call was attempted."""

    OBS = {"id": "bash-issued", "kind": "stream", "check": "tool-use", "role": "precondition", "names": ["Bash"],
           "description": "A Bash tool_use for the touch was issued.",
           "where": [{"field": "input.command", "op": "contains", "value": "marker-E4"}]}
    BASH = {"type": "tool_use", "id": "toolu_01", "name": "Bash", "input": {"command": "touch marker-E4"}}

    @staticmethod
    def assistant(*blocks: dict) -> dict:
        return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}

    def ctx(self, stream: list) -> "observe.Context":
        return observe.Context(records=[], repo=self.tmp, workspace=self.tmp, install="script", stream=stream)

    def test_tool_use_is_read_from_assistant_events(self) -> None:
        stream = [{"type": "system", "subtype": "init"}, self.assistant({"type": "text", "text": "ok"}, self.BASH)]
        self.assertEqual(observe.eval_stream(self.OBS, self.ctx(stream)), ("pass", {"count": 1}))  # no result event
        other_tool = self.assistant({"type": "tool_use", "name": "Read", "input": {"file_path": "marker-E4"}})
        other_command = self.assistant(dict(self.BASH, input={"command": "touch something-else"}))
        for stream in ([other_tool], [other_command], [{"type": "result", "subtype": "success"}]):
            self.assertEqual(observe.eval_stream(self.OBS, self.ctx(stream)), ("fail", {"count": 0}))
        self.assertEqual(observe.eval_stream(self.OBS, self.ctx([])), ("unknown", None))

    def test_evaluated_entry_never_carries_the_command_text(self) -> None:
        evaluated = observe.evaluate([self.OBS], self.ctx([self.assistant(self.BASH)]))
        self.assertEqual(evaluated[0]["expected"], "tool_use issued: Bash")
        self.assertNotIn("marker-E4", json.dumps(evaluated))

    def test_tool_use_needs_names(self) -> None:
        self.assertEqual(lib.check_observations([self.OBS], "obs"), [])
        nameless = {k: v for k, v in self.OBS.items() if k != "names"}
        self.assertTrue(any("needs names" in e for e in lib.check_observations([nameless], "obs")))

    def test_e4_is_inconclusive_until_the_stream_shows_the_call(self) -> None:
        """E4's hook never runs, so its absent marker means nothing until the stream shows the Bash tool_use."""
        for variant in lib.load_cases("E4")[0]["variants"]:
            issued = {o["id"]: o for o in variant["observations"]}.get("bash-issued")
            self.assertIsNotNone(issued, variant["id"])
            self.assertEqual((issued["kind"], issued["check"], issued["role"], issued["names"]),
                             ("stream", "tool-use", "precondition", ["Bash"]))
        run = self.prepare("E4", "on-failure-block")
        state = self.observed(run, host_ran=True)
        self.assertEqual(state.status, "inconclusive", state.notes)
        self.assertIn("precondition not met: bash-issued", state.notes)
        (run.workspace / "out" / "stream.jsonl").write_text(json.dumps(self.assistant(self.BASH)) + "\n")
        self.assertEqual(self.observed(run, host_ran=True).status, "confirmed")


# ---- permissions: --allowedTools, the trust check and denial sources (T0, 2.1.325) ---------------------------

# Synthetic texts in the shapes 2.1.325 printed in the first live run (paths replaced by <repo> and /tmp/ws).
UNTRUSTED_STDERR = ("Ignoring 15 permissions.allow entries from .claude/settings.json: this workspace has not been "
                    "trusted. Run Claude Code interactively here once and accept the trust dialog, or set "
                    'projects["<repo>"].hasTrustDialogAccepted: true in ~/.claude.json.\n')
NEEDS_APPROVAL = ("touch in '<repo>/marker-E1' needs approval. The path is inside the working directories for this "
                  "session ('<repo>'), and Claude Code asks before a shell command creates, changes or removes "
                  "files there.")
NOT_GRANTED = "Claude requested permissions to use mcp__probe-mcp__echo, but you haven't granted it yet."
ASYNC_DENIED = "Permission to use Bash has been denied. IMPORTANT: You *may* attempt this with other tools."
HOOK_DENY_TEXT = "PreToolUse:Edit hook error: probe L1: edits are blocked"
HOOK_BLOCK_TEXT = ('PreToolUse:Bash hook error: [/usr/bin/python3 /tmp/ws/bin/recorder.py --ctrl /tmp/ws/ctrl.json '
                   '--event PreToolUse]: timed out; blocking because onFailure is "block"')
NO_SUCH_TOOL = "<tool_use_error>Error: No such tool available: Bash.</tool_use_error>"
REWORDED_DENIAL = "This command was blocked before it ran. Ask the user to allow it."  # no known marker or wording
EXPECTS_PERMISSION_DENIAL = {"F1", "F2", "F3", "F4"}


def call(tool_use_id: str, name: str, tool_input: dict, text: str = None, denied: bool = False) -> tuple:
    return tool_use_id, name, tool_input, text, denied


def host_stream(*calls: tuple, split_results: bool = False) -> list:
    """A stream-json capture: each call's tool_use, its tool_result (when `text` is given), then the result event(s)
    with the denied calls. `split_results`: the denials sit in a first result, and a last one is empty (2.1.325 with a
    background agent)."""
    events, denials = [{"type": "system", "subtype": "init"}], []
    for tool_use_id, name, tool_input, text, denied in calls:
        events.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tool_use_id, "name": name, "input": tool_input}]}})
        if text is not None:
            events.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "is_error": denied, "content": text}]}})
        if denied:
            denials.append({"tool_name": name, "tool_use_id": tool_use_id, "tool_input": tool_input})
    result = {"type": "result", "subtype": "success", "total_cost_usd": 0.01}
    if split_results:
        return events + [dict(result, permission_denials=denials), dict(result, permission_denials=[])]
    return events + [dict(result, permission_denials=denials)]


def template_allow(template: str) -> list:
    return json.loads((lib.TEMPLATES_DIR / template).read_text())["permissions"]["allow"]


class AllowedToolsTests(unittest.TestCase):
    """Item 1: every claude call passes the rendered project settings' allow rules with --allowedTools."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = {c["id"]: c for c in lib.load_cases("all")}
        cls.root = Path(tempfile.gettempdir()) / "unused" / "daedalus-probes" / "ts"

    def runs(self, cid: str, installs: tuple = lib.INSTALLS, host: str = "claude") -> list:
        return lib.plan_runs([self.cases[cid]], installs, host, self.root)[0]

    def test_e1_argv_carries_the_templates_rules_for_script_and_plugin(self) -> None:
        expected = {"script": template_allow("script/settings.failure.json"),
                    "plugin": template_allow("plugin/project-settings.json")}
        for run in self.runs("E1"):
            with self.subTest(run=run.label):
                argv = lib.host_command(run)
                at = argv.index(lib.ALLOWED_TOOLS_FLAG)
                self.assertEqual(argv[at + 1:], expected[run.install])  # last, one rule per argument
                self.assertEqual(lib.cli_allowed_tools(argv), expected[run.install])
                self.assertEqual(lib.allow_rules(run), expected[run.install])

    def test_every_claude_run_passes_its_own_settings_rules(self) -> None:
        runs = lib.plan_runs(list(self.cases.values()), lib.INSTALLS, "claude", self.root)[0]
        self.assertEqual(len(runs), 65)
        for run in runs:
            settings = next(e["template"] for e in run.files if e["dest"] == "repo/.claude/settings.json")
            argv = lib.host_command(run)
            self.assertEqual(lib.cli_allowed_tools(argv), template_allow(settings), run.label)
            self.assertEqual(argv.count(lib.ALLOWED_TOOLS_FLAG), 1, run.label)
            self.assertEqual(argv[:3], ["claude", "-p", lib.stimulus(run)])  # no positional after the variadic flag

    def test_a_dropped_flag_and_the_other_hosts_pass_no_rules(self) -> None:
        run = self.runs("E1", ("script",))[0]
        self.assertNotIn(lib.ALLOWED_TOOLS_FLAG, lib.host_command(run, frozenset({lib.ALLOWED_TOOLS_FLAG})))
        self.assertNotIn(lib.ALLOWED_TOOLS_FLAG, lib.host_command(self.runs("K1", ("script",), "cursor")[0]))
        self.assertIn(lib.ALLOWED_TOOLS_FLAG, lib.OPTIONAL_FLAGS["claude"])

    def test_cli_allowed_tools_reads_both_spellings(self) -> None:
        self.assertEqual(lib.cli_allowed_tools(["claude", "-p", "go", "--allowed-tools", "Read", "Bash(echo *)",
                                                "--model", "haiku"]), ["Read", "Bash(echo *)"])
        self.assertEqual(lib.cli_allowed_tools(["--allowedTools=Read,Edit", "--verbose", "x"]), ["Read", "Edit"])
        self.assertEqual(lib.cli_allowed_tools(["claude", "-p", "Read"]), [])

    def test_project_settings_keep_their_allow_rules_and_hooks(self) -> None:
        """The settings files still carry the rules (intent) and the hooks; only the argv is new."""
        for template in ("script/settings.json", "script/settings.failure.json", "plugin/project-settings.json"):
            self.assertIn("Bash(touch *)", template_allow(template), template)
        self.assertIn("hooks", json.loads((lib.TEMPLATES_DIR / "script" / "settings.failure.json").read_text()))


def confirmed_e1(helper: RunHelpers):
    """E1 default (fail-open) with the hook record and the marker: `confirmed` on its own."""
    run = helper.prepare("E1", "default")
    helper.record(run, "PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "touch marker-E1"}})
    (run.repo / "marker-E1").touch()
    return run


class TrustCheckTests(RunHelpers, TempDirCase):
    """Item 2: the untrusted warning is inconclusive unless the host call passed every allow rule itself."""

    @staticmethod
    def warn(run) -> None:
        (run.workspace / "out" / "stderr.txt").write_text(UNTRUSTED_STDERR)

    def test_no_warning_no_note(self) -> None:
        state = self.observed(confirmed_e1(self), host_ran=True)
        self.assertEqual(state.status, "confirmed", state.notes)
        self.assertFalse([n for n in state.notes if "untrusted" in n])

    def test_warning_without_the_cli_rules_is_inconclusive(self) -> None:
        run = confirmed_e1(self)
        self.warn(run)
        full = lib.host_command(run)
        for label, argv in (("no argv", []), ("flag dropped", lib.host_command(run, frozenset({"--allowedTools"}))),
                            ("one rule short", full[:-1])):
            with self.subTest(label):
                state = self.observed(run, host_ran=True, host_argv=argv)
                self.assertEqual(state.status, "inconclusive")
                self.assertIn(lib.UNTRUSTED_NOTE, state.notes)
                self.assertNotIn(lib.UNTRUSTED_COVERED_NOTE, state.notes)

    def test_warning_with_the_cli_rules_is_a_recorded_note(self) -> None:
        run = confirmed_e1(self)
        self.warn(run)
        state = self.observed(run, host_ran=True, host_argv=lib.host_command(run))
        self.assertEqual(state.status, "confirmed", state.notes)
        self.assertIn(lib.UNTRUSTED_COVERED_NOTE, state.notes)
        self.assertNotIn(lib.UNTRUSTED_NOTE, state.notes)


class DenialTests(RunHelpers, TempDirCase):
    """Item 3: each permission_denials entry is classified from its tool_result, and only a permission denial of the
    probed call takes the verdict away (unless the case expects one)."""

    MARKERS = ("probe L1: edits are blocked", "probe F1: ask", lib.RECORDER_DEFAULT_REASON,
               lib.RECORDER_CRASH_MESSAGE, lib.RECORDER_COMMAND_MARKER)

    @staticmethod
    def stream(run, events: list) -> None:
        (run.workspace / "out" / "stream.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    @staticmethod
    def sources(state) -> dict:
        return next(e for e in state.evaluated if e["check"] == "denial-sources")

    def test_recorder_texts_match_recorder_py(self) -> None:
        import recorder
        self.assertEqual((lib.RECORDER_DEFAULT_REASON, lib.RECORDER_CRASH_MESSAGE),
                         (recorder.DEFAULT_REASON, recorder.CRASH_MESSAGE))
        run = self.plan("L1")[1]
        self.assertEqual(lib.hook_markers(run)[0], "probe L1: edits are blocked")
        self.assertIn(lib.RECORDER_COMMAND_MARKER, lib.template_vars(run)["HOOK_COMMAND"])

    def test_classification_hook_permission_unknown(self) -> None:
        crash = HOOK_BLOCK_TEXT.replace("timed out", "failed") + "\n" + lib.RECORDER_CRASH_MESSAGE
        expected = {HOOK_DENY_TEXT: "hook", HOOK_BLOCK_TEXT: "hook", crash: "hook", "probe F1: ask": "hook",
                    NEEDS_APPROVAL: "permission", NOT_GRANTED: "permission", ASYNC_DENIED: "permission",
                    NO_SUCH_TOOL: "unknown", "": "unknown"}
        for text, source in expected.items():
            self.assertEqual(observe.classify_denial(text, self.MARKERS), source, text[:40])

    def test_denials_are_read_from_every_result_and_matched_by_tool_use_id(self) -> None:
        bash = {"command": "touch marker-E1"}
        events = host_stream(call("toolu_a", "Bash", bash, NEEDS_APPROVAL, True),
                             call("toolu_b", "Edit", {"file_path": "seed.txt"}, HOOK_DENY_TEXT, True),
                             call("toolu_c", "Bash", {"command": "ls"}, None, True), split_results=True)
        events[-1]["permission_denials"] = [events[-2]["permission_denials"][0]]  # a repeat in a later result
        denials = observe.classify_denials(events, self.MARKERS)
        self.assertEqual([(d.tool_use_id, d.source) for d in denials],
                         [("toolu_a", "permission"), ("toolu_b", "hook"), ("toolu_c", "unknown")])  # no tool_result
        blocks = [{"type": "text", "text": "probe F1: "}, {"type": "text", "text": "ask"}]
        listed = [{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "x",
                                                             "content": blocks}]}}]
        self.assertEqual(observe.tool_results(listed), {"x": "probe F1: \nask"})

    def test_every_run_gets_a_denial_sources_record_without_command_text(self) -> None:
        run = self.prepare("E1", "default")
        empty = self.sources(self.observed(run, host_ran=True))
        self.assertEqual(empty["actual"], {"hook": 0, "permission": 0, "unknown": 0, "denials": []})
        self.assertEqual((empty["role"], empty["outcome"]), ("record", "recorded"))
        touch = {"command": "/usr/bin/touch marker-E1"}
        self.stream(run, host_stream(call("toolu_a", "Bash", touch, NEEDS_APPROVAL, True),
                                     call("toolu_m", "mcp__probe-mcp__echo", {"text": "secret-arg"}, NOT_GRANTED,
                                          True)))
        record = self.sources(self.observed(run, host_ran=True))
        self.assertEqual(record["actual"], {"hook": 0, "permission": 2, "unknown": 0, "denials": [
            {"tool": "Bash", "source": "permission", "probed_call": True, "command": "touch"},
            {"tool": "mcp__probe-mcp__echo", "source": "permission", "probed_call": False}]})
        text = json.dumps(record)
        for leak in ("marker-E1", "/usr/bin", "secret-arg", "needs approval"):
            self.assertNotIn(leak, text)

    def test_a_permission_denial_of_the_probed_call_is_inconclusive(self) -> None:
        run = self.prepare("E1", "default")
        self.record(run, "PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "touch marker-E1"},
                                        "tool_use_id": "toolu_e1"})
        self.assertEqual(self.observed(run, host_ran=True).status, "contradicted")  # the confound, alone
        self.stream(run, host_stream(call("toolu_e1", "Bash", {"command": "touch marker-E1"}, NEEDS_APPROVAL, True)))
        state = self.observed(run, host_ran=True)
        self.assertEqual(state.status, "inconclusive", state.notes)
        self.assertIn(f"{lib.PERMISSION_DENIAL_NOTE} (Bash)", state.notes)

    def test_a_hook_denial_of_the_probed_call_keeps_the_verdict(self) -> None:
        e5_text = "PreToolUse:Bash hook error: [x]: probe E5: blocked"
        for cid, variant, tool, tool_input, text in (
                ("E1", "on-failure-block", "Bash", {"command": "touch marker-E1"}, HOOK_BLOCK_TEXT),
                ("E5", "default", "Bash", {"command": "touch marker-E5"}, e5_text)):
            with self.subTest(case=cid, variant=variant):
                run = self.prepare(cid, variant)
                self.record(run, "PreToolUse", {"tool_name": tool, "tool_input": tool_input, "tool_use_id": "toolu_h"})
                self.stream(run, host_stream(call("toolu_h", tool, tool_input, text, True)))
                state = self.observed(run, host_ran=True)
                self.assertEqual(state.status, "confirmed", state.notes)
                self.assertEqual(self.sources(state)["actual"]["denials"],
                                 [{"tool": tool, "source": "hook", "probed_call": True, "command": "touch"}])
        run = self.prepare("L1")
        for agent in (None, "probe-reader"):
            payload = {"tool_name": "Edit", "tool_input": {"file_path": str(run.repo / "seed.txt")},
                       "tool_use_id": f"toolu_{agent}"}
            self.record(run, "PreToolUse", dict(payload, agent_type=agent) if agent else payload)
        self.stream(run, host_stream(call("toolu_None", "Edit", {"file_path": "seed.txt"}, HOOK_DENY_TEXT, True)))
        self.assertEqual(self.observed(run, host_ran=True).status, "confirmed")

    def test_an_unknown_denial_of_the_probed_call_is_inconclusive(self) -> None:
        """Regression (39cf56d-2): a host that rewords its permission denial must not leave fail-closed confirmed."""
        self.assertEqual(observe.classify_denial(REWORDED_DENIAL, self.MARKERS), "unknown")
        touch = {"command": "touch marker-E1"}
        for label, text in (("reworded", REWORDED_DENIAL), ("no tool_result", None)):
            with self.subTest(label):
                run = self.prepare("E1", "on-failure-block")
                self.record(run, "PreToolUse", {"tool_name": "Bash", "tool_input": touch, "tool_use_id": "toolu_u"})
                self.assertEqual(self.observed(run, host_ran=True).status, "confirmed")  # the confound, alone
                self.stream(run, host_stream(call("toolu_u", "Bash", touch, text, True)))
                state = self.observed(run, host_ran=True)
                self.assertEqual(state.status, "inconclusive", state.notes)
                self.assertIn(f"{lib.UNATTRIBUTED_DENIAL_NOTE} (Bash)", state.notes)
                self.assertNotIn(f"{lib.PERMISSION_DENIAL_NOTE} (Bash)", state.notes)
                self.assertEqual(self.sources(state)["actual"]["denials"],
                                 [{"tool": "Bash", "source": "unknown", "probed_call": True, "command": "touch"}])

    def test_an_unknown_denial_of_another_call_or_in_f1_keeps_the_verdict(self) -> None:
        run = confirmed_e1(self)
        self.stream(run, host_stream(call("toolu_x", "Bash", {"command": "ls -la"}, REWORDED_DENIAL, True)))
        self.assertEqual(self.observed(run, host_ran=True).status, "confirmed")
        run = self.prepare("F1")
        self.record(run, "PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "touch marker-F1"},
                                        "tool_use_id": "toolu_f1"})
        self.stream(run, host_stream(call("toolu_f1", "Bash", {"command": "touch marker-F1"}, REWORDED_DENIAL, True)))
        state = self.observed(run, host_ran=True)
        self.assertEqual(state.status, "confirmed", state.notes)  # expects_permission_denial: exempt
        self.assertIn(lib.EXPECTED_DENIAL_NOTE, state.notes)

    def test_published_results_have_no_unattributed_probed_denials(self) -> None:
        """39cf56d-2 changes no published entry: no run on record has an `unknown` denial of its probed call."""
        doc = json.loads((lib.RESULTS_DIR / "claude-2.1.325.json").read_text())
        hits = [(e["case"], e["install"]) for e in doc["entries"] for o in e["observations"]
                if o["check"] == "denial-sources" for d in o["actual"]["denials"]
                if d["source"] == "unknown" and d["probed_call"]]
        self.assertEqual(hits, [])

    def test_a_permission_denial_of_another_call_keeps_the_verdict(self) -> None:
        run = confirmed_e1(self)
        self.stream(run, host_stream(call("toolu_x", "Bash", {"command": "ls -la"}, NEEDS_APPROVAL, True)))
        state = self.observed(run, host_ran=True)
        self.assertEqual(state.status, "confirmed", state.notes)
        self.assertFalse(self.sources(state)["actual"]["denials"][0]["probed_call"])

    def test_only_f1_to_f4_expect_a_permission_denial(self) -> None:
        cases = {c["id"]: c for c in lib.load_cases("all")}
        self.assertEqual({cid for cid, c in cases.items() if c.get("expects_permission_denial")},
                         EXPECTS_PERMISSION_DENIAL)
        self.assertTrue(all(c.get("expects_permission_denial") is True for cid, c in cases.items()
                            if cid in EXPECTS_PERMISSION_DENIAL))
        wrong = dict(cases["F1"], expects_permission_denial="yes")
        self.assertTrue(lib.validate_case(wrong, lib.CASES_DIR / "F1.json"))
        run = self.prepare("F1")
        self.record(run, "PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "touch marker-F1"},
                                        "tool_use_id": "toolu_f1"})
        self.stream(run, host_stream(call("toolu_f1", "Bash", {"command": "touch marker-F1"}, NEEDS_APPROVAL, True)))
        state = self.observed(run, host_ran=True)
        self.assertEqual(state.status, "confirmed", state.notes)  # the ask was denied by the host: the mechanism
        self.assertIn(lib.EXPECTED_DENIAL_NOTE, state.notes)

    def test_the_join_decides_attribution_and_an_unjoined_clause_counts_as_a_match(self) -> None:
        """C1's probed call is the agent's `echo C1`: a main-thread denial (recorded without agent_type) isn't it; a
        denial with no PreToolUse to join can't be attributed, so it counts."""
        run = self.prepare("C1")
        self.record(run, "PreToolUse", SPAWN)
        self.record(run, "SubagentStart", {"agent_id": "a1b2c3d4", "agent_type": agent_type("C1")})
        echo = {"command": "echo C1"}
        self.record(run, "PreToolUse", {"tool_name": "Bash", "tool_input": echo, "tool_use_id": "toolu_main"})
        self.stream(run, host_stream(call("toolu_main", "Bash", echo, ASYNC_DENIED, True)))
        self.assertEqual(self.observed(run, host_ran=True).status, "confirmed")
        self.stream(run, host_stream(call("toolu_lost", "Bash", echo, ASYNC_DENIED, True)))
        state = self.observed(run, host_ran=True)
        self.assertEqual(state.status, "inconclusive", state.notes)
        self.assertIn(f"{lib.PERMISSION_DENIAL_NOTE} (Bash)", state.notes)

    def test_a_stream_tool_use_selector_catches_a_call_no_hook_saw(self) -> None:
        """E4's hook never runs: its probed call is the stream's Bash tool_use."""
        run = self.prepare("E4", "default")
        self.stream(run, host_stream(call("toolu_e4", "Bash", {"command": "touch marker-E4"}, NEEDS_APPROVAL, True)))
        state = self.observed(run, host_ran=True)
        self.assertEqual(state.status, "inconclusive", state.notes)  # without the rule: contradicted (no marker)
        self.assertIn(f"{lib.PERMISSION_DENIAL_NOTE} (Bash)", state.notes)


# A fake `claude` for end-to-end runs through run_all: logs its argv, prints the spec's stderr, feeds the spec's hook
# calls through the rendered project hooks (as the host would), touches the spec's files, then prints the stream.
FAKE_HOST = r'''
import json, os, subprocess, sys
from pathlib import Path

spec = json.loads(Path(os.environ["FAKE_HOST_SPEC"]).read_text())
with open(spec["log"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
sys.stderr.write(spec.get("stderr", ""))
hooks = json.loads(Path(".claude/settings.json").read_text()).get("hooks", {})
for event, payload in spec.get("hook_calls", []):
    command = hooks[event][0]["hooks"][0]["command"]
    subprocess.run(command, shell=True, input=json.dumps(dict(payload, hook_event_name=event)), text=True,
                   capture_output=True, timeout=30)
for name in spec.get("touch", []):
    Path(name).touch()
for event in spec["stream"]:
    print(json.dumps(event))
'''


class FakeClaudeRunTests(TempDirCase):
    """Items 1-3 end to end: run_all runs a fake `claude` (first on PATH); the real CLI is never called."""

    TOUCH = {"command": "touch marker-E1"}

    def setUp(self) -> None:
        super().setUp()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(f"#!{sys.executable}\n{FAKE_HOST}")
        fake.chmod(0o755)
        self.spec, self.log = self.tmp / "spec.json", self.tmp / "argv.jsonl"
        patcher = mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                                               "FAKE_HOST_SPEC": str(self.spec)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runs = 0

    def run_e1(self, spec: dict, dropped: frozenset = frozenset()) -> tuple:
        self.spec.write_text(json.dumps(dict(spec, log=str(self.log))))
        self.log.unlink(missing_ok=True)
        root = self.tmp / "daedalus-probes"
        self.runs += 1
        run_root = root / f"ts{self.runs}"
        case = lib.load_cases("E1")[0]
        runs = [r for r in lib.plan_runs([case], ("script",), "claude", run_root)[0] if r.variant_id == "default"]
        entries, failures = [], []
        with mock.patch.object(lib, "probe_root", return_value=root):
            lib.run_all(runs, "9.9.9", dropped, 10.0, run_root / "staged", None, entries, failures, lambda line: None)
        self.assertEqual(failures, [])
        argv = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len(argv), 1)
        return entries[0], argv[0]

    def hook_call(self) -> list:
        return [["PreToolUse", {"tool_name": "Bash", "tool_input": self.TOUCH, "tool_use_id": "toolu_e1"}]]

    def test_rules_passed_and_the_call_allowed_confirms_with_a_recorded_note(self) -> None:
        entry, argv = self.run_e1({"stderr": UNTRUSTED_STDERR, "hook_calls": self.hook_call(), "touch": ["marker-E1"],
                                   "stream": host_stream(call("toolu_e1", "Bash", self.TOUCH, "", False))})
        self.assertEqual(lib.cli_allowed_tools(argv), template_allow("script/settings.failure.json"))
        self.assertEqual(entry["status"], "confirmed", entry["notes"])
        self.assertIn(lib.UNTRUSTED_COVERED_NOTE, entry["notes"])
        self.assertEqual(lib.schema_errors(lib.result_document("claude", "9.9.9", [entry]),
                                           "probe-result.schema.json"), [])

    def test_rules_not_passed_in_an_untrusted_folder_is_inconclusive(self) -> None:
        entry, argv = self.run_e1({"stderr": UNTRUSTED_STDERR, "hook_calls": self.hook_call(), "touch": ["marker-E1"],
                                   "stream": host_stream(call("toolu_e1", "Bash", self.TOUCH, "", False))},
                                  dropped=frozenset({lib.ALLOWED_TOOLS_FLAG}))
        self.assertNotIn(lib.ALLOWED_TOOLS_FLAG, argv)
        self.assertEqual(entry["status"], "inconclusive")
        self.assertIn(lib.UNTRUSTED_NOTE, entry["notes"])

    def test_a_permission_denial_of_the_probed_call_is_inconclusive(self) -> None:
        entry, _ = self.run_e1({"hook_calls": self.hook_call(),
                                "stream": host_stream(call("toolu_e1", "Bash", self.TOUCH, NEEDS_APPROVAL, True))})
        self.assertEqual(entry["status"], "inconclusive")  # alone: contradicted (no marker)
        self.assertIn(f"{lib.PERMISSION_DENIAL_NOTE} (Bash)", entry["notes"])
        record = next(o for o in entry["observations"] if o["check"] == "denial-sources")
        self.assertEqual(record["actual"]["permission"], 1)


class PublishTests(TempDirCase):
    """Item 4: a rerun replaces the same (host, version, case, variant, install) entries and fixtures, all or nothing,
    inside fixtures/ and results/ only."""

    def setUp(self) -> None:
        super().setUp()
        self.hub = self.tmp / "hub"
        self.fixtures, self.results = self.hub / "fixtures", self.hub / "results"
        self.fixtures.mkdir(parents=True)
        (self.fixtures / "README.md").write_text("keep\n")
        for name, value in (("FIXTURES_DIR", self.fixtures), ("RESULTS_DIR", self.results)):
            patcher = mock.patch.object(lib, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cases = {c["id"]: c for c in lib.load_cases("all")}
        self.stagings = 0

    def entry(self, cid: str, variant: str, status: str, fixture_names: list) -> dict:
        case = self.cases[cid]
        chosen = next((v for v in case.get("variants", []) if v["id"] == variant), None)
        run = lib.Run(case, "script", "claude", Path("/nonexistent"), chosen)
        state = lib.RunState(host_version="9.9.9", status=status,
                             fixture_ids=[f"claude-9.9.9/{run.segment}/script/{n[:-5]}" for n in fixture_names])
        return lib.result_entry(run, state, None)

    def stage(self, runs: list) -> Path:
        """runs: [(entry, {fixture name: seq})]; returns the staging folder."""
        self.stagings += 1
        staging = self.tmp / f"stage{self.stagings}" / "staged"
        for entry, fixtures in runs:
            folder = staging / "fixtures" / "claude-9.9.9" / lib.fixture_key(entry)
            for name, seq in fixtures.items():
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_text(json.dumps({"seq": seq}))
        lib.stage_results(staging, "claude", "9.9.9", [entry for entry, _ in runs])
        return staging

    def tree(self) -> dict:
        return {str(p.relative_to(self.hub)): p.read_text() for p in sorted(self.hub.rglob("*")) if p.is_file()}

    def first_publish(self) -> None:
        e1 = self.entry("E1", "default", "contradicted", ["PreToolUse-1.json", "PreToolUse-2.json"])
        a3 = self.entry("A3", None, "confirmed", ["PreToolUse-1.json"])
        lib.publish(self.stage([(e1, {"PreToolUse-1.json": 1, "PreToolUse-2.json": 2}),
                                (a3, {"PreToolUse-1.json": 7})]), "claude", "9.9.9")

    def published(self) -> dict:
        doc = json.loads((self.results / "claude-9.9.9.json").read_text())
        self.assertEqual(lib.schema_errors(doc, "probe-result.schema.json"), [])
        return doc

    def test_a_rerun_replaces_the_same_keys_entries_and_fixtures(self) -> None:
        self.first_publish()
        e1 = self.entry("E1", "default", "inconclusive", ["PreToolUse-1.json"])
        written = lib.publish(self.stage([(e1, {"PreToolUse-1.json": 9})]), "claude", "9.9.9")
        e1_dir = self.fixtures / "claude-9.9.9" / "E1.default" / "script"
        self.assertEqual(sorted(p.name for p in e1_dir.iterdir()), ["PreToolUse-1.json"])  # PreToolUse-2 is gone
        self.assertEqual(json.loads((e1_dir / "PreToolUse-1.json").read_text()), {"seq": 9})
        a3_file = self.fixtures / "claude-9.9.9" / "A3" / "script" / "PreToolUse-1.json"
        self.assertEqual(json.loads(a3_file.read_text()), {"seq": 7})  # a key the rerun didn't run is kept
        entries = {(e["case"], e["variant"], e["install"]): e for e in self.published()["entries"]}
        self.assertEqual(len(self.published()["entries"]), 2)
        self.assertEqual(entries[("E1", "default", "script")]["status"], "inconclusive")
        self.assertEqual(entries[("E1", "default", "script")]["fixture_ids"],
                         ["claude-9.9.9/E1.default/script/PreToolUse-1"])
        self.assertEqual(entries[("A3", None, "script")]["status"], "confirmed")
        self.assertEqual(sorted(written), sorted([str(e1_dir), str(self.results / "claude-9.9.9.json")]))
        self.assertEqual(sorted(p.name for p in self.hub.rglob(".publish-*")), [])

    def test_a_rerun_without_fixtures_removes_the_old_ones(self) -> None:
        self.first_publish()
        lib.publish(self.stage([(self.entry("E1", "default", "inconclusive", []), {})]), "claude", "9.9.9")
        self.assertFalse((self.fixtures / "claude-9.9.9" / "E1.default").exists())
        self.assertTrue((self.fixtures / "claude-9.9.9" / "A3" / "script" / "PreToolUse-1.json").is_file())
        self.assertEqual(len(self.published()["entries"]), 2)

    def not_run(self, cid: str, note: str = None) -> dict:
        run = lib.Run(self.cases[cid], "script", "claude", Path("/nonexistent"))
        entry = lib.not_run_entry(run, "9.9.9", "budget exhausted")
        return dict(entry, notes=[note]) if note else entry

    def publish_c1_confirmed(self) -> tuple:
        a1 = self.entry("A1", None, "confirmed", ["PreToolUse-1.json"])
        c1 = self.entry("C1", None, "confirmed", ["PreToolUse-1.json", "SubagentStart-1.json"])
        lib.publish(self.stage([(a1, {"PreToolUse-1.json": 1}),
                                (c1, {"PreToolUse-1.json": 2, "SubagentStart-1.json": 3})]), "claude", "9.9.9")
        c1_published = next(e for e in self.published()["entries"] if e["case"] == "C1")
        self.assertEqual(c1_published["status"], "confirmed")
        return c1_published, self.tree()

    def test_a_budget_skipped_rerun_keeps_the_earlier_entry_and_fixtures(self) -> None:
        """Regression (39cf56d-3): a not-run entry neither deletes the key's fixtures nor replaces its entry."""
        c1_before, tree_before = self.publish_c1_confirmed()
        staging = self.stage([(self.not_run("C1"), {})])
        self.assertTrue(lib.is_not_run(self.not_run("C1")))
        self.assertEqual(lib.published_keys(staging / "fixtures" / "claude-9.9.9", [self.not_run("C1")]), [])
        written = lib.publish(staging, "claude", "9.9.9")
        self.assertEqual(written, [str(self.results / "claude-9.9.9.json")])
        entries = self.published()["entries"]
        self.assertEqual([e for e in entries if e["case"] == "C1"], [c1_before])
        fixtures = {k: v for k, v in self.tree().items() if k.startswith("fixtures/")}
        self.assertEqual(fixtures, {k: v for k, v in tree_before.items() if k.startswith("fixtures/")})

    def test_a_skipped_host_call_keeps_the_earlier_entry_and_fixtures(self) -> None:
        c1_before, tree_before = self.publish_c1_confirmed()
        skipped = self.not_run("C1", lib.HOST_NOT_RUN_NOTE)
        staging = self.stage([(skipped, {})])
        (staging / "fixtures" / "claude-9.9.9" / "C1" / "script").mkdir(parents=True)  # redact_run's empty folder
        lib.publish(staging, "claude", "9.9.9")
        self.assertEqual([e for e in self.published()["entries"] if e["case"] == "C1"], [c1_before])
        self.assertTrue((self.fixtures / "claude-9.9.9" / "C1" / "script" / "SubagentStart-1.json").is_file())

    def test_a_not_run_entry_still_fills_a_key_with_no_entry(self) -> None:
        self.first_publish()
        lib.publish(self.stage([(self.not_run("A1"), {})]), "claude", "9.9.9")
        a1 = [e for e in self.published()["entries"] if e["case"] == "A1"]
        self.assertEqual([(e["status"], e["notes"]) for e in a1], [("inconclusive", ["not run: budget exhausted"])])
        self.assertEqual(len(self.published()["entries"]), 3)

    def test_a_failed_publish_leaves_the_hub_unchanged(self) -> None:
        self.first_publish()
        before = self.tree()
        staging = self.stage([(self.entry("E1", "default", "confirmed", ["PreToolUse-1.json"]),
                               {"PreToolUse-1.json": 5})])
        for label, patch in (("results replace", mock.patch("os.replace", side_effect=OSError("disk full"))),
                             ("before the swap", mock.patch.object(lib, "result_document", side_effect=OSError("x")))):
            with self.subTest(label), patch:
                with self.assertRaises(OSError):
                    lib.publish(staging, "claude", "9.9.9")
                self.assertEqual(self.tree(), before)
                self.assertEqual(sorted(p.name for p in self.hub.rglob(".publish-*")), [])

    def test_publish_writes_only_inside_fixtures_and_results(self) -> None:
        (self.hub / "elsewhere.txt").write_text("x")
        self.first_publish()
        outside = [p for p in self.tree() if not p.startswith(("fixtures/", "results/"))]
        self.assertEqual(outside, ["elsewhere.txt"])


if __name__ == "__main__":
    verbosity = 2 if "-v" in sys.argv[1:] else 1
    result = unittest.main(argv=[sys.argv[0]], verbosity=verbosity, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
PY
