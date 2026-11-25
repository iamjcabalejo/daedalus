---
name: project-profile
description: >-
  How to read and trust .workflow/profile.json, the auto-detected project profile
  (roots, layers, languages, frameworks, stack packs, install/test/lint/typecheck/build/dev
  commands, UI dev URL, data and infra tools, ticket system, code host, gaps). Use before
  planning, coding, testing or reviewing in any repo, and when running /setup.
---

# Project profile

`detect-stack.py` writes `.workflow/profile.json` automatically at session start, and again whenever a manifest changes. `/setup` confirms it.

**Where the scripts are** (`detect-stack.py`, `validate-profile.py`): `<.claude>/scripts/` in a script install (`~/.claude/scripts/` or `<project>/.claude/scripts/`), or `${CLAUDE_PLUGIN_ROOT}/scripts/` in a plugin install. Run them with `python3 <path>`.

The profile holds **facts detected from files**. Choices live in `.workflow/config.yml`, which Phase 3 extends.

## Where values come from

**Precedence**, from lowest to highest:
1. the detected profile;
2. `~/.workflow/config.yml`;
3. `<workspace>/.workflow/config.yml`;
4. `<repo>/.workflow/config.yml`;
5. command arguments.

When config sets a command or stack, it wins over the profile.

## Reading it

- **`roots[]`:** one entry per app or package (a monorepo has several). `path` is relative to the repo or workspace root.
- **`layer`:** one of `ui | api | worker | data | infra | lib | cli`. It drives task blocks and implementer order: **data → api/worker → ui → infra**.
- **`packs`:** the stack packs to load for files under this root (`skills/stacks/<pack>.md`; the `stacks` skill). With no packs, use `skills/stacks/_generic.md` and `failure-modes.md` plus the repo's own conventions.
- **`commands.<name>`:** an object `{cmd, source, confidence, confirmed?, unsafe?}`.

## Running commands safely

| confidence | Meaning | May run without asking? |
|---|---|---|
| `script` | Declared script or target (`package.json` scripts, Makefile, Taskfile, justfile) | Yes |
| `derived` | Follows from a lockfile or tool convention (`pytest`, `go test ./...`) | Yes |
| `user` | Set in `/setup` | Yes |
| `inferred` | Heuristic (CI line, guessed entrypoint) | **Only if `confirmed: true`**; otherwise ask, or run `/setup` |

**Never auto-run** a command marked `unsafe: true`, whatever its confidence. Ask first, every time. The flag is set when either of these matches:
- **the command itself:** deploy, migrate, prod, publish, release, destroy or drop;
- **what it runs:** the `package.json` script body (plus one `npm run X` hop), the Makefile, Taskfile or justfile recipe, or tools like `dbt build`, `terraform apply`, `prisma migrate` or `alembic upgrade`.

A command without the flag is still only as safe as its detection: if you can see it does something irreversible, ask.

Always print the exact command before running it, and run it from `<repo>/<root.path>`.

## Gaps and staleness

- **`gaps[]`** lists what detection couldn't find (no lint command, a language with no stack pack, a UI with no dev command, early stop). Say so instead of guessing, and suggest `/setup`.
- **Freshness:** `detect-stack.py --check --root <repo>` exits 0 when the profile is fresh. **Staleness covers:**
  - manifest edits;
  - new manifests at depth 2 or less;
  - detection-rule changes (`rules_digest`: a hub upgrade or a changed stack pack).

  A brand-new deep manifest needs `/setup --refresh`.
- **Uncommitted profile:** if the profile is missing, read-only, or you're in a workspace that isn't a repo, run `detect-stack.py --stdout --root <dir>` and use its output without writing.

## Never

- Execute project code to "detect" something. The detector only reads files and runs `git` read commands.
- Edit `.workflow/profile.json` by hand. Use `/setup`, or `detect-stack.py --set ROOT:NAME=CMD` / `--confirm ROOT:NAME`.
- Copy profile values into rules, skills or docs. They change as the repo changes.
