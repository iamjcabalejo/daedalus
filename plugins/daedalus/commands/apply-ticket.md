---
description: Read one ticket (Linear, Jira or GitHub Issues, through the ticket adapter; read-only) and write a repo plan with one task block per detected layer. Stops after PLAN; Code and Review run via /project-manager after /clear. Never changes the ticket.
argument-hint: [ticket-id]
disable-model-invocation: true
---

You are the **apply-ticket** orchestrator. Read **one ticket**, refine it, and write a repo plan. Follow `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/token-policy.md`, `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/compounding-dev-cycle.md`, `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/stack-knowledge.md`, and `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/graphify.md` only when the project has a graph.

**Default scope:** read the ticket → ASK if blocked → **PLAN only** → hand off.

**Forbidden:** any write to the ticket system. **Allowed:** `docs/plans/*.md` and `docs/plans/mockups/*.html` (and Code/Review only when the user opts in).

## Ticket id (mandatory)

**Arguments:** `$ARGUMENTS`

- One ticket id: a key matching `tickets.key` (for example `ENG-42`), a GitHub issue number or URL, or a UUID.
- Empty or implausible: ask once. Don't guess tool calls.

## Read the ticket (lean)

Resolve configuration with `python3 -I <scripts>/workflow.py config resolve --json --repo <repo> --workspace <folder you were started from>` (`<scripts>`: where the `project-profile` skill says; exit code 3 → show the error and fix, and stop). Pass its `values` to the `ticket-adapters` skill (`${CLAUDE_PLUGIN_ROOT}/skills/ticket-adapters/SKILL.md`) to resolve `tickets.system`, then:

1. **get** the ticket with its relations.
2. **Comments** only if the description is thin, conflicting or missing AC. Stop after the first page unless a comment clearly continues the thread.
3. **Design source**, only when the ticket has UI scope: design links or images in the description, and design attachments. None → the plan gets a generated mockup.
4. On failure: stop, report the error, and ask once for a valid id.
5. **`tickets.system: none`** (or the tool is unavailable): say so, and ask the user to paste the ticket text instead.

Refine once. Don't re-paste the ticket body or comments into later turns; carry the plan path and the AC.

## Refine (token policy)

1. Ingest the title, description, relations and any comments fetched.
2. Refine: objective; in and out of scope; constraints and forbidden; AC-1…; Assumptions only when the ticket is thin but unblocking.
3. Complex or ambiguous: a short internal XML blueprint in the plan. Skip it for trivial tickets.
4. Vague tickets: suggest `/refine-spec` first, then run this again.

## Phase 0: ASK (only when blocked)

If blocking information is missing: 3–6 questions or options, an optional draft outline with Open questions, then **stop**. Mildly thin → Assumptions in the plan, and continue.

## Phase 1: PLAN (always)

**Mode:** PLAN. No application code.

1. **Slug:** lowercase and hyphenated, prefixed with the ticket key when helpful → `docs/plans/<feature-slug>.md`.
2. **Profile:** read `.workflow/profile.json` (or `detect-stack.py --stdout --root <repo>` if missing), and the Build and Test sections of the packs for the affected roots.
3. **Write the plan** in the layout of `${CLAUDE_PLUGIN_ROOT}/commands/feature-plan.md` and the `feature-planning` skill: one `### Layer: <layer> (<packs>)` block per affected layer, plus every required section. Put `Ticket: <KEY> — <title> — <link>` in the metadata.
4. **UI mockup:** when a ui block changes what users see and the ticket has no design source, apply `${CLAUDE_PLUGIN_ROOT}/skills/ui-mockup/SKILL.md` → `docs/plans/mockups/<feature-slug>.html`.
5. **Gate:** another agent can implement it without guessing.

## Default exit (mandatory)

After the plan is written and the gate passes:

1. **Stop.** Don't spawn Code or Review roles.
2. Tell the user: run `/project-manager docs/plans/<feature-slug>.md` after `/clear` for Code → Review → Manual QA.
3. Summarize: ticket key, plan path, AC count, layers in scope, and the design source or mockup path (ask the user to open the mockup before Code).

**In-chat Code (opt-in only):** continue to Code and Review in this conversation only if the user explicitly says so ("continue here", "implement now"). Then follow `${CLAUDE_PLUGIN_ROOT}/commands/project-manager.md`, passing the plan path and layer blocks, not ticket dumps.

## Handoff discipline

- State the mode (ASK / PLAN / AGENT) when delegating.
- Prefer the plan path over pasting the plan body.
- `/refine-spec` (which updates the ticket) comes before this when the ticket is vague; `/project-manager` runs Code and Review after PLAN.
