# Daedalus: a plug-and-play dev workflow for Claude Code

Daedalus plans, builds, tests and reviews changes in any repo, in whatever stack the repo already uses. When a session starts it detects the project's languages, frameworks, layers, commands and integrations into `.workflow/profile.json`. Every command and role then works from that profile: plans get one task block per layer, implementers follow the stack's own idioms, the test runner runs only the project's safe commands, and **Argus**, the hundred-eyed reviewer, checks the diff against universal failure modes plus the stack's packs.

Team- or org-specific behavior (ticket keys, domain rules, sign-in steps for browser QA) comes from an optional private **overlay**. It's never part of this repository.

## What it does

1. **Refine, then hand off.** Each request becomes a tight brief (objective, scope, constraints, forbidden) before any command or role runs, so tokens go to the work, not to re-clarifying it.
2. **Plan → Code → Review → QA → Plan.** Every phase ends with a written artifact: a plan in `docs/plans/`, implementation notes, a test report, an Argus review in `docs/reviews/`, and a QA report in `docs/qa/` when the project has a UI.
3. **Profile-driven.** Facts are detected, not configured: roots and layers (`ui`, `api`, `worker`, `data`, `infra`, `lib`, `cli`), stack packs, and `install` / `test` / `lint` / `typecheck` / `build` / `dev` commands, each with a confidence level and an `unsafe` flag. `/setup` confirms anything guessed.
4. **Safe by default.** Detection only reads files and runs read-only `git`. Roles run only commands marked `script`, `derived`, `user` or confirmed, and never one marked `unsafe` (deploy, migrate, publish, drop, or anything whose body does those) without asking. Nothing is committed or pushed unless you ask.

### Modes

| Mode | Behavior |
|---|---|
| **ASK** | No edits. Ask until scope and acceptance criteria are clear |
| **PLAN** | Write only `docs/plans/**` (and the mockup, or the ticket for `/refine-spec` and `/create-ticket`) |
| **AGENT (Code)** | `implementer` once per affected layer (data → api / worker → ui → infra), then `test-runner` |
| **AGENT (Review)** | `/argus --local`, read-only; critical and important findings are Critical, consider findings are Suggestions |
| **AGENT (QA)** | `qa-tester` in a real browser, only when the profile shows a UI |

### Why XML beats a single prose prompt

For complex work, `token-policy.md` asks for a short internal XML blueprint (`<role>`, `<task>`, `<forbidden>`, `<documents>`, `<error_handling>`, `<analysis>`, `<output_format>`). Unstructured text mixes role, task, constraints and output in one stream, so the model blends them and drifts (rules read as content, examples override instructions). Named tags give each concern its own slot, which makes negative rules (`<forbidden>`, `<error_handling>`) as visible as positive ones. Separating `<analysis>` from `<output_format>` makes the model think before it answers. Frontier models are trained heavily on XML-style instruction documents, so this format tends to be followed more reliably than a paragraph with the same words and no delimiters.

## Install

Two ways, same workflow. Both read and write the same `.workflow/` files in your projects.

### A. Claude Code plugin (recommended)

```
/plugin marketplace add tb-jcabalejo/tb-claude-custom-workflow
/plugin install daedalus@daedalus
```

Projects with a UI also install the browser-QA companion, which carries the Playwright MCP server so it only starts where you need it:

```
/plugin install daedalus-qa@daedalus
```

In a plugin install, commands and roles are prefixed: `/daedalus:feature-plan`, `/daedalus:project-manager`, `daedalus:implementer`, and `/daedalus-qa:manual-test`. Plugins can't ship always-on rules, so the session-start hook names the prefixes and points Claude at the `daedalus:workflow-contract` skill, which carries the rules.

### B. Script install

```bash
git clone https://github.com/tb-jcabalejo/tb-claude-custom-workflow.git && cd tb-claude-custom-workflow
```

```bash
./install.sh --user
```

- `--user` installs into `~/.claude` (every project); `--project <path>` installs into `<path>/.claude` (one project or a multi-repo workspace folder).
- `--overlay <dir>` also installs a private overlay; `--addon graphify` adds the optional `/graphify` build skill.
- It shows what will change and asks first (`--dry-run` to only look, `--yes` to skip the question). Files it would overwrite are backed up, hooks are merged into `settings.json` without touching your other entries, and older entries pointing at `.claude/hooks/` scripts are replaced.
- `./install.sh --uninstall --user` (or `--project <path>`) removes exactly what its manifest recorded and restores the backups.

Script installs keep bare names (`/feature-plan`, `implementer`) and load the rules as always-on `.claude/rules/*.md`. The session contract is installed as `rules/daedalus-workflow.md`, so your own `CLAUDE.md` is never overwritten.

### Requirements

| Tool | For | Required |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) | Running the workflow | Yes |
| Python 3.8+ (stdlib only) and `git` | Detector, hooks, scripts | Yes |
| `gh` (signed in) and `jq` | `/argus` bundles and the GitHub ticket adapter | For `/argus` and GitHub tickets |
| Linear, Jira, Microsoft 365 or Slack MCP | Ticket and chat adapters | Only for that system |
| Node.js 18+ and Chrome | Browser QA (`daedalus-qa`, or `qa-tester` in a script install) | Only for UI projects |
| Each project's own toolchain | `test-runner` runs the project's commands | Per project; a missing tool reports the check as BLOCKED, never as a code failure |
| [Graphify](https://github.com/Graphify-Labs/graphify) CLI | Optional code-graph orientation | Optional |

## First run

1. Open a project and start a session. The hook writes `.workflow/profile.json` and adds a one-paragraph summary to the session context.
2. Run `/setup` (`/daedalus:setup` for the plugin). It shows the profile, fills gaps from the repo's docs with citations, asks you to confirm guessed commands and the ticket system, and writes `.workflow/config.yml` only for choices you make. Commit `.workflow/` so the team shares it.
3. Plan a change: `/feature-plan <slug>`, or `/apply-ticket <id>` from a ticket.
4. Run `/clear`, then `/project-manager docs/plans/<slug>.md`. It runs the implementers, the test runner, the Argus review and (with a UI) browser QA, and loops through rework until the change is production ready or blocked on something only you can fix.

## Commands

| Command | Mode | What it does |
|---|---|---|
| `/setup [--refresh \| --print]` | read-only toward code | Detect and confirm the profile; write `.workflow/config.yml` only for your choices |
| `/feature-plan <slug>` | PLAN | `docs/plans/<slug>.md` with one task block per detected layer, plus a mockup when the UI changes and no design exists |
| `/apply-ticket <id>` | PLAN | Read one ticket (Linear, Jira or GitHub Issues) and write the layered plan |
| `/refine-spec <id>` | PLAN | Tighten a ticket's spec and save it back |
| `/create-ticket` | PLAN | File one ticket in the configured system |
| `/project-manager <plan>` | AGENT | implementer per layer → test-runner → `/argus --local` → qa-tester (UI only) → rework until production ready |
| `/scaffold <kind> <name>` | AGENT (Code) | New endpoint, component, job, migration or model in the project's framework, with tests |
| `/test-gen <target>` | AGENT (Code) | Tests for a file, endpoint, component or job in the detected test framework |
| `/code-cleanup`, `/code-optimize` | AGENT (Code) | Refactor, or a measure-first performance pass |
| `/new-task <task>` | ASK | Task breakdown only |
| `/trace-flow <page or action>` | read-only | Trace a page or action from route to database to render, into `docs/traces/` |
| `/argus <owner/repo#N \| N \| --local>` | AGENT (Review) | Argus review of a PR or the current branch; saves `docs/reviews/…`; posts only with `--post` |
| `/argus-scan <repo> [paths]` | AGENT (Review) | Security scan into `docs/scans/` with rule ids and a fix brief |
| `/manual-test <plan>` | AGENT (QA) | Browser QA of every UI-observable acceptance criterion, with screenshots; N/A without a UI |
| `/daily-report [48h \| since …]` | read-only | Done / next working day / blockers from git, tickets and chat |

## Roles

| Role | Mode | Does |
|---|---|---|
| `implementer` | AGENT (Code) | One layer's plan tasks, using the Build and Test sections of that layer's packs and the repo's own conventions |
| `test-runner` | AGENT (Code) | Runs the profile's safe checks for the touched roots, fills test gaps (test files only), separates new failures from old ones |
| `argus` | AGENT (Review) | Read-only review of a diff, PR or repo; material findings only, each with Fix / Where / Cost |
| `qa-tester` | AGENT (QA) | Read-only browser QA with screenshot evidence; never types credentials |
| `tech-stack-researcher` | PLAN | Technology options checked against the detected stack |
| `technical-writer` | AGENT | Documentation in the project's own stack and commands |

## The project profile

`.workflow/profile.json` holds **facts** (detected; refreshed automatically when a manifest changes); `.workflow/config.yml` holds **choices**. Config merges key by key: `<repo>/.workflow/config.yml`, then `<workspace>/.workflow/config.yml`, then `~/.workflow/config.yml`. See [templates/workflow-config.example.yml](templates/workflow-config.example.yml) for every key, and the `project-profile` skill for how roles read and trust the profile.

## Stack packs

Stack knowledge lives in packs under `.claude/skills/stacks/`, each with **Build**, **Review**, **Test**, **Commands** and **Entry points (scan mode)** sections; each role reads only the sections it needs. Packs today: `python`, `node-js`, `go`, `csharp-dotnet`, `web-frontend`, `sql-migrations`, `data-warehouse`, `iac`, `ci-cd`, `serverless-queues`. Code no pack covers gets `_generic.md` plus the universal failure modes (FM-01…FM-19) and the repo's own conventions, and reviews say which files had no pack.

Adding a stack: [docs/guides/adding-a-stack.md](docs/guides/adding-a-stack.md).

## Overlays

An overlay is a private folder that adds one team's specifics: an always-on context rule, an Argus domain pack (business invariants), ticket keys and chat settings, sign-in notes for browser QA, and daily-report sources. `overlays/*` is gitignored here; only `overlays/_template/` is tracked. Install one with `./install.sh --user --overlay overlays/<name>`, or copy it into `~/.claude/overlays/<name>/` for plugin installs.

Writing one: [docs/guides/writing-an-overlay.md](docs/guides/writing-an-overlay.md).

## Cursor

Cursor imports `.claude/agents`, `.claude/skills` and the `.claude/settings*.json` hooks, so a script install already gives Cursor the roles, the skills and the session-start detection, and both tools share `.workflow/`. The thin generated Cursor layer (always-apply rules, auto-attached stack-pack rules, command skills, and `readonly` overrides for Argus and QA) is plug-and-play Phase C; until it ships, use Claude Code for the commands. `install.sh --cursor` installs that layer once it's built.

## Migrating from the original install

Older installs used fixed backend/frontend roles and per-stack rules. In short:
- `backend-architect` and `frontend-architect` → `implementer`;
- `backend-reviewer` and `frontend-reviewer` → `argus`;
- `/api-new` → `/scaffold endpoint`, and `/api-test` → `/test-gen`;
- the per-stack rules → the packs;
- `.argus.yml` → `.workflow/config.yml` (`.argus.yml` is still read).

Details and cleanup steps: [docs/guides/migrating-from-the-original-install.md](docs/guides/migrating-from-the-original-install.md).

## Repository layout

```
CLAUDE.md                 Session contract, command table, roles (script installs load it as a rule)
.claude/                  The source tree: commands, agents (roles), skills (incl. stacks/ packs), rules, hooks, scripts
plugins/                  Generated plugins: daedalus and daedalus-qa (scripts/build-plugin.sh; don't edit)
.claude-plugin/           Generated marketplace manifest
install.sh                Script install / uninstall
templates/                workflow-config.example.yml
overlays/_template/       Overlay format and backup steps (real overlays are gitignored)
addons/graphify/          Optional /graphify build skill
scripts/                  Hub checks and builds: lint-packs, check-generic, test-detector, build-plugin
docs/                     Plans, validation results, reviews, guides, and the NRD Sight calibration corpus
.github/workflows/        CI: pack lint, generic check, detector matrix, plugin build check
```

## Maintaining

- Change `.claude/`, then run `scripts/build-plugin.sh` and commit the regenerated `plugins/`. CI fails if it's out of date (`--check`).
- Before committing, run `scripts/lint-packs.sh`, `scripts/check-generic.sh` and `scripts/test-detector.sh`.
- Keep `CLAUDE.md`'s command and role tables in step with `.claude/commands/` and `.claude/agents/`.
