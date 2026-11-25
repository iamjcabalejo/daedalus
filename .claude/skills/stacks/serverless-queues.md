---
name: serverless-queues
detect:
  files: ["**/lambda_handler*", "**/handler.*", "**/serverless.y*ml", "**/template.y*ml"]
  signals: ["sqs", "SQS", "lambda_handler", "batchItemFailures", "SNS", "EventBridge", "redis", "Redis", "pubsub", "kafka", "Kafka", "RabbitMQ", "celery"]
evidence: NRD Sight corpus (≈900 reliability findings on Lambda/SQS/Redis pipelines); the principles apply to Cloud Functions, Pub/Sub, Kafka and RabbitMQ
---

# Serverless functions, queues and caches (Lambda, SQS/SNS, EventBridge, Redis; any broker by analogy)

Load this pack together with the language pack.

## Build

- **Handlers:**
  - thin: parse and validate the event → service → side effects;
  - clients and connections at module scope, reused across invocations.
- **SQS:**
  - partial batch responses (`batchItemFailures`), with `ReportBatchItemFailures` enabled on the mapping;
  - idempotency keyed on the message id or a natural key (Powertools idempotency, or the repo's own table);
  - a DLQ with `maxReceiveCount`;
  - a visibility timeout comfortably above the function timeout plus retries.
- **EventBridge, SNS and schedules** deliver at least once, so make handlers idempotent and keep schedule expressions valid.
- **Redis:**
  - atomic operations (Lua or `MULTI`);
  - a TTL on every key;
  - per-purpose key namespaces;
  - locks released in `finally`.
- **Time budget:** check the remaining time (`getRemainingTimeInMillis()` or `get_remaining_time_in_millis()`) and stop before the timeout.
- **Observability:**
  - structured logs with a correlation id;
  - metrics for failures and DLQ depth;
  - alarms routed to a person.

## Review

### How the failure modes show up
- **FM-01 Partial failure:**
  - SQS batches return `batchItemFailures` instead of failing the whole batch;
  - re-enqueued messages stay under `maxReceiveCount` and land in a DLQ;
  - one unparseable item never replays the chunk.
- **FM-02 Unknown outcome:** partner 5xx, timeouts and transport errors after a buy, confirm or post go to an unknown-outcome path, never a blind retry.
- **FM-04 Duplicates:** standard queues and EventBridge deliver at least once; overlapping schedules and reconcile sweeps must not re-queue or re-alert in-flight work.
- **FM-05 Loops:** re-poll and follow-up chains get attempt or age caps, a terminal state and an alert.
- **FM-06 Budgets:** timeouts + retries + sleeps + lock TTL < function timeout < queue visibility timeout; lock TTLs don't outlive the worker.
- **FM-07 Concurrency:**
  - **Redis/Lua rate limiters and claims:** atomic grants; every waiter or claim (`ZADD`/`SET`) released on every exit path, including timeouts; keys scoped so paths can't collide; limits still hold when functions or tasks scale out.
  - **Backlog errors** are caught at the handler, so they aren't treated as batch failures.
- **FM-08 Silent degradation:**
  - a failed `send_message`/re-enqueue is never swallowed (critical on hot pipelines);
  - alert delivery can fail, so park or incident markers must not assume it succeeded.
- **FM-12 Caching:**
  - warm-container caches (secrets, tokens, identification lookups) need a TTL;
  - failures are never cached;
  - clients are created once per container, not per invocation.
- **FM-15 Config:** a runtime kill switch for automated buy, publish or broadcast; staging never points at live partner accounts or prod queue URLs.
- **FM-16 Cost:** a secret-store call on every request, including unauthenticated ones; polling that re-sends every open item each run.

## Test

- **Handlers:** test them with sample events (scrubbed real payloads). For mixed good and bad batches, assert the exact `batchItemFailures`.
- **Fakes:** moto, localstack or aws-sdk-client-mock for AWS; fakeredis or a Redis container for Redis.
- **Idempotency:** invoke the handler twice with the same event.
- **Isolation:** never point tests at real queues, topics or accounts.

## Commands

- **Tests:** use the language pack's commands (`pytest`, `npm test`).
- **Local invoke:** `sam local invoke` and `serverless invoke local` may need credentials, so confirm first.
- **Deploys:** `sam deploy`, `sls deploy` and `cdk deploy` are unsafe.

## Entry points (scan mode)
- Function handlers;
- event source mappings;
- schedules;
- queue producers and consumers;
- Redis key schemas;
- webhook endpoints, which must verify signatures and have replay protection.
