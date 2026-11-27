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

**Where the scripts are** (`detect-stack.py`, `validate-profile.py`, `workflow.py`): `<.claude>/scripts/` in a script install (`~/.claude/scripts/` or `<project>/.claude/scripts/`), or `${CLAUDE_PLUGIN_ROOT}/scripts/` in a plugin install. Run them with `python3 -I <path>` (isolated, so nothing in the project folder is imported).

The profile holds **facts detected from files**. Choices live in `.workflow/config.yml`, which Phase 3 extends.

## Where values come from

Read configuration through the resolver, never by reading and combining config files yourself:
- `python3 -I <scripts>/workflow.py config resolve --json --repo <repo> --workspace <folder the session started from>` prints every value (`values`), the files it read (`sources`) and where each value came from (`provenance`). `config get <key>` prints one value; `config explain <key>` shows every level's contribution and what was ignored.
- Exit code 3 is a configuration error: show its code, file, line and fix, and don't guess the values.
- When config sets a stack, it wins over the profile. A config `commands` override wins over the profile entry for the same root and name (`config commands` lists the hidden entry under `shadowed`).

## Reading it

- **`roots[]`:** one entry per app or package (a monorepo has several). `path` is relative to the repo or workspace root.
- **`layer`:** one of `ui | api | worker | data | infra | lib | cli`. It drives task blocks and implementer order: **data → api/worker → ui → infra**.
- **`packs`:** the stack packs to load for files under this root (`skills/stacks/<pack>.md`; the `stacks` skill). With no packs, use `skills/stacks/_generic.md` and `failure-modes.md` plus the repo's own conventions.
- **`commands.<name>`:** an object `{cmd, source, confidence, confirmed?, unsafe?}`.

## Running commands safely

A command's `confidence` and `confirmed` fields say how it was found, not whether it may run: a committed profile or config file can claim any value. Which commands may run without asking comes from the **effective command set**:

`python3 -I <scripts>/workflow.py config commands --json --repo <repo> --workspace <folder the session started from>`

- **Runnable without asking:** records with `trusted: true` and `unsafe: false`. Put exactly these, with their `cmd`, in briefs.
- **Anything else** (`trusted: false`, a command that isn't listed, or a failed call): never put it in a brief and never run it. Ask the user, or run `/setup`, which lists the untrusted commands and records the user's trust.
- **Trusted** means re-detection reproduces the entry (`basis: detected`), the user's trust store holds its digest (`trust-store`), or it comes from the user's own `~/.workflow/config.yml` (`user-config`) or organization policy (`policy`). A `commands` override in a repository or workspace folder needs the trust store.
- This rule is **prompt-followed in P1, enforced from P2** (the guard and `exec.py`).

| confidence | Meaning |
|---|---|
| `script` | Declared script or target (`package.json` scripts, Makefile, Taskfile, justfile) |
| `derived` | Follows from a lockfile or tool convention (`pytest`, `go test ./...`) |
| `user` | Set in `/setup` |
| `inferred` | Heuristic (CI line, guessed entrypoint); `/setup` asks about it |

**Never auto-run** a command marked `unsafe: true` (`config commands` recomputes the flag; a committed value never clears it), whatever its trust. Ask first, every time. The flag is set when either of these matches:
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
