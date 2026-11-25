# Rework 1: Phase 1 review findings

- **Source:** [Argus review of 6c7e2f5](../reviews/tb-claude-custom-workflow-feat-plug-and-play-6c7e2f5.md).
- **Plan:** [plug-and-play-workflow.md](plug-and-play-workflow.md).
- **Branch:** `feat/plug-and-play`.

**Trigger:** finding 1 is `important`, which maps to **Critical** under the compounding cycle. Findings 2–5 are Suggestions, and they are folded into this rework because they touch the same files.

## Acceptance criteria
- **RW-1 (finding 1):**
  - **What sets `unsafe`:** an emitted command gets `unsafe: true` when the command itself, **or the script body or recipe it runs**, contains a deploy, migrate, publish, release, destroy, apply or drop operation.
  - **What it covers:** one level of `npm|pnpm|yarn|bun run X` indirection, Makefile, Taskfile and justfile recipes, and `dbt build`.
  - **What stays safe:** the words `prod` and `production` inside a script body don't mark it unsafe.
- **RW-2 (finding 2):**
  - **Budgets:** the hook passes `--timeout 4`, its subprocess timeout is 8s, and the detector's hard alarm is `timeout + 3`. All of these fit under the hook's 10s.
  - **Failure notice:** when the detector exits non-zero or prints nothing, the hook adds `Project profile: detection failed; run /setup.` and still prints the contract.
- **RW-3 (finding 3):** the profile stores a `rules_digest` (the detector source plus every pack's frontmatter), and `--check`/`--ensure` treat a different digest as stale. `GENERATOR` is bumped to `detect-stack@2`.
- **RW-4 (finding 4):** install commands use top-level file names, so a `package-lock.json` gives `npm ci` and a `uv.lock` gives `uv sync`.
- **RW-5 (finding 5):**
  - **Fixtures:** every matrix row also pins `commands.lint`, `.build` and `.dev` (null when absent), and the harness compares them.
  - **Wording:** AC-2 in the plan is reworded to match what is verified: lint, build and dev must match the fixture, while missing test and lint for runnable layers go in `gaps`. The results doc is updated.
- **RW-6:** synthetic rows in the harness cover RW-1 and RW-4 (Prisma migrate in `build`, a Makefile deploy recipe, `dbt build`, npm with a lockfile, uv), plus a hook-failure check for RW-2.

## File changes
- `.claude/scripts/detect-stack.py`:
  - `cmd(…, body)`, `UNSAFE_BODY_RE`, `script_body()`, `recipe()`;
  - `node_commands` and `python_commands` take `names`;
  - `rules_digest()`, `is_fresh`, `GENERATOR`;
  - the hard timeout.
- `.claude/hooks/session-init.sh`: the budgets and the failure notice.
- `.claude/skills/project-profile/profile.schema.json`: a required `rules_digest`.
- `.claude/skills/project-profile/SKILL.md`: `unsafe` also covers script bodies, and staleness now includes hub upgrades.
- `scripts/test-detector.sh`: lint, build and dev in `facts()` and `compare()`; synthetic rows; a command-level expectation check.
- `docs/validation/matrix.json`: the re-frozen fixtures and the synthetic rows. The private expectations in `matrix.local.json` are also re-frozen.
- `docs/plans/plug-and-play-workflow.md` (AC-2 wording, Phase 1 note) and `docs/validation/results-2026-11-25.md` (rework section).

## Verification
1. `scripts/test-detector.sh` passes on all public, private and synthetic rows.
2. Hook: a failing detector, pointed at with `CLAUDE_PLUGIN_ROOT`, still yields the contract plus the failure notice. Cold and warm timing stays under 5s and 1s.
3. Staleness: change a pack's frontmatter and `--check` returns stale; restore it and the profile is fresh again after a refresh.
4. Re-review with `/argus --local` on the rework commit (optional; offered after the fix).

---

## Follow-up from the re-review

[Re-review of rework-1](../reviews/tb-claude-custom-workflow-feat-plug-and-play-rework1.md): all five original findings verified fixed. It raised three new consider findings, fixed here before committing:

| Finding | Fix | Verified by |
|---|---|---|
| rw1-1: TypeORM, Rails-style and drizzle verbs, and hops from `pre`/`post` scripts, passed the body scan | `UNSAFE_BODY_RE` adds `migrations?:\w+`, `schema:(drop\|sync)`, `db:(drop\|reset\|setup\|migrate\|seed\|push)`, `dropdb` and `drizzle-kit (push\|migrate)`. `script_body` follows `npm run X` from the main, `pre` and `post` bodies | S6: `pretest` hops to a neutrally named `fresh` script (`prisma migrate reset --force`), which flags `npm test` only through the hop; `typeorm schema:drop` flags `dev`; `lint` stays safe |
| rw1-2: a workspace root's fan-out build wasn't flagged | `propagate_unsafe()` marks a root command unsafe when any member's same-named command is unsafe | S7: root `pnpm build` (turbo) is unsafe because `apps/web` build migrates; root `lint` stays safe |
| rw1-3: npm-workspace members got `npm install` | Members of an npm workspace whose root uses `npm ci` install with `npm ci` (source: workspace lockfile) | S8: `packages/x` install is `npm ci` |
| rw2-1 (second re-review): S6 couldn't catch a reverted hop, because `db:reset` matched the regex by name | S6 renamed the hopped script to `fresh` | With `script_body` reverted to hop only from the main body (temporary copy), S6 fails (`test.unsafe=False`); with the fix it passes |

[Second re-review](../reviews/tb-claude-custom-workflow-feat-plug-and-play-rework1b.md): rw1-1…rw1-3 verified fixed, with no regressions in the original five.
