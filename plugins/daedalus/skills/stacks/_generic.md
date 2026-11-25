# Generic pack (fallback for stacks with no pack)

Use this when a root's `packs` is empty or a changed file matches no pack. It holds cross-language defaults. Everything here gives way to the repo's own conventions, which you must look up first.

## First, learn the repo
- **Read the docs:** README, CONTRIBUTING and `docs/` for the build, test and run commands and the conventions.
- **Read the tooling config:** lint and format settings (`.editorconfig`, linters, formatters) set the style. Don't invent a different one.
- **Copy the neighbors:** before adding a pattern, find the closest existing example (a similar endpoint, component, job or test) and follow it.
- **Note the gap:** record in your output which language had no pack. In a review this goes in the verdict; in other roles, use `pack_suggestions` or the implementation notes.

## Build
- **Validate at the boundary:** reject bad input where it enters (HTTP handler, message consumer, CLI arguments) with explicit errors.
- **Handle errors explicitly:** no empty catch blocks. Log with context (operation and an input summary, never secrets), then re-raise or return a typed error.
- **Thin entry points:** keep handlers thin and put business logic in plain, testable functions. Put side effects (I/O, network, clock) at the edges.
- **Configuration:** comes from the environment or a config file read once at startup, and is validated. No hard-coded secrets, URLs or credentials.
- **External calls** have timeouts, bounded retries with backoff, and an explicit unknown-outcome path (FM-02, FM-05, FM-06).
- **Persistence:** parameterized queries only; transactions around multi-step writes; idempotent handlers for anything retried (FM-04, FM-09).
- **Time and money:** store timestamps in UTC, and carry money with its currency in integer minor units (FM-11).
- **Function size:** keep functions focused, and extract when one passes about 30 lines or mixes concerns.

## Review
- **Ask every relevant question** in [failure-modes.md](failure-modes.md).
- **Watch language-level traps:** a panic or uncaught exception in a request path, integer overflow, and the null or nil conventions of the language.
- **Use the repo's toolchain:** if a linter or type checker is configured, treat a new violation in the diff as evidence. It isn't a finding unless it causes one of the failure modes.

## Test
- **Follow the existing layout:** use the repo's test framework, folder structure and naming; find one existing test and mirror it.
- **Write the failing test first:** for a bug fix, add the regression test that fails before the fix.
- **Cover four paths:** the happy path, invalid input, auth or permission failures, and the edge case the change is about.
- **Mock only at real edges** (network, clock, third-party SDKs), never the unit under test. Use the repo's own fixtures and factories.

## Commands
- **Where to look:** in README "Getting started", Makefile, Taskfile or justfile targets, the CI workflow `run:` steps, and language manifests (scripts sections).
- **If nothing is declared:** record a gap and ask the user in `/setup`. Never guess a destructive command.
