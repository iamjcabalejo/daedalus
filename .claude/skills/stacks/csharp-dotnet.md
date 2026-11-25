---
name: csharp-dotnet
detect:
  files: ["**/*.cs", "**/*.csproj", "**/*.sln", "**/appsettings*.json", "**/*.razor", "**/*.cshtml"]
evidence: NRD Sight corpus (≈135 C# reviews)
---

# C# / .NET (ASP.NET Core, workers, importers)

## Build

- **Language:**
  - the .NET version comes from `global.json` or `TargetFramework`;
  - nullable reference types are enabled;
  - records or DTOs for requests and responses;
  - no `dynamic`, and no unnecessary `object`.
- **Async:** all I/O is async (`Task` or `ValueTask`), never `.Result` or `.Wait()`, with a `CancellationToken` passed all the way through.
- **Validation:** at the endpoint, with `[ApiController]` model state, DataAnnotations or FluentValidation. Return 400 with `ProblemDetails`.
- **Structure:**
  - thin controllers or minimal APIs → application services;
  - constructor DI;
  - `IHttpClientFactory` for `HttpClient`.
- **Errors:**
  - domain exceptions;
  - a global exception handler that maps to `ProblemDetails`;
  - `throw;` to rethrow;
  - structured `ILogger<T>` logging without secrets.
- **Data:**
  - EF Core with migrations, or Dapper with parameters, never string-built SQL;
  - short units of work;
  - UTC timestamps.
- **Security:** `[Authorize]` with policies. Secrets come from configuration providers (Key Vault, Secrets Manager, user-secrets), never from committed `appsettings`.
- **HTTP status codes:** 200, 201 (`CreatedAtAction`), 204, 400, 401, 403, 404, 409, and 500 with a generic message.

## Review

### How the failure modes show up
- **FM-01 Partial failure:** one unmappable record stalls the whole page or run on every schedule; a single 404 item fails every run and never self-heals.
- **FM-02 Unknown outcome:**
  - the retry decision is made on the exception message rather than the status code or body;
  - the response body is read outside the retry loop;
  - the last attempt doesn't throw.
- **FM-06 Budgets:**
  - `Thread.Sleep` in retry paths (use `await Task.Delay(…, ct)`);
  - an `HttpClient` timeout (`TaskCanceledException` without caller cancellation) treated as user cancellation, aborting the run.
- **FM-07 Concurrency:** `async void`; `.Result`/`.Wait()` deadlocks; non-thread-safe collections shared across requests.
- **FM-14 Secrets:**
  - credentials in `appsettings*.json` or as code fallbacks (`?? "token"`);
  - a removed secret that is still live in git history and needs rotating;
  - token fingerprints or raw financial values logged at Info;
  - plaintext credentials in CSV/S3 exports.
- **FM-15 Config:** a cron schedule or lookback changed so the window no longer covers the interval (for example, a monthly run that queries 7 days).
- **FM-16 Cost:** re-exporting full history to new files every run.

### Stack-only checks
- **Disposal.** `IDisposable` resources (`HttpClient` per call, `DbConnection`) are disposed, and `HttpClient` is reused through `IHttpClientFactory`.
- **Nullable reference warnings.** Raise them only when a null path is reachable and changes behavior.
- **EF Core:** `AsNoTracking` on read paths, no client-side evaluation over large sets, and migrations included with model changes.

## Test

- **Framework:** xUnit, NUnit or MSTest, matching the repo.
- **Integration tests:** `WebApplicationFactory`, with EF Core on SQLite, Testcontainers or the repo's pattern.
- **Fakes:** Moq or NSubstitute at the edges.
- **Cases:** 400 validation, 401 and 403, 404, 409 conflicts, and the regression.

## Commands

- **install:** `dotnet restore`.
- **build:** `dotnet build`.
- **test:** `dotnet test`, when a test project exists.
- **format:** `dotnet format --verify-no-changes`.
- **dev:** `dotnet run --project <Web>.csproj` (inferred).
- **Migrations:** `dotnet ef database update` is unsafe.

## Entry points (scan mode)
- `Program.cs`/`Startup`;
- controllers and minimal APIs;
- `BackgroundService`/hosted services;
- Lambda function handlers;
- Hangfire or Quartz jobs.
