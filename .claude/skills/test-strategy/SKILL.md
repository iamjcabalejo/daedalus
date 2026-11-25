---
name: test-strategy
description: Framework-neutral guidance on which tests a change needs (test pyramid, what to mock, regression tests, naming, flakiness, coverage of acceptance criteria). Use from the implementer and test-runner roles and /test-gen. The stack pack's Test section names the framework, fixtures and layout.
---

# Test strategy

The repo's existing tests are the style guide: match their framework, layout, naming and fixtures. The stack pack (`skills/stacks/<pack>.md`, `## Test`) says how; this skill says what.

## What every change needs
1. **One test per acceptance criterion**, named after the behavior (`returns_404_when_order_missing`, `shows_empty_state_without_results`), not after the method.
2. **A regression test for every bug fix** that fails on the old code and passes on the new. Name or comment it with the ticket key.
3. **The unhappy paths the change introduces:** invalid input, unauthorized and forbidden, not found, conflict, timeout or upstream failure, empty results.
4. **Boundaries:** zero, one, many; the first and last page; limits and caps; time zones and date-only values; duplicate submissions.

## Shape (pyramid)
- **Unit:** pure logic and branching, fast, no I/O. Most tests live here.
- **Integration:** the real framework stack with a real test database or container where the repo has one (HTTP handler → service → DB, consumer → handler → store). Use these for anything involving transactions, serialization, auth middleware or queries.
- **End to end:** a few critical user flows only; run them only when the user confirms (they start browsers or need live services).

## Mocks
- Mock only at the edges you don't own: third-party HTTP APIs, payment providers, email, clocks, randomness. Prefer the repo's fakes, recorded fixtures or local emulators.
- Don't mock the code under test or your own database layer in integration tests.
- Assert on outcomes the caller can see (response, stored row, emitted event, rendered text), not on internal calls, unless the call itself is the contract (for example, "charges the card exactly once").

## Reliability
- No sleeps: wait on conditions. Freeze or inject time. Seed randomness.
- Tests are independent and order-free: each creates and cleans up its own data (transactions or fixtures).
- A flaky test is a bug: fix or quarantine it with a ticket, never delete it to get green.

## Coverage of the plan
- Map AC → tests in the handoff. Gaps are listed, not hidden.
- Coverage percentage is a smoke alarm, not a goal; untested branches in changed code are what matter.

## Running
- Run the narrowest set first (changed test files), then the root's full `test` command from the profile.
- Only run commands the profile marks safe (`script`, `derived`, `user`, or confirmed `inferred`); never `unsafe: true` ones.
