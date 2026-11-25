# Adding a stack

A stack pack teaches every role about one language, framework or platform: how to build in it, what goes wrong in reviews, how to test it, and how to find its commands. Packs live in `.claude/skills/stacks/<name>.md`.

## 1. Decide whether you need one

- **A new language or platform** (Ruby, Rust, Kotlin, Elixir, a mobile framework): yes.
- **A framework inside a covered language** (Flask under `python`, NestJS under `node-js`): usually no. Add "when `<framework>` is detected" lines to the existing pack instead.
- **A tool used across stacks** (a queue, a warehouse, IaC): it may already be covered (`serverless-queues`, `data-warehouse`, `iac`, `ci-cd`).

Until a pack exists, files in that stack get `_generic.md` and the universal failure modes, and Argus lists them under "not covered by a stack pack" with `pack_suggestions` in its findings JSON. Those suggestions are a good seed.

## 2. Write the pack

Copy `.claude/skills/stacks/_template.md` to `.claude/skills/stacks/<name>.md`, then fill in:

- **Frontmatter:** `name` (the file name), and a `detect` block:
  - `files`: globs that prove the stack (`**/*.rb`, `Gemfile`);
  - `weak`: shared extensions that count only alongside a `files` match or a signal;
  - `signals`: tokens found in manifests (imports, gem or package names).

  Add `evidence: seed — unvalidated` until real reviews back it.
- **`## Build`:** language and runtime version and where it's declared; typing and validation at the boundary; error handling; layering; async and concurrency; data access; configuration and secrets. Framework rules go under "when `<framework>` is detected".
- **`## Review`:**
  - `### How the failure modes show up`: map only the FM-01…FM-19 families that have a stack-specific signal;
  - `### Stack-only checks`: anything no family covers.
- **`## Test`:** the runner and layout, fixtures and factories, what to mock (edges only), and how to name a regression test.
- **`## Commands`:** how to find install, test, lint, typecheck, build and dev, and which commands are **unsafe** (deploy, migrate, publish).
- **`## Entry points (scan mode)`:** routes, handlers, consumers, jobs, CLI mains.

Keep each section to concrete, stack-specific lines. Generic advice belongs in `_generic.md` or `failure-modes.md`, and the whole pack must stay under 500 lines.

## 3. Teach the detector (if needed)

`detect-stack.py` loads every pack's `detect` block automatically, so most stacks need no code change. Edit the detector only to:
- recognize a new manifest (for example `Gemfile`), and derive commands from it (`bundle exec rspec`);
- flag a new kind of unsafe command (for example `rails db:migrate`) in `UNSAFE_BODY_RE`.

Changing a pack's frontmatter changes the detector's `rules_digest`, so existing profiles refresh on their next session.

## 4. Prove it

```bash
scripts/lint-packs.sh
```

```bash
scripts/test-detector.sh
```

- Add a row to `docs/validation/matrix.json` that proves detection: a public repo pinned by commit sha (`kind: git`), or a synthetic case with the files written inline (`kind: synthetic`). Freeze its expected facts with `scripts/test-detector.sh --print`, then review them.
- If you changed the detector's unsafe rules, add a synthetic row whose script body hides the unsafe operation behind a neutral name, and check it fails on the old code.
- Rebuild the plugin (`scripts/build-plugin.sh`) and run `scripts/check-generic.sh`.

## 5. Calibrate

Run `/argus` on 3–5 real PRs in that stack, ideally ones that later caused an incident or were reverted. Record what the pack caught and what it got wrong, sharpen the lines, and change `evidence` once it's earned.
