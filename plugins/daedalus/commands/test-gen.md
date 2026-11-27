---
description: Generate or extend tests for a file, endpoint, component or job using the project's detected test framework, fixtures and layout (from the project profile and the stack pack's Test section). Replaces /api-test.
argument-hint: <file | endpoint | component | symbol> [AC-n ...]
disable-model-invocation: true
---

**Mode:** AGENT (Code), test step, per `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/claude-code.md`. Write or update **test files only**; never change the code under test (report bugs instead). Don't commit or push.

## Rules to follow

- **Token policy:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/token-policy.md`.
- **Stack knowledge:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/stack-knowledge.md`: the profile's `roots[].test.frameworks` and `roots[].test.patterns`, and the pack's `## Test` section.
- **What to test:** the `test-strategy` skill.

## Target

$ARGUMENTS

**Interpret the arguments as:** a file path, an endpoint (`GET /orders/{id}`), a component, or a symbol, optionally followed by AC ids from a plan to map tests to. Empty → ask once and stop.

## Steps

1. **Locate** the target and its root in `.workflow/profile.json` (or `detect-stack.py --stdout --root <repo>` if missing). Read the target and the tests that already cover it.
2. **Load** the root's packs (`## Test`; `_generic.md` if none) and the `test-strategy` skill.
3. **List scenarios** before writing: the behaviors and AC to prove, the unhappy paths (invalid input, unauthorized, forbidden, not found, conflict, upstream failure, empty), and the boundaries. Skip what existing tests already prove.
4. **Write tests** in the root's framework, layout and naming, reusing the repo's fixtures and factories. Mock only at the edges the pack names. No sleeps; freeze time; seed randomness.
5. **Run** the new tests, then the root's full `test` command. Run only the commands `workflow.py config commands --json` reports `trusted: true` and `unsafe: false` (the `project-profile` skill); ask the user before any other, or run `/setup`. Never an end-to-end suite unless the user confirms. Print each command first.

## Output

1. **Tests added or changed**, each with the behavior or AC it proves.
2. **Run results:** command → pass/fail, with a one-line excerpt per failure, separating failures in the new tests from pre-existing ones.
3. **Bugs found:** a failing test that reveals a real bug stays failing (or is marked expected-failure per the repo's convention) and is reported with file:line; don't fix the code here.
4. **Gaps and setup:** scenarios not covered and why; fixtures, env or services the tests need.
