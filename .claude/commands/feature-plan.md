---
description: Create a feature plan with one task block per detected layer (from the project profile). Writes only docs/plans. Output is for /project-manager.
argument-hint: [feature-slug]
disable-model-invocation: true
---

**Scope of this command:** PLAN only. Write `docs/plans/<feature-slug>.md` and, when the mockup rule below applies, `docs/plans/mockups/<feature-slug>.html`. No application code, no other files, no build or test commands, and no Code or Review subagents. If asked to implement, decline and point to `/project-manager` with this plan.

## Rules to follow

- **Token policy:** `.claude/rules/token-policy.md`. Refine the request into a tight brief first, then write the plan.
- **Feature-planning skill:** `.claude/skills/feature-planning/SKILL.md` defines the layer blocks, the required sections and the checklists. Follow it.
- **Stack knowledge:** `.claude/rules/stack-knowledge.md`. Read `.workflow/profile.json`, and the Build and Test sections of the packs for the layers you plan.
- **Orientation:** `.claude/rules/graphify.md` only when the project has a graph; otherwise narrow search. Write concrete paths into File changes either way.
- **Cycle:** the Plan phase of `.claude/rules/compounding-dev-cycle.md`. The plan is done when another agent can implement it without guessing.
- **UI mockup:** when a ui-layer block changes what users see and the request supplies no design (link, screenshot, image), apply `.claude/skills/ui-mockup/SKILL.md`. The mockup is the visual contract for the ui implementer and `qa-tester`.

## Feature / plan target

$ARGUMENTS

**Interpret the arguments as:** a feature name or slug (`user-profile`). The path is `docs/plans/<feature-slug>.md`; a given path is used only if it's under `docs/plans/`. Empty → ask for the feature name.

## Steps

1. **Profile.** Read `.workflow/profile.json`. If it's missing or stale, run `detect-stack.py --stdout --root <repo>` (read-only) and use the output; suggest `/setup` in the final message.
2. **Refine** the request: objective, in and out of scope, constraints, AC-1…
3. **Find the affected layers.** Map the change to profile roots and layers. Read only what's needed (the graph or narrow search, then the files it points to).
4. **Load the packs** for those roots (`## Build`, `## Test`). Roots without a pack use `_generic.md`; say so under Technical design.
5. **Write the plan** with the sections below.
6. **Mockup** first, when the rule above applies.

## Plan layout

```markdown
# <Feature title>

- **Type:** Feature | Bug fix | Refactor | Infrastructure
- **Complexity:** Small | Medium | Large | Very large — one-line reason
- **Estimated effort:** …
- **Ticket:** <key + link, or none>
- **Metadata:** Security: critical / Performance: critical (when applicable)

## 1. Feature overview
Problem, audience, key functionality.

## 2. Acceptance criteria
- **AC-1** Given … when … then …

## 3. Technical design
Components, contracts (endpoints with method, path, request and response; events; schema; props), data model, data flow, failure handling. Name the packs and repo conventions it follows.

## 4. Layer tasks
### Layer: <layer> (<packs>)
- **Root(s):** `<path>`
- **Needs:** contracts from earlier layers · **Produces:** contracts for later layers
- **Tasks:** phased checkboxes with file paths
- **Tests:** AC-n → test, in `<framework>`
- **Commands:** test / lint / typecheck / build from the profile; flag missing, unconfirmed or unsafe ones

(one block per affected layer, in order: data → api / worker → ui → infra; lib and cli before their consumers)

## 5. Integration and testing
## 6. File changes
## 7. Dependencies / env
## 8. Design reference
## 9. Manual QA
## 10. Risks / potential issues
## 11. Next steps
Run `/project-manager docs/plans/<feature-slug>.md` (after `/clear`).
```

- **Design reference:** when a ui block exists: the supplied design, or the generated mockup path with the states and AC it covers, or "No visual change". Otherwise "N/A: no UI".
- **Manual QA:** when any AC is UI-observable and a root has `ui.present: true`: base URL (the profile's `ui.dev_url`, or `qa.base_url`), routes, required role and a visible role check (never an email), test data, mutations allowed (default: none), backend needed. Then a table: AC | Route | Steps | Expected (observable) | Mockup state, with at least one row per UI-observable AC. Otherwise "N/A: no UI-observable AC".

## Planning perspective

Apply the `agent-selection` skill for **planning only**: `tech-stack-researcher` for technology choices, and the `implementer` role's view of each layer to check the tasks are buildable. Don't spawn them for Code or Review.

## Output

1. Write the plan (and the mockup first, when it applies).
2. Confirm the plan path and say: "Run `/project-manager docs/plans/<feature-slug>.md` after `/clear` to run Code → Review → Manual QA. This command wrote the plan only."
3. If a mockup was generated, give its absolute path and ask the user to open it before Code.
