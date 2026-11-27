---
description: Manually test a feature in a real browser with Playwright. Opens the exact pages that changed, walks every acceptance criterion, compares with the plan's mockup, and writes docs/qa/<slug>-qa-N.md with screenshots. Runs automatically as Phase D of /daedalus:project-manager.
argument-hint: [plan-path] [AC-n ...] | --login [role] | --logout
disable-model-invocation: true
---

**Scope of this command:** **AGENT (QA)**. Verify; do not fix. Do not change application code, config, tests, or the plan. The only files you create are `docs/qa/<slug>-qa-N.md` and screenshots under `docs/qa/<slug>/run-N/`. All browser work goes to the `qa-tester` subagent.

## Rules to follow

- **Token policy:** the daedalus:workflow-contract skill's rules/token-policy.md. Refine the plan into a test brief, then hand off.
- **Cycle:** Manual QA phase in the daedalus:workflow-contract skill's rules/compounding-dev-cycle.md; mode map in the daedalus:workflow-contract skill's rules/claude-code.md.
- **Profile:** `.workflow/profile.json` (the `project-profile` skill): the UI root, its `ui.dev_url`, `ui.router` and `commands.dev`.
- **Configuration and commands:** `<workflow>` is `${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py` in a plugin install (this plugin's own copy), otherwise `scripts/workflow.py` in the `.claude/` folder this command was loaded from (`~/.claude/` for a user-level install, else `<workspace root>/.claude/`). Run `python3 -I <workflow> config resolve --json --repo <repo> --workspace <folder you were started from>` once and pass its `values` on (`qa.base_url`, `qa.auth`, `overlay`); exit code 3 → show the error and fix, and stop. Don't read config files yourself.
- **Orientation:** diff-first. The plan's File changes and the diff name the page; use a graph only when the project has one, and only if the route is still unclear.
- **Skill:** `${CLAUDE_PLUGIN_ROOT}/skills/manual-qa/SKILL.md` (case rules, verdicts, safety). Report shape: `${CLAUDE_PLUGIN_ROOT}/skills/manual-qa/report-template.md`.

## Target

$ARGUMENTS

**Interpret the arguments as:** a plan path or slug (`eng-42-session-pagination` → `docs/plans/eng-42-session-pagination.md`), optionally followed by AC ids to re-run only those (`AC-2 AC-4`). Empty or missing plan → ask for the plan path and stop. `--login [role]` or `--logout` → run **Sign-in modes** and stop.

## Sign-in modes

Rules: **Authentication** in `${CLAUDE_PLUGIN_ROOT}/skills/manual-qa/SKILL.md`. The user signs in; the tester only reuses the session.

- **`--login [role]`:** run the Node, base URL, dev-server, and production checks from Step 1.5. Tell the user: "Chrome will open on the sign-in page. Complete the sign-in (use the QA account for <role> if you have one). I'll wait up to 5 minutes." Spawn `qa-tester` with mode `login`, auth `attended`, base URL, and role. Reply with the probe result and that later runs reuse this session until the app's session expires.
- **`--logout`:** spawn `qa-tester` with mode `logout`. To wipe everything, the user deletes this workspace's `mcp-chrome-*` folder under `~/Library/Caches/ms-playwright/`.

## Step 1: Preflight (you, before spawning)

1. **Load the plan:** Acceptance criteria, the ui-layer block (older plans: Frontend tasks), File changes, Design reference, Manual QA. Include AC from `docs/plans/<slug>-rework-*.md`.
2. **Applicability:** no root with `ui.present: true` in the profile, or no ui block and no UI-observable AC → reply `Manual QA: N/A — <reason>` and stop. Write nothing.
3. **Cases:** use the plan's Manual QA table. If it is missing, derive at least one case per UI-observable AC from the AC text, File changes, and the router file. Each case cites its AC. No case without an AC.
4. **Changed files:** `git status --short` and `git diff --stat` against the base branch in the repo that holds the UI root. Pass the list to the tester.
5. **Environment:**
   - **Node:** `command -v npx`. Missing → stop: "Install Node.js 18+ (`brew install node`) so qa-tester can start Playwright."
   - **Base URL:** from the plan's Manual QA, else the resolved `qa.base_url`, else the UI root's `ui.dev_url` in the profile. Must be `localhost` or `127.0.0.1`.
   - **Dev server:** `curl -s -o /dev/null -w '%{http_code}' <base>`. Down → start the UI root's `dev` command in the background only when `python3 -I <workflow> config commands --json --repo <repo> --workspace <folder you were started from>` reports it `trusted: true` and `unsafe: false`, from `<repo>/<root.path>`, and poll up to 60 s. No dev command, an untrusted or unsafe one, or still down → report the server BLOCKED and ask the user to start it (or run `/daedalus:setup` to trust the command).
   - **Production guard:** find the API base-URL variable the UI uses (for example `VITE_API_URL`, `NEXT_PUBLIC_API_URL`, `REACT_APP_API_URL`) in the active env file (`.env.local`, else `.env`) and compare it with the production env file (`.env.production`, `.env.prod`). Equal → stop. Never test against production. Print only "local", "staging" or "other", not the URL.
   - **Backend scope:** the plan has api or worker blocks and the API isn't running locally → backend-dependent cases go in as BLOCKED (env), not FAIL.
6. **Mockup:** if `docs/plans/mockups/<slug>.html` exists, serve it: `python3 -I -m http.server 8765 --bind 127.0.0.1 --directory <plan dir>/mockups` in the background. Pass `http://127.0.0.1:8765/<slug>.html`. Otherwise pass the design link or "none".
7. **Run number:** next free N for `docs/qa/<slug>-qa-N.md`. Create `docs/qa/<slug>/run-N/`.
8. **Auth mode:** standalone runs are `attended`; tell the user (one line): "Chrome will open. If it asks you to sign in, complete the sign-in; the tester waits up to 3 minutes." Runs from `/daedalus:project-manager` are `unattended`: no wait.

## Step 2: Spawn `qa-tester` — AGENT (QA)

One tester at a time; the Playwright profile is shared.

- **Pass:** plan path; AC verbatim; cases (AC, route, steps, expected, mockup state); base URL; the resolved `qa.auth` and `overlay`; mockup URL or design link; changed files; absolute screenshot directory; mutation policy (from Manual QA, default "none"); backend availability; mode `test`; auth mode; required role and its role check (from Manual QA).
- **Instruct:** "Mode: AGENT (QA). Follow `${CLAUDE_PLUGIN_ROOT}/skills/manual-qa/SKILL.md`. Run only these cases, in AC order, on the exact routes. Diff-first. Do not edit code. Return the report body in `${CLAUDE_PLUGIN_ROOT}/skills/manual-qa/report-template.md` structure and the list of screenshot paths."

## Step 3: Write the report

- Write `docs/qa/<slug>-qa-N.md` from the tester's return and the template header (commit `git rev-parse --short HEAD`, dirty flag, date UTC, API env label).
- Check every evidence path exists (`ls`). A PASS without its screenshot becomes BLOCKED (no evidence).
- Stop the mockup server if you started it. Leave the dev server running and say so.

## Step 4: Verdict and handoff

- **PASS:** every UI-observable case PASS, the rest N/A.
- **FAIL:** any FAIL or Critical item. From `/daedalus:project-manager`: return to its rework loop. Standalone: tell the user to run `/daedalus:project-manager docs/plans/<slug>.md`; it resumes from this report.
- **BLOCKED:** list each blocker with the exact user action. No rework plan; blocked cases are not code failures. `AUTH_REQUIRED` or auth-expired → "run `/manual-test --login`, then re-run". auth-role → "sign in as <role> with `/manual-test --login <role>`, then re-run those AC".

**Reply (≤15 lines):** verdict, the Results table (AC | verdict | screenshot), Critical items, blockers, report path.
