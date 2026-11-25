---
name: workflow-contract
description: >-
  The session contract for the plug-and-play workflow (Daedalus): modes, the Plan → Code → Review → QA cycle,
  stack knowledge from .workflow/profile.json, safe commands, and how to name roles and commands in a script
  install vs a plugin install. Plugins can't ship always-on rules, so plugin installs load this skill (and the
  session-start context points here). Use at the start of any planning, coding, review or QA work, and
  whenever a command says to spawn a role.
---

# Workflow contract

This is the always-on contract in one place. Script installs also load it as rules (`${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/*.md`) and `CLAUDE.md`; plugin installs ship those rule files next to this skill, under `rules/`. Read the full rule when a digest below isn't enough.

## Contract

1. **Refine, then hand off.** Turn the request into a tight brief (objective, in and out of scope, constraints, forbidden) before running a command, loading a skill or spawning a role. Concise answers, no filler. Full rule: [rules/token-policy.md](rules/token-policy.md).
2. **Cycle:** Plan → Code → Review/Test → Manual QA → Plan. Each phase ends with a written artifact (plan, handoffs, review, QA report). Full rule: [rules/compounding-dev-cycle.md](rules/compounding-dev-cycle.md).
3. **Modes** ([rules/claude-code.md](rules/claude-code.md)):
   - **ASK:** no edits; ask until scope and AC are clear.
   - **PLAN:** write only `docs/plans/**` (and the ticket, for `/refine-spec` and `/create-ticket`).
   - **AGENT (Code):** `implementer` once per affected layer (data → api / worker → ui → infra), then `test-runner`.
   - **AGENT (Review):** `/argus --local`, read-only; critical/important → Critical, consider → Suggestion.
   - **AGENT (QA):** `qa-tester`, only when the profile shows a UI.
4. **Stack knowledge** ([rules/stack-knowledge.md](rules/stack-knowledge.md)): facts come from `.workflow/profile.json` (the `project-profile` skill), choices from `.workflow/config.yml`, idioms from the packs in the `stacks` skill. Load only the pack sections your role needs. Repo conventions win.
5. **Commands:** run only those with confidence `script`, `derived` or `user`, or `inferred` and confirmed. Never an `unsafe: true` one without asking. Print each command before running it.
6. **Standards** ([rules/core-standards.md](rules/core-standards.md)): UTC everywhere; config from the environment; no hard-coded secrets; validate at the boundary; parameterized queries only; explicit error handling; no secrets or personal data in logs.
7. **Code graph:** optional. Use [rules/graphify.md](rules/graphify.md) only when the project has a graph; otherwise narrow search. Never tell the user to build one.
8. **Git:** don't commit, push or open a pull request unless the user explicitly asks.

## Names per install type

| | Script install (`install.sh`) | Plugin install |
|---|---|---|
| Commands | `/feature-plan`, `/project-manager`, `/argus`, … | `/daedalus:feature-plan`, `/daedalus:project-manager`, `/daedalus:argus`, … |
| Roles (Agent tool) | `implementer`, `test-runner`, `argus`, `tech-stack-researcher`, `technical-writer`, `qa-tester` | `daedalus:implementer`, `daedalus:test-runner`, `daedalus:argus`, `daedalus:tech-stack-researcher`, `daedalus:technical-writer`; QA is the companion plugin: `daedalus-qa:qa-tester` |
| Manual QA command | `/manual-test` | `/daedalus-qa:manual-test` (companion plugin `daedalus-qa`) |
| Scripts | `<.claude>/scripts/` (`~/.claude/scripts/` or `<project>/.claude/scripts/`) | `${CLAUDE_PLUGIN_ROOT}/scripts/` |
| Rules | `<.claude>/rules/*.md` (always on) | `rules/` next to this skill (load on demand) |
| Overlay files | `<.claude>/overlays/<overlay>/` | `~/.claude/overlays/<overlay>/` |

**How to tell which applies:** when this skill's own path is inside a plugin cache (`~/.claude/plugins/…`), or the session-start context says "installed as the daedalus plugin", use the plugin column. Commands and role files name roles by their bare name; add the prefix yourself in a plugin install.

**Missing companion:** if `/project-manager` reaches Manual QA in a plugin install and `daedalus-qa` isn't installed, treat QA as **BLOCKED (env)** and tell the user to install it (`/plugin install daedalus-qa@daedalus`). Projects without a UI never need it.
