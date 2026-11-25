# Capability probes

Maintainer tooling for the P0 hardening phase (`docs/plans/daedalus-hardening-p0.md`, §3.2–§3.4; AC-1, AC-2, AC-3). The probes ask the host CLI questions that the hardening roadmap depends on: are hook payloads tagged with agent identity, can a hook deny a spawn, an edit, a fetch or an MCP call, what happens when a hook crashes or times out, and so on. Each question is one case file. Each answer is a `daedalus.probe-result/1` entry backed by redacted fixtures.

Nothing here ships in a plugin: `scripts/build-plugin.sh` reads only `.claude/`.

## Safety

- **Isolation.** Every run happens in a fresh throwaway git repository under `$TMPDIR/daedalus-probes/<UTC-ts>/<case>[.<variant>]/<install>/`. The runner never writes to `~/.claude`, `~/.cursor`, `~/.codex`, user-scope settings or the hub's own `.claude/`. Templates live under `templates/script/…` rather than a literal `.claude/` folder, so the hub's own sessions never discover probe agents, commands or hooks.
- **Cleanup and post-run check.** After each run the runner removes everything it installed: `repo/.claude`, `repo/.cursor`, `repo/.codex`, `repo/.mcp.json`, `probe-plugin/`, `bin/` and `ctrl.json`. It then confirms nothing is left. After the last run it compares the hub's `git status --porcelain` and SHA-256 digests of `~/.claude/settings.json`, the user plugin registries and the Cursor and Codex user hook files (plus `claude plugin list`) with a snapshot taken before the first run. Any difference is a FAIL.
- **Publishing.** Fixtures and results are staged in `$TMPDIR` first. They're copied into `fixtures/` and `results/` only when the isolation check and the leak scan are both clean.
- **Cost.**
  - Live runs refuse to start without `--budget-usd`. They print the run count and the estimated ceiling (the sum of the cases' per-run caps) and refuse when the ceiling exceeds the budget.
  - Every `claude` call gets `--model haiku`, `--max-budget-usd <case cap>` and `--max-turns <case cap>`.
  - The runner stops starting runs once the spend reported so far plus the next run's cap would pass the budget.
  - Cursor and Codex have no budget flag, so only the per-run timeout applies.
- **Dry run.** `--dry-run` prints every action, makes no model calls and writes nothing.
- **Raw payloads.** Raw payloads (`out/raw/*.jsonl`) stay in `$TMPDIR` and are never committed. Only `redact.py` output reaches `fixtures/`.

## Usage

```bash
bash scripts/probes/run-probes.sh --case A1 --install both --dry-run          # preview, no model calls
bash scripts/probes/run-probes.sh --case all --dry-run                        # all Claude Code cases
bash scripts/probes/run-probes.sh --case K1 --host cursor --dry-run           # Cursor CLI case
bash scripts/probes/run-probes.sh --case all --install both --budget-usd 15   # live (P0b, maintainer only)
```

| Flag | Values | Default |
|---|---|---|
| `--case` | a case id or `all` | required |
| `--install` | `script`, `plugin`, `both` | `both` |
| `--host` | `claude`, `cursor`, `codex` | `claude` |
| `--budget-usd` | total for a live run | required unless `--dry-run` |
| `--dry-run` | print the actions only | off |

**Exit codes:**
- `0`: ok.
- `1`: FAIL (a harness error, cleanup leftovers, an isolation difference or a redaction leak); nothing is published.
- `2`: refused or BLOCKED (usage, budget, a missing CLI or a missing required flag).

A missing `claude` CLI is BLOCKED (env). A missing `agent` (Cursor) or `codex` CLI records every K run as `docs-only` (§3.10).

## Files

| Path | What |
|---|---|
| `run-probes.sh` | CLI: argparse and the top-level flow in an embedded Python heredoc |
| `probelib.py` | Cases, template rendering, the action list, host commands, the budget guard, the live loop, results |
| `observe.py` | Evaluates a case's observations against one capture and decides its status |
| `isolation.py` | Snapshot and compare (hub and user scope), guarded `safe_remove`, leftover check |
| `recorder.py` | The hook command used inside probe projects |
| `redact.py` | Redaction library and CLI (`payload`, `capture`, `scan`) |
| `cases/<id>.json` | 30 case definitions (`daedalus.probe-case/1`, `bench/schema/probe-case.schema.json`) |
| `templates/{script,plugin,cursor,codex}/…` | Settings and hook files, probe agents, the probe command, and the `probe-mcp` server |
| `fixtures/` | Redacted fixtures from live runs (P0b) |
| `results/` | `<host>-<version>.json` result files from live runs (P0b) |
| `testdata/` | Synthetic, redacted samples used by `scripts/test-probes.sh` |

## Cases

S = script install (project `.claude/`), P = plugin install (generated `probe-plugin/`). Every Claude Code case runs on S and P unless noted.

| Case | Question | Notes |
|---|---|---|
| A1, A2, A3 | Agent identity on subagent calls, under concurrency, and absent on the main thread | A2 checks echo text (raw) and agent_id ↔ agent_type consistency, which also works on redacted fixtures |
| B1, B2 | What a spawn PreToolUse carries; whether a hook can deny a spawn | |
| C1–C4 | `tools`, `disallowedTools`, `maxTurns`, per-agent `hooks` and `permissionMode` | Each needs the probe agent's own `SubagentStart` (the agent really started), and C3 needs a step read by the agent. Only the agent's calls count (see Attribution). C4 expects S honored, P ignored (`expect_by_install`), and is inconclusive if the main thread edits `seed.txt` itself |
| D1 | `UserPromptSubmit` and `UserPromptExpansion` for `/probe-cmd x` | |
| E1–E5 | `crash`, `timeout`, `invalid-json`, `missing-interpreter`, `exit2` | Each has a `default` and an `on-failure-block` variant. E1–E3 and E5 need the recorder's PreToolUse for the touch (`hook-ran`). E4's hook never runs, so it needs the stream's Bash `tool_use` instead (`stream` check `tool-use`) |
| F1–F4 | `ask` under `-p`, `dontAsk`, a subagent, a background subagent | F3 and F4 need the agent's own touch, and are inconclusive if the main thread attempts it. F5 is interactive and lives in the QA checklist |
| G1 | Per-subagent usage from `agent_transcript_path` | |
| H1, H2 | Stopping an agent by denying its tools; a one-shot `Stop` block | H2 needs one `Stop` before a missing second one counts |
| I1 | Sandbox coverage for a subagent (macOS and Linux only) | Needs the agent's own outside write, and is inconclusive if the main thread attempts it |
| J1 | Native worktree isolation | Evaluated by the maintainer (`evaluate: manual`) |
| L1 | A hook denying `Edit\|Write\|MultiEdit` on the main thread and in a subagent | Both preconditions need an edit aimed at `seed.txt` |
| M1, M2 | `WebFetch` and `mcp__.*` matchers | M2 runs the stdlib `probe-mcp` server |
| N1 | Bare-name resolution with a project and a plugin `probe-reader` | Runs once as the plugin install, with the project agent present too |
| K1, K2 | Cursor and Codex hooks | Variants for deny and crash (with Cursor's `failClosed`) |

**Case format:**
- **Required keys:** `schema`, `id`, `title`, `refs`, `applies_to` (`installs`, `hosts`, optional `os`), `files` (per install: `{template, dest}`), `ctrl`, `stimulus.prompt`, `flags` (`max_turns`, `max_budget_usd`, optional `permission_mode`, `timeout_s`), `observations[]` and `status_rules`.
- **Optional keys:** `vars`, `variants`, `notes` and `requires` (case ids the verdict depends on; see Attribution).
- **Template destinations** stay under `repo/` or `probe-plugin/`.
- **Template variables** (`{{NAME}}`):
  - `HOOK_COMMAND` (the recorder, with the case's interpreter and dialect) and `RECORD_COMMAND` (always the real interpreter);
  - `FRONTMATTER_COMMAND_JSON`, `HOOK_TIMEOUT`, `ON_FAILURE`, `FAIL_CLOSED` (null drops the key);
  - `REPO`, `WORKSPACE`, `AGENT_PREFIX` (`probe:` on plugin installs), `PLUGIN_NAME`, `CASE`, `PYTHON` and `MCP_SERVER`.
- **Observations** are documented in `observe.py`.
- **Status:**
  - a run whose host didn't run (for example a plugin run while `--plugin-dir` is missing) or timed out is `inconclusive`, whatever its checks say;
  - a failed precondition means `inconclusive`;
  - any failed assertion means `contradicted` (a finding, not a failure);
  - all assertions passing means `confirmed`;
  - `evaluate: manual` records the facts and leaves the verdict to the findings document;
  - a `confirmed` or `contradicted` entry of a case with `requires` becomes `inconclusive`, with the note `requires <id> confirmed (<id> <status>)`, unless each required case is `confirmed` for the same host version and install (see Attribution).
- **Preconditions prove the attempt.** An asserted absence (no marker, no PostToolUse, fewer than n calls) also passes when nothing happened. So a case that asserts one also has a precondition showing the probed call was made: a hook record of the call, `SubagentStart`, or a `tool_use` in the stream. Without it, a run that never tried the call is `inconclusive`, not `confirmed` or `contradicted`.
- **Attribution depends on A1.** In C1–C4, F3, F4 and I1, a helpful main thread could otherwise decide the case by doing the agent's work itself. So:
  - the observations about the probe agent (its `SubagentStart`, its tool calls, its `SubagentStop`) match only payloads whose `agent_type` ends in the agent's name (`probe-tools`, or `probe:probe-tools` on plugin installs; `{"field": "agent_type", "op": "endswith", "value": "<agent>"}`);
  - where the verdict is a file or a marker the main thread could also touch (C4's `seed.txt`, F3, F4 and I1's markers), a precondition (`main-thread-no-edit`, `main-thread-no-touch`, `main-thread-no-write`) also requires that no call without `agent_type` attempted it.

  These cases therefore depend on A1 (`agent_type` on subagent payloads), and each declares `"requires": ["A1"]`. The agent-attributed preconditions alone don't cover C1 and C2: they assert an absence (no `echo C1` PostToolUse from the agent), which a host that names the agent on `SubagentStart` but not on its tool calls would pass trivially. A1 proves attribution on both the before-call and the after-call event: `agent-type` asserts `agent_type` on the PreToolUse of the agent's `echo A1` (what C3, C4, F3, F4 and I1 decide on), and `agent-type-after` asserts it on the PostToolUse (what C1 and C2 decide on). A host that attributes PreToolUse but leaves `agent_type` off PostToolUse makes A1 `contradicted`; one that records no PostToolUse for the call leaves it `inconclusive` (no evidence either way). Both hold all seven dependents `inconclusive`. The `requires` gate closes that gap when results are finalized:
  - **Staging** gates one run's entries on their own: a dependent is decided only when A1 is `confirmed` in the same run, for the same host version and install. A run without A1 (for example `--case C1`) leaves its dependents `inconclusive`, and the plan says so up front.
  - **Publishing** gates the merged `results/<host>-<version>.json` again. The gate only downgrades, so a later A1 that isn't `confirmed` also downgrades older dependents, and a later confirmed A1 never upgrades them: re-run the dependents with A1.

  L1 and H1 also match on `agent_type`, but only in preconditions that need a positive match, so a host without it already leaves them `inconclusive`; they don't declare `requires`.

## Recorder

`recorder.py [--ctrl PATH] [--out DIR] [--event NAME] [--tag TAG] [--dialect claude|cursor|codex]` (the defaults are `$PROBE_CTRL` and `$PROBE_OUT`).

It appends every call to `out/raw/<event>.jsonl` as `{seq, received_at, event, tool, tag, key, mode, dialect, payload}`. Then it answers from the control file:

```json
{"PreToolUse:Bash": {"mode": "deny", "after": 2, "limit": null, "agent": "probe-reader", "reason": "…"},
 "PreToolUse:mcp__.*": {"mode": "deny", "after": 1},
 "Stop": {"mode": "exit2", "limit": 1}}
```

**Modes:**
- `record`: exit 0, no output;
- `allow`, `deny`, `ask`: `hookSpecificOutput.permissionDecision` plus a reason;
- `exit2`: the reason on stderr, exit 2;
- `crash`: exit 1;
- `timeout`: sleep `sleep_s`, then exit 0;
- `invalid-json`: malformed JSON on stdout.

`missing-interpreter` isn't a recorder mode: the template points the hook command at a binary that doesn't exist.

**Rule options:**
- `after: n` answers `record` for the first n matching calls;
- `limit: n` applies the mode at most n times;
- `agent` matches `agent_type` (or `<plugin>:<agent>`).

**Key precedence:** the exact `<event>:<tool>` key, then `<event>:<regex>` keys (full match, sorted), then the bare `<event>`.

**Locking and errors:** calls are serialized with `flock`, so concurrent subagents get unique, ordered `seq` values. Recorder errors go to `out/raw/_errors.jsonl` and are answered with `record`. The runner turns them into a FAIL.

## Redaction and formats

`redact.py` applies these rules at any depth and keeps key order:

| What | Becomes |
|---|---|
| Prompt text, assistant messages and tool contents (`prompt`, `command_args`, `last_assistant_message`, `content`, `new_string`, `old_string`, `description`, `query`, `url`, …) | `<REDACTED:<rule>>` |
| Every string under `tool_response` | `<REDACTED:tool-response>` (shape kept) |
| Command text after its first word | `<first word> <REDACTED:command-args>` |
| The run workspace, home directories, macOS temp roots, encoded project folders and emails | `<WORKSPACE>`, `<HOME>`, `<TMP>`, `<PROJECT>`, `<EMAIL>` |
| Session, conversation, agent, tool-use and similar ids, and any other UUID | Stable placeholders (`<SESSION-1>`, `<AGENT-2>`, `<ID-1>`) |

Placeholders are stable across one capture, so equal ids stay equal (A2's consistency check still works), and an id inside a path gets the same placeholder. Each fixture lists its redactions as `{path, rule}`.

The leak scan (`redact.py scan`, run by `scripts/test-probes.sh` over `fixtures/` and `testdata/`) flags:
- home paths (plain and encoded), macOS temp paths, emails and UUIDs;
- prompt or message text without a marker, command text past the first word, and ids that aren't placeholders;
- any raw `.jsonl` file.

Findings report the location and kind, never the matched text.

**Fixture (`daedalus.probe-fixture/1`):**
- **Path:** `fixtures/<host>-<version>/<case>[.<variant>]/<install>/<event>-<n>.json`.
- **Fields:** `{schema, host, host_version, install, case, variant, event, seq, mode, tag, redactions[], payload}`.
- **Counters:** `n` counts per event; `seq` is the capture-wide order.

**Result (`daedalus.probe-result/1`):**
- **Path:** `results/<host>-<version>.json` = `{schema, host, host_version, generated_at, entries[]}`.
- **Each entry:** `{case, variant, install, host, host_version, os, status, observations[{check, expected, actual, outcome, role}], fixture_ids, cost_usd, plugins_enabled, notes, run_at}`.
- **`status`:** `confirmed`, `contradicted`, `inconclusive` or `docs-only`.
- **`plugins_enabled`:** lists `daedalus*` names plus `other:<count>`, never other plugin names.

## Verify in T0 (first task of P0b)

The P0a code assumes these host behaviors. T0 confirms them on the installed CLI, and any change is recorded in the findings document.

- **`claude` flags:**
  - `--plugin-dir` (fallback: a project-scope local marketplace install, removed after, done by hand; until then the runner skips the host call for plugin runs, and they're `inconclusive` with `host not run`);
  - `--max-budget-usd` (fallback: `--max-turns` plus the run total);
  - `--max-turns`, `--model haiku` and `--permission-mode dontAsk`;
  - `--output-format stream-json` with `--verbose`;
  - the stream's `result` fields (`total_cost_usd`, `usage`, `permission_denials`);
  - the assistant events' `tool_use` blocks (`{"type": "assistant", "message": {"content": [{"type": "tool_use", "name", "input"}]}}`), read by the `stream` check `tool-use`.
- **`claude plugin list`:** used for the isolation digest and `plugins_enabled`. The names of the user plugin registry files are `installed_plugins.json` and `known_marketplaces.json`.
- **Hook and settings keys:**
  - `onFailure`, `UserPromptExpansion` and `SubagentStart`;
  - `sandbox.enabled` and `allowUnsandboxedCommands`;
  - `enabledMcpjsonServers`;
  - the permission-rule syntax in the templates (`Bash(echo *)`, `WebFetch(domain:…)`, `mcp__…`);
  - agent frontmatter `hooks`, `permissionMode`, `maxTurns`, `disallowedTools` and `isolation: worktree`;
  - the plugin MCP tool-name format (M2 records it).
- **Cursor:** the `agent -p` invocation and output format, the hook response shape (`{permission, user_message, agent_message}`), `failClosed`, and the signed-in check.
- **Codex:** the `.codex/hooks.json` format, `codex exec --json` events (`turn.completed.usage`), and project trust. The runner never writes `~/.codex`, so the maintainer grants trust by hand.

## Tests

`bash scripts/test-probes.sh` runs offline (no credentials, no model calls). It covers:
- every recorder mode and control option, including concurrency;
- redaction rules and placeholder equality;
- the leak scan over `fixtures/` and `testdata/`, and fixture and result schema validation;
- validation of every case file, including variant ids that would leave the workspace;
- the status guards: a run without the host, a timed-out run, or a run that never attempted the probed call is `inconclusive`;
- attribution: a main-thread call can't decide C1–C4, F3, F4 or I1 (another agent's `SubagentStart` or one without `agent_type` doesn't count either);
- the `requires` gate: a dependent is decided only when A1 is `confirmed` for the same host version and install, in the run and in the merged results file; A1 needs `agent_type` on the agent's PostToolUse as well as its PreToolUse, so a C1 that would read `confirmed` on a host that attributes only PreToolUse ends `inconclusive`;
- the `probe-mcp` JSON-RPC handshake and echo;
- the `--dry-run` action list with no host calls;
- the isolation and cleanup logic on a fake hub, home and workspace;
- the offline pipeline (workspace → recorder → observe → redact → cleanup) on a synthetic capture.
