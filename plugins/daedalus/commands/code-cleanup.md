---
description: Refactor and clean up code following the project's own conventions and the stack pack for its language
argument-hint: [file]
disable-model-invocation: true
---

Clean up and refactor the following code to improve readability and maintainability without changing behavior.

## Rules to follow

- **Stack knowledge:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/stack-knowledge.md`. Find the file's root in `.workflow/profile.json`, then read that root's packs (`## Build` for idioms, `## Review` to self-check). Repo conventions and `house_rules` win.
- **Skill:** `refactoring-checklist` (small, behavior-preserving steps).
- **Roles:** apply the `agent-selection` skill: the `implementer` perspective for the change, and the `argus-rubric` skill to self-check before you finish. When cleanup follows a rework list, treat it as Code phase: implement only the rework items and write implementation notes.

## Code to clean

$ARGUMENTS

## Checklist

- **Tooling:** run the root's `format` and `lint` commands from the profile (with `--fix` where the tool supports it) and `typecheck` when present. Only safe commands (confidence `script`, `derived`, `user`, or confirmed `inferred`).
- **Structure:** one responsibility per function, component or class; thin handlers; extract helpers or hooks; early returns and guard clauses.
- **Names and constants:** descriptive names in the language's conventions (booleans `is`/`has`/`can`); no magic numbers or strings.
- **Duplication:** extract repeated code into shared modules.
- **Safety:** parameterized queries only; validation at the boundary; no swallowed errors.
- **Scope:** behavior stays the same; tests still pass (run the narrowest `test`); within the Plan → Code → Review cycle, don't go beyond the rework list.

## Output

1. **Issues found** (or rework items addressed)
2. **Cleaned code**
3. **What changed and why**
4. **Implementation notes** (in a cycle): done, deferred, assumptions, and the check results

Balance clean code with pragmatism.
