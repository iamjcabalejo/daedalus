# Plug-and-play dev workflow (Claude Code)

A stack-agnostic Plan → Code → Review → QA workflow. It detects each project's stacks, commands and integrations into `.workflow/profile.json`, and the roles, commands and reviews adapt to that profile. Team- or org-specific behavior comes from an optional overlay, never from the hub.

## Session contract

- Refine the request, then hand off (`.claude/rules/token-policy.md`).
- Plan → Code → Review/Test → Manual QA → Plan (`.claude/rules/compounding-dev-cycle.md`).
- ASK / PLAN / AGENT mean the behaviors in `.claude/rules/claude-code.md`.
- Stack knowledge: `.claude/rules/stack-knowledge.md`. Project facts are in `.workflow/profile.json`; choices are in `.workflow/config.yml`; stack packs are in `.claude/skills/stacks/`.
- Run only commands the profile marks safe (`script`, `derived`, `user`, or confirmed `inferred`); never an `unsafe: true` one without asking.
- Code graph: optional. `.claude/rules/graphify.md` applies only when the project has one.
- Do not commit, push, or open a pull request unless the user explicitly asks in this message.

## Commands

| Command | What it does |
|---|---|
| `/setup [--refresh \| --print]` | Detect the project's stacks, commands and integrations (read-only), fill gaps from its docs, confirm guessed commands and the ticket system, and write `.workflow/profile.json` (+ `.workflow/config.yml` only for choices you made). The session-start hook keeps the profile fresh automatically |
| `/feature-plan <slug>` | Write `docs/plans/<slug>.md` with one task block per detected layer, plus a mockup when the UI changes and no design exists |
| `/apply-ticket <id>` | Read one ticket (Linear, Jira or GitHub Issues) and write a layered plan. Stops after PLAN |
| `/project-manager <plan-path>` | `implementer` per layer → `test-runner` → `/argus --local` → `qa-tester` when there's a UI; rework until production ready |
| `/refine-spec <id>` | Tighten a ticket's spec and save it back. No product code |
| `/create-ticket` | Create one ticket in the configured system |
| `/new-task` | Task breakdown only (not the full cycle) |
| `/scaffold <kind> <name>` | New endpoint, component, job, migration or model in the project's own framework, with tests |
| `/test-gen <target>` | Tests for a file, endpoint, component or job in the detected test framework |
| `/code-cleanup`, `/code-optimize` | Refactor, or a measure-first performance pass |
| `/trace-flow <page or action>` | Read-only trace of a page or action to `docs/traces/<slug>.md` |
| `/argus <owner/repo#N \| --local>` | Argus review for any stack: universal failure modes plus the profile's and the diff's stack packs, material findings only (critical / important / consider, Fix / Where / Cost), checked against the linked ticket. Configured by `.workflow/config.yml` (legacy `.argus.yml` still read). Saves `docs/reviews/…`; posts only with `--post` |
| `/argus-scan <repo> [paths]` | Argus security scan to `docs/scans/<repo>-<date>.md` with rule ids and a fix brief; tickets only after you confirm |
| `/manual-test <plan-path>` | Browser QA with Playwright on the changed pages; writes `docs/qa/<slug>-qa-N.md`. N/A when the project has no UI. `--login` opens Chrome so you sign in once |
| `/daily-report [48h \| since <date time>]` | Read-only daily report (done, next working day, blockers) from local git, the ticket system and chat |

After `/feature-plan` or `/apply-ticket`, run `/clear`, then `/project-manager <plan-path>`.

Tickets and chat go through the `ticket-adapters` skill: `tickets.system` is `linear`, `jira`, `github` or `none`, and `chat` is `teams`, `slack` or `none`. Linear, Jira, Teams and Slack need their MCP connected.

## Roles

Commands live in `.claude/commands/`. Roles are defined in `.claude/agents/` and spawned with the Agent tool by name. In the `daedalus` plugin, commands and roles are prefixed (`/daedalus:feature-plan`, `daedalus:implementer`) and browser QA is the `daedalus-qa` companion; the `workflow-contract` skill has the full name table.

| Role | Mode | Does |
|---|---|---|
| `implementer` | AGENT (Code) | One layer's plan tasks in the detected stack, with tests |
| `test-runner` | AGENT (Code) | Runs the profile's safe checks, fills test gaps (test files only) |
| `argus` | AGENT (Review) | Read-only review of a diff, PR or repo |
| `qa-tester` | AGENT (QA) | Read-only browser QA, only when there's a UI; starts its own Playwright MCP server (Node.js 18+ and Chrome) |
| `tech-stack-researcher` | PLAN | Technology options against the detected stack |
| `technical-writer` | AGENT | Documentation |
