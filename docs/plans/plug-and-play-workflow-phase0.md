# Phase 0 findings: platform checks

- **Plan:** [plug-and-play-workflow.md](plug-and-play-workflow.md) · **Date:** 2026-11-25 · **Branch:** `feat/plug-and-play`.
- **Rollback point:** tag `v1-ticketboat` at `58e9fcc` (local, not pushed).

**Sources:**
1. Claude Code docs at code.claude.com, read on 2026-11-25 by a research agent; the URLs are listed per finding.
2. Cursor docs and changelog, read the same day; see §B.
3. A read-only look at the legacy Cursor hub repo (public; last pushed 2026-08-25).

Items marked UNVERIFIED weren't confirmed by the docs. Phase 4 runs `claude plugin validate`, and the Phase C Cursor checks re-test them in a clean project.

---

## A. Claude Code plugin format

| # | Finding | Source |
|---|---|---|
| A1 | Manifest at `.claude-plugin/plugin.json`. Only `name` (kebab-case) is required. Optional keys include `version`, `description`, `author`, `repository`, `license`, `keywords`, `skills`, `commands`, `agents`, `hooks`, `mcpServers`, `outputStyles` and `userConfig`. | docs/en/plugins/manifest-reference |
| A2 | Components sit at the **plugin root**, not under `.claude/`: `commands/`, `agents/`, `skills/<name>/SKILL.md`, `hooks/hooks.json`, `.mcp.json`, `output-styles/`, and `bin/` (added to PATH; must be executable). | docs/en/plugins/components |
| A3 | Marketplace at `.claude-plugin/marketplace.json`, with `name`, `owner.name` and `plugins[]` (`name`, `source`). One repo can be both the marketplace and the plugin (`"source": "./"`). Files must stay inside the root, since `..` is rejected. | docs/en/plugins/create-marketplace, marketplace-reference |
| A4 | Install: `/plugin marketplace add owner/repo`, then `/plugin install <name>@<marketplace>`; also `claude plugin validate`, `claude plugin update` and `/reload-plugins`. Scopes are user (the default), project (written to `.claude/settings.json`) and local. | docs/en/plugins/loading |
| A5 | Teams enable it with `enabledPlugins` and `extraKnownMarketplaces` in `.claude/settings.json`. Repo-level marketplaces are honored only after the workspace trust dialog, and each person still installs it. | docs/en/settings-reference |
| A6 | **Plugins cannot ship always-on rules (`.claude/rules/*.md`) or `CLAUDE.md`.** A root `CLAUDE.md` isn't loaded, and validate warns. Path-scoped `paths:` rules have no documented equivalent (UNVERIFIED). The documented alternatives are skills, plus a SessionStart hook returning `hookSpecificOutput.additionalContext`. | docs/en/plugins/components, memory |
| A7 | Hooks live in `hooks/hooks.json` (top-level `hooks` key). Hook processes get `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` (persistent, `~/.claude/plugins/data/<id>/`), `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_OPTION_<KEY>`. SessionStart `additionalContext` works from plugin hooks. Hooks run in the current directory. | docs/en/hooks |
| A8 | Namespacing: commands are `/<plugin>:<file>`, skills `/<plugin>:<dir>`, agents `<plugin>:<name>`. Whether the Agent tool resolves bare names inside a plugin is UNVERIFIED, so assume the full name is needed. | docs/en/skills, components |
| A9 | `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` are substituted inside plugin command, skill and agent Markdown bodies, but are **not** set in the Bash tool's environment. Skills can use `${CLAUDE_SKILL_DIR}`. | docs/en/plugins/components, skills |
| A10 | Plugin-agent frontmatter supports `name`, `description`, `model`, `effort`, `maxTurns`, `tools`, `disallowedTools`, `skills`, `memory`, `background`, `isolation` and `color`. It **ignores** `mcpServers`, `hooks`, `permissionMode` and `initialPrompt`. MCP servers go in the plugin's `.mcp.json`; tools appear as `mcp__plugin_<plugin>_<server>__<tool>`. | docs/en/sub-agents, components |
| A11 | Installed plugins are copied to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, which changes on update. Never write state under the plugin root; use `${CLAUDE_PLUGIN_DATA}`. Guidance is to keep a SKILL.md under 500 lines (graphify's is 699), and skill descriptions are truncated at 1,536 characters in listings. | docs/en/plugins/loading, skills |

### A — Implications for the plan

1. **Layout (§3.10, Phase 4).** The plugin needs root-level `commands/ agents/ skills/ hooks/ scripts/` and `.mcp.json`, plus `.claude-plugin/{plugin.json, marketplace.json}`. The hub keeps its `.claude/` tree as the source for copy installs. Two options:
   - **(a)** make the repo root the plugin and turn `.claude/` into a build output for script installs;
   - **(b)** generate a `plugin/` folder from `.claude/` (like `cursor/`) and point the marketplace at `./plugin`.

   **Recommend (b):** one source, two generated outputs (`plugin/` and `cursor/`), which reuses the Phase C build pattern. Phase 4 adds `scripts/build-plugin.sh --check`.
2. **Always-on rules.** For plugin installs, the session contract and the short rule digests (core-standards, compounding cycle, token policy, stack knowledge) ship as SessionStart `additionalContext` plus a `workflow-contract` skill. Script installs keep copying `rules/` and `CLAUDE.md`. AC-12's smoke test must cover both.
3. **Agent names.** Every command that spawns agents (`/project-manager`, `/argus`, `/argus-scan`, `/manual-test`, `/apply-ticket`, `/trace-flow`) must resolve the role name per install type: bare in script installs, `<plugin>:<name>` in plugin installs. Proposed fix: commands say "spawn the `implementer` role", and the contract skill states the resolved names for the active install. Phase 4 must test an Agent-tool spawn inside a plugin.
4. **`qa-tester` Playwright.** Move the server into the plugin's `.mcp.json`, and drop `mcpServers` from the agent for plugin builds. Note that a plugin MCP server starts whenever the plugin is enabled, so consider making QA an optional companion plugin (decide in Phase 4).
5. **Paths.** Scripts must be called as `"${CLAUDE_PLUGIN_ROOT}/scripts/…"` (from hooks) or with that variable written into the Markdown body, since it isn't in the Bash environment. The `argus` and `daily-report` commands need this.
6. **State.** `audit.log` and any caches move to `${CLAUDE_PLUGIN_DATA}` in plugin installs. The repo's `.claude/hooks/audit.log` stays only for script installs.
7. **Size.** The vendored graphify skill (699 lines) exceeds the 500-line guidance. Ship it as optional, or split it.

---

## B. Cursor capabilities

Source: cursor.com/docs and the changelog, checked on 2026-11-25. The latest CLI build is v2026.11.17, and the latest IDE changelog entry is 2026-11-06. Pages are listed per row.

| # | Finding | Source |
|---|---|---|
| B1 | **Rules:**<br>• must be `.mdc` under `.cursor/rules/`; plain `.md` there is ignored;<br>• frontmatter: `description`, `globs`, `alwaysApply`;<br>• types: Always (`alwaysApply: true`), Auto-attached (`globs`), Agent-requested (`description` only), Manual (`@rule`);<br>• nested folders are supported, and `.cursor/rules` folders in subdirectories are discovered;<br>• guidance is to keep rules under 500 lines;<br>• precedence: Team, then Project, then User. User rules are settings, not files. | docs/context/rules |
| B2 | `AGENTS.md` (root or nested, no frontmatter) is supported. How it combines with `.mdc` is UNVERIFIED. Cursor reading `CLAUDE.md` or `.claude/rules/` is UNVERIFIED (forum reports say it doesn't read `.claude/rules/`). | docs/context/rules |
| B3 | **Custom commands are legacy.** Since 2.4 (2026-01-22), `/migrate-to-skills` converts them into skills with `disable-model-invocation: true`. `$ARGUMENTS` substitution is not documented for commands or skills (UNVERIFIED). | changelog 1.6, 2.4; docs/context/skills |
| B4 | **Skills:** `.cursor/skills/<name>/SKILL.md`. Frontmatter `name` (must match the folder), `description`, `paths`, `disable-model-invocation`, `user-invocable`, `icon`, `color`, `metadata`. **Cursor also loads `.claude/skills`, `.agents/skills` and `.codex/skills`.** Skills can bundle `scripts/`. | docs/context/skills |
| B5 | **Subagents:** `.cursor/agents/` or `~/.cursor/agents/`. Frontmatter `name`, `description`, `model`, `readonly`, `is_background`. There is **no `tools` field**; subagents inherit the parent's tools. **Cursor also loads `.claude/agents/`**, and `.cursor/` wins on a name clash. Invoked by automatic delegation, `/name`, or naming them in the prompt. Nesting is one level (2.5). | docs/context/subagents |
| B6 | **Hooks:**<br>• files: `.cursor/hooks.json` (project), `~/.cursor/hooks.json` (user), with schema `{"version":1,"hooks":{...}}`;<br>• events include `sessionStart`, `sessionEnd`, `preToolUse`, `postToolUse`, `subagentStart`/`subagentStop`, `beforeShellExecution`/`afterShellExecution`, `afterFileEdit`, `beforeSubmitPrompt`, `stop` and `workspaceOpen`;<br>• `sessionStart` returns `additional_context` (snake_case), plus `env`. **It is fire-and-forget: the agent doesn't wait for it.** | docs/agent/hooks |
| B7 | **Third-party import, on by default:**<br>• Cursor loads hooks from `.claude/settings*.json` and `~/.claude/settings.json` (Bash→Shell, Edit→Write; Glob, Notification and PermissionRequest unsupported);<br>• the same setting loads `.claude/agents` and `.claude/skills`;<br>• whether Claude-format hook *output* (`hookSpecificOutput.additionalContext`) is translated is UNVERIFIED. | docs/reference/third-party-hooks |
| B8 | **MCP:** `.cursor/mcp.json` (project) and `~/.cursor/mcp.json` (global), shaped `{"mcpServers": {...}}`, with `${env:…}` and `${workspaceFolder}` interpolation. | docs/context/mcp |
| B9 | **Scripts and permissions:** the agent runs shell commands. Run modes are Auto-review (the default since 3.6), Allowlist and Run Everything. Allow-lists live in `~/.cursor/permissions.json` and `<repo>/.cursor/permissions.json`. | docs/agent/security/run-modes, reference/permissions |
| B10 | **Modes:** Agent, Ask, Plan and Debug are built in. Custom modes were removed in 2.1 (2025-11-21); the replacement is a skill used as a sticky mode. | changelog 2.1; docs/agent/modes |

### B0. Evidence from the legacy Cursor hub (as of 2026-08-25)

| Construct | What the old hub used | Meaning for Phase C |
|---|---|---|
| Rules | `.cursor/rules/*.mdc` with frontmatter `description`, `globs` (a string such as `"**/*.py"`) and `alwaysApply: true/false` | The always-on and auto-attach mappings in §3.11 hold |
| Agents | `.cursor/agents/<name>.md` with frontmatter `name`, `description` and `category` | Cursor reads file-defined agents, so roles can map to real agents, not just rules (confirm the spawn semantics in the docs) |
| Skills | `.cursor/skills/<name>/SKILL.md`, the same layout as Claude Code | Skills can be copied as they are; no conversion to `.mdc` needed (confirm) |
| Commands | `.cursor/commands/<group>/<name>.md` with frontmatter `description`; subfolders used | Commands map one to one; check `$ARGUMENTS` support |
| Hooks | `.cursor/hooks.json` `{"version": 1, "hooks": {"sessionStart", "sessionEnd", "stop", "beforeShellExecution", "afterShellExecution"}}` | **There is a `sessionStart` event**, so the auto-scan can run as a hook in Cursor too |
| Hook output | `sessionStart` prints `{"continue": true, "additional_context": "…"}` | Context injection is possible; the field is `additional_context` (snake_case), unlike Claude's `hookSpecificOutput.additionalContext` |
| Settings | `.cursor/settings.json` → `{"plugins": {"linear": {"enabled": true}}}` | Cursor has plugins, including Linear; the ticket adapter can use them |
| Other tools | The repo also carries `.codex/` (OpenAI Codex: agents, commands, rules, skills, hooks), `.agents/skills/` and an `AGENTS.md` | Out of scope per D3. Possible future D7: a Codex output from the same sources |

---

### B — Implications for the plan

1. **Phase C becomes a thin layer, not a parallel tree.** Because Cursor already imports `.claude/agents`, `.claude/skills` and `.claude/settings*.json` hooks (B4, B5, B7), a full `.cursor/` copy would load items twice. The generator emits only what Cursor can't read from `.claude/`:
   - `.cursor/rules/*.mdc` for always-on rules and stack packs (B1, B2);
   - commands converted to Cursor skills (B3);
   - agent overrides that need Cursor-only fields (B5);
   - `.cursor/mcp.json` (B8).
2. **Commands become Cursor skills.** Each `.claude/commands/<name>.md` becomes `.cursor/skills/<name>/SKILL.md` with `disable-model-invocation: true`. Because `$ARGUMENTS` is unverified, the body says "use the text typed after the command", and agent spawns become "delegate to the `<name>` subagent".
3. **Read-only roles in Cursor.** Cursor ignores `tools`, so `.cursor/agents/{argus,qa-tester}.md` overrides add `readonly: true` (and win the name clash). The other agents come in through the import.
4. **Hooks: one script, two output formats.** `session-init.sh` reads the event name on stdin. `SessionStart` (Claude) prints `hookSpecificOutput.additionalContext`; `sessionStart` (Cursor) prints `{"continue": true, "additional_context": …}`.
   - **Default:** rely on Cursor's import of the Claude hooks.
   - **For teams with the import off:** `install.sh --cursor` emits `.cursor/hooks.json`.
   - **Verify** the import behavior first thing in Phase C.
5. **Fire-and-forget `sessionStart`.** The Cursor agent may not see the profile summary on its first turn (B6). The always-apply rule `workflow-contract.mdc` therefore says "read `.workflow/profile.json` (or run `detect-stack.py --stdout`) before planning or coding".
6. **Plugin installs aren't visible to Cursor.** Cursor imports `.claude/` folders, not the Claude plugin cache. Cursor users install with `install.sh --project <repo> --cursor` (or `--user`), which copies the source tree plus the thin `.cursor/` layer.
7. **Same rule-size limit.** Keep rules and skills under 500 lines in both tools, so `graphify/SKILL.md` must be split or made optional.
8. **Codex (observation).** Cursor also reads `.codex/skills` and `.agents/skills`, and the legacy hub targeted Codex too. Producing a Codex output from the same sources would be cheap later. Recorded as possible decision D7, out of scope now.

---

## C. Changes to the plan

These are applied to [plug-and-play-workflow.md](plug-and-play-workflow.md) in the same change as this file.

| # | Change | Plan sections |
|---|---|---|
| C1 | **Plugin output is generated:** `scripts/build-plugin.sh` renders `plugin/` from `.claude/`, with root-level `commands/ agents/ skills/ hooks/hooks.json scripts/ .mcp.json` and `.claude-plugin/plugin.json`. The repo-root `.claude-plugin/marketplace.json` points at `./plugin`. `--check` runs in CI, and `claude plugin validate plugin` must pass. | §3.10, Phase 4, §6, AC-12 |
| C2 | **Always-on content for plugin installs:** a `workflow-contract` skill plus SessionStart `additionalContext`, because plugins can't ship rules or `CLAUDE.md`. Script installs keep `rules/` and `CLAUDE.md`. | §3.10, Phase 4 |
| C3 | **Role names per install type:** commands spawn roles by name, and the contract (skill and SessionStart text) maps each role to its resolved agent name: bare for script installs, `<plugin>:<name>` for plugin installs. Phase 4 tests one Agent-tool spawn in a plugin. | §3.6, Phase 4 |
| C4 | **Playwright moves:** it leaves `qa-tester` frontmatter and goes into `plugin/.mcp.json` and `.cursor/mcp.json`. Making QA an optional companion plugin, so Playwright doesn't start for every user, is decided in Phase 4. | §3.6, §3.10, §3.11 |
| C5 | **Paths and state:** plugin commands and hooks reference `${CLAUDE_PLUGIN_ROOT}` (substituted in Markdown bodies, and set in hook env), and audit and cache state go to `${CLAUDE_PLUGIN_DATA}`. | §3.10 |
| C6 | **Cursor layer is thin** (see B-implications 1–6). §3.11 is rewritten with the verified mapping, and Phase C shrinks to 1–1½ sessions. | §3.11, Phase C, AC-15, header |
| C7 | **Dual-format hook script** (`session-init.sh` detects Claude vs Cursor from stdin). | §3.4, Phase 1 |
| C8 | **graphify skill:** split, or ship it only in the optional graphify add-on (it is over the 500-line guidance in both tools). | Phase 3 |
| C9 | **D7 (deferred): Codex output.** | §11 |
