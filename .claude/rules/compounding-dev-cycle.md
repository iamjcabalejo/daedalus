# Compounding Development Cycle

Claude Code executes ASK / PLAN / AGENT as defined in `.claude/rules/claude-code.md`.

**Plan → Code → Review/Test → Manual QA → Plan.** Each phase ends with a written artifact. Switch modes explicitly (ASK → PLAN → AGENT). Full orchestration: `.claude/commands/project-manager.md`.

## Before modes: refine, then hand off

Apply the `token-policy.md` session entry flow first, then enter ASK or PLAN, or delegate with that brief — not a vague restatement.

## Modes

| Mode | When | Output | Exit |
|------|------|--------|------|
| **ASK** | Scope or AC unclear | Questions or structured requirements | Scope and success criteria unambiguous |
| **PLAN** | Scope clear | `docs/plans/<feature>.md` (AC, one task block per affected layer, File changes, Design reference, Manual QA) + `docs/plans/mockups/<feature>.html` when the UI changes and no design exists | Another agent can implement without guessing |
| **AGENT (Code)** | Plan ready | `implementer` per layer, then `test-runner`: code + tests + implementation notes (Done / Deferred / Assumptions / Env) + test report | Handoff to Review |
| **AGENT (Review)** | Code done | `/argus --local` review: findings (critical / important / consider) mapped to Critical / Suggestion | No Critical → Manual QA; else rework PLAN |
| **AGENT (QA)** | Review has no Critical; the profile shows a UI and the plan has UI-observable AC | `docs/qa/<feature>-qa-N.md` + screenshots (PASS / FAIL / BLOCKED per AC) | All UI AC PASS → production ready; FAIL → rework PLAN; BLOCKED → the user clears it |

## Transition (initial)

1. ASK (if needed) → 2. PLAN → 3. Code → 4. Review → 5. Manual QA (or N/A) → 6. production ready, or 7. rework PLAN → Code → Review → Manual QA until no Critical and no QA FAIL.

## Phase rules (short)

- **PLAN:** read `.workflow/profile.json` and the packs for the affected layers (`stack-knowledge.md`); use a graph only when the project has one (`graphify.md`); write concrete File changes. After PLAN, run `/clear`, then `/project-manager <plan-path>`. When a ui block changes what users see and no design was supplied, generate the mockup (`.claude/skills/ui-mockup/SKILL.md`). Write the Manual QA section (route, data, per-AC steps) when there's a UI.
- **Code:** plan-first; implement only to plan, one layer at a time; run only the commands `workflow.py config commands` reports trusted and not `unsafe` (ask otherwise, or run `/setup`). Pass the plan path and the layer's section, not full dumps. With a graph, `graphify update .` after substantive edits.
- **Review:** diff-first; findings carry file:line, the fix and the severity. Critical → rework plan `docs/plans/<feature>-rework-N.md`.
- **Manual QA:** AC-driven only. `qa-tester` opens the exact route in Playwright, runs each UI-observable AC, compares with the mockup, and proves each verdict with a screenshot (`.claude/skills/manual-qa/SKILL.md`). FAIL → rework plan; BLOCKED (auth, env, data) → ask the user.
- **Production ready:** every AC covered by tests; the test-runner's checks pass (or failures are shown to be pre-existing); no rule violations; no unresolved high-severity security or data-integrity issue; no Critical review item; Manual QA PASS (or N/A) for every UI-observable AC.

## Cross-phase

- `token-policy.md` for prose budget; `stack-knowledge.md` for stacks and commands; `graphify.md` only with a graph; `core-standards.md` always.
- The plan doc is the contract. Trace work to AC-n. No verbal-only handoffs.
