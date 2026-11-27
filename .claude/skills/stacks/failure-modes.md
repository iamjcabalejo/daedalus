# Failure modes (stack-neutral)

These are the universal bug families distilled from code review findings across Python, TypeScript, C#, Go, SQL, warehouse and IaC code. They apply to any language, framework or platform.

The stack packs in this folder only say how each family shows up in a given technology. When no pack matches a file, use this catalog alone.

Each family has:
- **Ask:** the question to put to the diff.
- **Look for:** signals in the code.
- **Grade:** severity by outcome (SKILL.md → Severity has the general rule).
- **Fix:** the usual shapes of the fix.

---

### FM-01 Partial failure in batches · reliability
- **Ask:** can one bad item fail, drop, acknowledge or replay the whole batch, page, file or run?
- **Look for:**
  - loops over messages, rows, files or API pages with a single try/except around them;
  - a batch acknowledged as a unit;
  - responses not mapped back to their items by id.
- **Grade:**
  - important when good items are lost or reprocessed;
  - critical when the loss is silent and permanent on a live pipeline.
- **Fix:** report per item (partial-failure APIs), skip and record bad items, and map results back by id.

### FM-02 Unknown outcome of external calls · correctness, reliability
- **Ask:** what happens on a timeout, 5xx, connection drop or malformed body? Is "no error raised" treated as success?
- **Look for:**
  - success inferred without checking the status;
  - retries decided by message text;
  - every non-429 error treated as terminal, or every error treated as retryable.
- **Grade:**
  - important;
  - critical when an unknown outcome is treated as success on a money or inventory path.
- **Fix:**
  - an explicit unknown-outcome state;
  - classify on status code or error type;
  - verify the result before you record it.

### FM-03 Irreversible side effects · correctness, reliability
- **Ask:** can a charge, buy, order, send, publish or delete happen twice, or stop halfway?
- **Look for:**
  - irreversible calls inside a retry or a re-delivered handler;
  - no durable "pending" record before the call;
  - an idempotency key regenerated on retry or reopen;
  - ambiguous cases auto-processed instead of sent to a person.
- **Grade:**
  - critical when a duplicate or wrong action moves money or goods;
  - important otherwise.
- **Fix:**
  - write a pending record first;
  - use a stable idempotency key that changes only with the payload;
  - send unknown outcomes and ambiguous cases to manual handling.

### FM-04 Duplicates under at-least-once delivery · reliability
- **Ask:** is every handler safe when its message, event, webhook or job runs twice, or when two schedules overlap?
- **Look for:**
  - dedupe markers written before the work succeeds;
  - flags lost between retries;
  - additive upserts where the intent was replace;
  - repeated alerts.
- **Grade:** important.
- **Fix:** mark done only after success, use idempotent writes, and dedupe on a natural key.

### FM-05 Unbounded loops and retries · reliability, cost
- **Ask:** does every retry, re-poll, re-enqueue, follow-up chain and pagination loop end?
- **Look for:**
  - no attempt or age cap;
  - no terminal state, and no alert when the cap is hit;
  - pagination that doesn't stop on empty, repeated or capped pages;
  - a partial walk reported as complete.
- **Grade:**
  - important;
  - cost is important when the calls to an external API are unbounded.
- **Fix:** add caps with a terminal state and an alert, and give pagination explicit stop conditions.

### FM-06 Time and resource budgets · reliability, performance
- **Ask:** do the timeouts, retries, sleeps and lock holds add up to less than the platform's limit?
- **Look for:**
  - platform limits such as function timeout, queue visibility, load-balancer, request or DB lock timeouts;
  - calls with no timeout at all;
  - blocking calls on an async event loop;
  - sleeps not counted in the budget;
  - lock TTLs that outlive the worker.
- **Grade:** important.
- **Fix:** compute the worst-case path, bound each call, budget the total, and use non-blocking I/O on async paths.

### FM-07 Concurrency and shared state · reliability, correctness
- **Ask:** what breaks with two requests, two workers or two instances at once?
- **Look for:**
  - races outside a transaction;
  - non-atomic check-then-act;
  - rate limiters or claims that aren't atomic, or aren't released on every exit path;
  - per-process caches or throttles that assume a single instance;
  - fire-and-forget background tasks;
  - a shared connection poisoned by a failed statement.
- **Grade:**
  - important;
  - critical when it double-grants or double-acts on money or goods.
- **Fix:**
  - use atomic operations, locks or transactions;
  - keep state in a shared store;
  - release in `finally`;
  - persist and supervise background work.

### FM-08 Silent degradation · reliability
- **Ask:** when something fails, will anyone know?
- **Look for:**
  - errors turned into an empty list, `null` or zero;
  - log levels demoted below what alarms watch;
  - alerts assumed to be delivered;
  - removed audit trails, metrics, feeds or fraud signals;
  - alarms with no recipient;
  - an empty input that silently overwrites state.
- **Grade:**
  - important;
  - critical when an audit trail or a safety signal silently disappears.
- **Fix:** surface errors distinctly, alarm on the metric that actually fails, and name a replacement before removing any signal.

### FM-09 Destructive and scoped writes · correctness
- **Ask:** can a delete, void, overwrite or replace touch more than intended, or leave two systems out of step?
- **Look for:**
  - writes not limited to rows the code owns;
  - PUT-replace of a whole map;
  - deletes that ignore dependent open work;
  - a commit followed by a side effect that can fail (DB vs queue, DB vs external API);
  - a response sent after a commit when the next step can still fail.
- **Grade:**
  - critical on live data or inventory;
  - important otherwise.
- **Fix:**
  - scope by owner or state;
  - skip rows with open dependents;
  - use an outbox or a single transaction, or reconcile;
  - fail closed.

### FM-10 Contract and schema evolution · reliability, correctness
- **Ask:** after this change, do every reader and writer, deploy order and stored datum still agree?
- **Look for:**
  - a schema or API change with no migration;
  - migrations that edit applied files;
  - constraints that existing rows violate;
  - backfills that write current values into history;
  - a frontend shipped ahead of its backend;
  - saved data, URLs or searches from earlier versions that no longer load;
  - an inner join that hides rows with newly-null keys.
- **Grade:**
  - critical when merging breaks the deploy or loses data;
  - important otherwise.
- **Fix:** expand, migrate, then contract; state the deploy order; keep backward-compatible reads.

### FM-11 Data semantics · correctness
- **Ask:** are values interpreted the same way everywhere?
- **Look for:**
  - null vs zero vs empty;
  - silent coercion;
  - truncation at row or page caps;
  - money without its currency, and sums across currencies;
  - timezones, and date-only values that shift;
  - an order-dependent first-row pick with no deciding `ORDER BY`;
  - case, whitespace or URL normalization that differs between layers;
  - logic keyed on labels or message text instead of ids;
  - the wrong identifier or unit shown.
- **Grade:**
  - important when wrong data persists or is acted on;
  - critical for financial totals;
  - consider when display-only.
- **Fix:** carry units, normalize once, decide ordering explicitly, and key on ids.

### FM-12 Caching and staleness · correctness, reliability
- **Ask:** can stale data be shown, acted on or written back?
- **Look for:**
  - cache keys missing an input;
  - no invalidation on write;
  - no TTL in long-lived processes;
  - failures that get cached;
  - async results applied after the user moved on;
  - mirrors that record the requested state instead of the actual one;
  - no freshness guard on upstream data.
- **Grade:** important.
- **Fix:**
  - full keys, invalidate on write, TTLs;
  - check the request is still current before applying;
  - record the confirmed state;
  - add freshness checks.

### FM-13 Authorization and trust boundaries · security
- **Ask:** is every permission enforced where the client can't bypass it?
- **Look for:**
  - client-only guards;
  - roles, ids or owners supplied by the client;
  - IDOR;
  - new routes with no guard;
  - client role lists out of step with the server's;
  - read and write merged under one permission;
  - inputs not restricted to the supported values.
- **Grade:**
  - critical when exploitable, or when a "fix" doesn't close the exploit;
  - important otherwise.
- **Fix:** server-side checks, one source of truth for roles, and allow-lists.

### FM-14 Secrets and sensitive data · security
- **Ask:** can a credential, token, card number, PII or full payload leak or stay live?
- **Look for:**
  - credentials in source, config or IaC;
  - secrets deleted but not rotated;
  - sensitive data in logs, exception text, URLs, consoles, exports or caches without expiry;
  - over-privileged credentials on public endpoints.
- **Grade:**
  - critical when a live or production credential is exposed;
  - important otherwise.
- **Fix:** a secret store plus rotation, redaction, and least privilege.

### FM-15 Configuration and environments · reliability
- **Ask:** will this behave correctly in every environment?
- **Look for:**
  - env or config names the code doesn't read;
  - staging pointed at production accounts, queues or secrets;
  - no runtime kill switch on automated money or publish actions;
  - prod toggles that fail silently;
  - invalid schedule expressions;
  - windows or lookbacks that stop covering the interval.
- **Grade:**
  - critical when certain to break or leave a gap;
  - important otherwise.
- **Fix:** validate config at startup, isolate environments, add kill switches, and check schedule math.

### FM-16 Performance and cost at scale · performance, cost
- **Ask:** what does this cost per request, per row and per run as data grows?
- **Look for:**
  - N+1 queries and per-row subqueries;
  - full scans on hot paths or scheduled jobs;
  - a new lookup with no index;
  - fan-out per keystroke or per item;
  - unbounded caches;
  - work that grows with history;
  - an external limiter bypassed.
- **Grade:**
  - important on hot paths, or when it grows without bound;
  - consider otherwise.
- **Fix:** batch the work, add indexes, filter or window it, debounce, and bound the cache.

### FM-17 User-facing truth · correctness, reliability
- **Ask:** does the UI tell the truth, and does it keep the user's work safe?
- **Look for:**
  - copy, tooltips or result messages that are false for the code path;
  - loading, error and empty states merged into one;
  - guards that fail open before data loads;
  - form state that leaks between open, cancel, create and edit;
  - refetches that wipe unsaved input;
  - bulk actions with no per-item outcome;
  - saves that ignore the version the user reviewed.
- **Grade:**
  - important when the user acts on a falsehood or loses work;
  - consider when cosmetic.
- **Fix:** distinct states, fail closed, reset on open, per-item results, and optimistic-concurrency versions.

### FM-18 Verification that verifies · correctness
- **Ask:** do the tests and checks prove the claimed behavior?
- **Look for:**
  - tests that never run (markers, collection, CI wiring);
  - fixtures that don't exercise the path;
  - assertions on strings instead of behavior;
  - mocks of the unit under test;
  - CI checks added but not executed;
  - dependency pins to unreleased versions.
- **Grade:**
  - important when a test gives false confidence on the change's main risk;
  - otherwise use it as evidence.
- **Fix:** name the regression test that would fail before the fix.

### FM-19 Change hygiene · ownership, pattern_fit, architecture
- **Ask:** does the change say what it does, and leave nothing behind?
- **Look for:**
  - descriptions, test plans, docs or comments that don't match the diff;
  - debug scaffolding;
  - placeholders;
  - env vars added but never read;
  - duplicated logic that must "be kept in step";
  - work outside the ticket's scope.
- **Grade:** per SKILL.md category thresholds.
  - Debug code that runs on every invocation, or writes to disk in prod, is critical.
  - A description that misleads an approver on a security fix or a merge blocker is important.
  - Most other gaps are consider.
- **Fix:** align the docs, delete the scaffolding, share the logic or state the drift risk.
