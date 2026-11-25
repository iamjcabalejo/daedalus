---
name: sql-migrations
detect:
  files: ["**/migrations/**", "**/migration/**", "**/V*__*.sql", "**/R__*.sql", "**/alembic/**", "**/db/migrate/**", "**/Migrations/*.cs", "**/liquibase/**", "**/changelog*.xml"]
  weak: ["**/*.sql"]   # loose SQL files load this pack only alongside a migration path
evidence: NRD Sight corpus (≈200 findings on Flyway/Postgres); the principles apply to Alembic, Rails, EF, Liquibase and Prisma
---

# SQL schema migrations (Flyway, Alembic, Rails, EF, Liquibase; Postgres first)

## Build

- **Follow the tool's conventions:**
  - Flyway: `V<version>__<desc>.sql`, versioned and never edited once applied, plus `R__` repeatables for views and functions;
  - Alembic: the `down_revision` chain;
  - Rails, EF and Prisma: use the generator rather than hand-writing ids.
- **One logical change per migration.** Breaking changes use expand, migrate, contract: add a nullable column → backfill → enforce → drop the old one in a later release.
- **Safe DDL on Postgres:**
  - `SET lock_timeout` and `statement_timeout`;
  - `NOT VALID` then `VALIDATE CONSTRAINT`;
  - `CREATE INDEX CONCURRENTLY`, outside the migration transaction;
  - no table rewrites on large tables (volatile defaults, type changes).
- **Constraints:**
  - `UNIQUE` on the full natural key;
  - `CHECK` lists matching the app's enums;
  - foreign keys, with an index on the referencing column;
  - explicit nullability.
- **Backfills:** batched, idempotent and using historical values, kept separate from DDL when large.
- **Housekeeping:**
  - grants for new tables and roles;
  - `timestamptz` in UTC;
  - the repo's naming conventions;
  - no secrets in migrations.

## Review

### How the failure modes show up
- **FM-10 Contract evolution:**
  - **Applied files are frozen.** Never rename, re-version or edit an applied migration; even comments change the checksum. Check the version string against the intended date. [critical when it breaks deploy]
  - **Constraints meet existing data.** New constraints and indexes must pass existing rows. Conditional DDL must fail loudly, never silently skip.
  - **Backfills** write historical values, not current ones, and cover rows written between migrate and app rollout.
  - **Deploy order.** State it when merging auto-migrates an environment.
- **FM-07 Concurrency:** triggers must be correct for multi-row statements and inside transactions.
- **FM-11 Semantics:**
  - `UNIQUE` covers the full natural key;
  - `CHECK` lists match app and partner enums;
  - nullability matches docs and code.
- **FM-13 Authz:** new tables and roles get their `GRANT`s; there are no broad grants to public roles.
- **FM-14 Secrets:** no plaintext default passwords or keys in migration history. [critical]
- **FM-16 Perf:** a new lookup has no index; a correlated subquery in an `UPDATE` runs once per row.

### Stack-only checks
- **Locks (Postgres):**
  - use `lock_timeout` on busy tables;
  - add constraints as `NOT VALID` then `VALIDATE CONSTRAINT`;
  - `CREATE INDEX CONCURRENTLY` runs outside the migration transaction, and a failed build leaves an INVALID index;
  - avoid table rewrites (type changes, volatile defaults) on large tables.
- **Reversibility.** A down migration, or a documented roll-forward plan, when the tool expects one.

## Test

- **Fresh run:** apply migrations to a fresh, disposable DB (docker, testcontainers). For risky changes, also apply them to a copy with representative data.
- **Down migrations:** verify the down path where the tool supports it.
- **Constraints:** prove them with tests that insert invalid rows. Run the app's queries, or its test suite, against the migrated schema.
- **Repeatable views and functions:** query them after apply.

## Commands

- **Migrations are unsafe by definition.** Never auto-run `flyway migrate`, `alembic upgrade`, `rails db:migrate`, `prisma migrate deploy` or `dotnet ef database update` against any shared database.
- **Read-only checks against a local DB only:** `flyway validate` and `flyway info`, and `sqlfluff lint` when configured.
- **The test command is usually a gap.** Ask in `/setup` for the local migrate-and-verify command.

## Entry points (scan mode)
- The migration folder in version order;
- repeatable (`R__`) views and functions;
- seed and fixture SQL.
