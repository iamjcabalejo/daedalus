---
name: api-design
description: Framework-neutral guidance for designing HTTP/REST and RPC APIs (resources, methods, status codes, error shape, validation, pagination, idempotency, versioning, security). Use when planning or implementing an endpoint, or with /scaffold endpoint. Framework specifics come from the stack pack's Build section.
---

# API design

Use the project's existing API style first (look at two or three neighbouring endpoints). This skill fills gaps; the stack pack (`skills/stacks/<pack>.md`, `## Build`) says how to do each item in the detected framework.

## Resources and methods
- **Nouns, plural:** `/orders`, `/orders/{id}`, `/users/{id}/orders`. Actions that aren't CRUD become sub-resources (`POST /orders/{id}/cancel`).
- **Methods:** GET reads (safe, cacheable), POST creates or triggers, PUT replaces, PATCH partially updates, DELETE removes. GET never changes state.
- **RPC styles** (gRPC, GraphQL, JSON-RPC): keep one verb per operation, typed request and response messages, and the same error and idempotency rules.

## Status codes

| Code | Use |
|---|---|
| 200 / 201 / 204 | OK / created (with `Location`) / no content |
| 400 / 422 | malformed request / validation failed (follow the framework's default) |
| 401 / 403 | not authenticated / authenticated but not allowed |
| 404 / 409 | not found / conflicts with current state (duplicate, version mismatch) |
| 429 | rate limited (with `Retry-After`) |
| 500 / 502 / 503 / 504 | server error / bad upstream / unavailable / upstream timeout |

## Errors
- **One error shape** across the API, for example `{"error": {"code": "VALIDATION_ERROR", "message": "…", "details": [{"field": "email", "reason": "invalid"}]}}`, or RFC 9457 problem details where the framework uses them.
- Stable machine-readable `code`s; human `message`s may change. Clients must not branch on message text.
- Never return stack traces, SQL, internal ids or upstream error bodies. Log them server-side with a correlation id and return the id.

## Validation and contracts
- Validate every input at the boundary (body, query, path, headers) with the framework's schema tool; reject unknown fields where the API is strict.
- Response schemas are part of the contract: don't over-fetch (no secrets, no internal columns).
- Publish the contract the framework supports (OpenAPI, protobuf, GraphQL schema) and keep it in step with the code.

## Collections
- Paginate every list (cursor or `limit`/`offset` with a max). Return the next cursor or total, and say which.
- Filters and sorts are explicit, allow-listed query parameters. A client-side cap must never silently truncate results.

## Writes that matter
- **Idempotency:** creating money movements, orders or messages accepts an idempotency key (or a natural unique key) so retries don't duplicate.
- **Concurrency:** use ETags / version columns for updates that can race (409 or 412 on mismatch).
- **Long work:** return 202 with a status resource instead of holding the request open.

## Versioning and change
- Additive changes only within a version: new optional fields, new endpoints. Removing or renaming a field, or tightening validation, is breaking.
- Version in the path or a header, following the repo. Deprecate with a date and a header before removal.

## Security
- Authenticate every non-public route; authorize per resource on the server (never trust client-side role checks).
- Rate limit authentication and expensive endpoints. Limit body size and content types.
- Treat ids from the client as untrusted: check ownership, not just existence.
- Configure CORS to the known origins only.
