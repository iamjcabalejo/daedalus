# Plan: plug-and-play workflow with automatic stack detection

| Field | Value |
|---|---|
| **Type** | Refactor / Infrastructure (workflow hub) |
| **Complexity** | Very Large. It touches every layer of the hub: 15 commands, 8 agents, 11 rules, 22 skills, hooks, packaging, plus a new detector and profile format, and a generated Cursor tree kept in sync (D3). |
| **Estimated effort** | 6–8 focused sessions remaining. Phase 0: **done** (see [phase0 findings](plug-and-play-workflow-phase0.md)) · Phase 1: **done** · Phase 2: 1 · Phase 3: 2–3 · Phase 4: 1 · Phase C (Cursor thin layer, alongside 1–4): 1–1½ |
| **Priority** | TBD by owner |
| **Scope / metadata** | `Security: critical` (the hub is public; the detector must never execute project code or leak overlay content) |
| **Branch** | `feat/plug-and-play` cut from `feat/nrd-review` |
| **Graph gate** | Skipped. This is workflow-hub work (`.claude/rules/graphify.md` → "Workflow hub: skip graph gate"). |

---

## 1. Feature overview

**Problem.** The hub is a Ticketboat-specific workflow:
- The agents assume FastAPI/Pydantic, C#/ASP.NET, and React/Ant Design/Jotai.
- The ticket commands assume Linear and Teams.
- The always-on rules state "Ticketboat dual stack".
- Every phase assumes graphify.

Installing it in any other project gives wrong instructions, and needs manual edits even inside Ticketboat for repos outside that stack (Go, Node, dbt, Terraform).

**Audience.** Developers who install the workflow into any repo or workspace, Ticketboat included.

**Key functionality.**
1. **Auto-scan on install and on session start.** A deterministic detector writes a **project profile**: roots, languages, frameworks, the matching stack packs, the exact install/test/lint/typecheck/build/dev commands, UI presence and dev URL, data and migration tools, IaC/CI, code host, ticket system, and the gaps it couldn't fill.
2. **One shared stack-knowledge layer.** Argus's stack packs grow **Build**, **Review** and **Test** sections, so the same pack guides coding, review and testing. Unknown stacks fall back to `_generic` plus the universal failure modes.
3. **Role-based agents.** `implementer` (per layer), `test-runner`, `argus` (review) and `qa-tester` (only when there's a UI) replace the stack-named agents.
4. **Commands that read the profile:** planning, orchestration, scaffolding, test generation, tracing and QA.
5. **Adapters** for tickets (Linear / Jira / GitHub Issues / none) and chat (Teams / Slack / none).
6. **A private overlay.** Ticketboat specifics move into an overlay in a gitignored `overlays/` folder of this repo (D2), installed only where wanted. The public hub becomes generic.
7. **Plug-and-play install** as a Claude Code plugin, with an `install.sh` fallback (user-level or per project).
8. **Cursor parity (D3).**
   - A `.cursor/` tree is generated from the same sources by a build script, and CI checks that it hasn't drifted.
   - The profile and config live in a tool-neutral `.workflow/` folder, so Claude Code and Cursor users of one repo share them.

---

## 2. Acceptance criteria

- **AC-1 — Auto-scan on first session.** Given a repo with no `.workflow/profile.json`:
  - When a Claude Code session starts, the SessionStart hook runs the detector, which finishes within 5s.
  - It writes a profile that validates against `profile.schema.json`.
  - It injects a summary of 12 lines or fewer: roots, packs, test/lint/build/dev commands, UI dev URL, ticket system, gaps, and "run `/setup` to confirm".
  - A detector error or timeout never blocks the session. The hook prints a one-line notice instead.
- **AC-2 — Detection accuracy.** On every repo in the validation matrix (§8):
  - the detected roots, `packs`, `layer`, `ui.present` and `commands.test/lint/build/dev` match the expected fixture exactly (`null` when the repo has no such command);
  - missing commands go in `gaps`: test for `ui`, `api`, `worker`, `cli` and standalone `lib` roots; lint for `ui`, `api`, `worker` and `cli` roots; dev for UI roots;
  - a command whose own text, or whose script body or recipe, deploys, migrates, publishes, releases, destroys, applies or drops is marked `unsafe` (synthetic matrix rows).

  *(Reworded in rework-1 to match what is verified.)*
- **AC-3 — Unknown stacks degrade cleanly.** For a stack with no pack (for example Rust), the detector exits 0 with `packs: []`, records the language, and lists `gaps`. Commands then run on `_generic` plus `failure-modes.md` and say which files are uncovered.
- **AC-4 — Refresh only when needed.**
  - Editing a manifest (`package.json`, `pyproject.toml`, `go.mod`, `*.csproj`, …) triggers re-detection at the next session start.
  - With unchanged manifests the hook only compares hashes and finishes in under 1s.
- **AC-5 — `/setup` is interactive and contained.**
  - It shows the detected profile and fills gaps from README, CONTRIBUTING, Makefile and CI config, citing the file for each filled value.
  - It asks the user to confirm each command marked `inferred`.
  - It writes only `.workflow/profile.json` and `.workflow/config.yml` inside the target repo.
  - `--print` writes nothing.
- **AC-6 — Detection is safe.** The detector never executes project code: no `npm`, `pip`, `make`, scripts or test runs. It only reads files and runs `git` read commands. No network calls.
- **AC-7 — Shared packs.** Every pack under `.claude/skills/stacks/`:
  - has `detect` frontmatter and `## Build`, `## Review`, `## Test` and `## Commands` sections;
  - has a `_generic.md` fallback alongside it.

  Argus loads packs from this shared path, and an Argus `--local` review of an unchanged sample still passes Phase C validation.
- **AC-8 — Profile-driven orchestration.** On a non-Ticketboat sample repo (validation matrix row G or H), `/project-manager <plan>` runs, in order:
  1. `implementer` once per affected layer, in dependency order;
  2. `test-runner`, running only confirmed profile commands;
  3. `argus --local` on the diff;
  4. `qa-tester` only when `ui.present` is true.

  No step mentions FastAPI, React, Ant Design, Linear or Teams unless the profile or the overlay declares them.
- **AC-9 — Layered plans.** `/feature-plan` and `/apply-ticket` write task blocks per detected layer (for example "Layer: api (python)", "Layer: ui (web-frontend)") instead of the fixed Backend / C# Backend / Frontend sections. The plan still contains every section `/project-manager` requires.
- **AC-10 — Ticket and chat adapters.**
  - **Tickets:** `/create-ticket`, `/refine-spec`, `/apply-ticket` and `/daily-report` work with `tickets.system` set to `linear` (MCP), `github` (`gh`) or `none`. With `jira` and no Jira MCP connected, they print a clear message and continue as `none`.
  - **Chat:** `/daily-report` works with `chat` set to `teams`, `slack` or `none`.
- **AC-11 — The public hub is generic.**
  - `scripts/check-generic.sh` greps the hub (excluding `docs/research/`) for org, product and partner terms and returns 0 hits. It also checks that `git ls-files overlays/` lists only `overlays/_template/`. It runs in CI.
  - Installing the private `ticketboat` overlay restores today's Ticketboat behavior: Linear keys, domain pack, context rule, QA sign-in steps, daily-report sources. To verify, run `/feature-plan` and `/argus --local` in one Ticketboat repo and compare with the current outputs.
- **AC-12 — Install and uninstall.** Both install paths pass the smoke test (`/setup --print`, `/argus --local` on a sample repo):
  - **(a)** plugin install from this repo's marketplace;
  - **(b)** `install.sh --user | --project <path> [--overlay <dir>] [--cursor] [--dry-run]`.

  `install.sh --uninstall` removes exactly the files it installed, using its manifest.

  Also:
  - `claude plugin validate plugin` passes;
  - `build-plugin.sh --check` is clean;
  - in a plugin install, one role spawned through the Agent tool resolves correctly (`<plugin>:<name>`), and nothing writes under `${CLAUDE_PLUGIN_ROOT}`.
- **AC-13 — graphify is optional.** With no `graphify-out/`:
  - no command tells the user to build a graph;
  - exploration uses plain search;
  - graph steps run only when the profile shows `graph.graphify: true` or `.workflow/config.yml` sets `graph: graphify`.
- **AC-14 — Docs.**
  - The README covers install, first run, the command table, roles, profile, packs, overlays, adding a stack, writing an overlay, and migrating from the Ticketboat install (old command and agent names → new ones).
  - `CLAUDE.md` is generic.
  - A Cursor section covers install, the commands available in Cursor, and what differs from Claude Code.
- **AC-15 — Cursor parity (D3).**
  - `scripts/build-cursor.sh` regenerates `cursor/.cursor/` deterministically from `.claude/` plus `cursor-overrides/`. `--check` fails CI when the generated tree is out of date.
  - In Cursor, on validation rows B and G:
    - `/setup` writes the shared `.workflow/profile.json`;
    - editing a file auto-attaches the matching stack-pack rule;
    - `/feature-plan`, `/argus --local`, `/scaffold` and `/test-gen` work;
    - `/project-manager` runs the roles in sequence in one agent, or through Cursor subagents if Phase 0 finds them.
  - Both tools read the same `.workflow/` files, with no tool-specific copies of the profile.
  - No skill or agent loads twice in Cursor: skills and agents come from the `.claude/` import, and only the `argus` and `qa-tester` overrides exist under `.cursor/agents/`.

---

## 3. Technical design

### 3.1 Architecture

```
SessionStart hook ──► detect-stack.py ──► .workflow/profile.json   (facts, regenerated)
        │                                   ▲
        │                       /setup ─────┘ (enrich + confirm)    .workflow/config.yml (choices, human-edited)
        ▼
 additionalContext: contract + profile summary
        │
Commands (/feature-plan, /project-manager, /scaffold, /test-gen, /argus, /manual-test, /trace-flow …)
        │  read profile + .workflow/config.yml (+ overlay)
        ▼
Roles: implementer(layer) → test-runner → argus → qa-tester(if UI)
        │  load packs from skills/stacks/<pack>.md  (Build | Review | Test | Commands)
        ▼
Fallback: skills/stacks/_generic.md + skills/stacks/failure-modes.md
```

**Precedence**, from lowest to highest: detected profile → `~/.workflow/config.yml` (personal) → `<workspace>/.workflow/config.yml` → `<repo>/.workflow/config.yml` → command arguments. An overlay supplies defaults at the personal level.

### 3.2 Project profile: `.workflow/profile.json` (schema v1)

```json
{
  "schema": 1,
  "generator": "detect-stack@1",
  "generated_at": "2026-11-25T10:00:00Z",
  "manifest_hash": "sha256:…",
  "roots": [
    {
      "path": ".",
      "name": "web",
      "layer": "ui",
      "languages": [{"name": "typescript", "files": 412}],
      "frameworks": ["react", "vite", "tanstack-query"],
      "packs": ["web-frontend"],
      "package_manager": "npm",
      "commands": {
        "install": {"cmd": "npm ci", "source": "package-lock.json", "confidence": "derived"},
        "test":    {"cmd": "npm test", "source": "package.json#scripts.test", "confidence": "script"},
        "lint":    {"cmd": "npm run lint", "source": "package.json#scripts.lint", "confidence": "script"},
        "typecheck": {"cmd": "npx tsc --noEmit", "source": "tsconfig.json", "confidence": "inferred"},
        "build":   {"cmd": "npm run build", "source": "package.json#scripts.build", "confidence": "script"},
        "dev":     {"cmd": "npm run dev", "source": "package.json#scripts.dev", "confidence": "script"}
      },
      "test": {"frameworks": ["vitest"], "patterns": ["**/*.test.ts", "**/*.test.tsx"]},
      "ui": {"present": true, "dev_url": "http://localhost:5173", "router": "react-router"},
      "data": {"databases": [], "migrations": null},
      "infra": {"iac": [], "ci": ["github-actions"], "containers": ["docker"]}
    }
  ],
  "integrations": {
    "code_host": {"kind": "github", "repo": "owner/name"},
    "tickets": {"system": "linear", "key": "[A-Z][A-Z0-9]+-\\d+", "evidence": "18 of last 200 commit subjects"},
    "graph": {"graphify": false}
  },
  "gaps": ["root '.': no lint command found"],
  "confirmed": false
}
```

- **`layer`** ∈ `ui | api | worker | data | infra | lib | cli`. It is derived from packs and frameworks (for example, `web-frontend` → `ui`; `python` + fastapi → `api`; `serverless-queues` → `worker`; `sql-migrations`/`data-warehouse` → `data`; `iac`/`ci-cd` → `infra`). It drives task blocks and implementer order: **data → api/worker → ui → infra**.
- **Command `confidence`:**
  - `script` means taken from a declared script or target;
  - `derived` means it follows from a lockfile or tool convention;
  - `inferred` means a heuristic.

  `test-runner` auto-runs only `script` and `derived` commands, plus `inferred` ones the user has confirmed in `/setup` (stored with `confirmed: true` per command).
- **Monorepos** produce one root per workspace or package (npm/pnpm/yarn workspaces, `go.work`, Cargo/Gradle multi-projects, `apps/*`, `services/*`, or sibling product folders when run from a workspace root).

### 3.3 Detector: `.claude/scripts/detect-stack.py`

- **Runtime:** `python3` 3.8 or later, standard library only (no `tomllib`; a regex or mini-parser handles `pyproject.toml`). The current hooks already rely on `python3`.
- **Modes:**
  - default writes the profile;
  - `--stdout` prints it and writes nothing (used for validation and by `/setup --print`);
  - `--check` prints only the manifest hash;
  - `--root <dir>` and `--max-depth N` (default 4).
- **Discovery:** walk to depth 4, skipping `node_modules`, `.venv`, `venv`, `vendor`, `dist`, `build`, `target`, `.git` and the `.gitignore` patterns at the top level. Collect manifests: `package.json`, lockfiles, `pyproject.toml`, `requirements*.txt`, `setup.cfg`, `go.mod`, `go.work`, `*.csproj`, `*.sln`, `Cargo.toml`, `Gemfile`, `pom.xml`, `build.gradle*`, `composer.json`, `mix.exs`, `Package.swift`, `dbt_project.yml`, `*.tf`, `serverless.yml`, `template.yaml`, `Dockerfile*`, `.github/workflows/*`, `Makefile`, `Taskfile.yml`, `justfile`, `tox.ini`, `pytest.ini`, `jest.config.*`, `vitest.config.*`, `playwright.config.*`, `vite.config.*`, `next.config.*` and migration folders.
- **Packs:** evaluate every `skills/stacks/*.md` frontmatter (`detect.files`, `detect.weak`, `detect.signals`). Signals are matched against manifest contents only, never against source files, which keeps detection fast.
- **Commands:** in priority order:
  1. declared scripts (`package.json#scripts`, `[tool.poetry.scripts]`, `[project.scripts]`, Makefile, Taskfile and justfile targets named `test|lint|typecheck|build|dev|start|format`);
  2. tool conventions (`pytest`, `go test ./...`, `dotnet test`, `cargo test`, `bundle exec rspec`, `mvn test`, `./gradlew test`);
  3. CI workflow `run:` steps.
- **UI:**
  - a UI pack, or a framework among react, vue, svelte, angular or next;
  - dev URL from `vite.config` `server.port`, Next defaults, `--port` flags in scripts, or `.env*` `PORT`;
  - router from the dependencies.
- **Tickets:** key regexes counted over `git log --format=%s -200` and branch names, `.github/ISSUE_TEMPLATE`, and the `.jira`/`.linear` config files. No MCP calls.
- **Safety:** read-only. No subprocesses except `git -C <root> log|remote|branch|rev-parse`. Never `eval`, import or execute project files. A hard 5s budget; on timeout, emit a partial profile with a `gaps` note.

### 3.4 SessionStart hook: `.claude/hooks/session-init.sh`

1. Compute the manifest hash, using the same file list as the detector (`detect-stack.py --check`, which caches the list).
2. If there's no profile, or the hash differs, run `detect-stack.py` with `timeout 5`, ignoring its exit code.
3. Emit the context:
   - the generic session contract (what the Ticketboat sentence says today, minus Ticketboat), including the resolved role names for this install type (C3);
   - a summary of the profile, 12 lines or fewer;
   - overlay context lines when an overlay is installed.
4. **Dual output format (C7).** Read the event name on stdin:
   - `SessionStart` (Claude Code) → print `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":…}}`;
   - `sessionStart` (Cursor) → print `{"continue":true,"additional_context":…}`.

   Cursor doesn't wait for this hook (Phase 0 B6), so `workflow-contract.mdc` also tells the agent to read the profile.
5. Always `exit 0`. In plugin installs, the script is referenced as `"${CLAUDE_PLUGIN_ROOT}/scripts/…"` and writes no state into the plugin root.

### 3.5 Shared stack knowledge: `.claude/skills/stacks/`

- **Moves:** `skills/argus/stacks/*` → `skills/stacks/*`, and `skills/argus/failure-modes.md` → `skills/stacks/failure-modes.md`.
- **New:** `_generic.md`, holding cross-language Build/Test defaults and pointers to `failure-modes.md`.
- **Each pack gets this section layout:**
  - `## Build`: conventions and idioms for implementers. The content comes from the stack rules and skillsets being retired (§5).
  - `## Review`: today's "How the failure modes show up" plus "Stack-only checks".
  - `## Test`: frameworks, layout, fixtures, what to mock, the regression-test pattern. Content comes from `api-testing`, `react-frontend` testing notes and similar.
  - `## Commands`: how to locate or confirm commands for this stack, a hint list for the detector and `/setup`.
  - `## Entry points (scan mode)`: unchanged.
- **New `typescript` pack?** No. `web-frontend` and `node-js` cover TypeScript. Shared TS rules (`typescript.md`) go into both packs' Build sections.

### 3.6 Roles (agents)

| Agent | Status | Responsibility | Loads |
|---|---|---|---|
| `implementer` | new; replaces `backend-architect` and `frontend-architect` | Implements one layer's tasks from the plan | profile, Build + Test of that layer's packs, `failure-modes.md`, overlay rules |
| `test-runner` | new | Runs confirmed test/lint/typecheck/build commands for the affected roots; writes or updates tests from the pack Test sections; reports pass/fail with output excerpts | profile, Test sections |
| `argus` | updated | Reviews the diff (`--local`) or the PR; reads packs from `skills/stacks/`; uses `profile.packs` when present | as now, plus the profile |
| `qa-tester` | updated | Browser QA only when `ui.present`. Base URL and dev command come from the profile; auth steps come from `.workflow/config.yml` or the overlay. Playwright MCP is declared in `.mcp.json` / `.cursor/mcp.json` for plugin and Cursor installs (C4); `mcpServers` frontmatter remains only for script installs | profile, `manual-qa` |
| `tech-stack-researcher` | updated | Compares options against the detected profile instead of a fixed stack | profile |
| `technical-writer` | minor | Unchanged, apart from wording | — |
| `backend-reviewer`, `frontend-reviewer` | removed | Replaced by `argus` (severity mapping critical/important → Critical, consider → Suggestion already exists). Accessibility checks move into `web-frontend` Review. | — |

### 3.7 Commands

| Command | Change |
|---|---|
| `/setup` | **New.** Run the detector, enrich gaps from docs, confirm inferred commands, write the profile and `.workflow/config.yml`. Flags: `--refresh`, `--print`. |
| `/feature-plan`, `/apply-ticket` | Task blocks per detected layer. Technical design references the packs, not FastAPI/React. |
| `/project-manager` | Orchestration from profile layers: implementer per layer → test-runner → argus → qa-tester (if UI) → rework loop. |
| `/scaffold <kind> <name>` | **New**, replaces `/api-new`. The kind is endpoint, component, job, migration or model, and the framework comes from the packs. |
| `/test-gen <target>` | **New**, replaces `/api-test`. Uses the pack Test section and the detected test framework. |
| `/create-ticket`, `/refine-spec`, `/daily-report` | Go through the `ticket-adapters` skill (tickets: linear / jira / github / none; chat: teams / slack / none). |
| `/manual-test` | Base URL and dev command from the profile; skips with N/A when there's no UI. |
| `/trace-flow` | Generic layers (entry → handler → service → data → render) mapped through the profile. |
| `/code-cleanup`, `/code-optimize`, `/new-task` | Language list from the profile. |
| `/argus`, `/argus-scan` | Merge `.workflow/config.yml` (Argus keys under `review:`) and the legacy `.argus.yml` key by key, nearest first; load the profile's packs plus any pack matching the diff. |

### 3.8 Configuration: `.workflow/config.yml` (replaces `.argus.yml`; keeps reading it for backward compatibility)

```yaml
overlay: none                 # name of an installed overlay, e.g. ticketboat
stacks: auto                  # or explicit pack list; extra_stacks: []
tickets: {system: auto, key: '[A-Z][A-Z0-9]+-\d+'}
chat: none                    # teams | slack | none
graph: auto                   # auto | graphify | none
ignore: ["**/*.lock", "**/vendor/**", "**/dist/**"]
house_rules: []
commands: {}                  # per-root overrides, e.g. {".": {test: "make test"}}
qa: {auth: none, base_url: null}   # or steps from overlay
review: {header: "Argus review", max_findings: 0, severity: {overrides: [], critical_triggers: []}}
```

### 3.9 Overlays (private)

An overlay is a folder with `overlay.yml`, plus any of: `rules/*.md`, `skills/<name>/…` (for example, a domain pack at `skills/argus/domains/<name>.md`), `config.yml` defaults (merged at the personal level), `hooks/context.txt` (extra SessionStart lines), `qa/auth.md` and `daily-report/sources.md`. `install.sh --overlay <dir>` copies it in on top of the hub. Plugin installs read `~/.claude/overlays/<name>/`.

The `ticketboat` overlay contains:
- today's Ticketboat context (the dual stack, AWS Secrets Manager/SSM conventions, UTC);
- the Linear team keys;
- the domain pack;
- the QA sign-in steps;
- the daily-report sources (Linear plus Teams);
- the graphify multi-root note.

**Location (D2):** `overlays/ticketboat/` in this repo, gitignored with `overlays/*` and `!overlays/_template/`. Only `overlays/_template/` is tracked.
- **Not backed up.** The folder isn't backed up or shared by git. Keep a private copy (for example, an encrypted archive in team storage) and document the restore steps in `overlays/_template/README.md`.
- **Install:** `install.sh --overlay overlays/ticketboat`.

### 3.10 Packaging

The format is verified in Phase 0 §A.

- **Plugin (generated, C1):** `scripts/build-plugin.sh` renders `plugin/` from `.claude/`, with:
  - `plugin/.claude-plugin/plugin.json` (only `name` is required; we also set `version`, `description`, `repository`, `license`);
  - root-level `commands/`, `agents/`, `skills/`, `scripts/` (executable), `hooks/hooks.json` and `.mcp.json`.

  The repo-root `.claude-plugin/marketplace.json` (`name`, `owner.name`, `plugins: [{name, source: "./plugin"}]`) makes this repo its own marketplace.
  - **Install:** `/plugin marketplace add <owner>/<repo>`, then `/plugin install <name>@<marketplace>`.
  - **CI:** `build-plugin.sh --check` and `claude plugin validate plugin`.
- **Always-on content in plugins (C2):** plugins can't ship `rules/` or `CLAUDE.md`. So the contract and the rule digests ship as:
  - a `workflow-contract` skill;
  - the SessionStart `additionalContext`.
- **Names (C3):** plugin agents and commands are `<plugin>:<name>`, so commands refer to roles, and the contract resolves them per install type.
- **MCP (C4):** Playwright for `qa-tester` goes in `plugin/.mcp.json`, because plugin agents ignore `mcpServers`. Phase 4 decides whether QA ships as an optional companion plugin, so the server doesn't start for every user.
- **Paths and state (C5):** commands and skills use `${CLAUDE_PLUGIN_ROOT}` in their Markdown bodies; it isn't in the Bash environment. Hooks get it in their environment. Audit logs and caches go to `${CLAUDE_PLUGIN_DATA}`, never to the plugin root (which changes on update).
- **Script:** `install.sh`
  - copies `commands/ agents/ skills/ scripts/ hooks/ rules/` into `~/.claude` (`--user`) or `<path>/.claude` (`--project`);
  - merges hook registration into `settings.json` without overwriting user hooks;
  - writes `.workflow-install-manifest` for `--uninstall`;
  - defaults to `--dry-run` output plus a confirmation prompt;
  - with `--cursor`, also copies the generated thin layer `cursor/.cursor/` into `<path>/.cursor/` (or `~/.cursor/` with `--user`). Cursor imports `.claude/` folders, not the Claude plugin cache, so Cursor users install with the script.

### 3.11 Cursor parity (D3), verified in Phase 0 §B

**Thin layer, not a parallel tree (C6).** By default, Cursor already imports `.claude/agents/`, `.claude/skills/` and the hooks in `.claude/settings*.json` (Phase 0 B4, B5, B7). A full `.cursor/` copy would load items twice. So `scripts/build-cursor.sh` renders only what Cursor can't read from `.claude/` into `cursor/.cursor/`, which is committed. Cursor-only snippets live in `cursor-overrides/`, and CI runs `--check`.

| Claude Code source | Cursor | How |
|---|---|---|
| Always-on rules (`rules/*.md`, `CLAUDE.md` contract) | `.cursor/rules/workflow/<name>.mdc`, `alwaysApply: true` | **Generated.** Cursor doesn't read `.claude/rules` (B2) |
| Path-scoped rules | `.mdc` with `globs` | Generated. After Phase 2 only `stack-knowledge` remains |
| Stack packs `skills/stacks/<pack>.md` | `.cursor/rules/stacks/<pack>.mdc`, `globs` = the pack's `detect.files` (auto-attached) | Generated. Weak globs and signals are noted in the body. Rules stay under 500 lines |
| Skills `skills/<name>/SKILL.md` | Imported from `.claude/skills` | **Not generated** (B4). Skills over 500 lines are split (C8) |
| Agents (roles) | Imported from `.claude/agents` | Not generated, except overrides `.cursor/agents/{argus,qa-tester}.md` with `readonly: true` (Cursor ignores `tools`; `.cursor/` wins on a clash) |
| Commands `commands/<name>.md` | `.cursor/skills/<name>/SKILL.md` with `disable-model-invocation: true`, invoked as `/name` | Generated (B3: commands are legacy). The body says "use the text typed after the command" (no `$ARGUMENTS`), and Agent-tool spawns become "delegate to the `<name>` subagent" |
| SessionStart hook (auto-scan) | Imported from `.claude/settings*.json`; the same script prints Cursor's format (§3.4, C7) | Fallback for teams with the import off: generated `.cursor/hooks.json` (`sessionStart`). Because the hook is fire-and-forget, the `workflow-contract.mdc` rule also says "read `.workflow/profile.json`, or run `detect-stack.py --stdout`, before planning or coding" |
| Audit hooks (Pre/PostToolUse, Stop) | Imported (Bash→Shell, Edit→Write) | Glob, Notification and PermissionRequest are unsupported in Cursor. No action needed |
| MCP (Playwright for QA) | `.cursor/mcp.json` | Generated from `cursor-overrides/mcp.json` |
| `scripts/*` | Used from `.claude/scripts/` | Not copied; rules and skills reference `.claude/scripts/…` |

**Verify first in Phase C:**
1. Cursor's import translates or accepts the hook *output* (B7, unverified), and the dual-format script works.
2. A Cursor skill receives the text typed after `/name`.
3. `readonly: true` blocks edits in a subagent.

- **Legacy Cursor hub:** the separate Cursor hub repo (`tb-custom-workflow`) is superseded once AC-15 passes. Archiving it is a later decision.

---

## 4. Tasks (workflow hub; no product backend/frontend work)

The template's Backend, C# Backend and Frontend blocks don't apply: this is hub work, so tasks are grouped by phase instead. Each phase ends with `/argus --local` on the hub branch, plus the phase checks in §8.

### Phase 0 — Platform checks (1 session): DONE 2026-11-25
Findings: [plug-and-play-workflow-phase0.md](plug-and-play-workflow-phase0.md). Changes C1–C9 are applied in this plan.

- [x] Confirm the Claude Code plugin format with the `claude-code-guide` agent:
  - the manifest fields;
  - the component types (commands, agents, skills, hooks, MCP; rules?);
  - the hook environment variables (`CLAUDE_PLUGIN_ROOT`);
  - the marketplace layout.
- [x] Confirm Cursor's current capabilities, from Cursor docs (web) plus a read-only look at the existing Cursor hub repo:
  - `.mdc` frontmatter (`description`, `globs`, `alwaysApply`);
  - custom commands;
  - hooks and their events (is there a session or start event?);
  - subagent or background-agent support;
  - how the old hub expressed modes.

  Fill in the §3.11 table with verified mappings.
- [x] Record all findings in `docs/plans/plug-and-play-workflow-phase0.md`. Decisions D1–D6 are already recorded in §11.
- [x] Tag the current hub `v1-ticketboat` so the old behavior can be restored. Done: a local tag at `58e9fcc`, not pushed.

### Phase 1 — Project profile (1–1½ sessions) → AC-1…AC-6: DONE 2026-11-25
Results: [results-2026-11-25.md](../validation/results-2026-11-25.md). The interactive `/setup` end-to-end run is deferred to the Phase 3 row-G check.
Review: [Argus review of 6c7e2f5](../reviews/tb-claude-custom-workflow-feat-plug-and-play-6c7e2f5.md) found 1 important and 4 consider findings, all fixed in [rework-1](plug-and-play-workflow-rework-1.md).

- [x] Create `.claude/skills/project-profile/SKILL.md`: how agents read the profile, the precedence rules, how to handle `gaps`, and the confidence levels.
- [x] Create `.claude/skills/project-profile/profile.schema.json` (JSON Schema draft-07).
- [x] Create `.claude/scripts/detect-stack.py`, following §3.3: discovery, packs, commands, UI, data, infra, tickets, code host, graph, monorepo roots, the `--stdout`/`--check` modes and the timeout.
- [x] Create `.claude/scripts/validate-profile.py`: a stdlib-only schema check used by tests and `/setup`.
- [x] Modify `.claude/hooks/session-init.sh` per §3.4: generic contract text, and dual Claude/Cursor output keyed on the stdin event name (C7).
- [x] Create `.claude/commands/setup.md`: detect, enrich from docs with citations, confirm inferred commands, write the profile and `.workflow/config.yml`; support `--refresh` and `--print`.
- [x] Create the fixtures. These live in `docs/validation/matrix.json` (public rows, pinned by sha) and the gitignored `docs/validation/matrix.local.json` (private rows' paths and expectations), instead of per-row `expected.json` files.
- [x] Create `scripts/test-detector.sh`: runs `detect-stack.py --stdout` against each matrix repo (read-only) and diffs against the fixture.

### Phase 2 — Shared stack knowledge (1 session) → AC-7
- [x] Move `.claude/skills/argus/stacks/` → `.claude/skills/stacks/`, and `.claude/skills/argus/failure-modes.md` → `.claude/skills/stacks/failure-modes.md`.
- [x] Create `.claude/skills/stacks/_generic.md`.
- [x] For each pack (`python`, `node-js`, `go`, `csharp-dotnet`, `web-frontend`, `sql-migrations`, `data-warehouse`, `iac`, `ci-cd`, `serverless-queues`):
  - add `## Build`, `## Test` and `## Commands`;
  - retitle the existing content under `## Review`.

  Sources: `rules/python-backend.md`, `rules/api-routes-python.md`, `rules/csharp-backend.md`, `rules/api-routes-csharp.md`, `rules/react-frontend.md`, `rules/typescript.md`, `skills/api-design-patterns`, `skills/api-testing`, `skills/backend-architect`, `skills/frontend-architect`, `skills/backend-reviewer`, `skills/frontend-reviewer`, `skills/accessibility-checklist` (into the `web-frontend` Review section).
- [x] Create `.claude/rules/stack-knowledge.md`, a short always-on rule: "read the profile; load the Build/Test/Review sections of the packs for the files you touch; fall back to `_generic`."
- [x] Update `skills/argus/SKILL.md`, `agents/argus.md`, `commands/argus.md` and `commands/argus-scan.md`: pack path `../stacks/`, use `profile.packs` when present, read the `.workflow/config.yml` `review:` section and fall back to `.argus.yml`. Rework 2 refined this: config merges key by key, and packs are the profile's plus the diff's.
- [x] Update `.claude/skills/stacks/_template.md` for the new section layout.
- [x] Create `scripts/lint-packs.sh` (the Phase 2 check): pack name, `detect` block, required sections in order, FM ids, size.
- [x] Phase check: Argus `--local` on the Phase 2 working tree validates, loading packs from `skills/stacks/` (AC-7). Its findings are fixed in [rework 2](plug-and-play-workflow-rework-2.md).
- Kept for now: the six stack rules (`python-backend.md` … `typescript.md`) stay until the Phase 3 parity check.

### Phase 3 — Roles, commands, adapters, overlay (2–3 sessions) → AC-8…AC-11, AC-13
- [x] **Agents:**
  - create `agents/implementer.md` and `agents/test-runner.md`;
  - update `agents/qa-tester.md`, `agents/tech-stack-researcher.md` and `agents/technical-writer.md`;
  - delete `agents/backend-architect.md`, `agents/frontend-architect.md`, `agents/backend-reviewer.md` and `agents/frontend-reviewer.md`.
- [x] **Skills:**
  - create `skills/ticket-adapters/SKILL.md` (tickets: linear, jira, github, none; chat: teams, slack, none);
  - create `skills/api-design/SKILL.md` (generic REST/RPC guidance) and `skills/test-strategy/SKILL.md` (generic test pyramid and regression tests);
  - update `skills/feature-planning/SKILL.md` (layer blocks), `skills/agent-selection/SKILL.md` (roles), `skills/manual-qa/SKILL.md` (auth from config or overlay), `skills/trace-flow/SKILL.md` (generic layers), `skills/ui-mockup/SKILL.md` (design system from the profile; no default Ant Design), `skills/graphify-navigation/SKILL.md` (optional; drop "Ticketboat product-repo") and `skills/postgresql/SKILL.md` (load only when the profile shows Postgres);
  - split `skills/graphify/SKILL.md` (699 lines) under the 500-line guidance, or move it to an optional graphify add-on (C8);
  - delete `skills/backend-architect/`, `skills/frontend-architect/`, `skills/backend-reviewer/`, `skills/frontend-reviewer/`, `skills/api-design-patterns/` and `skills/api-testing/`, once their content has moved into packs or the generic skills.
- [x] **Commands:**
  - create `commands/scaffold.md` and `commands/test-gen.md`;
  - update `commands/feature-plan.md`, `apply-ticket.md`, `refine-spec.md`, `create-ticket.md`, `project-manager.md`, `manual-test.md`, `trace-flow.md`, `code-cleanup.md`, `code-optimize.md`, `new-task.md` and `daily-report.md`;
  - delete `commands/api-new.md` and `commands/api-test.md`.
- [x] **Rules:**
  - `core-standards.md`: remove the Ticketboat context, and move stack-specific items into packs;
  - `compounding-dev-cycle.md` and `claude-code.md`: switch to the new role names (AGENT (Code) = implementer per layer, then test-runner; Review = argus; QA = qa-tester when there's a UI);
  - `graphify.md`: make it conditional on `graph`;
  - `token-policy.md`: drop the Ticketboat references.
- [x] **Config:** create `templates/workflow-config.example.yml`, and `skills/argus/config-template.yml` → point it at the `review:` section of `.workflow/config.yml`.
- [x] **Overlay**, in the gitignored `overlays/ticketboat/` (D2):
  - add `overlays/*` and `!overlays/_template/` to `.gitignore`;
  - create the tracked `overlays/_template/overlay.yml` and `overlays/_template/README.md` (overlay format, plus private backup and restore steps);
  - create `overlays/ticketboat/overlay.yml`, `rules/ticketboat-context.md`, `skills/argus/domains/ticketboat.md` (moved), `config.yml`, `hooks/context.txt`, `qa/auth.md` and `daily-report/sources.md`;
  - remove `skills/argus/domains/ticketboat.md` from the hub tree.
- [x] **CLAUDE.md:** make it the generic session contract, with the command table and role list.
- [x] **CI check:** create `scripts/check-generic.sh` (AC-11) and wire it into `.github/workflows/check.yml`.
- **Choices made while implementing:**
  - The 699-line `/graphify` build skill moved to an optional add-on (`addons/graphify/`, C8). `graphify-navigation` stays in core and applies only when a graph exists.
  - `check-generic.sh` stores its terms as SHA-256 hashes (`scripts/generic-terms.sha256`), so the public repo never contains the words it guards against. Private terms fail anywhere; org terms fail outside `docs/`; `README.md` warns until Phase 4; `docs/research/` is excluded per AC-11, with its hit count printed.
  - The old stack rules, architect and reviewer roles, their skillsets, and `/api-new` / `/api-test` are deleted (git history keeps them). Their content had already moved into the packs, `implementer`, `argus`, `api-design` and `test-strategy`.
- [x] Phase check: end to end on row G (temp clone): `/setup` → `/feature-plan` → `/project-manager`, showing the AC-8 order. Order verified. The first run correctly ended BLOCKED (env) with no Go toolchain; after installing Go, the rerun passed every gate and the change reached production ready (results doc).
- [x] Phase check: the ticket adapter with `none` and with `github` on row G (AC-10). Reads verified against the public repo; writes checked for flags only.
- [ ] Phase check: overlay parity in one Ticketboat repo (AC-11). Needs the overlay installed and the user's go-ahead, since `/feature-plan` writes into that repo.

### Phase 4 — Packaging, install, docs, validation (1 session) → AC-12, AC-14
- [x] **Contract skill (C2):** create `.claude/skills/workflow-contract/SKILL.md`, with the session contract, rule digests and the role-name resolution table (C3).
- [x] **Plugin build (C1):** create `scripts/build-plugin.sh`, which renders `plugin/`:
  - `plugin/.claude-plugin/plugin.json`;
  - the root-level components;
  - `hooks/hooks.json` with `"${CLAUDE_PLUGIN_ROOT}/scripts/session-init.sh"` and the audit hooks writing to `${CLAUDE_PLUGIN_DATA}`;
  - `.mcp.json` with Playwright (C4).

  It also creates the repo-root `.claude-plugin/marketplace.json` (`source: "./plugin"`).
- [x] **Validate:** run `claude plugin validate plugin`. In a clean temp project, install from the local marketplace, spawn one role through the Agent tool (to confirm the `<plugin>:<name>` resolution), and run `/reload-plugins` after edits.
- [x] **QA packaging (C4):** decide on a companion plugin vs bundled Playwright, and record the choice in §11 as D8.
- [x] **`install.sh`:**
  - flags `--user`, `--project <path>`, `--overlay <dir>`, `--cursor`, `--uninstall`, `--dry-run`;
  - a settings.json hook merge that doesn't duplicate existing user or project audit hooks;
  - an install manifest.
- [x] Rewrite `README.md` per AC-14, and add `docs/guides/adding-a-stack.md`, `docs/guides/writing-an-overlay.md` and `docs/guides/migrating-from-ticketboat-install.md`.
- [x] Run the validation matrix and the end-to-end checks (§8), and record the results in `docs/validation/results-<date>.md`.
- **Choices made while implementing:**
  - The plugin is named **daedalus** (the user's choice). Two plugins are generated, in `plugins/daedalus/` and `plugins/daedalus-qa/`, instead of one `plugin/` folder, because QA ships as a companion (D8).
  - Rules ship inside the plugin under `skills/workflow-contract/rules/`, and every `.claude/…` reference in commands, skills and agents is rewritten to `${CLAUDE_PLUGIN_ROOT}/…` (or to the other plugin's command or role name).
  - The migration guide is `docs/guides/migrating-from-the-original-install.md`, so the README link carries no org name.
  - `install.sh` gained `--addon graphify` and `--prune-legacy` (back up and remove the retired files of the original install; restored on uninstall). The session contract is installed as `rules/daedalus-workflow.md`, so no `CLAUDE.md` is overwritten.
- [x] Marketplace install smoke: local marketplace + `/plugin install` of both plugins at project scope in a scratch project, two headless sessions, then uninstall (results doc). The user's settings were untouched.

### Phase C — Cursor thin layer (alongside Phases 1–4; 1–1½ sessions) → AC-15
- [ ] **Step 1, verify the three open items in §3.11** in a scratch Cursor project, and record the results in the phase0 findings:
  1. whether the hook import accepts the output, and the dual-format script works;
  2. whether `/name` passes the text after it;
  3. whether `readonly: true` blocks edits.
- [ ] **Generator:** create `scripts/build-cursor.sh` (the §3.11 mapping, `--check`) and `cursor-overrides/`, holding `workflow-contract.mdc` text, `mcp.json`, the `hooks.json` fallback, and agent overrides with `readonly`.
- [ ] **After Phase 1:**
  - emit `.cursor/rules/workflow/workflow-contract.mdc` (always-apply, with the "read the profile first" instruction) and `.cursor/skills/setup/SKILL.md`;
  - verify `/setup` in Cursor on row B, and confirm the `sessionStart` summary arrives through the import.
- [ ] **After Phase 2:**
  - emit `.cursor/rules/stacks/<pack>.mdc` (auto-attached by `detect.files`);
  - verify a pack attaches when editing a matching file, and that no skill loads twice (`.claude/skills` import only).
- [ ] **After Phase 3:**
  - emit the command skills, the `argus` and `qa-tester` overrides, and `.cursor/mcp.json`;
  - verify the AC-15 commands on rows B and G, with `/project-manager` delegating to the imported subagents (nesting is one level deep in Cursor).
- [ ] **After Phase 4:**
  - add `install.sh --cursor` (project or user);
  - wire `build-cursor.sh --check` into CI;
  - add the Cursor section to the README, covering the third-party import setting and the `hooks.json` fallback.

---

## 5. Migration map (current → new)

| Current | New | Notes |
|---|---|---|
| `rules/python-backend.md`, `rules/api-routes-python.md` | `skills/stacks/python.md` → Build/Test | Path-scoped rules retire |
| `rules/csharp-backend.md`, `rules/api-routes-csharp.md` | `skills/stacks/csharp-dotnet.md` → Build/Test | |
| `rules/react-frontend.md`, `rules/typescript.md` | `skills/stacks/web-frontend.md` (+ `node-js.md` for TS) → Build/Test | Ant Design and Jotai specifics only under "if detected" |
| `rules/core-standards.md` | generic `core-standards.md` + `overlays/ticketboat/rules/ticketboat-context.md` | |
| `agents/backend-architect.md`, `agents/frontend-architect.md` | `agents/implementer.md` | layer-aware |
| `agents/backend-reviewer.md`, `agents/frontend-reviewer.md` | `agents/argus.md` | a11y → `web-frontend` Review |
| `skills/backend-*`, `skills/frontend-*` | packs + `implementer`/`argus` | |
| `skills/api-design-patterns` | `skills/api-design` (generic) + Python Build | FastAPI specifics → python pack |
| `skills/api-testing` | `skills/test-strategy` (generic) + Python Test | |
| `commands/api-new.md`, `commands/api-test.md` | `commands/scaffold.md`, `commands/test-gen.md` | |
| `skills/argus/stacks/*`, `failure-modes.md` | `skills/stacks/*` | shared by all roles |
| `skills/argus/domains/ticketboat.md` | `overlays/ticketboat/skills/argus/domains/ticketboat.md` | private |
| `.argus.yml` | `.workflow/config.yml` `review:` | `.argus.yml` still read |
| Linear and Teams in commands | `skills/ticket-adapters` | |

---

## 6. File changes

Paths are relative to the hub repo. Overlay paths are under `overlays/ticketboat/`, which is gitignored (D2). The generated Cursor tree is `cursor/.cursor/` (D3).

**Create**
- `.claude/scripts/detect-stack.py`
- `.claude/scripts/validate-profile.py`
- `.claude/skills/project-profile/SKILL.md`
- `.claude/skills/project-profile/profile.schema.json`
- `.claude/commands/setup.md`
- `.claude/skills/stacks/_generic.md`
- `.claude/rules/stack-knowledge.md`
- `.claude/agents/implementer.md`
- `.claude/agents/test-runner.md`
- `.claude/skills/ticket-adapters/SKILL.md`
- `.claude/skills/api-design/SKILL.md`
- `.claude/skills/test-strategy/SKILL.md`
- `.claude/commands/scaffold.md`
- `.claude/commands/test-gen.md`
- `templates/workflow-config.example.yml`
- `.claude/skills/workflow-contract/SKILL.md` (C2, C3)
- `scripts/build-plugin.sh` (C1)
- `.claude-plugin/marketplace.json` (repo root; `source: "./plugin"`)
- `plugin/**`, generated and committed: `.claude-plugin/plugin.json`, `commands/`, `agents/`, `skills/`, `scripts/`, `hooks/hooks.json`, `.mcp.json`
- `hooks/hooks.json` (if the plugin format requires it)
- `install.sh`
- `scripts/test-detector.sh`
- `scripts/check-generic.sh`
- `.github/workflows/check.yml`
- `docs/validation/matrix.json` (+ gitignored `docs/validation/matrix.local.json`)
- `docs/validation/results-<date>.md`
- `docs/guides/adding-a-stack.md`
- `docs/guides/writing-an-overlay.md`
- `docs/guides/migrating-from-ticketboat-install.md`
- `docs/plans/plug-and-play-workflow-phase0.md`
- **Overlay template (tracked):** `overlays/_template/overlay.yml`, `overlays/_template/README.md`
- **Overlay (gitignored):** `overlays/ticketboat/{overlay.yml, rules/ticketboat-context.md, skills/argus/domains/ticketboat.md, config.yml, hooks/context.txt, qa/auth.md, daily-report/sources.md}`
- **Cursor (D3):**
  - `scripts/build-cursor.sh`;
  - `cursor-overrides/` (`workflow-contract.mdc` text, `mcp.json`, the `hooks.json` fallback, `agents/{argus,qa-tester}.md` with `readonly`);
  - `cursor/.cursor/**`, generated and committed as a thin layer: `rules/workflow/*.mdc`, `rules/stacks/*.mdc`, `skills/<command>/SKILL.md`, `agents/{argus,qa-tester}.md`, `mcp.json`, and the optional `hooks.json`. Skills, agents and scripts are **not** copied, because Cursor imports `.claude/`.

**Move**
- `.claude/skills/argus/stacks/*` → `.claude/skills/stacks/*`
- `.claude/skills/argus/failure-modes.md` → `.claude/skills/stacks/failure-modes.md`
- `.claude/skills/argus/domains/ticketboat.md` → overlay

**Modify**
- **Hooks:** `.claude/hooks/session-init.sh`.
- **Stack packs:** `.claude/skills/stacks/*.md` (section layout and content).
- **Argus:** `.claude/skills/argus/SKILL.md`, `.claude/skills/argus/config-template.yml`, `.claude/agents/argus.md`, `.claude/commands/argus.md`, `.claude/commands/argus-scan.md`.
- **Agents:** `.claude/agents/qa-tester.md`, `.claude/agents/tech-stack-researcher.md`, `.claude/agents/technical-writer.md`.
- **Commands:** `.claude/commands/{feature-plan, apply-ticket, refine-spec, create-ticket, project-manager, manual-test, trace-flow, code-cleanup, code-optimize, new-task, daily-report}.md`.
- **Skills:** `.claude/skills/{feature-planning, agent-selection, manual-qa, trace-flow, ui-mockup, graphify-navigation, postgresql}/SKILL.md`.
- **Rules:** `.claude/rules/{core-standards, compounding-dev-cycle, claude-code, graphify, token-policy}.md`.
- **Top level:** `CLAUDE.md`, `README.md`, `.gitignore` (add `overlays/*` and `!overlays/_template/`).

**Delete** (after the content has moved and AC-11's parity check passes)
- `.claude/rules/{python-backend, api-routes-python, csharp-backend, api-routes-csharp, react-frontend, typescript}.md`
- `.claude/agents/{backend-architect, frontend-architect, backend-reviewer, frontend-reviewer}.md`
- `.claude/skills/{backend-architect, frontend-architect, backend-reviewer, frontend-reviewer, api-design-patterns, api-testing}/`
- `.claude/commands/{api-new, api-test}.md`

---

## 7. Dependencies / env

| Item | Purpose | Required |
|---|---|---|
| `python3` ≥ 3.8 (stdlib only) | Detector, validator, hooks (already used by the hooks) | Yes |
| `git` | Read-only history and remote for tickets and code-host detection | Yes |
| `jq`, `gh` (signed in) | Argus bundle, GitHub ticket adapter | For `/argus` and GitHub tickets |
| Linear MCP / Jira MCP | Ticket adapters | Optional |
| Playwright MCP (Node 18+, Chrome) | `qa-tester` | Only for UI projects |
| `graphify` CLI | Optional exploration speed-up | Optional |
| Cursor (current release) | Verifying the generated `.cursor/` tree (AC-15) | For Phase C checks |

**Environment variables:**
- `WORKFLOW_DETECT_TIMEOUT`: detector budget in seconds. Optional; default `5`.
- `ARGUS_TICKET_RE`: existing; kept as an override.

**Config files:**
- `.workflow/config.yml` at repo or workspace level, or `~/.workflow/config.yml` for personal settings;
- `.workflow/profile.json`, generated and committed by teams (D5). Both Claude Code and Cursor read the same files.

---

## 8. Integration and testing

### Validation matrix (read-only)
- **Ticketboat repos:** use `detect-stack.py --stdout --root <path>` against the local clones. Nothing is written into them, and nothing in any product repo is modified.
- **Public repos:** shallow-clone into a temp directory, and delete the clone afterwards.

| Row | Repo type | Expected packs | Expected test command | Notes |
|---|---|---|---|---|
| A | Ticketboat Python FastAPI service | `python` | `pytest` (or the declared script) | API layer |
| B | Ticketboat React/Vite admin UI | `web-frontend` | the `package.json` test script | `ui.present: true`, dev URL |
| C | Ticketboat Python Lambda/SQS worker | `python`, `serverless-queues` | `pytest` | worker layer |
| D | Ticketboat Flyway migrations repo | `sql-migrations` | gap (none) | data layer |
| E | Ticketboat Snowflake/dbt repo | `data-warehouse` | gap or the dbt test command | data layer |
| F | Ticketboat Node.js service | `node-js` (+ `serverless-queues` if signalled) | the `package.json` test script | |
| G | Public Go service | `go` | `go test ./...` | non-Ticketboat |
| H | Public Django or Rails app | `python` / *(none → `_generic`)* | `pytest`/`manage.py test` or `bundle exec rspec` | the Rails case exercises the fallback |
| I | Public pnpm/turbo monorepo | multiple roots | a per-root script | monorepo roots |
| J | Public Rust repo | `[]` | `cargo test` (derived) | AC-3 fallback |

### Phase checks
- **Phase 1:**
  - `scripts/test-detector.sh` passes on every row (AC-2, AC-3);
  - the hook timing is under 5s cold and under 1s warm (AC-1, AC-4);
  - the detector runs no subprocesses beyond `git`, checked with an `strace`/`dtruss` spot check or a code review (AC-6).
- **Phase 2:**
  - every pack has the required sections (a lint script);
  - Argus `--local` on a known commit still validates (AC-7).
- **Phase 3:**
  - end to end on row G (temp clone): `/setup` → `/feature-plan` for a one-line change → `/project-manager` shows the AC-8 order;
  - the ticket adapter with `none` and with `github` on row G (AC-10);
  - `check-generic.sh` returns 0 hits (AC-11);
  - overlay parity in one Ticketboat repo (AC-11): compare `/feature-plan` sections and `/argus --local` output before and after.
- **Phase 4:**
  - plugin install and `install.sh --project` into a temp directory; smoke test; `--uninstall` leaves no stray files (AC-12).
- **Phase C (Cursor):**
  - `build-cursor.sh --check` is clean after every phase;
  - in Cursor, on rows B and G, `/setup` writes `.workflow/profile.json`, a pack rule auto-attaches, and `/feature-plan`, `/argus --local`, `/scaffold` and `/test-gen` work;
  - `/project-manager` runs the roles in order (AC-15);
  - `install.sh --cursor --project <tmp>` installs and uninstalls cleanly.

### Critical paths
1. Detector correctness on commands, since test-runner executes them.
2. Never auto-running unconfirmed `inferred` commands, or any command matching `deploy|migrate|prod|publish|release|destroy`.
3. Overlay parity, so Ticketboat users lose nothing.

---

## 9. Design reference

No visual change. This is workflow-hub tooling with no product UI.

## 10. Manual QA

N/A: no acceptance criterion is UI-observable in a product. The acceptance checks are the validation matrix and the phase checks in §8, run by the implementer of each phase and recorded in `docs/validation/results-<date>.md`.

---

## 11. Decisions (resolved 2026-11-25)

| ID | Decision | Chosen | Was recommended | Effect on this plan |
|---|---|---|---|---|
| D1 | Distribution | **Plugin + `install.sh`** | same | §3.10, Phase 4 |
| D2 | Ticketboat overlay home | **Gitignored `overlays/ticketboat/` in this repo** | separate private repo | §3.9: tracked `overlays/_template/`, private backup steps, `check-generic.sh` asserts that only the template is tracked; risk 6 |
| D3 | Cursor parity | **Keep the Cursor tree in sync** | Claude Code only | §3.11, Phase C, AC-15; profile and config moved to a tool-neutral `.workflow/`; Phase 0 shrank the Cursor work to a thin layer (+1–1½ sessions); risk 7 |
| D4 | graphify | **Optional accelerator (`graph: auto`)** | same | AC-13 |
| D5 | Commit the profile in target repos | **Commit `.workflow/profile.json` and `.workflow/config.yml`; personal overrides in `~/.workflow/config.yml`** | same | §3.2, §3.8 |
| D6 | Role names | **`implementer`, `test-runner`** | same | §3.6 |
| D7 | Codex output from the same sources | **Deferred** (observed in the legacy hub; Cursor also reads `.codex/skills`) | — | Out of scope; revisit after AC-15 |
| D8 | QA packaging for plugin installs | **Companion plugin `daedalus-qa`** (qa-tester, manual-qa, /manual-test, Playwright `.mcp.json`) | companion (recommended in Phase 0) | §3.10, Phase 4: the Playwright server starts only for projects that install it; `/project-manager` treats missing QA as BLOCKED (env) |

---

## 12. Risks / potential issues

1. **Plugins can't ship always-on rules or `CLAUDE.md`** (confirmed in Phase 0 A6). Mitigation: a `workflow-contract` skill plus SessionStart `additionalContext` for plugin installs (C2); `install.sh` still copies `rules/` and `CLAUDE.md` for script installs; AC-12 smoke-tests both.
2. **Wrong detected commands could run something harmful.** Mitigation: the confidence levels; `inferred` commands need confirmation; a denylist for deploy/migrate/prod/publish/release/destroy; test-runner prints each command before running it.
3. **Hook latency in large monorepos.** Mitigation: a depth limit, cached manifest hashing, a 5s cap, partial profiles; `/setup --refresh` for the full scan.
4. **Ticketboat regressions** from merging the backend and frontend architects into `implementer`. Mitigation: the pack Build sections carry the specifics, the overlay parity test (AC-11), the `v1-ticketboat` tag for rollback, and deleting old files only after parity passes.
5. **Public exposure of internal content.** Mitigation:
   - the overlay is gitignored (`overlays/*`), and `check-generic.sh` fails CI if anything besides `overlays/_template/` is tracked, or if org or partner terms appear in tracked files;
   - `install.sh` never copies overlays into the hub tree.

   The earlier branch history is out of scope here; tracked separately.
6. **The overlay isn't backed up or shared (D2).** A lost laptop loses the Ticketboat add-on, and teammates can't get it from git. Mitigation: a private backup procedure in `overlays/_template/README.md`, and moving it to a private repo later if the team needs it.
7. **Cursor gaps and double-loading (D3).** Phase 0 confirmed that Cursor has subagents, skills and a `sessionStart` hook. The remaining risks:
   - the hook is fire-and-forget;
   - subagents have no per-tool limits (only `readonly`);
   - commands are legacy, and `$ARGUMENTS` is unverified;
   - by default Cursor imports `.claude/agents`, `.claude/skills` and `.claude/settings` hooks, so a full parallel tree would load items twice.

   Mitigation:
   - a thin generated layer only (§3.11, C6);
   - an always-apply "read the profile first" rule;
   - `readonly` overrides for reviewers and QA;
   - command skills phrased without `$ARGUMENTS`;
   - `build-cursor.sh --check` in CI;
   - the three open items are verified first in Phase C.

---

## 13. Next steps

1. Decisions D1–D6 are resolved (§11).
2. Execute Phase 0, including the Cursor capability check, then Phase 1 on `feat/plug-and-play`. Phase C runs alongside, after each phase.
   - `/project-manager` currently delegates to product-oriented backend/frontend architects, which don't fit hub work. So phases 0–2 run directly in a session, reviewed with `/argus --local` and the §8 checks.
   - From Phase 3 onward, the new `implementer`/`test-runner` roles exist, and `/project-manager docs/plans/plug-and-play-workflow.md` can drive the remaining phases.
3. After each phase, record the results in `docs/validation/results-<date>.md`. Commit only when asked.
4. Once AC-15 passes, decide whether to archive the separate legacy Cursor hub repo.

This document is the PLAN artifact only. No implementation has been done.
