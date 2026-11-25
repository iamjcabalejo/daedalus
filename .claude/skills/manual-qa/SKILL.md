---
name: manual-qa
description: Browser-based manual QA against a plan's acceptance criteria with Playwright MCP. Test-case rules, navigation protocol, mockup comparison, verdicts, and safety. Used by the qa-tester agent and the /manual-test command.
---

# Manual QA

The acceptance criteria are the test oracle. The mockup or supplied design is the visual reference. Test only what changed.

## Inputs

Plan path, AC (verbatim), test cases (each linked to an AC), base URL, changed files, mockup URL or design link, screenshot directory, mutation policy, backend availability, mode (`test` | `login` | `logout`), auth mode (`attended` | `unattended`), required role and its role check.

## Authentication

The user signs in. The tester reuses that browser session and never handles credentials.

- **Session store:** Playwright MCP keeps one persistent Chrome profile per workspace (macOS: `~/Library/Caches/ms-playwright/mcp-chrome-<workspace-hash>`). Whatever the app stores for its sign-in (cookies, localStorage, IndexedDB) survives there between runs. Storage-state files are not used: they carry cookies and localStorage only. One browser per profile at a time.
- **Lifetime:** when the app's session lapses, the user signs in again. The app's own rules (how long a session lasts, whether refresh extends it) come from its auth notes, below.
- **Account:** use the role the plan's Manual QA names. Prefer a dedicated least-privilege QA account per role over a personal admin account. Reports name the role, never the email.
- **App-specific auth notes:** `qa.auth` in `.workflow/config.yml`: a path to a notes file, or `none` for a public app. When it's unset, use the installed overlay's `qa/auth.md` (`<.claude>/overlays/<overlay>/qa/auth.md`, or `~/.claude/overlays/<overlay>/qa/auth.md` for plugin installs), else the plan's Manual QA section. They supply the sign-in button, the signal for each probe state below, and the identity-provider hosts. With none of these, treat the app as public and report BLOCKED (auth) at the first sign-in wall.

### Auth probe (first action of every run)

Open the base URL, `browser_snapshot`, and classify:

| State | Typical signal (the auth notes give the app's exact one) | Action |
|---|---|---|
| signed-in | The app shell; URL not on a sign-in route | Check the required role with the plan's role check. Wrong role → that role's cases BLOCKED (auth-role); run the rest. |
| expiring | A "session ending soon" banner | Attended: use the app's "sign in again" control and wait as below. Unattended: continue; note it in the report. |
| signed-out | A sign-in route or the app's sign-in button | Attended: click the app's own sign-in button once, then poll every 15 s until signed-in (3 min; 5 min in `login` mode). Unattended: return `AUTH_REQUIRED`; all cases BLOCKED (auth). |
| reauth-needed | A "sign in to continue" modal | Same as signed-out, using the modal's sign-in button. |
| account-changed | A "signed-in account changed" notice | BLOCKED (auth); the user re-runs `--login`. |
| access-denied | An "access unavailable" or 403 page | BLOCKED (auth-role). |
| reconnecting | A "reconnecting" or "checking your session" notice | Wait up to 30 s and re-probe. Still there → BLOCKED (env: API unreachable). |

A state the auth notes don't describe and the page doesn't make obvious → BLOCKED (auth), with a screenshot.

Re-probe whenever a case lands on a sign-in screen or session modal. Mid-run lapse: attended → same flow, then restart the case; unattended → that case and later ones BLOCKED (auth-expired).

### Credential rules (hard)

- Never click, type into, or read form fields on identity-provider pages (for example `login.microsoftonline.com`, `accounts.google.com`, `*.okta.com`, `*.auth0.com`, `*.firebaseapp.com/__/auth/*`, the hosts the auth notes list, or any SSO or MFA page). The user completes them. Only the app's own sign-in buttons may be clicked.
- Never type passwords, MFA codes, or tokens anywhere.
- Never read auth storage: no `browser_evaluate` against IndexedDB, localStorage, sessionStorage, or cookies.
- Never open single-request details (`browser_network_request`) for requests carrying an `Authorization` header. Cite requests as method + path + status, without query strings.
- Never copy, export, or move the browser profile, and never save a storage state.
- Keep emails and names out of evidence: screenshot the element under test (by ref), not the header user menu.
- Do not sign out at the end; the next run reuses the session. `logout` mode signs out on request.

## Test-case rules

- Every case cites one AC. Every UI-observable AC has at least one case. No case without an AC.
- Expected result is the AC's observable outcome, taken from the AC text. Do not add expectations the AC does not state.
- AC not observable in a browser (test coverage, internal refactor, logging) → **N/A**, naming where it is covered.
- AC about an API contract → verify through the requests the UI fires (`browser_network_requests`: method, path, status, fields named in the AC).
- AC ambiguous as written → test the literal reading and record "AC ambiguous" under Observations. Do not guess intent.
- Cover each state the AC names: default, loading, empty, error, boundaries (for example page size + 1), permissions.
- Use the test data named in the plan's Manual QA section. If it is missing and cannot be reached without a forbidden mutation → **BLOCKED (data)**.

## Navigation protocol (per case)

1. `browser_navigate` to base URL + route exactly as given. Do not wander menus to reach it unless the AC is about that navigation.
2. **Session:** if the page is a sign-in screen or a session modal, handle it per **Authentication**, then restart this case.
3. `browser_snapshot` for element refs. Act only through refs from the latest snapshot (`browser_click`, `browser_type`, `browser_select_option`, `browser_press_key`). Re-snapshot after each action that changes the page.
4. Wait with `browser_wait_for` (text or textGone). No fixed waits longer than 2 s.
5. Assert from the snapshot for text, counts, enabled or disabled, selected, and visibility. Judge layout, color, and spacing from a screenshot.
6. `browser_take_screenshot` named `AC-<n>-<case>-<state>.png`, then `mv` it from the reported path into the screenshot directory. At least one screenshot per verdict. A FAIL needs a screenshot of the wrong state.
7. After each case, read `browser_console_messages` and `browser_network_requests`. Record errors and 4xx/5xx responses raised during that case, as method + path + status.
8. When the AC covers an interactive control, operate it once by keyboard too (Tab, Enter, Space, Escape).

**Strict scope:** every action serves a listed case. Do not explore other pages or features.

## Mockup comparison

Open the mockup URL in a second tab at the same viewport, select the state that matches the case, and screenshot it. Compare: elements present, copy and labels exact, order and placement, states.

- Elements tagged `data-ac="AC-n"` are graded under that AC.
- Design-system token differences and small pixel offsets are not failures.
- AC and mockup disagree → the AC wins; report the conflict under Observations.

## Verdicts

| Verdict | Meaning |
|---|---|
| **PASS** | Observed outcome matches the AC; screenshot attached. |
| **FAIL** | Observed outcome differs from the AC. Give expected vs actual, screenshot, console/network evidence, and the suspected file from the changed-file list. |
| **BLOCKED** | Could not test: auth, server down, missing data, backend change not running locally, or mutation needs approval. Not a code failure. Name the user action that unblocks it. |
| **N/A** | Not UI-observable. Name where it is covered. |

**Severity:** FAIL → Critical. A new console error or 4xx/5xx inside a changed flow → Critical. Mockup deviation on an element no AC governs → Suggestion. Anything outside the changed pages → Observation (not graded).

## Safety (hard rules)

- Never test production. The base URL must be `localhost` or `127.0.0.1`, and the parent has checked that the app's API is not production.
- No edits to app code, config, tests, or the plan. Bash is for moving screenshots and read-only commands only.
- Irreversible or outward-facing actions (delete, purchase, payment, refund, send email or SMS, bulk update, publish or list inventory) only when the plan's Manual QA allows that action and the API is local. Otherwise fill the form, screenshot it, do not submit → **BLOCKED (needs approval)**.
- Credentials and sessions: follow **Credential rules** under Authentication.
- No secrets or customer PII in the report. Describe the data instead of copying it.
