---
description: Analyze task complexity and create actionable implementation plan
argument-hint: [task]
disable-model-invocation: true
---

**Scope:** This command produces a **task breakdown and implementation plan** only. It does **not** write to `docs/plans/` and does **not** run the full Plan → Code → Review cycle. For the full compounding cycle, use **feature-plan** to create a plan at `docs/plans/<feature-slug>.md`, then run **project-manager** with that plan path.

Analyze the following task and create a clear, actionable implementation plan.

**Profile and orientation:** read `.workflow/profile.json` for the roots, layers, packs and commands (or `detect-stack.py --stdout --root <repo>` if missing). Use a graph only when the project has one (`${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/graphify.md`); otherwise narrow search. Write concrete file paths either way.

## Task

$ARGUMENTS

## Agent Definitions

**Apply the agent-selection skill** (`${CLAUDE_PLUGIN_ROOT}/skills/agent-selection/SKILL.md`): identify relevant agents from `${CLAUDE_PLUGIN_ROOT}/agents/` and apply their perspective to the analysis and implementation plan.

**Relevant roles for this command (task breakdown):** `implementer` (per layer), `tech-stack-researcher`, `technical-writer`. Use the subset that matches the task. The stack comes from the profile and the packs' Build sections, never from this file.

## Analysis framework

### 1. Task breakdown
- Understand requirements
- Identify dependencies
- List affected files/components
- Estimate complexity (Small / Medium / Large)

### 2. Time estimation
- **Small**: 1–2 hours (simple bug fix, minor feature)
- **Medium**: Half day to 1 day (new component, API endpoint)
- **Large**: 2–5 days (complex feature, multiple integrations)
- **Very Large**: 1+ week (major refactor, new subsystem)

### 3. Risk assessment
- Unknown dependencies, API limitations, data migration needs, breaking changes, third-party service issues

### 4. Implementation steps
- Sequential steps per affected layer, in order: data → api / worker → ui → infra, then testing and documentation
- For each layer, the units in the pack's natural order (for example schema → repository → service → handler, or component → page → data wiring) and tests in the root's test framework

### 5. Success criteria
- Feature works as specified; tests pass; no regressions; code reviewed; documented

## Output format

- **Task analysis**: Type, Complexity, Estimated time, Priority
- **Implementation plan**: Phased steps with checkboxes
- **Files to modify/create**
- **Dependencies**: Packages, env vars
- **Testing strategy**
- **Potential issues and mitigations**
- **Next steps**: e.g. run feature-plan then project-manager for full cycle

Provide a clear, actionable plan. For full Plan → Code → Review/Test cycle, direct the user to feature-plan and project-manager.
