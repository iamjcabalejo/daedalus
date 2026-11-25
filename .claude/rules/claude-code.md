# Claude Code mode map

Mode names in this workflow mean the following in Claude Code. State the mode when delegating.

| Mode | Behavior |
|---|---|
| **ASK** | Don't edit files. Ask until scope and acceptance criteria are unambiguous. |
| **PLAN** | Create or edit only `docs/plans/**`, including the UI mockup `docs/plans/mockups/<feature>.html` when no design was supplied (and, for `/refine-spec` or `/create-ticket`, the ticket through the `ticket-adapters` skill). Don't change application code or run build, test or install commands. |
| **AGENT (Code)** | Implement the plan. Spawn `implementer` once per affected layer, in plan order (data → api / worker → ui → infra), then `test-runner`. They may edit files and run the profile's safe commands. |
| **AGENT (Review)** | Run `/argus --local` (the `argus` role). It's read-only and returns findings; critical and important map to **Critical**, consider to **Suggestion**. The parent writes `docs/plans/<feature>-rework-N.md` when Critical items exist. |
| **AGENT (QA)** | Only when the profile shows a UI (`ui.present: true`). Spawn `qa-tester`: it drives a Playwright browser on the exact pages changed and checks each acceptance criterion. It doesn't edit code. The parent writes `docs/qa/<feature>-qa-N.md`; a FAIL becomes a rework plan. |

Role files live in `.claude/agents/`; identity is the `name` field. In a plugin install, spawn roles as `<plugin>:<name>`.

After a plan is written, `/clear`, then `/project-manager <plan-path>`, so plan-authoring context doesn't stack into Code.

Don't commit, push or open a pull request unless the user explicitly asks.
