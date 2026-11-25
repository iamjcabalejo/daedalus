# Daedalus hardening P0: findings

| Field | Value |
|---|---|
| **Status** | Skeleton (P0a). P0b fills every `pending P0b` cell from probe runs, benchmark transcripts and dry runs |
| **Owner ACs** | P0 plan **AC-4** (findings), **AC-5** (decision records), **AC-6** (role-needs analysis; the static part is complete here) |
| **Sources** | [daedalus-hardening-p0.md](daedalus-hardening-p0.md) §3.3, §3.5, §3.6; [daedalus-hardening-roadmap.md](daedalus-hardening-roadmap.md) §5, §6.19, §7, §14 |
| **Related** | [daedalus-hardening-threat-model.md](daedalus-hardening-threat-model.md) (AC-7) |
| **Base** | `main` @ `71a3214`, plugin `0.4.0` |
| **Rule** | Nothing here is a probe result yet. Results, host versions, costs and decisions come only from P0b |

Install codes: **S** = Claude Code script install, **P** = Claude Code plugin install. Roadmap ACs are written **R-AC-n**.

---

## 1. Environment

| Field | Value |
|---|---|
| Hub commit under test | `71a3214` |
| `daedalus` plugin version | `0.4.0` |
| Claude Code CLI version (S) | pending P0b |
| Claude Code CLI version (P) | pending P0b |
| OS and version | pending P0b |
| Python, git | pending P0b |
| Docker or colima (benchmark boundary) | pending P0b |
| Cursor CLI version (case K1) | pending P0b (or docs-only [D]) |
| Codex CLI version (case K2) | pending P0b (or docs-only [D]) |
| Probe model id | pending P0b |
| Plugins enabled during probes | pending P0b |
| T0 flag check: `--plugin-dir`, `--max-budget-usd`, `--max-turns`, `--model`, `stream-json` usage fields | pending P0b |
| Probe run dates (UTC) | pending P0b |
| Probe spend (USD) | pending P0b |

---

## 2. Results by case

One row per case in P0 plan §3.3 and per install. Each row records the result, the evidence fixture ids, the fallback when the result isn't confirmed, and the roadmap ACs that depend on it.

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

| Case | Install | Question | Status | Fixture ids | Fallback | Depends (R-AC) |
|---|---|---|---|---|---|---|
| A1 | S | Identity on subagent tool calls | pending P0b | pending P0b | FB-ro | 1a, 2, 45, 58, 60 |
| A1 | P | Identity on subagent tool calls | pending P0b | pending P0b | FB-ro | 1a, 2, 45, 58, 60 |
| A2 | S | Identity under concurrency (D20) | pending P0b | pending P0b | FB-seq | 1a, 17, 50, 58 |
| A2 | P | Identity under concurrency (D20) | pending P0b | pending P0b | FB-seq | 1a, 17, 50, 58 |
| A3 | S | Main thread has no agent fields | pending P0b | pending P0b | FB-mode | 2, 58 |
| A3 | P | Main thread has no agent fields | pending P0b | pending P0b | FB-mode | 2, 58 |
| B1 | S | What an `Agent` `PreToolUse` carries | pending P0b | pending P0b | FB-admit | 1b, 2, 50 |
| B1 | P | What an `Agent` `PreToolUse` carries | pending P0b | pending P0b | FB-admit | 1b, 2, 50 |
| B2 | S | A hook can deny a spawn | pending P0b | pending P0b | FB-admit | 1b, 2, 50 |
| B2 | P | A hook can deny a spawn | pending P0b | pending P0b | FB-admit | 1b, 2, 50 |
| C1 | S | `tools` list honored | pending P0b | pending P0b | FB-allow | 1c, 3, 45, 60 |
| C1 | P | `tools` list honored | pending P0b | pending P0b | FB-allow | 1c, 3, 45, 60 |
| C2 | S | `disallowedTools` honored | pending P0b | pending P0b | FB-allow | 1c, 3, 45, 60 |
| C2 | P | `disallowedTools` honored | pending P0b | pending P0b | FB-allow | 1c, 3, 45, 60 |
| C3 | S | `maxTurns` honored | pending P0b | pending P0b | FB-caps | 1c, 8 |
| C3 | P | `maxTurns` honored | pending P0b | pending P0b | FB-caps | 1c, 8 |
| C4 | S | Script agents honor `hooks` and `permissionMode` (control) | pending P0b | pending P0b | none named | 1c, 2, 60 |
| C4 | P | Plugin agents ignore `hooks` and `permissionMode` | pending P0b | pending P0b | FB-plugin-hooks | 1c, 2, 60 |
| D1 | S | Prompt-event fields for bare commands | pending P0b | pending P0b | none named | 1d, 2 |
| D1 | P | Prompt-event fields for plugin-prefixed commands | pending P0b | pending P0b | none named | 1d, 2 |
| E1 | S | `crash`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E1 | P | `crash`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E2 | S | `timeout`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E2 | P | `timeout`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E3 | S | `invalid-json`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E3 | P | `invalid-json`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E4 | S | `missing-interpreter`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E4 | P | `missing-interpreter`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E5 | S | `exit2`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| E5 | P | `exit2`, with and without `onFailure` | pending P0b | pending P0b | FB-cond | 1e, 2, 65 |
| F1 | S | `ask` in `-p` (default mode) | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F1 | P | `ask` in `-p` (default mode) | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F2 | S | `ask` in `-p --permission-mode dontAsk` | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F2 | P | `ask` in `-p --permission-mode dontAsk` | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F3 | S | `ask` in a `-p` subagent | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F3 | P | `ask` in a `-p` subagent | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F4 | S | `ask` in a `-p` background subagent | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F4 | P | `ask` in a `-p` background subagent | pending P0b | pending P0b | FB-nonint | 1f, 2 |
| F5 | S | `ask` interactive (maintainer; QA checklist) | pending P0b | pending P0b | FB-nonint | 1f, 2, 66 |
| F5 | P | `ask` interactive (maintainer; QA checklist) | pending P0b | pending P0b | FB-nonint | 1f, 2, 66 |
| G1 | S | Usage per subagent from `SubagentStop` | pending P0b | pending P0b | none named | 1g, 7, 28, 50 |
| G1 | P | Usage per subagent from `SubagentStop` | pending P0b | pending P0b | none named | 1g, 7, 28, 50 |
| H1 | S | Stopping an agent with tool denial | pending P0b | pending P0b | none named | 1h, 8, 14 |
| H1 | P | Stopping an agent with tool denial | pending P0b | pending P0b | none named | 1h, 8, 14 |
| H2 | S | One-shot `Stop` block | pending P0b | pending P0b | none named | 43 |
| H2 | P | One-shot `Stop` block | pending P0b | pending P0b | none named | 43 |
| I1 | S | Sandbox coverage of subagent Bash (macOS or Linux) | pending P0b | pending P0b | FB-sandbox-U | 1i, 10, 60 |
| I1 | P | Sandbox coverage of subagent Bash (macOS or Linux) | pending P0b | pending P0b | FB-sandbox-U | 1i, 10, 60 |
| J1 | S | Native worktree isolation (D21) | pending P0b | pending P0b | FB-helper | 1j, 19, 21 |
| J1 | P | Native worktree isolation (D21) | pending P0b | pending P0b | FB-helper | 1j, 19, 21 |
| L1 | S | A hook denies an edit before it lands (main thread and subagent) | pending P0b | pending P0b | none named | 2, 21, 58, 60 |
| L1 | P | A hook denies an edit before it lands (main thread and subagent) | pending P0b | pending P0b | none named | 2, 21, 58, 60 |
| M1 | S | `WebFetch` matcher: a hook denies a fetch | pending P0b | pending P0b | none named | 2, 60, 67 |
| M1 | P | `WebFetch` matcher: a hook denies a fetch | pending P0b | pending P0b | none named | 2, 60, 67 |
| M2 | S | `mcp__.*` matcher: tool-name format, and whether a hook can deny | pending P0b | pending P0b | none named | 2, 60, 67 |
| M2 | P | `mcp__.*` matcher: tool-name format, and whether a hook can deny | pending P0b | pending P0b | none named | 2, 60, 67 |
| N1 | S+P | Bare-name resolution: a project agent and a plugin agent named `probe-reader` (T12 residual) | pending P0b | pending P0b | none named | 45, 58 |
| K1 | Cursor | Deny, fail-closed, identity; Claude-format import | pending P0b | pending P0b | FB-docs | 1k, 37, 38 |
| K2 | Codex | Deny, identity, failure behavior, usage | pending P0b | pending P0b | FB-docs | 1k, 38, 39 |

---

## 3. Tag changes to the roadmap

Every [D] or [C] item in roadmap §6.19 and in the §5 AC text, plus the [D]/[C] conditions in the §5.19 matrix (merged into the matching row). "Same" cells in §6.19 inherit the tag of the cell they repeat. Untagged "verify" cells are included. [I] and [U] cells aren't listed.

**Status values** after P0b: `confirmed`, `contradicted` or `conditional`. "No §3.3 case" means P0 has no probe for the item; it stays as it is unless P0b adds one or checks the docs.

### 3.1 From the platform matrix (roadmap §6.19)

| # | Guarantee | Platform | Tag now | Probe case(s) | New tag | Status |
|---|---|---|---|---|---|---|
| TC-01 | Hook can deny a shell or MCP call | CC S | [D] | H1, E5 (shell); M2 (MCP) | pending | pending |
| TC-02 | Hook can deny a shell or MCP call | CC P | [D] | H1, E5 (shell); M2 (MCP) | pending | pending |
| TC-03 | Hook can deny a shell or MCP call | Cursor | [D] | K1 | pending | pending |
| TC-04 | Hook can deny a shell or MCP call | Codex | [D] | K2 | pending | pending |
| TC-05 | Hook can deny a file edit before it lands | CC S | [D] | L1 | pending | pending |
| TC-06 | Hook can deny a file edit before it lands | CC P | [D] | L1 | pending | pending |
| TC-07 | Hook can deny a file edit before it lands | Cursor | untagged ("verify") | K1 | pending | pending |
| TC-08 | Hook can deny a file edit before it lands | Codex | untagged ("verify") | K2 | pending | pending |
| TC-09 | Hook fails closed on a crash or timeout (`onFailure`) | CC S | [D] | E1–E5 | pending | pending |
| TC-10 | Hook fails closed on a crash or timeout (`onFailure`) | CC P | [D] | E1–E5 | pending | pending |
| TC-11 | Hook fails closed (`failClosed: true`) | Cursor | [D] | K1 | pending | pending |
| TC-12 | Hook fails closed | Codex | [C] (not documented) | K2 | pending | pending |
| TC-13 | Role identity on every tool call | CC S | [D] | A1, A2, A3 | pending | pending |
| TC-14 | Role identity on every tool call | CC P | [D] | A1, A2, A3 | pending | pending |
| TC-15 | Native per-role tool removal (honored for plugin agents) | CC P | [D] | C1, C2 | pending | pending |
| TC-16 | `readonly: true` only; no tool lists | Cursor | [D] | No §3.3 case | pending | pending |
| TC-17 | No tool removal; subagents inherit the sandbox | Codex | [D] | No §3.3 case | pending | pending |
| TC-18 | Per-agent hooks or permission mode supported | CC S | [D] | C4 (S) | pending | pending |
| TC-19 | Per-agent hooks or permission mode ignored for plugin agents | CC P | [D] | C4 (P) | pending | pending |
| TC-20 | Agents can't override sandbox or approval | Codex | [D] | No §3.3 case | pending | pending |
| TC-21 | Org-locked policy: managed settings, `allowManagedHooksOnly` | CC S | [D] | No §3.3 case | pending | pending |
| TC-22 | Org-locked policy: managed settings, `allowManagedHooksOnly` | CC P | [D] | No §3.3 case | pending | pending |
| TC-23 | Org-locked policy: MDM `hooks.json`; team run-mode policy | Cursor | [D] | No §3.3 case | pending | pending |
| TC-24 | Org-locked policy: `requirements.toml`, `allow_managed_hooks_only` | Codex | [D] | No §3.3 case | pending | pending |
| TC-25 | Org ruleset requires a workflow (plan-dependent) | CI (GitHub) | [D] | D25 (docs and organization check) | pending | pending |
| TC-26 | Sandbox for commands: Bash and children, opt-in | CC S | [D] | I1 | pending | pending |
| TC-27 | Sandbox for commands: Bash and children, opt-in | CC P | [D] | I1 | pending | pending |
| TC-28 | Sandbox for commands; network blocked by default | Cursor | [D] | No §3.3 case | pending | pending |
| TC-29 | Sandbox read-only or workspace-write; network off by default | Codex | [D] | No §3.3 case | pending | pending |
| TC-30 | Network restriction for Bash: sandbox only | CC S | [D] | I1 | pending | pending |
| TC-31 | Network restriction for Bash: sandbox only | CC P | [D] | I1 | pending | pending |
| TC-32 | Network restriction for Bash: sandbox | Cursor | [D] | No §3.3 case | pending | pending |
| TC-33 | Network restriction for Bash: sandbox | Codex | [D] | No §3.3 case | pending | pending |
| TC-34 | Turn cap per role: `maxTurns` (§5.19 condition for R-AC-8) | CC S | [D] | C3 | pending | pending |
| TC-35 | Turn cap per role: `maxTurns` honored | CC P | [D] | C3 | pending | pending |
| TC-36 | Token usage per subagent: transcript path on `SubagentStop` | CC S | [D] | G1 | pending | pending |
| TC-37 | Token usage per subagent: transcript path on `SubagentStop` | CC P | [D] | G1 | pending | pending |
| TC-38 | Token usage: `turn.completed.usage` | Codex | [D] | K2 | pending | pending |
| TC-39 | Main-thread mode: `UserPromptExpansion.command_name` | CC S | [D] | D1 | pending | pending |
| TC-40 | Main-thread mode: `UserPromptExpansion.command_name` | CC P | [D] | D1 | pending | pending |
| TC-41 | Main-thread mode: `UserPromptSubmit` | Codex | [D] | No §3.3 case | pending | pending |
| TC-42 | Native `isolation: worktree` creates a branch | CC S | [D] | J1 | pending | pending |
| TC-43 | Native `isolation: worktree` creates a branch | CC P | [D] | J1 | pending | pending |

### 3.2 From the AC text (roadmap §5) and the §5.19 conditions

| # | AC | Item | Tag now | Probe case(s) | New tag | Status |
|---|---|---|---|---|---|---|
| TC-44 | R-AC-2 | `guard.py` registered with `onFailure: "block"` | [D] | E1–E5 | pending | pending |
| TC-45 | R-AC-2 | Older hosts without `onFailure`: guard marked [C] (§5.19: "[C] `onFailure` version") | [C] | E1–E5 plus the host version (D9) | pending | pending |
| TC-46 | R-AC-3 | Native tool lists remove Bash (§5.19: "[D] tool lists") | [D] | C1, C2 | pending | pending |
| TC-47 | R-AC-7 | `agent_transcript_path` on `SubagentStop` (§5.19: "[D] transcripts") | [D] | G1 | pending | pending |
| TC-48 | R-AC-8 | `maxTurns` per role, confirmed for plugins by R-AC-1c (§5.19: "[D] `maxTurns`") | [D] | C3 | pending | pending |
| TC-49 | R-AC-19 | Native host isolation creates a branch | [D] | J1 | pending | pending |
| TC-50 | R-AC-21 | The host's native worktree blocking (§5.19: "[D] native blocks") | [D] | J1 | pending | pending |
| TC-51 | R-AC-37 | Cursor guard behavior under imported hooks (§5.19: "[C] W0-k") | [C] | K1 | pending | pending |
| TC-52 | R-AC-38 | Matrix extended to Cursor and Codex (§5.19: "[C]") | [C] | K1, K2 | pending | pending |
| TC-53 | R-AC-40 | OpenSpec CLI with `--json` (§5.19: "[D] CLI") | [D] | No §3.3 case (P6) | pending | pending |
| TC-54 | R-AC-40 | OpenSpec needs Node ≥ 22.20 | [D] | No §3.3 case (P6) | pending | pending |
| TC-55 | R-AC-41 | OpenSpec archive writes in place, non-atomically | [D] | No §3.3 case (P6) | pending | pending |
| TC-56 | R-AC-53 | Enforce mode needs an org ruleset requiring the workflow at a pinned SHA (§5.19: "[D] ruleset plan") | [D] | D25 | pending | pending |
| TC-57 | R-AC-53 | A repository-level caller workflow is advisory, because a PR can edit it | [D] | No §3.3 case (docs) | pending | pending |
| TC-58 | R-AC-67 | Guard limits browser navigation to localhost (§5.19: "[C] MCP matcher") | [C] | M2 | pending | pending |

---

## 4. Decision records

Template: P0 plan §3.5. Context is filled from the roadmap and the repository. Evidence, decision, consequences and status are filled in P0b. AC-5 allows `pending` as a final status only for D25, and only when it names the exact organization setting the user must check.

### D9: Minimum host version for fail-closed hooks
- **Context:** The guard must fail closed on protected operations (R-AC-2; roadmap D9). Today every hook fails open by design (`.claude/hooks/session-init.sh:5`, `:12`; `.claude/hooks/audit.sh:3`, `:14`). By the docs, a hook that crashes, times out or emits invalid JSON doesn't block unless it sets `onFailure: "block"` [D] (F7). The P0 plan records the docs' minimum as v2.1.295 [D] (P0 plan §7). Until a probe confirms it, the "fails closed" cells in §6.19 stay [D], and R-AC-65's `doctor` check has no version to enforce.
- **Evidence:** pending P0b. Planned: E1–E5 on S and P, each with and without `onFailure`; host versions from T0; the docs URL.
- **Decision:** pending P0b.
- **Consequences:** pending P0b. Affects §6.19 "Hook fails closed" (CC S and P), R-AC-2 "Older hosts" [C], R-AC-65 (`doctor` minimum version) and the session banner.
- **Status:** pending P0b.

### D20: Role identity under parallel spawns
- **Context:** Roadmap D20 makes "unknown" Bash relative to the role: allow and audit for the implementer, deny for other subagents, ask in the interactive main thread. That only holds if every tool call carries the right role. The docs say `PreToolUse` inside a subagent carries `agent_id` and `agent_type` [D]. Nothing yet shows the fields stay correct when two subagents run at once. If they don't, the implementer's permissive class could apply to a read-only role, or the reverse. R-AC-58 requires a concurrent-attribution test, and R-AC-17 and R-AC-50 assume correct attribution.
- **Evidence:** pending P0b. Planned: A2 on S and P, with A1 and A3 as controls; redacted fixtures for R-AC-58.
- **Decision:** pending P0b.
- **Consequences:** pending P0b. Affects §6.19 "Role identity on every tool call", R-AC-58, R-AC-17 and R-AC-50. FB-seq applies if A2 is contradicted.
- **Status:** pending P0b.

### D21: Native worktree isolation
- **Context:** The workflow never commits or creates branches unless asked (`.claude/rules/claude-code.md:17`). By the docs, native `isolation: worktree` creates a `worktree-<name>` branch under `.claude/worktrees/` and blocks file-tool writes to the main checkout [D] (roadmap §6.13). D21 makes Daedalus' own helper (`worktree.py`: detached, no commits or branches) the default, and native isolation opt-in. P0 must record the branch name and location, whether the main-checkout edit is blocked, and the cleanup behavior.
- **Evidence:** pending P0b. Planned: J1 on S and P.
- **Decision:** pending P0b.
- **Consequences:** pending P0b. Affects §6.19 "Worktree isolation", R-AC-19 ("No branches") and R-AC-21 (native blocking [D]).
- **Status:** pending P0b.

### D22: Role tool needs
- **Context:** D22 removes capabilities natively before inspecting them, and R-AC-3 depends on it. Today argus, tech-stack-researcher and technical-writer list Bash (`.claude/agents/argus.md:4`, `tech-stack-researcher.md:4`, `technical-writer.md:4`). qa-tester has no `tools` list and only disallows Edit, Write and NotebookEdit (`.claude/agents/qa-tester.md:4`), so it inherits Bash. The roadmap's wording ("data comes from bundles or `exec.py ro`") doesn't hold, because `exec.py` is itself started through Bash (§6.1, C-1). P0 must choose per role among the options in P0 plan §3.6. The static scan is complete (§5); the dynamic evidence is pending.
- **Evidence:** pending P0b. Planned: the static scan in §5; Bash commands issued in the baseline transcripts, counted by class; one Bash-removed dry run per role.
- **Decision:** pending P0b. Provisional choices per role are in §5.6.
- **Consequences:** pending P0b. Affects R-AC-3, the roadmap §6.6 capability table, R-AC-45 contracts, `.mcp.json` (if option b) and the guard's prefix rule (if option c).
- **Status:** pending P0b.

### D25: Ruleset availability
- **Context:** R-AC-53's enforce mode needs an organization ruleset that requires the gate workflow at a pinned SHA [D; plan availability to verify], or a required check pinned to a dedicated GitHub App. A repository-level caller workflow is advisory only, because a PR can edit it [D]. Whether the organization's GitHub plan offers that ruleset is open (P0 plan §11, question 6).
- **Evidence:** pending P0b. Planned: the docs URL and a check by an organization owner.
- **Decision:** pending P0b.
- **Consequences:** pending P0b. Affects R-AC-53 enforce mode, the §6.19 CI cell, D14 and the P5 estimate (§14).
- **Status:** pending P0b. If P0b gets no answer, the status may stay `pending`, but the record must then name the exact organization setting the user must check.

---

## 5. Role-needs analysis (D22)

### 5.1 Method

- **Static scan (done, P0a):** each role's agent file, plus the skill and command text the role is told to follow. Every Bash use the text allows, requests or implies is listed with `file:line`, checked against the working tree on 2026-11-25.
- **Dynamic evidence (pending P0b):** Bash commands each role issued in the baseline transcripts, counted by class, and one representative brief per role run with Bash removed, in a throwaway copy of the agent (§5.7).

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

| Role | Bash today | Uses found | Provisional choice | P0b must confirm |
|---|---|---|---|---|
| argus | Listed (`argus.md:4`) | 8 (AR1–AR8) | (a); (b) only if the dry run needs follow-ups | The bundle answers the review without follow-up shell calls |
| qa-tester | Inherited (`qa-tester.md:4`) | 3 (QA1–QA3) | (a) plus an explicit `tools` list | Screenshots reach the run directory without the tester's Bash |
| tech-stack-researcher | Listed (`tech-stack-researcher.md:4`) | 2 (RS1–RS2) | (a) | The parent-supplied profile is enough |
| technical-writer | Listed (`technical-writer.md:4`) | 3 implied, 1 from a brief (TW2–TW4) | (a); profile doc-build through `exec.py run` | No doc task needs a shell beyond that |

### 5.7 Dynamic evidence (pending P0b)

**Bash commands in the baseline transcripts, by class** (classes from roadmap §6.7):

| Role | readonly-inspection | executor | profile-command | git-mutate | unsafe | indirect | complex | network | unknown |
|---|---|---|---|---|---|---|---|---|---|
| argus | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b |
| qa-tester | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b |
| tech-stack-researcher | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b |
| technical-writer | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b | pending P0b |

**Bash-removed dry runs** (throwaway agent copies):

| Role | Brief | Result | Capability it missed | Final choice |
|---|---|---|---|---|
| argus | pending P0b | pending P0b | pending P0b | pending P0b |
| qa-tester | pending P0b | pending P0b | pending P0b | pending P0b |
| tech-stack-researcher | pending P0b | pending P0b | pending P0b | pending P0b |
| technical-writer | pending P0b | pending P0b | pending P0b | pending P0b |

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

| # | Gap | Effect | Suggested action | Status after P0a |
|---|---|---|---|---|
| G-1 | Roadmap T12's residual names "bare-name shadowing in script installs (P0 probe)", but no §3.3 case tests it. A1 only checks the `agent_type` value | T12's residual stays [D] | Add a shadowing case in P0b (a project-level agent with a role's name, in a user-scope script install), or record it as [D] | Case N1 added: a project agent and a plugin agent with the same bare name, one run under the plugin install type. A project agent shadowing a **user-scope** agent isn't probed, because the runner never writes `~/.claude`; that part stays [D] |
| G-2 | No §3.3 case exercises `PreToolUse` on `mcp__.*`, WebFetch or WebSearch | R-AC-67's [C: MCP matcher] and TC-01, TC-02, TC-58 can't be confirmed | Add an MCP-matcher case, or leave the cells [D] | Cases M1 (`WebFetch`) and M2 (`mcp__.*`) added. WebSearch still has no case |
| G-3 | No case denies Edit or Write directly; H1 covers it only if its task edits | TC-05, TC-06 can't say *enforced* (R-AC-60) | Make H1's task include an edit, or add a case | Case L1 added (`Edit\|Write\|MultiEdit`, main thread and subagent). NotebookEdit isn't in its matcher |
| G-4 | C4 runs on P only, so per-agent hooks on script installs (TC-18) have no probe | TC-18 stays [D] | Run C4's setup on S too, as a control | C4 runs on S and P |
| G-5 | The §3.3 table has no install column, although it defines S, P and S+P | Applicability is inferred here (§2) | State the install per case in the case files | Each case file states its installs in `applies_to` |

---

## 7. Re-estimate inputs (pending P0b)

Current ranges are from roadmap §14. P0b fills the last two columns.

| Phase | Current range (days) | Uncertainty P0 addresses | P0 inputs | Resolved? | New range |
|---|---|---|---|---|---|
| P1 | 12–20 | Usage parsing for the run store; completion check | G1, H2, D1 | pending P0b | pending P0b |
| P2 | 12–22 | Bash removal per role; identity in parallel spawns; `onFailure` version spread; guard matcher coverage (Edit, WebFetch, MCP); bare-name resolution | D9 (E1–E5), D20 (A2), D22 (§5), A1, A3, B1, B2, C1–C4, F1–F5, H1, I1, L1, M1, M2, N1 | pending P0b | pending P0b |
| P3 | 8–14 | Baseline for TDD and tier promotion | Benchmark baseline (P0 plan AC-11) | pending P0b | pending P0b |
| P4 | 8–15 | Native isolation behavior; parallel attribution | D21 (J1), D20 (A2) | pending P0b | pending P0b |
| P5 | 8–14 | Ruleset availability on the organization's plan | D25 | pending P0b | pending P0b |
| P6 | 10–25 | Cursor and Codex enforcement | K1, K2 | pending P0b | pending P0b |
| **Total** | **62–118** | | | pending P0b | pending P0b |
| **MVH (P0–P2)** | **28–50** | | | pending P0b | pending P0b |
