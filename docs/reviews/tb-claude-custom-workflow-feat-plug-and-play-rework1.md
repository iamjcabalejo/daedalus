## Argus review

The rework closes all five earlier findings and RW-2…RW-6 hold, but RW-1's body scan still lets some dropping or migrating scripts through (TypeORM verbs, `pre`/`post` hops, turbo fan-out from a workspace root); not covered by a stack pack: shell, Markdown, JSON; not reviewed: `docs/validation/matrix.local.json` (private fixtures).

**Done well:** `.claude/hooks/session-init.sh:39-40` treats empty stdout as a failure even when the exit code is 0. That is exactly what `main()` returns after a `HardTimeout`, so the 7s alarm path also gets the notice, not just crashes.

**Since the last revision:** 5 earlier findings verified fixed.

**1. [consider · reliability] TypeORM `schema:drop`/`migration:run` and `npm run` hops from `pre`/`post` hooks still look safe to auto-run**
`UNSAFE_BODY_RE` lost `UNSAFE_RE`'s `migration` and bare `drop`, so `"pretest": "typeorm schema:drop && typeorm migration:run"` leaves `npm test` unflagged. `script_body` follows `npm run X` only from the main script, so `"pretest": "npm run db:reset"` (`prisma migrate reset --force`) is never read. Both let an agent wipe the `.env` database unasked.
- Fix: add `migration:\w+`, `schema:(?:drop|sync)` and `drizzle-kit\s+push` to `UNSAFE_BODY_RE`, and run the hop over all three bodies in `script_body`, not only `body[0]`. Add a synthetic row with `"pretest": "npm run db:reset"` → `prisma migrate reset --force` and `"dev": "typeorm migration:run && nest start"`, asserting both are unsafe. S2 can't catch a broken hop, because `npm run db:migrate` already matches `migrate` by its name. Land this before Phase 3's test-runner auto-runs `test`; from then on it is important.
- Where: `.claude/scripts/detect-stack.py:41-45`; `.claude/scripts/detect-stack.py:493-499`; `docs/validation/matrix.json:436`
- Cost: `migration:generate` and `migration:create` (file-only) get flagged too, so TypeORM repos see one more confirmation.
<!-- argus-finding:rw1-1 -->

**2. [consider · reliability] A workspace root's `build` that fans out through turbo stays unflagged when the member build it runs migrates**
With root `"build": "turbo run build"` and `apps/web` `"build": "prisma migrate deploy && next build"`, `apps/web` gets `unsafe` but root `pnpm build` doesn't: `script_body` hops only through `npm|pnpm|yarn|bun run X`, and `adjust_workspace` never carries the flag up. An agent that builds from the root runs the migration unasked.
- Fix: in `adjust_workspace`, mark the top root's same-named command `unsafe` when any member's is, since workspace-root scripts usually fan out (turbo, nx, lerna, `pnpm -r`, `npm --workspaces`). Add a synthetic pnpm/turbo row for this layout asserting `commands["."].build.unsafe`.
- Where: `.claude/scripts/detect-stack.py:814-830`; `.claude/scripts/detect-stack.py:496`
- Cost: a root script that doesn't fan out gets one extra confirmation.
<!-- argus-finding:rw1-2 -->

**3. [consider · correctness] npm-workspace members still get `npm install`: `adjust_workspace` inherits pnpm/yarn/bun lockfiles, not npm's**
RW-4 looks for `package-lock.json` in each root's own `names`, but an npm workspace keeps it only at `.`. `adjust_workspace` rewrites member installs for pnpm, yarn and bun only, so `packages/x` keeps `npm install` (derived, so auto-runnable). That can rewrite the root lockfile or leave a stray one in the member: the diff noise RW-4 set out to stop.
- Fix: when the top root's install is `npm ci`, set member installs to `npm ci` with source `workspace lockfile` (or drop them so agents install from the root). Add an npm-workspace synthetic row asserting the member's `install.cmd`.
- Where: `.claude/scripts/detect-stack.py:821-830`; `.claude/scripts/detect-stack.py:507-508`
- Cost: `npm ci` deletes `node_modules` first, so installs are slower.
<!-- argus-finding:rw1-3 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:tb-jcabalejo/tb-claude-custom-workflow@feat/plug-and-play:WORKTREE-rework1-over-6c7e2f5 -->

<details><summary>findings.json and run notes (not posted)</summary>

- **Run:** re-review of the uncommitted rework-1 working tree against `6c7e2f5`. The bundle was built by hand, because local mode only sees commits: 10 files, 984 diff lines. The prior review was supplied as `prior.md`.
- **Prior findings:** `6c7e2f5-1` … `6c7e2f5-5` are all verified fixed.
- **AC (RW-1…RW-6):** 5 met; RW-1 partly met (see finding 1).
- **Verified by the caller with synthetic repos:**
  - rw1-1: a `pretest` hop to `prisma migrate reset` → test unflagged; `dev` with `typeorm schema:drop` → unflagged;
  - rw1-2: member build flagged while root `pnpm build` isn't;
  - rw1-3: root `npm ci` while member `npm install`.
- **Rework mapping:** all three are consider → Suggestion; there are no Critical items. Finding rw1-1 is to land before Phase 3.

```json
{"prior": {"6c7e2f5-1": "verified_fixed", "6c7e2f5-2": "verified_fixed", "6c7e2f5-3": "verified_fixed", "6c7e2f5-4": "verified_fixed", "6c7e2f5-5": "verified_fixed"},
 "ac": {"met": 5, "not_met": 1, "not_visible": 0},
 "findings": [
  {"id": "rw1-1", "severity": "consider", "category": "reliability", "family": "FM-03", "path": ".claude/scripts/detect-stack.py", "line": 41, "new": true},
  {"id": "rw1-2", "severity": "consider", "category": "reliability", "family": "FM-03", "path": ".claude/scripts/detect-stack.py", "line": 814, "new": true},
  {"id": "rw1-3", "severity": "consider", "category": "correctness", "family": "FM-11", "path": ".claude/scripts/detect-stack.py", "line": 821, "new": true}
 ]}
```
</details>
