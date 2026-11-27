---
name: node-js
detect:
  files: ["**/server.js", "**/server.ts", "**/handler.js", "**/handler.ts", "**/worker*.js", "**/worker*.ts", "**/nest-cli.json", "**/ecosystem.config.js"]
  weak: ["**/*.js", "**/*.ts", "**/*.mjs", "**/*.cjs", "**/app.js", "**/package.json", "**/index.js", "**/index.ts"]   # count only when a files glob or signal also matches
  signals: ["express", "fastify", "koa", "@nestjs/", "@aws-sdk/", "aws-sdk", "\"pg\"", "mysql2", "mongoose", "prisma", "sequelize", "knex", "ioredis", "\"redis\"", "bullmq", "kafkajs", "amqplib", "node-cron", "process.on(", "exports.handler", "require(\"node:"]
evidence: "seed: idioms from a live calibration run plus a small set of code review findings on Node services; the rest is unvalidated"
---

# Node.js services (Express, Fastify, NestJS, Lambda, workers, CLIs)

This pack is for server-side JavaScript and TypeScript. Browser code belongs to `web-frontend`. A repo with both loads both packs.

## Build

- **Runtime and modules:** the Node version comes from `.nvmrc` or `engines`, and the module system from package.json `type` (ESM vs CommonJS). Don't mix them.
- **TypeScript:**
  - strict mode;
  - no `any` (use `unknown` and narrow);
  - explicit types on exported functions;
  - `import type` for types;
  - `readonly` and `as const` where values shouldn't change;
  - no circular imports.
- **Validate at the edge:** HTTP bodies, queue messages and `process.env` go through the repo's validator (zod, joi, class-validator) at startup or entry.
- **Errors:**
  - throw `Error` subclasses with `cause`;
  - use the framework's central error handling: Express 4 needs an async wrapper (or express-async-errors), while Fastify and Nest have it built in;
  - never send stack traces to clients.
- **Async:**
  - always `await` or return promises;
  - `Promise.allSettled` for batches;
  - `AbortSignal.timeout()`, or an axios `timeout`, on every outbound call.
- **Data:**
  - parameterized queries (pg `$1`, knex bindings, ORM APIs);
  - a transaction on one client from `pool.connect()`, released in `finally`.
- **Services and workers:**
  - create clients at module scope and reuse them;
  - handle SIGTERM idempotently and drain in-flight work;
  - log with a correlation id and no secrets.

## Review

### How the failure modes show up
- **FM-01 Partial failure:**
  - `Promise.all` rejects on the first failure and drops every other result. Use `Promise.allSettled` and report per item.
  - SQS handlers return `batchItemFailures`.
  - Stream pipelines use `stream.pipeline` (or `await pipeline(...)`), so one error doesn't leave a half-written file.
- **FM-02 Unknown outcome:**
  - `fetch` doesn't reject on HTTP 4xx/5xx; check `res.ok`.
  - `axios` throws on non-2xx unless `validateStatus` overrides it.
  - Treat `ECONNRESET`, `ETIMEDOUT` and `ECONNABORTED` after a write as unknown, never as success or a plain retry.
- **FM-03 Irreversible:** `axios-retry` or a generic retry wrapper around POSTs with no idempotency key.
- **FM-04 Duplicates:** BullMQ, SQS and cron jobs run again. Dedupe after success, use stable `jobId`s, and keep overlapping `node-cron` runs from double-processing.
- **FM-05 Loops:**
  - recursive `setTimeout` or `setInterval` polling with no cap;
  - `while (next)` pagination with no repeat or empty-page stop;
  - backoff that never resets on success, or resets on a counter (`retry % 3`) instead of on outcome;
  - recovery paths that skip the retry counter and so bypass the max-retries cap.
- **FM-06 Budgets:**
  - **No default timeout:** `fetch` and `axios` have none (`timeout: 0` means wait forever); use `AbortSignal.timeout()` or the `timeout` option.
  - **Event-loop blocking:** sync calls on request paths (`readFileSync`, `pbkdf2Sync`, `execSync`, giant `JSON.parse`, regex backtracking).
  - **Lambda:** budget against `context.getRemainingTimeInMillis()`.
  - **Graceful shutdown:** a bounded wait can't interrupt a worker blocked inside a job, so check cancellation inside the job.
- **FM-07 Concurrency:**
  - **Floating promises.** A missing `await`, or `.then()` with no `.catch()`, is an unhandled rejection, which crashes Node ≥15 or drops the error.
  - **Check-then-act across an `await`** lets another request interleave.
  - **Module-level state** is shared by concurrent requests and is per-instance under scale-out.
  - **pg transactions.** `pool.query()` per statement may use different connections, which breaks the transaction. Use one `client` from `pool.connect()` with `BEGIN`…`COMMIT`, and `client.release()` in `finally`.
  - **Redis:** a pipeline isn't atomic; use `MULTI` or a Lua script.
  - **Shutdown re-entrancy:** `SIGTERM` and `SIGINT` handlers must be idempotent, so `shutdown()` can't run twice during the drain window.
- **FM-08 Silent degradation:**
  - `catch {}` or `catch (e) { return [] }`;
  - per-step timeouts swallowed without signalling partial failure;
  - per-row read failures in a reconcile loop swallowed without retry or metric;
  - `process.on('unhandledRejection')` that only logs.
- **FM-09 Scoped writes:** ORM `update`/`deleteMany` with an empty or undefined `where` (Prisma, Sequelize and Mongoose can then match every row).
- **FM-11 Semantics:**
  - **Money:**
    - `Number(x) || 0` and `parseFloat(x) || 0` on money, rate or fee fields turn a missing value into a silent $0;
    - float math on cents (`Math.round(cents * rate / 100)`) can round a cent low, so use integer cents and explicit rounding;
    - `toFixed` returns a string.
  - **Numbers:** `parseInt` without a radix. Ids above 2^53 (`Number.MAX_SAFE_INTEGER`) lose precision through `JSON.parse`, so keep them as strings.
  - **Dates:** `new Date('YYYY-MM-DD')` is UTC midnight and shifts a day in local zones. ISO strings must match the DB column type.
  - **Comparison:** `==` coercion.
- **FM-12 Caching:**
  - module-level caches in warm Lambdas or long-lived workers with no TTL;
  - a memoized promise that caches a rejection;
  - `Map`/object caches keyed by worker, job or session ids that are never deleted on crash paths, an unbounded memory leak.
- **FM-13 Authz:**
  - Express middleware order: an auth middleware registered after the routes it should protect;
  - owner or role ids taken from `req.body`;
  - prototype pollution through deep-merging user input (`_.merge`, `Object.assign` on parsed JSON);
  - SQL built with template literals (`` `LIMIT ${n}` ``) instead of parameters.
- **FM-14 Secrets:**
  - committed `.env` files;
  - `console.log(req.headers)` or `console.log(config)`;
  - the default Express error handler sending stack traces to clients in prod;
  - tokens in query strings.
- **FM-15 Config:**
  - `process.env.X` read without validation at startup, so a typo becomes `undefined`;
  - state files (tokens, caches, IP lists) written to the working directory, which assumes a single persistent instance.
- **FM-16 Perf:**
  - ORM N+1 (`include`/`populate` in loops);
  - sequential `await` in a loop where bounded parallelism (`p-limit`) fits;
  - loading whole tables or files into memory.
- **FM-18 Tests:**
  - async tests that don't `await` or `return` the promise pass falsely (Jest, Mocha);
  - `jest.mock` of the module under test;
  - snapshot tests standing in for behavior.
- **FM-19 Hygiene:** the same derived value (for example, base plus fee plus tax) recomputed separately in each writer (CSV builders, queue or Redis adapters), so a new component reaches only some of them. Share one function.

### Stack-only checks
- **Express 4 async errors.** A rejected `async` handler doesn't reach `next(err)` without a wrapper (fixed in Express 5).
- **Module systems.** ESM/CJS mismatch: `require()` of an ESM-only package fails at runtime, and `"type": "module"` changes `.js` semantics.
- **Errors.** Throw `Error` objects, not strings, so stacks survive. Use `cause` when wrapping.
- **Timers.** `.unref()` on watchdog or interval timers: removing it keeps the process alive at shutdown, and adding it can let the process exit early. Raise only when the change in behavior matters.
- **Dependencies:**
  - a new dependency without a lockfile update;
  - `postinstall` scripts from new packages (supply chain);
  - a major-version bump with no changelog check.

## Test

- **Runner:** use the repo's (Vitest, Jest, Mocha or `node:test`). Async tests must `await` or return their promise.
- **HTTP:** supertest (Express), `inject()` (Fastify) or the Nest testing module.
- **Mocks:** only at the edges: nock or msw for HTTP, aws-sdk-client-mock for AWS. Never mock the module under test.
- **Integration:** use a real test DB or container when the repo has one (testcontainers, docker-compose). Reset state between tests.
- **Cases:** the happy path, validation errors, auth failures, not found, retries or timeouts where relevant, and the regression.

## Commands

- **install:** follows the lockfile: `npm ci`, `pnpm install --frozen-lockfile`, `yarn install --frozen-lockfile` or `bun install`. Workspace members install from the root lockfile.
- **Scripts:** test, lint, typecheck, build, dev and start come from `package.json` scripts. The typecheck fallback is `npx tsc --noEmit` (inferred).
- **Read the script body before running it.** The detector flags scripts that migrate, deploy or publish, including through `pre`/`post` scripts and one `npm run` hop.

## Entry points (scan mode)
- `package.json` `main`, `bin` and `scripts`;
- `server`/`app` bootstrap and Express, Fastify or NestJS routers;
- Lambda `exports.handler`;
- BullMQ, SQS or Kafka consumers;
- `node-cron` jobs and CLI scripts;
- `process.on` signal handlers.
