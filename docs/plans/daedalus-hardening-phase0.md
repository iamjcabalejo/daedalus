# Daedalus hardening P0: findings

| Field | Value |
|---|---|
| **Status** | Complete for the probes (P0b, written 2026-11-26). The benchmark and AC-6's dynamic part moved to P2 (roadmap D29). Reruns and case redesigns that P0b found necessary are listed in §2.1 |
| **Owner ACs** | P0 plan **AC-4** (findings), **AC-5** (decision records), **AC-6** (role-needs analysis; static part complete, dynamic part deferred to P2) |
| **Sources** | [daedalus-hardening-p0.md](daedalus-hardening-p0.md) §3.3, §3.5, §3.6; [daedalus-hardening-roadmap.md](daedalus-hardening-roadmap.md) §5, §6.19, §7, §14; `scripts/probes/results/claude-2.1.325.json`; `scripts/probes/fixtures/claude-2.1.325/**` |
| **Related** | [daedalus-hardening-threat-model.md](daedalus-hardening-threat-model.md) (AC-7) |
| **Base** | `main` @ `71a3214`, plugin `0.4.0` |
| **Rule** | Results come from the clean rerun `20261125T173552Z` and its published files. Where this document reads a run differently from its published status, §2.1 gives the reason. Facts taken from a raw run folder (never committed) say "raw only" |

Install codes: **S** = Claude Code script install, **P** = Claude Code plugin install. Roadmap ACs are written **R-AC-n**. Fixture ids are relative to `scripts/probes/fixtures/claude-2.1.325/`, without `.json`.

---

## 1. Environment

| Field | Value |
|---|---|
| Shipped workflow under test | `71a3214` (plugin `0.4.0`); `.claude/**` unchanged |
| Probe harness | `feat/hardening-p0a` @ `39cf56d`, plus the uncommitted T0 changes (`--allowedTools`, the trust check, denial classification; `scripts/probes/README.md`, "Verify in T0") |
| Claude Code CLI version (S) | **2.1.325** (the result file and each session's `init` event) |
| Claude Code CLI version (P) | **2.1.325**, the same binary. Plugin runs load the generated `probe` plugin with `--plugin-dir` |
| OS and version | macOS, Darwin 27.2.0 (`os: darwin-27.2.0` on every result) |
| Python, git | Python 3.9.6 (the recorder's interpreter); git 2.54.0 |
| Docker or colima (benchmark boundary) | Docker CLI with a reachable daemon (server 29.9.3), checked 2026-11-26. Not used in P0b: the benchmark moved to P2 (D29) |
| Cursor CLI version (case K1) | Not installed (`agent`, `cursor-agent` not found, 2026-11-26): K1 is docs-only [D] |
| Codex CLI version (case K2) | Not installed (`codex` not found, 2026-11-26): K2 is docs-only [D] |
| Probe model id | `claude-haiku-5-5` (`--model haiku`, as recorded in each session's `init` event) |
| Plugins enabled during probes | The results record `daedalus` (0.4.0, user scope) from `claude plugin list`. The sessions' `init` events also listed other user-scope plugins, agents and MCP servers (names not recorded). Probe sessions inherit whatever is configured at user scope; see §8 |
| T0 flag check | `--plugin-dir`, `--max-budget-usd`, `--model haiku`, `--permission-mode dontAsk`, `--output-format stream-json --verbose` and `--allowedTools`: present. `--max-turns`: accepted but hidden from `claude --help` (the preflight's parse check). Stream `result` events carry `total_cost_usd`, `usage` and `permission_denials`; 2.1.325 emits one `result` per turn, with a cumulative cost |
| Workspace trust | Every probe folder was untrusted. Each session's stderr says `Ignoring 15 permissions.allow entries from .claude/settings.json: this workspace has not been trusted` (65 of 65 rerun sessions) |
| Probe run dates (UTC) | 2026-11-25. First run `20261125T170427Z`; clean rerun `20261125T173552Z` (runs 17:36:03Z–17:46:14Z; results generated 17:46:15Z) |
| Probe spend (USD) | First run **$0.65**; rerun **$0.66** (sum of the 65 entries' `cost_usd`: $0.664). Total **$1.31** of the $15 budget |

### 1.1 The two runs

- **First run (`20261125T170427Z`): superseded, kept only as a recorded confound.** Every one of its 65 sessions ignored the probe project's `permissions.allow`, because the folder was untrusted and `-p` doesn't ask. The host then denied calls the rules should have allowed (`touch … needs approval`; `… but you haven't granted it yet`) before the mechanism under test mattered. E1–E4 `default`, E3 `on-failure-block`, H2, I1, J1, C4's plugin edit and M2's first MCP call were confounded that way. Its published files were replaced by the rerun's.
- **Lesson.** A probe must show that the permission layer isn't what stopped the call. The harness now passes the project's allow rules with `--allowedTools`, marks a run `inconclusive` when the trust warning appears without them, and classifies every denial by source (`hook`, `permission`, `unknown`). A permission denial of the probed call makes the run `inconclusive`, except in F1–F4, which test that layer.
- **One first-run fact is still used** (§2.1, C3): a turn-limit notice from the host on the plugin install. The calls involved were `Read`s, which need no allow rule, so the trust confound doesn't touch them. It is cited as "raw only".
- **Clean rerun (`20261125T173552Z`): the published results.** All 65 runs passed the allow rules on the command line, and each result notes it.

---

## 2. Results by case

One row per case in P0 plan §3.3 and per install: the published status, the finding with its key evidence, the fallback when the result isn't confirmed, and the roadmap ACs that depend on it.

**Totals (published):** 65 runs: 52 `confirmed`, 5 `contradicted`, 8 `inconclusive`. After investigation (§2.1):
- E3 `on-failure-block` (S, P) is the only contradiction that stands.
- C3 (S, P) is a case gap, so it reads `inconclusive`.
- C4/S splits: `permissionMode` is honored; per-agent `hooks` didn't fire.

**Install applicability.** Every Claude Code case runs on S and P (P0 plan §3.3), and each case file states its installs in `applies_to`. Two exceptions:
- **C4** runs on both installs with different expectations: per-agent `hooks` and `permissionMode` honored on S, ignored on P.
- **N1** runs once, under the plugin install type, with the project agent also present (S+P together), so a project agent and a plugin agent share the bare name `probe-reader`.

K1 and K2 use their host's own project hooks. F5 is interactive and is recorded in the operational QA checklist (P0 plan AC-13).

**E-case modes.** The mapping is fixed by the case files (`scripts/probes/cases/E1.json`…`E5.json`): E1 `crash`, E2 `timeout`, E3 `invalid-json`, E4 `missing-interpreter`, E5 `exit2`. Each runs a `default` variant and an `on-failure-block` variant.

**Fallbacks** (from the roadmap; used in the table):

| Code | Fallback | Source |
|---|---|---|
| FB-ro | An unidentified actor gets the read-only contract | R-AC-2 |
| FB-seq | Parallel spawns stay off; layers run in sequence | R-AC-17, D20 |
| FB-mode | Main-thread mode comes from the prompt events (D1) | Roadmap §6.6 |
| FB-admit | Admission by `agent_type` on the subagent's first tool call | Roadmap §4.5 |
| FB-allow | Guard-enforced read-only Bash allowlist where a tool list can't be applied | R-AC-3 |
| FB-caps | Guard-enforced tool-call and wall-clock caps per attempt | R-AC-8 |
| FB-plugin-hooks | The guard lives in the plugin-level `hooks/hooks.json` | F11 |
| FB-cond | The guard is marked [C]; the session banner says a crash fails open | R-AC-2 (older hosts) |
| FB-nonint | Non-interactive detection from `permission_mode` and `DAEDALUS_NONINTERACTIVE=1`; `ask` becomes deny `E_NEEDS_HUMAN` | R-AC-2, roadmap §6.7 |
| FB-sandbox-U | No network or process control for Bash without the sandbox, documented as [U] | Roadmap §4.4 T10 |
| FB-helper | Daedalus' own `worktree.py` helper | D21 |
| FB-docs | Recorded as docs-only [D] | P0 plan AC-2 |
| none named | The roadmap names no fallback; P0b proposes one if the result isn't confirmed | — |

| Case | Install | Question | Status | Finding and evidence (fixture ids) | Fallback | Depends (R-AC) |
|---|---|---|---|---|---|---|
| A1 | S | Identity on subagent tool calls | confirmed | `agent_id` present; `agent_type: "probe-reader"` on the agent's PreToolUse and PostToolUse. `A1/script/PreToolUse-3`, `A1/script/PostToolUse-2`, `A1/script/SubagentStart-1` | Not needed (FB-ro still covers unidentified actors) | 1a, 2, 45, 58, 60 |
| A1 | P | Identity on subagent tool calls | confirmed | `agent_type: "probe:probe-reader"`: the plugin prefix is part of the name. `A1/plugin/PreToolUse-3`, `A1/plugin/PostToolUse-3`, `A1/plugin/SubagentStart-1` | Not needed | 1a, 2, 45, 58, 60 |
| A2 | S | Identity under concurrency (D20) | confirmed | Two background agents overlapped: both `SubagentStart`s came before either `SubagentStop`, and their calls interleaved (a, a, b, b, a, b). 6 calls, 2 `agent_id`s, no mismatch between `agent_type` and the echoed name. `A2/script/SubagentStart-1`, `-2`, `A2/script/PreToolUse-3`…`-8` | Not needed (no FB-seq) | 1a, 17, 50, 58 |
| A2 | P | Identity under concurrency (D20) | confirmed | Same; calls interleaved a, b, a, a, b, b. `A2/plugin/SubagentStart-1`, `-2`, `A2/plugin/PreToolUse-3`…`-8` | Not needed | 1a, 17, 50, 58 |
| A3 | S | Main thread has no agent fields | confirmed | No `agent_id` or `agent_type` on the main thread's Bash call. `A3/script/PreToolUse-1` | Not needed | 2, 58 |
| A3 | P | Main thread has no agent fields | confirmed | Same. `A3/plugin/PreToolUse-1` | Not needed | 2, 58 |
| B1 | S | What an `Agent` `PreToolUse` carries | confirmed | `tool_name: "Agent"`; `tool_input` keys `description`, `prompt`, `subagent_type`; `subagent_type: "probe-reader"` names the target. `B1/script/PreToolUse-1` | Not needed for spawns (resumes: §2.2) | 1b, 2, 50 |
| B1 | P | What an `Agent` `PreToolUse` carries | confirmed | Same, with `subagent_type: "probe:probe-reader"`. `B1/plugin/PreToolUse-1` | Not needed for spawns | 1b, 2, 50 |
| B2 | S | A hook can deny a spawn | confirmed | The hook's deny on `Agent` stopped the spawn: no `SubagentStart`, no agent calls; denial source `hook`. `B2/script/PreToolUse-1` | Not needed | 1b, 2, 50 |
| B2 | P | A hook can deny a spawn | confirmed | Same. `B2/plugin/PreToolUse-1` | Not needed | 1b, 2, 50 |
| C1 | S | `tools` list honored | confirmed | `tools: Read, Grep`. The agent still emitted a Bash call; the host rejected it before any hook ran (`No such tool available: Bash`, transcript only), so no PreToolUse was recorded. `C1/script/SubagentStart-1`, `C1/script/SubagentStop-1` | Not needed | 1c, 3, 45, 60 |
| C1 | P | `tools` list honored | confirmed | Same. `C1/plugin/SubagentStart-1`, `C1/plugin/SubagentStop-1` | Not needed | 1c, 3, 45, 60 |
| C2 | S | `disallowedTools` honored | confirmed | `disallowedTools: Bash`. The agent saw no Bash and made no call. `C2/script/SubagentStart-1`, `C2/script/SubagentStop-1` | Not needed | 1c, 3, 45, 60 |
| C2 | P | `disallowedTools` honored | confirmed | The agent tried Bash; the host rejected it before any hook, as in C1. `C2/plugin/SubagentStart-1`, `C2/plugin/SubagentStop-1` | Not needed | 1c, 3, 45, 60 |
| C3 | S | `maxTurns` honored | contradicted → **inconclusive** (§2.1) | Case gap. The main thread split the task over 5 invocations of one agent (a spawn, then 4 `SendMessage` resumes, one `agent_id`). Each invocation used 2 model turns, so the cap was never reached. `C3/script/SubagentStart-1`…`-5`, `C3/script/PreToolUse-4` (`SendMessage`) | FB-caps | 1c, 8 |
| C3 | P | `maxTurns` honored | contradicted → **inconclusive** (§2.1) | Same pattern. The superseded first run shows the cap holding per invocation: the host reported that the agent "stopped at its 2-turn limit" (raw only). `C3/plugin/SubagentStart-1`…`-5`, `C3/plugin/PreToolUse-4` | FB-caps (lifetime caps across resumes) | 1c, 8 |
| C4 | S | Script agents honor `hooks` and `permissionMode` (control) | contradicted → **split** (§2.1) | `permissionMode: plan` applied: the agent's payloads carry `permission_mode: "plan"`, and the agent declined the edit itself, so a host block of an attempted edit wasn't exercised. The frontmatter hook (`matcher: "*"`) didn't fire on the agent's Read, in either run. `C4/script/PreToolUse-2`, `C4/script/SubagentStop-1` | FB-plugin-hooks, on both installs | 1c, 2, 60 |
| C4 | P | Plugin agents ignore `hooks` and `permissionMode` | confirmed | `permission_mode: "default"` on the agent's calls; its Edit landed; no frontmatter-hook record. `C4/plugin/PreToolUse-2`, `C4/plugin/PreToolUse-3`, `C4/plugin/PostToolUse-2` | FB-plugin-hooks (already the design) | 1c, 2, 60 |
| D1 | S | Prompt-event fields for bare commands | confirmed | `UserPromptExpansion` carries `command_name: "probe-cmd"`, `command_args`, `command_source: "projectSettings"`, `expansion_type: "slash_command"`. `D1/script/UserPromptExpansion-1`, `D1/script/UserPromptSubmit-1` | Not needed | 1d, 2 |
| D1 | P | Prompt-event fields for plugin-prefixed commands | confirmed | `command_name: "probe:probe-cmd"`, `command_source: "plugin"`. `D1/plugin/UserPromptExpansion-1` | Not needed | 1d, 2 |
| E1 | S | `crash`, with and without `onFailure` | confirmed (both variants) | Without `onFailure` the command ran (fail-open). With `onFailure: "block"` it was blocked: `… failed; blocking because onFailure is "block"`. `E1.default/script/PreToolUse-1`, `PostToolUse-1`; `E1.on-failure-block/script/PreToolUse-1` | Not needed on 2.1.325; FB-cond below the floor (D9) | 1e, 2, 65 |
| E1 | P | `crash`, with and without `onFailure` | confirmed (both variants) | Same. `E1.default/plugin/PreToolUse-1`, `PostToolUse-1`; `E1.on-failure-block/plugin/PreToolUse-1` | As S | 1e, 2, 65 |
| E2 | S | `timeout`, with and without `onFailure` | confirmed (both variants) | Fail-open without `onFailure`; with it, `… timed out; blocking because onFailure is "block"`. `E2.default/script/PreToolUse-1`, `PostToolUse-1`; `E2.on-failure-block/script/PreToolUse-1` | As E1 | 1e, 2, 65 |
| E2 | P | `timeout`, with and without `onFailure` | confirmed (both variants) | Same. `E2.default/plugin/PreToolUse-1`, `PostToolUse-1`; `E2.on-failure-block/plugin/PreToolUse-1` | As E1 | 1e, 2, 65 |
| E3 | S | `invalid-json`, with and without `onFailure` | `default` confirmed; `on-failure-block` **contradicted** | Malformed JSON with exit 0 never blocks. The host emits a `hook_no_verdict` warning ("A hook gave no usable answer, so it didn't check this action.") and runs the command, even with `onFailure: "block"`. `E3.default/script/PreToolUse-1`; `E3.on-failure-block/script/PreToolUse-1`, `PostToolUse-1` | Guard design: deny = exit 2; never depend on JSON being read (D9) | 1e, 2, 65 |
| E3 | P | `invalid-json`, with and without `onFailure` | `default` confirmed; `on-failure-block` **contradicted** | Same. `E3.default/plugin/PreToolUse-1`; `E3.on-failure-block/plugin/PreToolUse-1`, `PostToolUse-1` | As S | 1e, 2, 65 |
| E4 | S | `missing-interpreter`, with and without `onFailure` | confirmed (both variants) | Without `onFailure` the command ran. With it, blocked (`… failed; blocking because onFailure is "block"`). The hook never runs, so the blocked variant has no fixture; its evidence is the stream's tool result (raw only). `E4.default/script/PostToolUse-1` | As E1 | 1e, 2, 65 |
| E4 | P | `missing-interpreter`, with and without `onFailure` | confirmed (both variants) | Same. `E4.default/plugin/PostToolUse-1` | As E1 | 1e, 2, 65 |
| E5 | S | `exit2`, with and without `onFailure` | confirmed (both variants) | Exit 2 blocks with and without `onFailure`. `E5.default/script/PreToolUse-1`, `E5.on-failure-block/script/PreToolUse-1` | Not needed | 1e, 2, 65 |
| E5 | P | `exit2`, with and without `onFailure` | confirmed (both variants) | Same. `E5.default/plugin/PreToolUse-1`, `E5.on-failure-block/plugin/PreToolUse-1` | Not needed | 1e, 2, 65 |
| F1 | S | `ask` in `-p` (default mode) | confirmed | The hook's `ask` became a host denial: a `permission_denied` event carrying the hook's reason, and `touch` didn't run, though `Bash(touch *)` was allowed on the command line. The payload says `permission_mode: "default"`, as in an interactive session. `F1/script/PreToolUse-1` | Not needed for safety; detection still needs FB-nonint's env var (§2.2) | 1f, 2 |
| F1 | P | `ask` in `-p` (default mode) | confirmed | Same. `F1/plugin/PreToolUse-1` | As S | 1f, 2 |
| F2 | S | `ask` in `-p --permission-mode dontAsk` | confirmed | Same denial; payloads carry `permission_mode: "dontAsk"`. `F2/script/PreToolUse-1` | As F1 | 1f, 2 |
| F2 | P | `ask` in `-p --permission-mode dontAsk` | confirmed | Same. `F2/plugin/PreToolUse-1` | As F1 | 1f, 2 |
| F3 | S | `ask` in a `-p` subagent | confirmed | Same denial, inside the agent (its call was `cd … && touch …`). `F3/script/PreToolUse-2` | As F1 | 1f, 2 |
| F3 | P | `ask` in a `-p` subagent | confirmed | Same. `F3/plugin/PreToolUse-2` | As F1 | 1f, 2 |
| F4 | S | `ask` in a `-p` background subagent | confirmed | Same; nothing in the payload marks the agent as background. `F4/script/PreToolUse-2` | As F1 | 1f, 2 |
| F4 | P | `ask` in a `-p` background subagent | confirmed | Same. `F4/plugin/PreToolUse-2` | As F1 | 1f, 2 |
| F5 | S | `ask` interactive (maintainer; QA checklist) | **open**: not yet run (AC-13) | — | FB-nonint | 1f, 2, 66 |
| F5 | P | `ask` interactive (maintainer; QA checklist) | **open**: not yet run (AC-13) | — | FB-nonint | 1f, 2, 66 |
| G1 | S | Usage per subagent from `SubagentStop` | confirmed | `agent_transcript_path` on `SubagentStop`. The transcript's usage keys (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `cache_creation`, …) match the stream's. `G1/script/SubagentStop-1` | Not needed | 1g, 7, 28, 50 |
| G1 | P | Usage per subagent from `SubagentStop` | confirmed | Same. `G1/plugin/SubagentStop-1` | Not needed | 1g, 7, 28, 50 |
| H1 | S | Stopping an agent with tool denial | confirmed | Every call after the second was denied. The third Read was denied, and the agent ended at once with a final message: 3 calls, none after the denial. `H1/script/PreToolUse-4`, `H1/script/SubagentStop-1` | Not needed | 1h, 8, 14 |
| H1 | P | Stopping an agent with tool denial | confirmed | Same. `H1/plugin/PreToolUse-4`, `H1/plugin/SubagentStop-1` | Not needed | 1h, 8, 14 |
| H2 | S | One-shot `Stop` block | confirmed | The first `Stop` was blocked once; the second carried `stop_hook_active: true`; the session then finished the task. `H2/script/Stop-1`, `H2/script/Stop-2` | Not needed | 43 |
| H2 | P | One-shot `Stop` block | confirmed | Same. `H2/plugin/Stop-1`, `H2/plugin/Stop-2` | Not needed | 43 |
| I1 | S | Sandbox coverage of subagent Bash (macOS or Linux) | inconclusive (§2.1) | The out-of-tree `touch` was stopped by the permission layer's working-directory check, before the sandbox. `curl` wasn't blocked by a permission rule: it went through an HTTP proxy (`200 Connection Established`) and failed TLS (exit 60). `I1/script/PreToolUse-2`, `I1/script/PreToolUse-3` | FB-sandbox-U | 1i, 10, 60 |
| I1 | P | Sandbox coverage of subagent Bash (macOS or Linux) | inconclusive (§2.1) | Same. `I1/plugin/PreToolUse-2`, `I1/plugin/PreToolUse-3` | FB-sandbox-U | 1i, 10, 60 |
| J1 | S | Native worktree isolation (D21) | manual → finding (§2.1) | A branch was created (`branches: 2` in the result entry); worktree at `<repo>/.claude/worktrees/agent-<agent_id>/` (payload `cwd`); the worktree edit landed. The main-checkout edit wasn't attempted. The branch name `worktree-agent-<agent_id>` at the base commit, and that the worktree and the branch were kept, are observed in raw output, not in committed fixtures. `J1/script/SubagentStart-1`, `J1/script/PreToolUse-3` (Edit), `J1/script/PreToolUse-4` (`git branch`) | FB-helper (the default under D21) | 1j, 19, 21 |
| J1 | P | Native worktree isolation (D21) | manual → finding (§2.1) | The same location (payload `cwd`) and a created branch (`branches: 2`). The branch form was read from the probe repo's git state, because the agent's own `git` call was denied by the permission layer: observed in raw output, not in committed fixtures. `J1/plugin/SubagentStart-1`, `J1/plugin/PreToolUse-3`, `J1/plugin/PreToolUse-4` | FB-helper | 1j, 19, 21 |
| L1 | S | A hook denies an edit before it lands (main thread and subagent) | inconclusive (§2.1) | Main thread: the hook denied the Edit, `seed.txt` stayed unchanged, and no PostToolUse fired. The main thread then skipped the agent step, so the subagent half didn't run. `L1/script/PreToolUse-2` | Rerun the subagent half (split case) | 2, 21, 58, 60 |
| L1 | P | A hook denies an edit before it lands (main thread and subagent) | confirmed | Both the main thread's and the agent's Edit were denied; `seed.txt` unchanged. `L1/plugin/PreToolUse-2` (main), `L1/plugin/PreToolUse-5` (agent) | Not needed | 2, 21, 58, 60 |
| M1 | S | `WebFetch` matcher: a hook denies a fetch | inconclusive (§2.1) | WebFetch wasn't in the session's tool list. The model searched for it (`ToolSearch`) and made no fetch. `M1/script/PreToolUse-1` (`ToolSearch`) | Proposed: keep `WebFetch` in the guard's matchers, tagged [C] until M1 runs | 2, 60, 67 |
| M1 | P | `WebFetch` matcher: a hook denies a fetch | inconclusive (§2.1) | No tool call at all. `M1/plugin/UserPromptSubmit-1` | As S | 2, 60, 67 |
| M2 | S | `mcp__.*` matcher: tool-name format, and whether a hook can deny | confirmed | Tool name `mcp__probe-mcp__echo`. The first call ran; the hook denied the second. `M2/script/PreToolUse-2`, `M2/script/PreToolUse-3` | Not needed | 2, 60, 67 |
| M2 | P | `mcp__.*` matcher: tool-name format, and whether a hook can deny | confirmed | Tool name `mcp__plugin_probe_probe-mcp__echo`; same outcome. `M2/plugin/PreToolUse-2`, `M2/plugin/PreToolUse-3` | Not needed | 2, 60, 67 |
| N1 | S+P | Bare-name resolution: a project agent and a plugin agent named `probe-reader` (T12 residual) | manual → finding (§2.1) | The session listed both `probe-reader` and `probe:probe-reader`. The main thread asked for `probe-reader`, and the project agent ran (`agent_type: "probe-reader"`, marker `N1-project`); the plugin agent didn't. `N1/plugin/PreToolUse-1`, `N1/plugin/PreToolUse-2`, `N1/plugin/SubagentStart-1` | Not needed on plugin installs; script installs: §8 | 45, 58 |
| K1 | Cursor | Deny, fail-closed, identity; Claude-format import | docs-only [D] | Cursor CLI not installed (2026-11-26); no result entry | FB-docs | 1k, 37, 38 |
| K2 | Codex | Deny, identity, failure behavior, usage | docs-only [D] | Codex CLI not installed (2026-11-26); no result entry | FB-docs | 1k, 38, 39 |

### 2.1 Investigations

Each answer comes from the rerun's raw streams, hook records and subagent transcripts, read in place and never copied.

#### C3: `maxTurns` (contradicted on both installs → inconclusive)

- **Question.** The agent read all 5 steps under `maxTurns: 2`. Is `maxTurns` ignored, or did the agent make several tool calls in one turn?
- **Neither.** Every assistant message in the agent's transcript holds exactly one tool call, so there were no parallel calls.
- **What happened.** The main thread read the agent's description ("Probe agent with a two-turn limit") and planned around it. It briefed the agent to read only `step1.txt`, then resumed the same agent with `SendMessage` four times, one step each.
  - On both installs: one `agent_id`, five `SubagentStart`/`SubagentStop` pairs.
  - Each invocation: one Read turn, then one final-text turn. That is 2 model turns, exactly the cap, so the cap was never tested.
  - Its last reply claimed the agent "went past its stated two-turn limit". That misreads 5 invocations as one.
- **The superseded first run decides the question for P** (raw only). There, the plugin agent's first two invocations each made two Read turns and then stopped with no report. The host's task notification said the agent "stopped at its 2-turn limit before finishing" and told the main thread to continue it with `SendMessage`. The main thread did so twice, and the agent finished. On S, the first run's main thread split the work as in the rerun, so S never reached the cap.
- **Answer:**
  - `maxTurns` is honored **per invocation** for a plugin agent on 2.1.325.
  - It isn't a lifetime cap: a stopped agent can be resumed with `SendMessage`, each resume gets a fresh budget, and the host itself suggests resuming. Across resumes the agent ran 10 model turns under `maxTurns: 2`.
  - S wasn't observed at the cap.
- **Redesign, then rerun on S and P:**
  1. Give the agent a neutral description that doesn't announce the cap.
  2. Tell the main thread to spawn once and not message the agent. Pass `--disallowedTools SendMessage` too (check the flag form in T0).
  3. Make the task need at least 3 dependent turns, so the agent can't finish in 2 (each step file names the next one).
  4. Assert per invocation (the calls between one `SubagentStart` and its `SubagentStop`), and record the host's turn-limit notice.

#### C4/script: per-agent `hooks` and `permissionMode` (contradicted → split)

- **Did the agent try an edit?** No. It read `seed.txt` and then answered that plan mode was active and the edit was blocked, without calling Edit. `seed.txt` is unchanged because of the agent's choice, not because the host blocked an attempt.
- **`permissionMode`: honored.** The agent's PreToolUse, PostToolUse and SubagentStop payloads carry `permission_mode: "plan"` (`C4/script/PreToolUse-2`, `SubagentStop-1`). On P the same agent's payloads say `default`. Whether plan mode would block an attempted edit at the host wasn't exercised.
- **`hooks`: not observed.** The frontmatter hook uses `matcher: "*"`, so it should also have fired on the agent's Read. No `frontmatter`-tagged record exists in the rerun or in the first run (2 runs, one Read each). The case gap therefore covers only the edit-specific question. A hook that stays silent on a call its matcher covers is evidence that per-agent `hooks` didn't fire on the script install.
  - **Caveat:** the folder was untrusted. Whether trust changes this is undetermined.
- **Reading:** `permissionMode` honored on S; per-agent `hooks` contradicted on S (indicative, two calls).
- **Consequence:** no enforcement may live in agent frontmatter on either install. The guard stays in settings or plugin hooks (FB-plugin-hooks).
- **Redesign, then rerun on S and P.** Split the case:
  - C4a (`hooks`): `permissionMode` left at default; the agent must Read and Edit; frontmatter hook on `Read|Edit`.
  - C4b (`permissionMode: plan`): the brief tells the agent to attempt the edit even if it expects a block, and to report the host's error.

#### E3: invalid JSON under `onFailure: "block"` (contradicted on both installs; stands)

- **Confirmed from both streams.**
  - The recorder printed a truncated JSON object (`{"hookSpecificOutput": {"permissionDecision": `) and exited 0.
  - The host then emitted `system/informational` with tag `hook_no_verdict` (`timed_out: false`) and ran `touch` ("Bash completed with no output").
  - The PostToolUse recorder fired, and `marker-E3` exists.
- The same `onFailure: "block"` setting blocked a crash, a timeout and a missing interpreter (E1, E2, E4). `onFailure` therefore treats a non-zero exit other than 2, a timeout and a missing interpreter as failures, but **not** unparseable stdout with exit 0.
- **Consequence for the guard:** it must never rely on its JSON being read.
  - It denies with **exit 2** and the reason on stderr. E5 shows exit 2 blocking on both installs, with and without `onFailure`.
  - Any JSON it prints is complete and valid, serialized in full before the first byte is written.
  - Its top-level handler turns every internal error into exit 2, never into exit 0 with partial output.
  - R-AC-58 gets a test that injects a serialization failure and expects exit 2.
- **No rerun needed.**

#### I1: sandbox coverage (inconclusive on both installs)

- **Was the out-of-tree write blocked?** Yes, but by the permission layer, not by the sandbox. The agent's `touch ../outside.txt` got a `permission_denied` event: `touch in '<path>' needs approval. The path is outside the working directories for this session …`. That happened even though `Bash(touch *)` was passed with `--allowedTools`. This is the one denial the classifier counted (`permission`, probed call), so the run is `inconclusive` by rule. The sandbox's own filesystem confinement was never reached. `../outside.txt` doesn't exist.
- **Was the network call blocked, and by what?** Not by a permission rule: the only denial was the `touch`.
  - `curl -sI https://example.com` ran. Its output starts with `HTTP/1.1 200 Connection Established`, a proxy's reply to `CONNECT`, and curl exited 60 (TLS certificate verification failed), so no page was fetched.
  - The runner passes its environment through, and the operator's shell has no proxy variables. The proxy therefore most likely came from the host sandbox, which allowed the `CONNECT` to `example.com` (the allow rules include `WebFetch(domain:example.com)`).
  - Whether the TLS failure is the sandbox's doing is undetermined.
- **`failIfUnavailable`:** not exercised; the sandbox appears to have started.
- **Redesign, then rerun on S and P:**
  1. Write outside through a path the permission layer can't see statically: a repo script allowed by an exact rule (`Bash(./probe-write.sh)`) that writes `../outside.txt`. Then only the sandbox can stop it.
  2. Test the network over plain HTTP, against an allowed domain and a domain that isn't allowed, so TLS doesn't confound the result. Record the proxy variable names (not values) from inside the command.
  3. Add a `sandbox.enabled: false` control variant.

#### J1: native worktree isolation (manual)

- **Branch:** `worktree-agent-<agent_id>`. The name and the base commit are observed in raw output, not in committed fixtures; the result entries' `branches: 2` shows only that a branch was created.
  - On S, the agent's `git branch --show-current` printed it.
  - On P, it comes from the probe repo's git state after the run, because the agent's `git -C … branch` call didn't match the allow rule `Bash(git branch *)` and the permission layer denied it.
  - The branch points at the base commit (the same SHA as `main`), and nothing was committed on it.
- **Location:** `<repo>/.claude/worktrees/agent-<agent_id>/`, inside the main checkout's `.claude/` folder. The agent's payload `cwd` is the worktree, so relative edits land there.
- **Main-checkout edit:** not attempted on either install. Both agents declined, quoting an instruction they had been given not to edit the main working tree (P: "Your brief both asks for that edit and says 'Do not edit anything in the main working tree'"). The probe agent's own prompt says no such thing, so the host injects it. Whether the host would *block* a file-tool write to the main checkout is **undetermined**. The main checkout's `seed.txt` is unchanged.
- **Cleanup** (observed in raw output, not in committed fixtures; the post-run counts `worktrees: 2` and `branches: 2` in the result entries are consistent with it): the agent changed a file, and the host kept both the worktree and the branch after the agent finished. The branch is still listed, and the worktree is still registered; git marks it `prunable` only because the runner later removed `repo/.claude`. The worktree edit stayed uncommitted.
- **Rerun:** not needed for D21, which keeps the helper as the default. If native isolation is ever made the default, add a case that forces a write outside the worktree at an absolute path.

#### N1: bare-name resolution (manual)

- The session's `init` event listed both `probe-reader` (project) and `probe:probe-reader` (plugin).
- The main thread asked for `subagent_type: "probe-reader"`. The host ran the **project** agent: `agent_type: "probe-reader"` on `SubagentStart` and on its Bash call, which echoed `N1-project`. The plugin agent didn't run (`N1-plugin` count 0).
- Plugin agents are always namespaced, so a project agent can't take a plugin role's name. But `agent_type` carries no scope. On a plugin install, only `daedalus:<role>` is a Daedalus role, and a bare role name means a project or user agent.
- The user-scope form (a project agent shadowing a user-scope script install's role) isn't probed and stays [D] (§6.3 G-1).

#### L1/script: edit deny in a subagent (inconclusive)

- The main thread's Edit was denied by the hook (`PreToolUse:Edit hook error: probe L1: edits are blocked`), `seed.txt` stayed unchanged, and no PostToolUse fired. **The main-thread half is confirmed on S.**
- The main thread then refused step 2, reasoning that having the agent make the same edit "would get around the block". The subagent's edit was never attempted, so the precondition failed.
- This is a case gap, not a host gap. H1/S shows a project hook denying a subagent's call on S, and L1/P shows a subagent's Edit denied on P.
- **Redesign, then rerun the `agent` half on S** (and on P, for symmetry). Split L1 into `main` and `agent` variants, so a denial in one can't steer the other.

#### M1: WebFetch matcher (inconclusive on both installs)

- WebFetch wasn't available. The session's `init` tool list (31 tools) has `WebSearch` but no `WebFetch`, and `ToolSearch` (`select:WebFetch`) found no deferred tool. The model said so and, as told, used nothing else. On P it didn't even search. A `web-fetch` agent was offered in the agent list.
- Why WebFetch is absent (a 2.1.325 default, or the operator's configuration) can't be told from the stream.
- **Rerun after a T0 check** of `init.tools` in a bare session. If the host no longer exposes WebFetch to the main thread, redesign M1 around the tool that actually fetches: first record the `web-fetch` agent's calls with a `.*` matcher, then deny that tool.

### 2.2 Other findings from the streams

1. **Spawn tool naming differs by surface.** Hook payloads and stream `tool_use` blocks say `Agent`; `init.tools` and `result.permission_denials` say `Task` (B2). Matchers and parsers must accept both.
2. **Removed tools never reach hooks** (C1, C2). The host rejects a call to a removed tool (`No such tool available`) before `PreToolUse`, so the guard never sees the attempt. Attempts show only in transcripts.
3. **A resume bypasses the spawn hook** (C3). `SendMessage` restarts a finished agent with the same `agent_id` and a new `SubagentStart`, without any `Agent` PreToolUse. Admission must also match `SendMessage`, and reservations and caps must key on `agent_id`.
4. **`-p` isn't visible in payloads.** `permission_mode` is `default` in `-p` (A3, F1), and background agents carry no marker (F4). Non-interactive detection therefore needs `DAEDALUS_NONINTERACTIVE=1` (FB-nonint). The host already turns a hook's `ask` into a deny in `-p`, even over an allow rule passed with `--allowedTools` (F1–F4), so the outcome is safe; only the message differs.
5. **Payload paths are canonical.** `cwd` and `file_path` use `/private/var/…` where the runner used `/var/…` (a macOS symlink; J1). Path confinement must compare `realpath` on both sides.
6. **One `result` per turn, cumulative.** Sessions with background agents emit several `result` events (C3/S: 5, with rising `total_cost_usd`). The last one holds the session total.

---

## 3. Tag changes to the roadmap

Every [D] or [C] item in roadmap §6.19 and in the §5 AC text, plus the [D]/[C] conditions in the §5.19 matrix (merged into the matching row). "Same" cells in §6.19 inherit the tag of the cell they repeat. Untagged "verify" cells are included. [I] and [U] cells aren't listed.

**Status values:**
- `verified`: a passing probe on that install, on Claude Code 2.1.325;
- `contradicted`: a probe shows the opposite;
- `conditional`: not settled; the fallback is named;
- `docs-only`: no probe ran, so the cell keeps its [D] (or [C]).

"No §3.3 case" means P0 has no probe for the item.

### 3.1 From the platform matrix (roadmap §6.19)

| # | Guarantee | Platform | Tag now | Probe case(s) | New tag | Status |
|---|---|---|---|---|---|---|
| TC-01 | Hook can deny a shell or MCP call | CC S | [D] | H1, E5 (shell); M2 (MCP) | Yes, verified on 2.1.325 (E5 exit 2 on Bash; M2 deny on `mcp__probe-mcp__echo`; also B2, H1, L1) | verified |
| TC-02 | Hook can deny a shell or MCP call | CC P | [D] | H1, E5 (shell); M2 (MCP) | Yes, verified (E5; M2 on `mcp__plugin_probe_probe-mcp__echo`) | verified |
| TC-03 | Hook can deny a shell or MCP call | Cursor | [D] | K1 | [D] (K1 not run) | docs-only |
| TC-04 | Hook can deny a shell or MCP call | Codex | [D] | K2 | [D] (K2 not run) | docs-only |
| TC-05 | Hook can deny a file edit before it lands | CC S | [D] | L1 | Main thread verified (L1/S). Subagent edit unverified on S | conditional (fallback: rerun L1's `agent` half; the mechanism is shown on S by H1's subagent deny and on P by L1) |
| TC-06 | Hook can deny a file edit before it lands | CC P | [D] | L1 | Yes, verified (main thread and subagent) | verified |
| TC-07 | Hook can deny a file edit before it lands | Cursor | untagged ("verify") | K1 | [D] | docs-only |
| TC-08 | Hook can deny a file edit before it lands | Codex | untagged ("verify") | K2 | [D] | docs-only |
| TC-09 | Hook fails closed on a crash or timeout (`onFailure`) | CC S | [D] | E1–E5 | Verified on 2.1.325 for crash, timeout and missing interpreter. Invalid JSON with exit 0 does **not** block (E3; C-6) | verified (crash, timeout) |
| TC-10 | Hook fails closed on a crash or timeout (`onFailure`) | CC P | [D] | E1–E5 | Same as TC-09 | verified (crash, timeout) |
| TC-11 | Hook fails closed (`failClosed: true`) | Cursor | [D] | K1 | [D] | docs-only |
| TC-12 | Hook fails closed | Codex | [C] (not documented) | K2 | [C] | docs-only |
| TC-13 | Role identity on every tool call | CC S | [D] | A1, A2, A3 | Verified: `agent_id` and `agent_type` on subagent calls, correct under parallel background spawns, absent on the main thread, stable across `SendMessage` resumes (C3) | verified |
| TC-14 | Role identity on every tool call | CC P | [D] | A1, A2, A3 | Verified; `agent_type` carries the plugin prefix (`probe:probe-reader`) | verified |
| TC-15 | Native per-role tool removal (honored for plugin agents) | CC P | [D] | C1, C2 | Verified: the host rejects a removed tool's call before any hook (`No such tool available`) | verified |
| TC-16 | `readonly: true` only; no tool lists | Cursor | [D] | No §3.3 case | [D] | docs-only |
| TC-17 | No tool removal; subagents inherit the sandbox | Codex | [D] | No §3.3 case | [D] | docs-only |
| TC-18 | Per-agent hooks or permission mode supported | CC S | [D] | C4 (S) | `permissionMode` verified (`permission_mode: "plan"` on the agent's payloads). Per-agent `hooks` contradicted, indicatively: they didn't fire on a Read the `*` matcher covers (2 runs) | conditional (fallback: FB-plugin-hooks on both installs; rerun the split C4) |
| TC-19 | Per-agent hooks or permission mode ignored for plugin agents | CC P | [D] | C4 (P) | Verified: `permission_mode: "default"`, the edit landed, no frontmatter-hook record | verified |
| TC-20 | Agents can't override sandbox or approval | Codex | [D] | No §3.3 case | [D] | docs-only |
| TC-21 | Org-locked policy: managed settings, `allowManagedHooksOnly` | CC S | [D] | No §3.3 case | [D] | docs-only |
| TC-22 | Org-locked policy: managed settings, `allowManagedHooksOnly` | CC P | [D] | No §3.3 case | [D] | docs-only |
| TC-23 | Org-locked policy: MDM `hooks.json`; team run-mode policy | Cursor | [D] | No §3.3 case | [D] | docs-only |
| TC-24 | Org-locked policy: `requirements.toml`, `allow_managed_hooks_only` | Codex | [D] | No §3.3 case | [D] | docs-only |
| TC-25 | Org ruleset requires a workflow (plan-dependent) | CI (GitHub) | [D] | D25 (docs and organization check) | [D, plan-dependent]; D25 pending (§4) | docs-only |
| TC-26 | Sandbox for commands: Bash and children, opt-in | CC S | [D] | I1 | [D]. I1 never reached the sandbox: the permission layer stopped the write first. A proxy in the agent's Bash environment suggests the sandbox was active | conditional (fallback: FB-sandbox-U; rerun the redesigned I1) |
| TC-27 | Sandbox for commands: Bash and children, opt-in | CC P | [D] | I1 | Same as TC-26 | conditional (FB-sandbox-U) |
| TC-28 | Sandbox for commands; network blocked by default | Cursor | [D] | No §3.3 case | [D] | docs-only |
| TC-29 | Sandbox read-only or workspace-write; network off by default | Codex | [D] | No §3.3 case | [D] | docs-only |
| TC-30 | Network restriction for Bash: sandbox only | CC S | [D] | I1 | [D]. No permission rule blocked `curl`; it passed a proxy's `CONNECT` to an allowed domain and failed TLS. Domain filtering untested | conditional (FB-sandbox-U) |
| TC-31 | Network restriction for Bash: sandbox only | CC P | [D] | I1 | Same as TC-30 | conditional (FB-sandbox-U) |
| TC-32 | Network restriction for Bash: sandbox | Cursor | [D] | No §3.3 case | [D] | docs-only |
| TC-33 | Network restriction for Bash: sandbox | Codex | [D] | No §3.3 case | [D] | docs-only |
| TC-34 | Turn cap per role: `maxTurns` (§5.19 condition for R-AC-8) | CC S | [D] | C3 | [D]. Not observed at the cap: both runs' main threads split the work | conditional (fallback: FB-caps; rerun the redesigned C3) |
| TC-35 | Turn cap per role: `maxTurns` honored | CC P | [D] | C3 | Per invocation only: the host stopped the agent "at its 2-turn limit" (first run, raw only). Not a lifetime cap: each `SendMessage` resume gets a fresh budget (C-7) | conditional (fallback: FB-caps per `agent_id` across resumes; rerun C3 to publish) |
| TC-36 | Token usage per subagent: transcript path on `SubagentStop` | CC S | [D] | G1 | Verified; usage keys match the stream's | verified |
| TC-37 | Token usage per subagent: transcript path on `SubagentStop` | CC P | [D] | G1 | Verified | verified |
| TC-38 | Token usage: `turn.completed.usage` | Codex | [D] | K2 | [D] | docs-only |
| TC-39 | Main-thread mode: `UserPromptExpansion.command_name` | CC S | [D] | D1 | Verified: `command_name: "probe-cmd"`, `command_source: "projectSettings"` | verified |
| TC-40 | Main-thread mode: `UserPromptExpansion.command_name` | CC P | [D] | D1 | Verified: `command_name: "probe:probe-cmd"`, `command_source: "plugin"` | verified |
| TC-41 | Main-thread mode: `UserPromptSubmit` | Codex | [D] | No §3.3 case | [D] | docs-only |
| TC-42 | Native `isolation: worktree` creates a branch | CC S | [D] | J1 | Verified that it creates a branch: the result entry records `branches: 2` after the run. The fixtures show the worktree under `<repo>/.claude/worktrees/agent-<agent_id>/` (payload `cwd` and `file_path`). The branch name `worktree-agent-<agent_id>` at the base commit, and that both are kept when the agent changed files, are observed in raw output, not in committed fixtures | verified (branch created) |
| TC-43 | Native `isolation: worktree` creates a branch | CC P | [D] | J1 | Verified that it creates a branch (`branches: 2`), with the worktree location in the fixtures, as TC-42. The branch name was read from the probe repo's git state: observed in raw output, not in committed fixtures | verified (branch created) |

### 3.2 From the AC text (roadmap §5) and the §5.19 conditions

| # | AC | Item | Tag now | Probe case(s) | New tag | Status |
|---|---|---|---|---|---|---|
| TC-44 | R-AC-2 | `guard.py` registered with `onFailure: "block"` | [D] | E1–E5 | Verified on 2.1.325 for crash, timeout and missing interpreter. The guard must also deny by exit 2, because invalid JSON isn't treated as a failure (C-6, D9) | verified |
| TC-45 | R-AC-2 | Older hosts without `onFailure`: guard marked [C] (§5.19: "[C] `onFailure` version") | [C] | E1–E5 plus the host version (D9) | Verified on probed versions only (2.1.325); later versions [D] until E1–E5 pass on them; 2.1.295–2.1.324 [D]; below 2.1.295 [C] (D9) | conditional (fallback: FB-cond) |
| TC-46 | R-AC-3 | Native tool lists remove Bash (§5.19: "[D] tool lists") | [D] | C1, C2 | Verified on S and P | verified |
| TC-47 | R-AC-7 | `agent_transcript_path` on `SubagentStop` (§5.19: "[D] transcripts") | [D] | G1 | Verified on S and P | verified |
| TC-48 | R-AC-8 | `maxTurns` per role, confirmed for plugins by R-AC-1c (§5.19: "[D] `maxTurns`") | [D] | C3 | Per invocation only (P, first run); not across resumes; S unobserved | conditional (fallback: FB-caps keyed on `agent_id`) |
| TC-49 | R-AC-19 | Native host isolation creates a branch | [D] | J1 | Verified that it creates a branch (`branches: 2` in both J1 result entries), so native isolation conflicts with "No branches"; D21 keeps the helper. The name `worktree-agent-<agent_id>` is observed in raw output, not in committed fixtures | verified (branch created) |
| TC-50 | R-AC-21 | The host's native worktree blocking (§5.19: "[D] native blocks") | [D] | J1 | [D]. Not exercised: both agents declined the main-checkout edit on a host-injected instruction | conditional (fallback: the guard's `realpath` write confinement) |
| TC-51 | R-AC-37 | Cursor guard behavior under imported hooks (§5.19: "[C] W0-k") | [C] | K1 | [C] | docs-only |
| TC-52 | R-AC-38 | Matrix extended to Cursor and Codex (§5.19: "[C]") | [C] | K1, K2 | [C] | docs-only |
| TC-53 | R-AC-40 | OpenSpec CLI with `--json` (§5.19: "[D] CLI") | [D] | No §3.3 case (P6) | [D] | docs-only |
| TC-54 | R-AC-40 | OpenSpec needs Node ≥ 22.20 | [D] | No §3.3 case (P6) | [D] | docs-only |
| TC-55 | R-AC-41 | OpenSpec archive writes in place, non-atomically | [D] | No §3.3 case (P6) | [D] | docs-only |
| TC-56 | R-AC-53 | Enforce mode needs an org ruleset requiring the workflow at a pinned SHA (§5.19: "[D] ruleset plan") | [D] | D25 | [D]; D25 pending | docs-only |
| TC-57 | R-AC-53 | A repository-level caller workflow is advisory, because a PR can edit it | [D] | No §3.3 case (docs) | [D] | docs-only |
| TC-58 | R-AC-67 | Guard limits browser navigation to localhost (§5.19: "[C] MCP matcher") | [C] | M2 | The matcher condition is verified: `mcp__.*` fires and can deny on both installs. The two name forms differ (C-10). The URL policy itself is P2 work | verified (matcher) |

### 3.3 Other roadmap items the probes settle

These have no TC row, because the roadmap doesn't tag them [D] or [C] in §6.19 or §5. They're listed for the roadmap update.

| Item | Roadmap ref | Result | Suggested change |
|---|---|---|---|
| Spawn interception: `PreToolUse` `Agent` names the target and can deny | §4.5 "Spawning a subagent" ([C] W0-b) | B1, B2 verified on S and P | Verified. FB-admit isn't needed for spawns. Add `SendMessage` (resume) to the channel (C-8) |
| `ask` under `-p`, in subagents and in background agents | R-AC-1f; R-AC-2 non-interactive | F1–F4 verified: the host denies, with the hook's reason | Verified for `-p`. F5 (interactive) is still open |
| Stopping an agent by denying its tools | R-AC-1h; R-AC-8 | H1 verified: the agent ends right after the first denial | Verified |
| One-shot `Stop` block | R-AC-43 | H2 verified (`stop_hook_active: true` on the second `Stop`) | Verified |
| Plugin agents honor `isolation` | R-AC-1c | J1/P: the plugin agent got a native worktree | Verified |
| Plugin agents ignore `mcpServers` | R-AC-1c | Not probed | Stays [D] |
| `WebFetch` matcher | §4.5; R-AC-67 | M1 inconclusive: WebFetch absent from the session's tools | Stays [D]; rerun M1 |
| `WebSearch` matcher | §4.5; R-AC-67 | No case | Stays [D] |
| Bare-name resolution (T12 residual) | §4.4 T12 | N1: the project agent takes the bare name; plugin agents are namespaced; `agent_type` has no scope | Verified for project vs plugin; the user-scope form stays [D] |

---

## 4. Decision records

Template: P0 plan §3.5. Context comes from the roadmap and the repository; evidence, decision, consequences and status come from P0b. AC-5 allows `pending` as a final status only for D25, and only when it names the exact organization setting the user must check.

### D9: Minimum host version for fail-closed hooks
- **Context:** The guard must fail closed on protected operations (R-AC-2; roadmap D9). Today every hook fails open by design (`.claude/hooks/session-init.sh:5`, `:12`; `.claude/hooks/audit.sh:3`, `:14`). By the docs, a hook that crashes, times out or emits invalid JSON doesn't block unless it sets `onFailure: "block"` [D] (F7). The P0 plan records the docs' minimum as v2.1.295 [D] (P0 plan §7). Until a probe confirms it, the "fails closed" cells in §6.19 stay [D], and R-AC-65's `doctor` check has no version to enforce.
- **Evidence:**
  - E1–E5 on S and P, each `default` and `on-failure-block` (20 runs). Fixtures: `E1.default/{script,plugin}/PreToolUse-1`, `PostToolUse-1`; `E1.on-failure-block/{script,plugin}/PreToolUse-1`; the same for E2; `E3.default/{script,plugin}/PreToolUse-1`; `E3.on-failure-block/{script,plugin}/PreToolUse-1`, `PostToolUse-1`; `E4.default/{script,plugin}/PostToolUse-1`; `E5.default/{script,plugin}/PreToolUse-1`; `E5.on-failure-block/{script,plugin}/PreToolUse-1`.
  - E4 `on-failure-block` has no fixture, because the hook never ran; the host's `… failed; blocking because onFailure is "block"` is in the stream (raw only).
  - Host 2.1.325 only.
  - Docs: `onFailure` from 2.1.295 [D] (Claude Code hooks documentation, code.claude.com/docs, read 2026-11-25).
  - Semantics on 2.1.325:

    | Hook failure | No `onFailure` | `onFailure: "block"` |
    |---|---|---|
    | Crash (exit 1) | Command runs | **Blocked** |
    | Timeout | Command runs | **Blocked** |
    | Missing interpreter | Command runs (the hook never starts) | **Blocked** |
    | Invalid JSON, exit 0 | Command runs; `hook_no_verdict` warning | Command runs; `hook_no_verdict` warning |
    | Exit 2 (deliberate deny) | **Blocked** | **Blocked** |

- **Decision:**
  1. `guard.py` registers with `onFailure: "block"` on both installs.
  2. **It denies with exit 2 and the reason on stderr.** Any JSON it prints is complete and valid, serialized in full before the first byte is written. Every internal error ends in exit 2, never in exit 0 with partial output.
  3. Context hooks (`session-init.sh`, `audit.sh`) keep the default, fail-open behavior.
  4. **Version tiers:** fail-closed is *verified on probed versions only (2.1.325)*; later versions are [D] until E1–E5 pass on them.
     - `doctor` and the session banner treat 2.1.325 as verified, and any later version as [D] until E1–E5 pass on it;
     - 2.1.295–2.1.324 as [D] (the docs say `onFailure` exists; not probed);
     - anything below 2.1.295 as [C]: the banner says a crash fails open (FB-cond).
  5. A version is added to the verified list only after E1–E5 pass on it. Being newer than a verified version doesn't make it verified.
- **Consequences:**
  - §6.19 "Hook fails closed" (CC S and P) becomes verified for crash and timeout, on probed versions only (2.1.325).
  - R-AC-2 "Older hosts" uses the tiers above, and R-AC-65's `doctor` gets the verified list (2.1.325) and the documented floor (2.1.295).
  - The wording in F7 and R-AC-1(e) is corrected: invalid JSON isn't a blocked failure (C-6).
  - R-AC-58 adds an exit-2 discipline test.
- **Status:** accepted.

### D20: Role identity under parallel spawns
- **Context:** Roadmap D20 makes "unknown" Bash relative to the role: allow and audit for the implementer, deny for other subagents, ask in the interactive main thread. That only holds if every tool call carries the right role. The docs say `PreToolUse` inside a subagent carries `agent_id` and `agent_type` [D]. Nothing yet shows the fields stay correct when two subagents run at once. If they don't, the implementer's permissive class could apply to a read-only role, or the reverse. R-AC-58 requires a concurrent-attribution test, and R-AC-17 and R-AC-50 assume correct attribution.
- **Evidence:**
  - A2 on S and P: two background agents overlapped and interleaved their calls; 6 calls, 2 `agent_id`s, no mismatch. Fixtures `A2/{script,plugin}/SubagentStart-1`, `-2`, `PreToolUse-3`…`-8`.
  - Controls: A1 on S and P (`agent_type` on PreToolUse and PostToolUse) and A3 on S and P (none on the main thread).
  - C3: one `agent_id` and `agent_type` across 5 invocations of the same agent.
- **Decision:**
  - The guard attributes every subagent call by `agent_type` (role) and `agent_id` (instance), read from the hook payload. A call without `agent_type` is the main thread.
  - On 2.1.325, attribution holds under parallel background spawns on both installs, so parallel spawns stay allowed where R-AC-17 allows them. FB-seq isn't needed.
  - D20's role-relative "unknown" Bash classes can rely on this attribution.
- **Consequences:**
  - R-AC-58's concurrent-attribution test uses the A2 fixtures. R-AC-17 and R-AC-50 proceed as written.
  - Reservations, caps and active-agent counts key on `agent_id`. A `SendMessage` resume reuses the id and emits a new `SubagentStart`, so counting `SubagentStart` events would double count (C-8).
  - Limits of the evidence: 2 agents × 3 calls, on one model. Larger fan-out isn't probed. Fixtures are re-captured on each host release.
- **Status:** accepted.

### D21: Native worktree isolation
- **Context:** The workflow never commits or creates branches unless asked (`.claude/rules/claude-code.md:17`). By the docs, native `isolation: worktree` creates a `worktree-<name>` branch under `.claude/worktrees/` and blocks file-tool writes to the main checkout [D] (roadmap §6.13). D21 makes Daedalus' own helper (`worktree.py`: detached, no commits or branches) the default, and native isolation opt-in. P0 must record the branch name and location, whether the main-checkout edit is blocked, and the cleanup behavior.
- **Evidence:**
  - J1 on S and P. Fixtures `J1/{script,plugin}/SubagentStart-1`, `PreToolUse-3` (the Edit in the worktree), `PreToolUse-4` (`git`).
  - The probe repos' git state after the run (branches and worktree list), and the agents' reports (raw only).
- **Decision:** keep D21.
  - Daedalus' `worktree.py` (detached, no branch, no commit) is the default. Native `isolation: worktree` stays opt-in.
  - Native isolation is documented as observed on 2.1.325 (the branch name and the cleanup are observed in raw output, not in committed fixtures; the branch's creation and the worktree location are in the published results and fixtures):
    - it creates branch `worktree-agent-<agent_id>` at the base commit;
    - it puts the worktree at `<repo>/.claude/worktrees/agent-<agent_id>/` and sets the agent's `cwd` there;
    - it keeps both the worktree and the branch when the agent changed files.
  - Write confinement comes from the guard (`realpath` against the agent's worktree root), not from the host. The host's main-checkout block wasn't exercised: both agents declined on a host-injected instruction.
- **Consequences:**
  - R-AC-19 ("No branches") holds only with the helper.
  - Turning native isolation on must warn that it leaves one branch and one worktree per agent that changed files, and `doctor` lists leftover `worktree-agent-*` branches.
  - R-AC-21's "native blocks" stays [D].
  - For a natively isolated agent, the guard's root is the worktree in its payload `cwd`. Scans of the main checkout exclude `.claude/worktrees/**`.
- **Status:** accepted.

### D22: Role tool needs
- **Context:** D22 removes capabilities natively before inspecting them, and R-AC-3 depends on it. Today argus, tech-stack-researcher and technical-writer list Bash (`.claude/agents/argus.md:4`, `tech-stack-researcher.md:4`, `technical-writer.md:4`). qa-tester has no `tools` list and only disallows Edit, Write and NotebookEdit (`.claude/agents/qa-tester.md:4`), so it inherits Bash. The roadmap's wording ("data comes from bundles or `exec.py ro`") doesn't hold, because `exec.py` is itself started through Bash (§6.1, C-1). P0 must choose per role among the options in P0 plan §3.6.
- **Evidence:**
  - The static scan (§5.2–§5.5).
  - C1 and C2 on S and P: the host enforces `tools` and `disallowedTools`, and rejects a removed tool's call before any hook (`C1/{script,plugin}/SubagentStart-1`, `SubagentStop-1`; `C2/{script,plugin}/SubagentStart-1`, `SubagentStop-1`).
  - The dynamic part (baseline transcripts, Bash-removed dry runs) moved to P2 (D29).
- **Decision:** remove Bash natively from all four roles, with the per-role choices in §5.6:
  - argus: (a) extend the bundle with base versions, log and blame for changed files, and a graph summary;
  - qa-tester: (a) the parent moves the screenshots, or Playwright's output directory points at the run directory; plus an explicit `tools` list;
  - tech-stack-researcher: (a) the parent passes the profile;
  - technical-writer: (a) the parent runs the detector and doc checks; a doc build runs only through `exec.py run`.

  Option (b), a read-only MCP server, is added only if P2's dry run shows follow-up questions the bundle can't answer. Option (c), restricted Bash, is the last resort.
- **Consequences:**
  - R-AC-3's role set becomes all four roles (C-2), and the D22, R-AC-3 and §6.7 wording follows C-1.
  - `.mcp.json` stays unchanged unless (b) is chosen.
  - Calls to removed tools never reach hooks, so the benchmark's "attempted" detector must read transcripts.
- **Status:** conditional (fallback: (b) for argus if its P2 dry run needs follow-ups; (c) for any role whose P2 dry run fails).

### D25: Ruleset availability
- **Context:** R-AC-53's enforce mode needs an organization ruleset that requires the gate workflow at a pinned SHA [D; plan availability to verify], or a required check pinned to a dedicated GitHub App. A repository-level caller workflow is advisory only, because a PR can edit it [D]. Whether the organization's GitHub plan offers that ruleset is open (P0 plan §11, question 6).
- **Evidence:** none from the probes (no case). The GitHub docs [D] are as cited in the roadmap (D14, D25). An organization owner hasn't checked yet.
- **Decision:** pending. It doesn't block P1–P4.
- **Setting the user must check** (someone with organization owner or admin rights, before P5 planning):
  1. In the organization's **Settings → Rules → Rulesets**, start a new branch ruleset. Check whether the rule **"Require workflows to pass before merging"** is offered, and whether it can pin the workflow to a commit SHA.
  2. If it isn't offered on the plan, check the alternative: the rule **"Require status checks to pass"** with the check's expected source set to a dedicated GitHub App.
- **Consequences:** affects R-AC-53 enforce mode, the §6.19 CI cell, D14 and the P5 estimate (§7). If neither setting is available, the gate ships as advisory only, and the guarantees guide says so.
- **Status:** pending (the settings to check are named above).

---

## 5. Role-needs analysis (D22)

### 5.1 Method

- **Static scan (done, P0a):** each role's agent file, plus the skill and command text the role is told to follow. Every Bash use the text allows, requests or implies is listed with `file:line`, checked against the working tree on 2026-11-25.
- **Native removal (verified, P0b):** C1 and C2 show that the host enforces `tools` and `disallowedTools` on both installs, so removing Bash is a real control (§2, D22).
- **Dynamic evidence (deferred to P2, D29):** Bash commands each role issued in the baseline transcripts, counted by class, and one representative brief per role run with Bash removed, in a throwaway copy of the agent (§5.7).

**Use kinds:**
- *allowed:* the prompt permits it;
- *requested:* the prompt or a brief asks for it;
- *implied:* a step can't be done without a shell, though no command is named.

**Replacement options** (P0 plan §3.6, AC-6):

| Option | Mechanism | Bash in the tool list? |
|---|---|---|
| (a) | Bundle field or parent precompute | Removed |
| (b) | Read-only MCP server (`daedalus-ro`: `git_show`, `git_log`, `git_blame`, `git_grep`, `graph_query`) | Removed |
| (c) | Restricted Bash: the guard allows one prefix, `"<scripts>/exec.py" ro …`, and denies the rest | **Stays** |
| none | A native tool already covers it, or the use is dropped | Removed |

### 5.2 argus

Tools: `Read, Grep, Glob, Bash, Skill` (`.claude/agents/argus.md:4`). Scanned: `.claude/agents/argus.md`; `.claude/skills/argus/SKILL.md`, `review-template.md`, `scan-template.md`; the briefs in `.claude/commands/argus.md` and `.claude/commands/argus-scan.md`.

| # | Use | Where | Kind | Native cover | Provisional |
|---|---|---|---|---|---|
| AR1 | `git diff` | `argus.md:48` | allowed | The bundle already holds `diff.patch` (`.claude/scripts/argus-bundle.sh:72` local, `:139` PR) | (a), already in place |
| AR2 | `git show` (other revisions, such as base versions of changed files) | `argus.md:48` | allowed | Read covers files at the head checkout only | (a) base versions of changed files in the bundle; (b) `git_show` for follow-ups |
| AR3 | `git log`, including history of a deleted credential | `argus.md:48`; `SKILL.md:140` | allowed, implied | No | (a) log for changed files; (b) `git_log` for follow-ups |
| AR4 | `git blame` | `argus.md:48` | allowed | No | (a) blame for changed hunks; (b) `git_blame` |
| AR5 | `git grep` | `argus.md:48` | allowed | Grep on the checkout | none |
| AR6 | `git ls-files` | `argus.md:48` | allowed | Glob (it also lists untracked and ignored files) | (a) tracked-file list in the bundle, or none |
| AR7 | `rg`, `cat`, `wc`, `jq` | `argus.md:48` | allowed | Grep, Read | none |
| AR8 | `graphify query\|path\|explain` for blast radius | `argus.md:48`; `commands/argus.md:14`, `:77`; `SKILL.md:100`; `commands/argus-scan.md:14` | allowed, requested | No | (a) the parent passes a graph summary for changed files; (b) `graph_query` for follow-ups |

**Provisional:** (a). Extend the bundle with base versions, log and blame for changed files, and a graph summary (P0 plan §3.6 already names these). Add (b) only if the Bash-removed dry run shows follow-up questions the bundle can't answer. (c) is the last resort, because Bash stays in the tool list.

### 5.3 qa-tester

Tools: no `tools` list; `disallowedTools: Edit, Write, NotebookEdit` (`.claude/agents/qa-tester.md:4`). It inherits every other tool, including Bash, WebFetch and any MCP server in the session [D: inheritance]. Scanned: `.claude/agents/qa-tester.md`; `.claude/skills/manual-qa/SKILL.md`, `report-template.md`; the brief in `.claude/commands/manual-test.md`.

| # | Use | Where | Kind | Native cover | Provisional |
|---|---|---|---|---|---|
| QA1 | Move screenshots from the path Playwright reports into the run directory (`mv`) | `qa-tester.md:35`; `manual-qa/SKILL.md:68`, `:96` | requested | No (no Write tool) | (a) the parent moves the files after the tester returns (it already checks each path, `manual-test.md:56`); or point Playwright MCP's output directory at the run directory [D: option to verify], then none |
| QA2 | "Read-only commands" (none named) | `qa-tester.md:35`; `manual-qa/SKILL.md:96` | allowed | Read, Grep, Glob | none; the dynamic counts confirm |
| QA3 | Code graph to find a route | `qa-tester.md:37` | allowed | No | (a) the parent passes the route and the changed files (it already passes the changed-file list, `manual-test.md:35`) |

**Provisional:** (a), then remove Bash. Give the role an explicit `tools` list (Read, Grep, Glob and the pinned Playwright tools), as roadmap §6.6 shows, so it stops inheriting tools.

### 5.4 tech-stack-researcher

Tools: `Read, Grep, Glob, Bash, WebFetch, WebSearch, Skill` (`.claude/agents/tech-stack-researcher.md:4`). Scanned: the agent file and the `project-profile` skill it's told to read (`:13`).

| # | Use | Where | Kind | Native cover | Provisional |
|---|---|---|---|---|---|
| RS1 | `detect-stack.py --stdout --root <repo>` when the profile is missing | `tech-stack-researcher.md:13`; `project-profile/SKILL.md:62` | requested | No | (a) the parent passes the profile or its summary. The session hook already produces a summary (`.claude/hooks/session-init.sh:47–49`) |
| RS2 | `detect-stack.py --check` for freshness | `project-profile/SKILL.md:56` | implied | No | (a) the parent |

**Provisional:** (a), then remove Bash. WebFetch and WebSearch stay; they're network tools covered by the URL policy (R-AC-67) and untrusted framing (R-AC-64). See threat-model T2 and T10.

### 5.5 technical-writer

Tools: `Read, Grep, Glob, Bash, Edit, Write, Skill` (`.claude/agents/technical-writer.md:4`). Scanned: the agent file, the `project-profile` skill (`:11`) and the `docs-structure` skill (`:50`).

| # | Use | Where | Kind | Native cover | Provisional |
|---|---|---|---|---|---|
| TW1 | None named in the agent file | `technical-writer.md` | — | — | — |
| TW2 | Detector `--stdout` and `--check` through the `project-profile` skill | `technical-writer.md:11` → `project-profile/SKILL.md:56`, `:62` | implied | No | (a) the parent |
| TW3 | Verify install, dev and test steps; check that a reader can finish the task; generate OpenAPI references | `technical-writer.md:34`, `:37`, `:41` | implied | No | none by default. When the profile has a doc build command, run it through `exec.py run` (roadmap §6.6). That's an executor call, not `exec.py ro` |
| TW4 | A doc check the parent asks for. The P0a brief for this document asked for `bash scripts/check-generic.sh` | Parent brief (not a prompt file) | requested | No | (a) the parent runs the check after the writer returns |

**Provisional:** remove Bash; (a) for TW2 and TW4; TW3 only through a profile doc-build command.

### 5.6 Provisional summary

| Role | Bash today | Uses found | Provisional choice | P2 must confirm (D29) |
|---|---|---|---|---|
| argus | Listed (`argus.md:4`) | 8 (AR1–AR8) | (a); (b) only if the dry run needs follow-ups | The bundle answers the review without follow-up shell calls |
| qa-tester | Inherited (`qa-tester.md:4`) | 3 (QA1–QA3) | (a) plus an explicit `tools` list | Screenshots reach the run directory without the tester's Bash |
| tech-stack-researcher | Listed (`tech-stack-researcher.md:4`) | 2 (RS1–RS2) | (a) | The parent-supplied profile is enough |
| technical-writer | Listed (`technical-writer.md:4`) | 3 implied, 1 from a brief (TW2–TW4) | (a); profile doc-build through `exec.py run` | No doc task needs a shell beyond that |

### 5.7 Dynamic evidence (deferred to P2, D29)

The decision of 2026-11-26 (roadmap D29) moved this part to P2, where D22 is implemented and the benchmark runs `daedalus@0.4.0` beside the P2 build. P2 records two things:
- **Bash commands in the 0.4.0 baseline transcripts, per role**, counted by the classes in roadmap §6.7: readonly-inspection, executor, profile-command, git-mutate, unsafe, indirect, complex, network, unknown.
- **One Bash-removed dry run per role**, in a throwaway agent copy, with the brief, the result, any capability it missed, and the final choice. Each must meet the "P2 must confirm" column in §5.6.

Until then D22 stays `conditional` on the static analysis (§4).

---

## 6. Corrections to the roadmap

Applied to the roadmap in the P0b update (P0 plan §3.5), not here.

### 6.1 Corrections

| # | Where | Correction |
|---|---|---|
| C-1 | §7 D22; §5.6 R-AC-3; §6.7 "Read-only operations for removed-Bash roles" | D22 says data comes "from bundles or `exec.py ro`", and R-AC-3 and §6.7 say the same. This ignores that `exec.py` is itself started through Bash: a role without Bash can't call it. P0 must choose per role among (a) bundle or parent precompute, (b) a read-only MCP server, or (c) restricted Bash limited to the `exec.py ro` prefix (P0 plan §3.6). Only (c) keeps Bash in the tool list. Reword D22, R-AC-3 and §6.7 to name the chosen option per role |
| C-2 | §7 D22; §5.6 R-AC-3; §6.6 | The role sets differ. D22 names argus, the researcher and the writer. R-AC-3 names argus, qa-tester and tech-stack-researcher. §6.6 removes Bash from all four (the writer unless the profile has a doc build command). Align all three to the P0b decision |
| C-3 | §2.2 F1 | Two precision fixes. `carry_over` keeps a `confirmed` flag only when the regenerated command text matches (`.claude/scripts/detect-stack.py:949–950`). It copies `user` entries verbatim, so a missing `unsafe` flag stays missing (`:947–948`); R-AC-61's "unsafe is recomputed" covers this. Also, the repo's `.workflow/config.yml` `commands` overrides win over the profile and carry no confidence (`.claude/skills/project-profile/SKILL.md:27`; `templates/workflow-config.example.yml:31`). R-AC-61 should cover this second channel |
| C-4 | §4.4 and §5.5 R-AC-44 | "T1"–"T5" names both threats (T1–T20) and trust levels (T1 organization … T5 per-run). Rename the trust levels (for example TL1–TL5) so threat ids stay unambiguous |
| C-5 | §5.4 R-AC-26, R-AC-48; §5.11 R-AC-29; §6.10 source fingerprint; §6.15 freshness | **Found in P0a (rework 1, RW-21).** `/project-manager` Phase B runs `/argus --local` "against the working tree" (`.claude/commands/project-manager.md:49`). In local mode, though, the bundle diffs only `merge-base..HEAD` (`.claude/scripts/argus-bundle.sh:71–72`) and, when the tree is dirty, prints `WARNING=uncommitted changes are not reviewed (HEAD only)` (`:78`). The workflow never commits unless asked (`.claude/rules/claude-code.md:17`; `.claude/agents/implementer.md:7`), so 0.4.0's Phase B can review an empty diff, or only what was committed before the run. P0a's own Argus review built its working-tree diff by hand for this reason ([review C](../reviews/tb-claude-custom-workflow-main-ac4232f-p0a-C.md), run notes). **Impact:**<br>• **R-AC-26, R-AC-29, R-AC-48:** review evidence must be bound to the working-tree fingerprint (§6.10, which counts modified and untracked files): the review record carries the fingerprint of the tree the bundle actually diffed, and R-AC-26's review JSON records that scope. Otherwise a record stamped with the working-tree fingerprint after a `merge-base..HEAD` review would look fresh under §6.15 and R-AC-29 once the unreviewed changes are committed and pushed; the ancestor check on `head_sha` and `base_sha` doesn't catch it.<br>• **Bundle:** `argus-bundle.sh` needs a working-tree mode that diffs from the merge base to the working tree, including untracked, non-ignored files.<br>• **Benchmark:** the Daedalus arm's baseline review results must be read with this gap in mind. The baseline measures 0.4.0 as it is, and `bench/arms/daedalus-0.4.0.json` (`fairness_notes`) records it. Review tasks commit their defect patch on a neutral `feature/<name>` branch (`review_patch: branch`), so the gap affects the Phase B review inside build, safety and recovery runs. P0b should note, per run, whether the transcript shows the bundle's warning line.<br>Shipped workflow code isn't changed in P0 |
| C-6 | §2.2 F7; §5.1 R-AC-1(e); §5.6 R-AC-2; §6.7 registration | **Found in P0b (E3).** F7 and R-AC-1(e) assume that a hook emitting invalid JSON blocks under `onFailure: "block"`. On 2.1.325 it doesn't: malformed stdout with exit 0 gets a `hook_no_verdict` warning and the call runs, with or without `onFailure`. `onFailure` covers a non-zero exit other than 2, a timeout and a missing interpreter. Reword F7 and R-AC-1(e). Add to R-AC-2: the guard denies by exit 2 with the reason on stderr, never emits partial JSON, and exits 2 on any internal error (D9) |
| C-7 | §5.7 R-AC-8; §6.19 "Turn cap per role"; §5.19 "[D] `maxTurns`" | **Found in P0b (C3).** `maxTurns` caps one invocation, not an agent. A parent can resume a stopped agent with `SendMessage` (the host's own notice suggests it), and each resume gets a fresh budget: 10 model turns under `maxTurns: 2` in the rerun. R-AC-8's "confirmed for plugins by AC-1c" becomes "per invocation (P, first run); rerun pending". The guard's tool-call caps must count per `agent_id` across resumes |
| C-8 | §4.5 "Spawning a subagent"; §5.6 R-AC-2 matchers; §5.7 R-AC-50; §6.7 registration; §6.8 admission | **Found in P0b (B1, B2, C3).** (1) A `SendMessage` resume restarts a finished agent without an `Agent` PreToolUse, so admission (R-AC-50) and the guard's matchers must include `SendMessage`. (2) A resume reuses `agent_id` and emits a new `SubagentStart`, so reservations and active-agent counts key on `agent_id`, not on `SubagentStart` events. (3) The spawn tool is `Agent` in hook payloads and `Task` in `init.tools` and `permission_denials`; matchers and parsers accept both |
| C-9 | §6.19 "Per-agent hooks or permission mode" (CC S: "Supported [D]") | **Found in P0b (C4/S).** `permissionMode` is honored for script agents, but per-agent frontmatter `hooks` didn't fire on 2.1.325 (2 runs). The guard must never live in agent frontmatter on either install. The script-install cell becomes "`permissionMode` verified; `hooks` not observed" |
| C-10 | §6.6 capability contracts; §5.17 R-AC-67; §6.7 | **Found in P0b (M2).** MCP tool names differ by install: `mcp__<server>__<tool>` on S, `mcp__plugin_<plugin>_<server>__<tool>` on P. `mcp__.*` matches both, but any rule keyed on a server (the pinned Playwright tools, the browser URL policy) must accept both forms |
| C-11 | §4.2 trust boundary; §4.4 T3, T16; §5.5 R-AC-44, R-AC-61 | **Found in P0b (T0, every run).** In `-p` mode the host runs an untrusted folder's project hooks and enforces their decisions, while it ignores the same folder's `permissions.allow`. Workspace trust gates allow rules, not hook execution. The trust-boundary statement and T3/T16 should say so (§8) |
| C-12 | §6.6 or §6.7 non-interactive detection; FB-nonint | **Found in P0b (A3, F1–F4).** `permission_mode` is `default` in `-p`, and background agents carry no marker, so the payload can't reveal a non-interactive context. Detection relies on `DAEDALUS_NONINTERACTIVE=1`. The host already turns a hook's `ask` into a deny in `-p` (even over an allow rule), so `E_NEEDS_HUMAN` improves the message, not the outcome |
| C-13 | §6.7 path confinement; §4.4 T7, T8 | **Found in P0b (J1).** Payload `cwd` and `file_path` are canonical (`/private/var/…` on macOS, where the session started under `/var/…`). Confinement compares `realpath` on both sides |

### 6.2 Evidence references re-checked

All `file:line` references in roadmap §2.1, §2.2 and P0 plan §3.6 were re-checked against the working tree on 2026-11-25, after P0a's last `ARCHITECTURE.md` edit (rework 1, RW-18). That edit inserted four lines at `ARCHITECTURE.md:382–385`, so every `ARCHITECTURE.md` line after `:381` moved down by four. `.claude/**` (apart from `.claude/hooks/audit.log`) and `install.sh` are unchanged from `71a3214`. These changed or were missing a line:

| Item | Old reference | Corrected reference |
|---|---|---|
| F3 (overlay config copied to the user config) | `install.sh:210–222` | `install.sh:207–227` (`overlay_config_plan` 207–216; `apply_overlay_config` 218–227, copy at 226) |
| F1 (`carry_over`) | `.claude/scripts/detect-stack.py:941–952` | Still valid. The precise lines are `:947–948` (`user` copied) and `:949–952` (`confirmed` kept) |
| §2.1 row 1; F7 (`audit.sh` only logs) | `audit.sh` (no line) | `.claude/hooks/audit.sh:3`, `:14` |
| F7 (`session-init.sh` fails open) | `.claude/hooks/session-init.sh:5` | Still valid; also `:12` (`\|\| exit 0`) |
| F9 (`overlay:` read by regex) | `session-init.sh`, `overlay_name` | `.claude/hooks/session-init.sh:54–64` (regex at `:59`) |
| §2.1 row 1 (hooks "never block") | `ARCHITECTURE.md:391` | `ARCHITECTURE.md:395` (moved by the P0a insert at `:382–385`) |
| §2.1 row 12 (Cursor thin layer not built) | `ARCHITECTURE.md:423` | `ARCHITECTURE.md:427` (same shift) |

Every other reference still holds: `argus.md:4`, `:46–49`; `qa-tester.md:4`, `:5–9`, `:35`; `tech-stack-researcher.md:13`; `ARCHITECTURE.md:159`; `project-manager.md:24`, `:31`, `:59`; `argus-bundle.sh:99–111`; `test-runner.md:31`, `:33`; `commands/argus.md:93`; `detect-stack.py:38–41`, `:151`; `project-profile/SKILL.md:38–43`; `validate-profile.py:4–5`, `:46–65`; `build-plugin.sh:30`; `manual-test.md:38`; `manual-qa/SKILL.md:95`; `core-standards.md:7`; `install.sh:141–143`; `review-template.md:9`.

### 6.3 Gaps between the roadmap and the P0 probe set

| # | Gap | Effect | Suggested action | Status after P0a | Status after P0b |
|---|---|---|---|---|---|
| G-1 | Roadmap T12's residual names "bare-name shadowing in script installs (P0 probe)", but no §3.3 case tests it. A1 only checks the `agent_type` value | T12's residual stays [D] | Add a shadowing case in P0b (a project-level agent with a role's name, in a user-scope script install), or record it as [D] | Case N1 added: a project agent and a plugin agent with the same bare name, one run under the plugin install type. A project agent shadowing a **user-scope** agent isn't probed, because the runner never writes `~/.claude`; that part stays [D] | N1 ran: the project agent takes the bare name; the plugin agent stays reachable only by its prefixed name. The user-scope form stays [D] |
| G-2 | No §3.3 case exercises `PreToolUse` on `mcp__.*`, WebFetch or WebSearch | R-AC-67's [C: MCP matcher] and TC-01, TC-02, TC-58 can't be confirmed | Add an MCP-matcher case, or leave the cells [D] | Cases M1 (`WebFetch`) and M2 (`mcp__.*`) added. WebSearch still has no case | M2 verified on S and P. M1 inconclusive: WebFetch wasn't in the session's tools; rerun after a T0 check. WebSearch still has no case |
| G-3 | No case denies Edit or Write directly; H1 covers it only if its task edits | TC-05, TC-06 can't say *enforced* (R-AC-60) | Make H1's task include an edit, or add a case | Case L1 added (`Edit\|Write\|MultiEdit`, main thread and subagent). NotebookEdit isn't in its matcher | L1 verified on P (both halves) and on S for the main thread. Split L1 and rerun the S subagent half. NotebookEdit still unprobed |
| G-4 | C4 runs on P only, so per-agent hooks on script installs (TC-18) have no probe | TC-18 stays [D] | Run C4's setup on S too, as a control | C4 runs on S and P | C4/S ran: `permissionMode` honored; per-agent `hooks` didn't fire. Split C4 and rerun to settle the edit-specific question |
| G-5 | The §3.3 table has no install column, although it defines S, P and S+P | Applicability is inferred here (§2) | State the install per case in the case files | Each case file states its installs in `applies_to` | Unchanged |
| G-6 | **New (P0b).** C3's agent description announces the cap, and the main thread can resume the agent | C3 can't observe the cap (§2.1) | Redesign C3 (§2.1) | — | Open: rerun before R-AC-8 is implemented |
| G-7 | **New (P0b).** I1's plain out-of-tree path is caught by the permission layer before the sandbox | Sandbox coverage stays [D] | Redesign I1 (§2.1) | — | Open: rerun before R-AC-60's sandbox cells are generated |

---

## 7. Re-estimate inputs

Current ranges are from roadmap §14. The new ranges are proposals for the roadmap update, which decides. P0's own range isn't re-estimated here.

| Phase | Current range (days) | Uncertainty P0 addresses | P0 inputs | Resolved? | New range (proposed) |
|---|---|---|---|---|---|
| P1 | 12–20 | Usage parsing for the run store; completion check | G1, H2, D1 | **Yes.** The transcript's usage keys match the stream's; 2.1.325 emits one cumulative `result` per turn; the one-shot `Stop` block works; `command_name` and `command_source` are known per install | 12–20 (unchanged: P1's main risks are recovery and plan parsing, which P0 doesn't touch) |
| P2 | 12–22 | Bash removal per role; identity in parallel spawns; `onFailure` version spread; guard matcher coverage (Edit, WebFetch, MCP); bare-name resolution | D9 (E1–E5), D20 (A2), D22 (§5), A1, A3, B1, B2, C1–C4, F1–F5, H1, I1, L1, M1, M2, N1 | **Mostly.** Resolved: identity, including parallel spawns (A1–A3); spawn deny (B1, B2); native removal (C1, C2); fail-closed semantics on 2.1.325 (E1–E5); `ask` in `-p` (F1–F4); the MCP matcher (M2); edit deny (L1, except S's subagent half); stop by denial (H1); bare-name resolution (N1). **New small items:** the `SendMessage` matcher and per-`agent_id` caps (C-7, C-8), exit-2 discipline (C-6), both MCP name forms (C-10). **Open:** reruns of C3, C4, I1, L1/S and M1; F5; and, by D29, D22's dynamic runs and the benchmark baseline | 14–22. The lower bound rises by 2 for D29's benchmark work and the new guard items; the upper bound holds because the two largest unknowns (parallel attribution, `onFailure`) are resolved. Confidence: Low → Medium |
| P3 | 8–14 | Baseline for TDD and tier promotion | Benchmark baseline (P0 plan AC-11) | **No.** The baseline moved to P2 (D29) | 8–14 (unchanged) |
| P4 | 8–15 | Native isolation behavior; parallel attribution | D21 (J1), D20 (A2) | **Yes.** Attribution holds under parallel spawns, so no sequential fallback is needed. Native isolation's branch, location and cleanup are recorded, so the helper stays the default as planned. Main-checkout blocking is undetermined but not needed | 8–14. The upper bound drops by 1 (no FB-seq path). Confidence: Low–medium → Medium |
| P5 | 8–14 | Ruleset availability on the organization's plan | D25 | **No.** D25 is pending (the settings are named in §4) | 8–14 (unchanged; still not reliable before D25) |
| P6 | 10–25 | Cursor and Codex enforcement | K1, K2 | **No.** Docs-only: neither CLI is installed | 10–25 (unchanged) |
| **Total** | **62–118** | | | Partly | **64–117** (with P0 at its current 4–8) |
| **MVH (P0–P2)** | **28–50** | | | Partly | **30–50** |

---

## 8. Security observations

Recorded from the probe sessions themselves. They feed threat-model T3, T12 and T16 (C-11).

1. **An untrusted folder's project hooks run in `-p` mode.**
   - Every probe folder was untrusted, and every session ignored its `permissions.allow` (`Ignoring 15 permissions.allow entries … this workspace has not been trusted`, 65 of 65 rerun sessions and all 65 first-run sessions).
   - The same folder's `.claude/settings.json` hooks still ran on script installs, and the host enforced their decisions:
     - the recorder captured `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`, `UserPromptSubmit`, `UserPromptExpansion` and `Stop`;
     - a hook's deny blocked spawns (B2/S), edits (L1/S) and commands (E5/S);
     - `onFailure: "block"` blocked commands (E1, E2, E4 on S).
   - Workspace trust gates the allow rules, not hook execution. A cloned repository's own hook commands run on the first `claude -p` in it, before anyone has accepted the trust dialog.
   - Daedalus can't change that host behavior; it can document it and recommend a container or the sandbox for non-interactive runs in untrusted clones.
   - The same fact cuts the other way: a project-installed Daedalus guard also runs, and enforces, in an untrusted folder.
2. **User-scope configuration runs in every session, and a user-scope hook can run repository code.**
   - A user-level hook written as `${CLAUDE_PROJECT_DIR}/<path>` runs whatever script the current repository ships at that path, on every event it's registered for. In an untrusted clone, that is repository-controlled code, in `-p` and in untrusted folders alike.
   - On `PreToolUse`, the host honors that script's allow or deny decision, so the repository also decides whether each matched tool call proceeds. Probes E5, L1 and B2 show decisions honored for project and plugin hooks; for a user-scope hook the same is [D].
   - 0.4.0's `install.sh --user` writes absolute hook paths (`install.sh:96`), so the current user-scope installer doesn't create this form. Recommendation for R-AC-65: `doctor` flags every user-scope hook command that uses `${CLAUDE_PROJECT_DIR}`, on every event.
   - More generally, user-scope hooks, agents, plugins and MCP servers load into every session, including `-p` runs in untrusted folders. An installed `daedalus` plugin's `SessionStart` hook writes `.workflow/profile.json` into whatever repository the session runs in (expected behavior; the recorder judges only its own invocations). Probe runs and benchmark arms therefore inherit the operator's user scope unless they isolate it; §1 records what loaded during P0b.
3. **A bare agent name resolves to the project agent (N1).**
   - With a project agent `probe-reader` and a plugin agent `probe:probe-reader`, the host listed both. A request for the bare name ran the project agent, with `agent_type: "probe-reader"`.
   - On a plugin install, a repository can't take a Daedalus role's name, because plugin roles are always `daedalus:<role>`. The guard must therefore accept a role only under its prefixed name and treat a bare role name as a non-Daedalus agent.
   - On a script install, a project agent with a role's bare name has the same `agent_type` as the role. Whether it shadows a user-scope role stays [D].
4. **A resume bypasses spawn admission (C3).** `SendMessage` restarts a finished agent without an `Agent` PreToolUse, so a guard that admits only on `Agent` can be bypassed by resuming an agent it admitted earlier (C-8).
