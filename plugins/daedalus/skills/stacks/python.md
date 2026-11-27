---
name: python
detect:
  files: ["**/*.py", "pyproject.toml", "requirements*.txt", "Pipfile", "setup.py", "setup.cfg"]
  signals: ["fastapi", "django", "flask", "pydantic", "boto3", "psycopg", "sqlalchemy", "celery"]
evidence: code review findings on Python services
---

# Python (FastAPI / Django / Flask, workers, scripts)

## Build

- **Python version:** take it from `requires-python` or `.python-version`, and don't use syntax newer than that.
- **Types:**
  - type hints on public functions, using built-in generics (`list[str]`, `dict[str, T]`);
  - run the repo's type checker (mypy or pyright) when one is configured;
  - narrow `Any` immediately.
- **Validate at the boundary:** use Pydantic v2 models for requests, responses, messages and settings when `pydantic` is a dependency; otherwise dataclasses plus explicit checks.
- **Errors:**
  - small domain exceptions;
  - never a bare `except:` or a broad `except Exception` around a side effect;
  - `raise … from err`;
  - log with context (operation, input summary), never secrets or PII.
- **Structure:** thin handlers (FastAPI routers, Django views, Flask blueprints, Lambda handlers) → a service layer → data access. With FastAPI, inject the DB session, current user and services through `Depends()`.
- **Async:** inside `async def`, use async clients (httpx `AsyncClient`, asyncpg, aioboto3) or `run_in_executor`. Give every outbound call an explicit timeout, and retry with jittered backoff (tenacity if the repo uses it).
- **Data:**
  - parameterized queries only (SQLAlchemy binds, psycopg `%s` parameters);
  - one business action per transaction, kept short;
  - timezone-aware UTC timestamps.
- **Configuration:** read it once at startup (pydantic-settings or env vars), validated. No secrets or URLs in code.
- **Lambda:**
  - a thin handler, with clients created at module scope;
  - AWS Lambda Powertools for logging, metrics and idempotency when the repo uses it;
  - no heavy system dependencies.
- **Packaging:** follow the repo's lock style (poetry, uv, pip-tools); pin versions.

**HTTP contract (when `fastapi`, `django` or `flask` is detected):**
- **Status codes:**

  | Code | Use |
  |---|---|
  | 200 | GET, PUT, PATCH |
  | 201 | POST that creates |
  | 204 | DELETE |
  | 400 / 422 | Validation (FastAPI returns 422 with field details) |
  | 401 | Not authenticated |
  | 403 | Not allowed |
  | 404 | Not found |
  | 409 | Conflict or duplicate |
  | 500 | Generic message; details are logged |

- **Errors:** one error shape through exception handlers, for example `{"error": {"code", "message", "details"}}`. Never return stack traces or internal paths.
- **Routes:**
  - one `APIRouter(prefix=…, tags=[…])` per resource, with `response_model` on routes;
  - authentication as a dependency that returns 401 or 403 before any work;
  - validate content-type and body size.

## Review

### How the failure modes show up
- **FM-02 Unknown outcome:**
  - `requests`/`httpx` calls with no `timeout=`;
  - `raise_for_status()` missing;
  - success inferred from a parsed body without checking the status;
  - the retry decision made on `str(exc)`.
- **FM-06 Budgets:**
  - sync I/O (`requests`, boto3, DB drivers) inside `async def` blocks the event loop; use async clients or `run_in_executor`;
  - `time.sleep` inside retries counts against the budget.
- **FM-07 Concurrency:**
  - `BackgroundTasks` or `asyncio.create_task` results that are never awaited or retained;
  - module-level caches and clients shared across workers;
  - a psycopg connection left aborted after a failed statement, or used after its `with` block closed it.
- **FM-09 Scoped writes:** missing `with conn.transaction()` around write plus audit; the response returned after `commit()` while a later step can still raise.
- **FM-11 Semantics:**
  - `int()` or `float()` coercion of ids or keys;
  - `0`/`0.0` treated as falsy (`if amount:`);
  - Pydantic `model_fields_set` vs defaults;
  - naive vs aware `datetime`.
- **FM-12 Caching:** `functools.lru_cache` or module globals in a long-lived process without TTL or invalidation; failures cached as `None`.
- **FM-13 Authz:**
  - FastAPI routes missing the auth `Depends()`;
  - role checks against client-supplied fields;
  - Pydantic models that accept owner or source ids from the body.
- **FM-14 Secrets:** values in `config.*.py`, `.env*` or `settings.py` defaults; `logger.info(payload)` with tokens or PII; f-strings logging full responses.
- **FM-16 Perf:**
  - an ORM or psycopg query inside a loop (N+1);
  - re-fetching all rows `FOR UPDATE` after each insert;
  - pandas on unbounded result sets.
- **FM-18 Tests:**
  - async tests missing `@pytest.mark.asyncio` (or the anyio marker) never run;
  - mocks patch the function under test;
  - fixtures that don't exercise the branch.

### Stack-only checks
- **Parameterized SQL only.** Concatenation inside SQL with a bound value (`%s || ' hours'`) is not injection; an f-string into `execute()` is.
- **Mutable default arguments** that leak state between calls. Raise only when the leak changes behavior.
- **Bare `except:` or `except Exception: pass`** around a side effect hides FM-08 failures.

## Test

- **Framework:** pytest, with pytest-asyncio or anyio for async code. Mark async tests, or set `asyncio_mode = auto`. An unmarked async test silently doesn't run.
- **Layout:** follow the repo (`tests/unit`, `tests/integration`, `conftest.py`). The usual fixtures are:
  - an app client: httpx `AsyncClient` with `ASGITransport(app=app)` for FastAPI, or Django's test client;
  - a DB-session override;
  - an auth override.
- **Endpoint cases:**
  - the happy path;
  - validation (422 or 400 with field details);
  - 401 and 403;
  - 404;
  - edge cases (empty body, wrong types, boundary values);
  - the regression the change fixes.
- **Data and services:** never a production or shared database. Use a disposable test DB or container, transactions rolled back per test, or fakes. Use moto for AWS when the repo does.
- **Naming:** name tests after the behavior, for example `test_returns_409_when_order_already_linked`. Assert on status, body shape and side effects, not on implementation calls.

## Commands

- **install:** follows the lockfile present: `poetry install`, `uv sync`, `pipenv install --dev`, or `pip install -r requirements*.txt`.
- **test:**
  - a Makefile, Taskfile or justfile target comes first;
  - otherwise `pytest` (from `pytest.ini`, `conftest.py` or `[tool.pytest.ini_options]`);
  - Django uses `python manage.py test`.
- **lint, format and typecheck:**
  - lint: `ruff check .` or `flake8`;
  - format: `ruff format --check .` or `black --check .`;
  - typecheck: `mypy .` or `pyright` (when configured).
- **dev:** `uvicorn <module>:app --reload` (FastAPI; inferred, so confirm it in `/setup`), `python manage.py runserver`, or `flask run`.
- **Migration and deploy commands** (`alembic upgrade`, `manage.py migrate`, `sam deploy`) are unsafe. Never auto-run them.

## Entry points (scan mode)
- FastAPI/Flask routers;
- Django `urls.py`/views;
- Lambda `handler(event, context)`;
- Celery or RQ tasks;
- `if __name__ == "__main__"`;
- management commands.
