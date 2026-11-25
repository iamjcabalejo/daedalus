---
name: <pack-name>                 # kebab-case; must match the file name
detect:
  files: ["**/*.<ext>", "<manifest file>"]   # globs matched against changed paths and the repo root
  weak: ["**/*.<shared ext>"]                # optional: shared extensions (.ts, .sql, .yaml) that count only when a files glob or signal also matches
  signals: ["<import or keyword>"]           # optional: case-insensitive token matches in manifests (and sampled SQL)
evidence: <where the checks come from: "NRD Sight corpus (≈N findings)", "team incidents", or "seed — unvalidated">
---

# <Stack name>

One line on what this pack covers, and which other pack it combines with if any (for example, "load together with the language pack").

The sections are read by different roles. Keep each to concrete, stack-specific lines; generic advice belongs in `_generic.md` or `failure-modes.md`.

## Build
Conventions for writing code in this stack, read by the implementer and architect:
- the language or runtime version and where it's declared;
- typing and validation at the boundary;
- error handling;
- layering and dependency injection;
- async and concurrency model and timeouts;
- data access and transactions;
- configuration and secrets.

Framework-specific rules apply only when the profile detects the framework, so say "when `<framework>` is detected".

## Review
How the universal failure modes show up here, read by the reviewer.

### How the failure modes show up
- **FM-01 Partial failure:** <the batch, queue or page API of this stack, and its partial-failure mechanism>
- **FM-02 Unknown outcome:** <HTTP client, error types, telling a timeout from cancellation>
- **FM-06 Budgets:** <runtime limits, blocking calls to avoid, timeout APIs>
- **FM-07 Concurrency:** <threading, async or actor-model pitfalls>
- **FM-14 Secrets:** <config files where secrets hide, logging APIs that leak>

Only include the families with a stack-specific signal.

### Stack-only checks
- <checks that no failure family covers>

## Test
For the test-runner and implementer:
- the framework or runner, and where tests live;
- the fixtures and factories the repo uses;
- what to mock (only at the edges) and what to run for real (test DB, containers);
- the cases every change needs, and how to name a regression test.

## Commands
How `/setup` and the detector find install, test, lint, typecheck, build and dev, plus the commands that are **unsafe** (deploy, migrate, publish) and must never auto-run.

## Entry points (scan mode)
- <routes, handlers, consumers, jobs, CLI mains, manifests>

---

## Adding a pack
1. Copy this file to `<name>.md` in this folder, and fill in `detect` (the detector loads only files with a `detect:` block).
2. Seed each section, mapping FM-01…FM-19 in Review. Mark it `evidence: seed — unvalidated` until it has been checked against real reviews or incidents.
3. Run `scripts/lint-packs.sh` and `scripts/test-detector.sh`. Add a matrix row (a public repo pinned by sha, or a synthetic case) that proves detection.
4. Calibrate on 3–5 PRs that later caused an incident or were reverted, and record recall and false positives in the hub's research notes.
