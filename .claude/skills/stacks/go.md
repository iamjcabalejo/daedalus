---
name: go
detect:
  files: ["**/*.go", "go.mod", "go.sum"]
evidence: code review findings on Go services
---

# Go

## Build

- **Style and layout:** the Go version comes from `go.mod`; format with gofmt or goimports; follow the repo's package layout (`cmd/`, `internal/`, `pkg/`).
- **Errors:**
  - check every error, and wrap with `fmt.Errorf("…: %w", err)`;
  - use sentinel or typed errors with `errors.Is` and `errors.As`;
  - never write `_ =` for an error that matters.
- **Context:** `context.Context` is the first parameter of I/O functions. Respect cancellation, and set timeouts on the `http.Client` and on per-call contexts.
- **Concurrency:**
  - `errgroup` for fan-out with error propagation;
  - guard shared maps (`sync.Mutex`);
  - every goroutine has a way to stop.
- **HTTP:**
  - thin handlers that validate input;
  - one JSON error shape and correct status codes;
  - auth in middleware.
- **Data:** `database/sql` placeholders, or sqlx or gorm bindings. In transactions, `defer tx.Rollback()`.
- **Configuration:** env vars or flags parsed and validated at startup; no secrets in code.

## Review

### How the failure modes show up
- **FM-01 Partial failure:** a webhook returns 5xx for a payload that will always fail, so it is redelivered forever (return 4xx instead); one bad record aborts the whole run.
- **FM-04 Duplicates:** dedupe or replay markers written before a forward succeeds; flags lost across queue retries.
- **FM-05 Loops:** pagination that never detects a repeated full page; a partial walk published as complete.
- **FM-06 Budgets:**
  - results written on an already-cancelled `ctx`;
  - per-call timeouts that add up past the server `WriteTimeout` or the function limit;
  - account loops with no per-item deadline.
- **FM-07 Concurrency:**
  - goroutines with no `WaitGroup`/`errgroup` or error propagation;
  - data races on maps;
  - `defer` inside loops holding resources.
- **FM-08 Silent degradation:** `log.Error` → `Warn` demotions that silence alarms; ignored `err` returns (`_ =`).
- **FM-11 Semantics:** domain, prefix or keyword matchers that aren't anchored (`strings.Contains`) or case-normalized.
- **FM-14 Secrets:** keys in plaintext URL paths; tokens logged via `%v` on structs.

### Stack-only checks
- **Shared module pins.** `go.mod` must pin a released, merged version of any shared internal module that contains the needed change, not an unmerged pseudo-version, and the bump belongs in this PR.
- **Nil handling.** No nil pointer or map writes on the error path.
- **Shadowing.** `err` shadowing (`:=` in inner scopes) must not drop the real error.

## Test

- **Style:** table-driven tests with `t.Run` subtests, `httptest` for handlers, and testify if the repo uses it.
- **Race detector:** use `-race` for concurrent code when CI does.
- **Complex output:** golden files.
- **Fakes:** define small interfaces at the edges; no global state between tests.

## Commands

- **install:** `go mod download`.
- **test:** `go test ./...`.
- **build:** `go build ./...`.
- **typecheck:** `go vet ./...`.
- **lint:** `golangci-lint run`, when configured.
- **dev:** usually `go run ./cmd/<app>`. It's not detected, so confirm it in `/setup`.

## Entry points (scan mode)
- `main` packages;
- `http.Handle`/router setup;
- Lambda `lambda.Start`;
- queue consumers;
- cron workers.
