---
name: feature-planning
description: Break a feature into implementation tasks per detected layer (data, api, worker, ui, infra, lib, cli) from the project profile. Use when planning features, creating implementation plans, or running /feature-plan or /apply-ticket. Writes the plan only; no implementation.
---

# Feature planning

## Plan file only

When this skill is used (including by `/feature-plan` and `/apply-ticket`), write only `docs/plans/<feature-slug>.md` and, when `.claude/skills/ui-mockup/SKILL.md` applies, `docs/plans/mockups/<feature-slug>.html`. No application code and no other files. Do not spawn Code or Review subagents. If asked to implement, decline and point to `/project-manager` with the plan. PLAN behavior: `.claude/rules/claude-code.md`.

## Rules to follow

- **Profile first:** read `.workflow/profile.json` (the `project-profile` skill). If it's missing or stale, run `detect-stack.py --stdout --root <repo>` and use its output without writing. Which roots, layers, packs and commands exist decides the task blocks.
- **Packs:** for each layer you plan, read the `## Build` and `## Test` sections of its packs (`skills/stacks/<pack>.md`) so the technical design uses the project's idioms. Roots with no pack use `_generic.md`; say so in the plan.
- **Orientation:** with a graph (`integrations.graph.graphify: true`, or `graph: graphify` in `.workflow/config.yml`), apply `.claude/rules/graphify.md` before exploring; otherwise use narrow search. Either way, write concrete **File changes**.
- **Compounding cycle:** the Plan phase in `.claude/rules/compounding-dev-cycle.md`: unambiguous scope, acceptance criteria and technical approach in one plan doc that another agent can implement without guessing.

## Layers

Plan one **task block per affected layer**, named after the layer and its packs, for example `### Layer: api (python)`, `### Layer: ui (web-frontend)`, `### Layer: data (sql-migrations)`. Take layers from `roots[].layer`; when one root serves several layers (a monolith), split blocks by layer anyway and give each the same root path.

**Order** (used by `/project-manager`): **data → api / worker → ui → infra**, with `lib` and `cli` placed before whatever consumes them. A block lists what it needs from earlier blocks (contracts) and what it produces for later ones.

Each block contains:
- **Root(s):** `roots[].path`, and the packs.
- **Tasks:** phased checkboxes in the pack's natural order (for example schema → repository → service → handler, or component → page → state/data wiring → polish), each with the files to create or modify.
- **Contracts:** endpoints (method, path, request and response shape), events, schema or component props that other layers depend on.
- **Tests:** what proves each AC in this layer, in the root's test framework (`roots[].test.frameworks`).
- **Commands:** the root's checks from the profile (`test`, `lint`, `typecheck`, `build`). Flag any that are missing, `inferred` and unconfirmed, or `unsafe`.

## Required sections (for /project-manager)

- **Scope / Metadata** (optional): `Security: critical`, `Performance: critical` when applicable; the ticket key and link when there is one.
- **Feature overview:** problem, audience, key functionality.
- **Acceptance criteria:** testable conditions, numbered AC-1, AC-2, …
- **Technical design:** components, contracts, data model, data flow, failure handling.
- **Layer task blocks:** one per affected layer, as above.
- **Integration and testing:** critical paths across layers, unit and integration areas.
- **File changes:** every path, create or modify, grouped by root.
- **Dependencies / env:** packages (with the root's package manager), env vars (name, purpose, example, required or optional), config changes.
- **Design reference** (when a ui block exists): the supplied design link or attachment, the generated mockup path, or "No visual change".
- **Manual QA** (when any AC is UI-observable and a root has `ui.present: true`): base URL (from the profile's `ui.dev_url` or `qa.base_url`), routes, required role and visible role check (no emails), test data, mutations allowed, and one row per AC (route, steps, expected result, mockup state). Otherwise write "N/A: no UI-observable AC".
- **Risks / potential issues** (recommended): 2–5 bullets with mitigations.
- **Next steps:** run `/project-manager <plan path>`.

## Per-block checklist

- [ ] Root, packs and order stated
- [ ] Files to create or modify listed
- [ ] Contracts described for every cross-layer dependency
- [ ] Tests named for each AC in the layer
- [ ] Commands available, or the gap flagged

## Plan-mode checklist (before the plan is done)

- [ ] All required sections are present, with one block per affected layer.
- [ ] Acceptance criteria are testable and numbered.
- [ ] UI changes: Design reference set; mockup generated when no design was supplied; Manual QA has a case for every UI-observable AC.
- [ ] No framework appears that the profile, the packs or the repo don't show.
- [ ] Only the plan (and the mockup, when applicable) was written.
- [ ] The plan path is `docs/plans/<feature-slug>.md`, and the user is pointed to `/project-manager` with it.

## Context to pass on

Feature overview, technical design, layer blocks with contracts, file changes, dependencies, and the user flows behind the AC.
