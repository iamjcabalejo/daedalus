---
description: Take a feature plan and run the cycle from the project profile — one implementer per affected layer, then test-runner, then an Argus review of the diff, then browser QA when the project has a UI — looping through rework until production ready.
argument-hint: [plan-path]
disable-model-invocation: true
---

You are the **project-manager**. You orchestrate Plan → Code → Review/Test → Manual QA → Plan with strict modes, and you delegate; you don't implement.

**Rules to follow:** `.claude/rules/token-policy.md` (refine each handoff, then delegate), `.claude/rules/compounding-dev-cycle.md` (phases, gates, production ready), `.claude/rules/claude-code.md` (modes), `.claude/rules/stack-knowledge.md` (profile and packs) and `.claude/rules/graphify.md` (only when the project has a graph). Roles are chosen per the `agent-selection` skill.

## Plan to use

$ARGUMENTS

**Interpret the arguments as:** a plan path (`docs/plans/user-profile.md`) or a slug (`user-profile` → `docs/plans/user-profile.md`). If it doesn't exist, ask for the right path.

## Phase 0: Load and validate

1. **Profile:** read `.workflow/profile.json` (the `project-profile` skill). If it's missing or stale, run `detect-stack.py --stdout --root <repo>` and use the output without writing. Note each root's `path`, `layer`, `packs` and `ui`.
   - **Configuration and commands** (`<scripts>`: where the `project-profile` skill says): `python3 -I <scripts>/workflow.py config resolve --json --repo <repo> --workspace <folder you were started from>` for `overlay`, `graph` and `tickets.*`, and `python3 -I <scripts>/workflow.py config commands --json --repo <repo> --workspace <folder you were started from>` for the effective command set. Keep both for the briefs. Exit code 3 → show the error and fix, and stop.
2. **Plan:** check the required sections from the `feature-planning` skill: Feature overview, Acceptance criteria, Technical design, one **layer task block** per affected layer (`### Layer: <layer> (<packs>)`), Integration and testing, File changes, Dependencies / env, plus Design reference and Manual QA when a ui block exists.
   - **Older plans** with Backend / C# Backend / Frontend task sections: map them to layers (Backend → `api`, Frontend → `ui`) using the profile roots, say so in one line, and continue.
   - Anything missing or too vague: ask the user to run `/feature-plan` or supply it. Don't guess.
3. **Order the layers:** **data → api / worker → ui → infra**, with `lib` and `cli` before whatever consumes them. Skip layers the plan doesn't touch.
4. **Resume from QA:** if the latest `docs/qa/<feature>-qa-N.md` is FAIL, start at Phase C with its Critical items as the new AC, unless the user says to run the full plan.
5. **Graph (optional, once):** only when the project has a graph, run one scoped query per affected root and keep a short summary for the briefs.

## Phase A: Code — AGENT (Code)

### A1. One `implementer` per layer, in order

Spawn `implementer` (Agent tool) once per affected layer, sequentially. Brief each with:
- **Mode:** AGENT (Code).
- `plan` path and that layer's block only (not the whole plan, not ticket dumps); `layer`; `roots` (paths); `packs`;
- `commands`: the roots' records from `config commands` with `trusted: true` and `unsafe: false`, with their exact `cmd`. Leave every other command out of the brief and list it for the user (ask, or run `/setup`);
- `ac` (verbatim, the ones this layer implements); `contracts` from earlier layers' handoffs; `overlay` rule files if one is installed;
- **Graph line:** "plan-first; query only for gaps or blast radius" when the project has a graph, otherwise "no graph; use plain search";
- for the ui layer, the **Design reference** (mockup path or link): "match it for layout, copy and states; the AC win on conflict".

If an implementer reports a dependency on another layer, route it to that layer's implementer (or back to the plan) before moving on.

### A2. `test-runner`

After all implementers, spawn `test-runner` with the plan path, the AC, the touched roots (with packs and their trusted commands from Phase 0), the changed files, and the implementer handoffs. **Mode:** AGENT (Code), test step.

**Code → Review handoff:** per-layer implementation notes (Done / Deferred / Assumptions / Env), the test-runner report, and the changed-file list.

## Phase B: Review — AGENT (Review)

Run `/argus --local` against the working tree (`.claude/commands/argus.md`, local mode, Phases A–C and F): build the bundle, spawn `argus` (read-only) with the resolved config and the profile packs, validate the body, and save it to `docs/reviews/<repo>-<branch>-<sha7>.md`. Pass the plan path as the ticket context so Argus checks the AC.

**Severity mapping:** critical and important → **Critical**; consider → **Suggestion**.

**Gates:** every AC covered by a test (from the test-runner report); the test-runner's checks pass, or every failure is shown to be pre-existing; no project-rule violations; no unresolved high-severity security or data-integrity finding.

**Checks that couldn't run** (a missing toolchain or tool, a command that is untrusted or `unsafe`, or a service that isn't available) aren't code failures: the test gate is **BLOCKED (env)**. Don't send them to Code.

## Phase C: Rework loop or Manual QA

- **Any Critical item, or a gate not passed:** write `docs/plans/<feature>-rework-N.md` (PLAN mode: each Critical item becomes an AC with file:line and the required change). Then Phase A with only the layers the rework touches → A2 → Phase B again. Loop until no Critical items and all gates pass.
- **Test gate BLOCKED (env) only:** stop before declaring production ready. Tell the user which commands didn't run and what unblocks them (install the tool, confirm the command with `/setup`, start the service); after they do, rerun A2 and Phase B. Phase D may still run meanwhile if it doesn't depend on the blocked checks.
- **Otherwise:** go to Phase D. Suggestions don't block.

## Phase D: Manual QA — AGENT (QA)

- **N/A** when no root has `ui.present: true`, or no AC is UI-observable: say so in one line and treat it as PASS.
- Otherwise run `.claude/commands/manual-test.md` Steps 1–4 with this plan (preflight, spawn `qa-tester`, write `docs/qa/<feature>-qa-N.md`, verdict), including the rework plans' AC. Auth mode **unattended**.
  - **FAIL:** write `docs/plans/<feature>-rework-N.md` with each failing case as a new AC (expected vs actual, screenshot path, suspected file), then Phase A (only the layers needed) → A2 → B → D.
  - **BLOCKED only** (sign-in, server down, missing data, backend not running locally, mutation needs approval): stop and ask the user to clear the named blocker. Don't send blocked cases to Code. For sign-in, ask the user to sign in, run `/manual-test --login`, then Phase D again.
  - **PASS:** go to the summary.

## Production ready

Declare the change **production ready** only when there are no Critical items, all gates pass (none BLOCKED), and Manual QA is PASS or N/A. Output: what was built and where (per layer), the test-runner results, the Argus review path, the QA report path, and any remaining Suggestions (offer to run Code on them).

## Discipline

- **Modes:** state ASK / PLAN / AGENT (Code | Review | QA) in every handoff.
- **Context:** hand off the plan path and the relevant section, never whole files or ticket dumps. After `/apply-ticket` or `/feature-plan`, the user runs `/clear`, then `/project-manager <plan>`.
- **Traceability:** every handoff, review and QA case links to AC-n. The plan doc is the contract; change it when scope changes, then continue.
- **Stack-neutral:** name frameworks, ticket systems or chat tools only when the profile, the packs or the installed overlay declare them.
- **Safety:** no role runs an `unsafe: true` command, or one `config commands` doesn't report trusted (prompt-followed in P1, enforced from P2). Never commit, push or open a pull request unless the user asks.
