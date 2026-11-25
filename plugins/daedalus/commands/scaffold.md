---
description: Scaffold a new endpoint, component, job, migration or model in the project's own framework (from the project profile and stack packs), with tests and implementation notes. Replaces /api-new.
argument-hint: <endpoint|component|job|migration|model> <name> [details]
disable-model-invocation: true
---

**Mode:** AGENT (Code) per `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/claude-code.md`. Create the new unit and its tests in the detected stack; don't expand scope. Don't commit or push.

## Rules to follow

- **Token policy:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/token-policy.md`. Refine the request into a one-paragraph brief first.
- **Stack knowledge:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/stack-knowledge.md`. The profile decides the root and framework; the pack's `## Build` and `## Test` sections decide the idioms.
- **Generic guidance:** the `api-design` skill for endpoints, the `test-strategy` skill for tests.
- **Cycle:** if the unit belongs to a plan in `docs/plans/`, implement to that plan; otherwise treat the request as minimal scope.

## Target

$ARGUMENTS

**Interpret the arguments as:** `<kind> <name> [details]`, where kind is one of:

| Kind | Typical layer | What it creates (in the project's framework) |
|---|---|---|
| `endpoint` | api | route or controller + request/response schema + service call + tests |
| `component` | ui | component + its states (loading, empty, error) + tests |
| `job` | worker | handler, consumer or scheduled job + idempotency + tests |
| `migration` | data | a new migration in the repo's migration tool + rollback notes |
| `model` | api / data | entity or schema type + persistence mapping + tests |

Missing kind or name → ask once and stop.

## Steps

1. **Pick the root.** From `.workflow/profile.json`, choose the root whose layer fits the kind; if several fit, ask which. If the profile is missing, run `detect-stack.py --stdout --root <repo>` and use the output.
2. **Load the packs** for that root (`## Build`, `## Test`; `_generic.md` if none).
3. **Copy the house pattern.** Find two or three existing units of the same kind (narrow search; a graph only if the project has one) and mirror their file layout, naming, registration (router mounting, DI registration, module exports, migration numbering) and test style.
4. **Create** the files. Validate at the boundary, handle errors explicitly, and keep handlers thin.
   - `endpoint`: follow `api-design` (status codes, one error shape, auth, pagination when it lists).
   - `job`: make it idempotent, give external calls timeouts, and handle partial failure per the pack.
   - `migration`: name and number it per the repo's tool; include down or rollback steps where the tool supports them. **Never run it**: migration commands are unsafe.
5. **Test** per `test-strategy`, in the root's framework.
6. **Run the checks** for the root: `typecheck`, `lint`, then the narrowest `test`. Only commands with confidence `script`, `derived` or `user`, or confirmed `inferred`; never `unsafe: true`. Print each command first.

## Output (handoff for Review)

1. **Files created or modified**, one line each.
2. **Tests** and the check results (command → pass/fail, with a one-line excerpt on failure).
3. **Implementation notes:** done, deferred (for example auth or rate limiting), assumptions, and env or config needed.
4. **Next:** "Run `/argus --local` to review, or `/test-gen <target>` for more tests."
