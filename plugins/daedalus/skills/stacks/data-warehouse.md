---
name: data-warehouse
detect:
  files: ["**/dbt_project.yml", "**/models/**/*.sql", "**/macros/**/*.sql", "**/snapshots/**", "**/*snowflake*/**", "**/*.snowsql"]
  signals: ["MERGE INTO", "COPY INTO", "CREATE OR REPLACE TASK", "dynamic table", "{{ ref(", "{{ config(", "snowflake", "schemachange", "snowsql", "bigquery", "redshift"]
evidence: NRD Sight corpus (≈150 findings on Snowflake and dbt); the principles apply to BigQuery and Redshift
---

# Data warehouse (Snowflake, dbt; BigQuery and Redshift by analogy)

## Build

- **dbt:**
  - layered models (staging → intermediate → marts) as the repo does;
  - `ref()` and `source()`, never hard-coded table names;
  - explicit materializations;
  - incremental models with a `unique_key` and an `is_incremental()` filter;
  - schema tests in yml (`unique`, `not_null`, `relationships`, `accepted_values`).
- **Warehouse SQL:**
  - explicit column lists, with no `SELECT *` in views used downstream;
  - deterministic dedupe (`QUALIFY ROW_NUMBER() OVER (PARTITION BY key ORDER BY <total order>)`);
  - MERGE with one source row per key and every `WHEN` branch;
  - explicit time zones (`CONVERT_TIMEZONE`).
- **Cost:** prune with filters on partition or clustering columns. Don't scan full history in scheduled tasks. Size each warehouse per task.
- **Loads:** COPY with explicit file patterns and `ON_ERROR = ABORT_STATEMENT` for critical tables; stage, then merge or swap.
- **Access:** roles and grants per environment; no credentials in SQL or `profiles.yml` committed to the repo.

## Review

### How the failure modes show up
- **FM-01 Partial failure:** COPY `on_error = skip_file`/`continue`, or file-window filters, silently skipping data.
- **FM-08 Silent degradation:**
  - work or staging tables dropped while they still hold unmerged rows;
  - stale-row deletes run after a partial extract;
  - a removed audit or history feed.
- **FM-09 Scoped writes / MERGE:**
  - the source has exactly one row per key, chosen by a total `ORDER BY`;
  - every needed `WHEN MATCHED`/`NOT MATCHED` branch exists;
  - soft-deletes come only from complete snapshots.

  [critical when matched rows are dropped]
- **FM-07 Concurrency:** dbt pre-hooks, sequences and incremental models survive concurrent or retried runs; a flag-off or undo reverses rows already persisted.
- **FM-11 Semantics:**
  - filters promised by the spec are actually applied;
  - joins don't fan out;
  - guards work at the right grain (session vs row);
  - timezones are explicit;
  - currency is picked from the rows that survive filtering.
- **FM-12 Staleness:** freshness or staleness guards on snapshots and dynamic tables that downstream logic depends on.
- **FM-16 Cost:**
  - full-history rescans on every scheduled run;
  - MERGE on hashed keys over whole tables;
  - clustering on a column with poor pruning.

  Credits are `consider` unless they grow without bound.

### Stack-only checks
- **Shared rules.** Duplicated selection rules across views should be shared through one upstream model rather than "kept in step".
- **Task schedules.** `CRON`/`SCHEDULE` expressions must match the documented cadence and timezone.

## Test

- **dbt:**
  - `dbt test` (schema and singular tests) and `dbt build` in a **dev target only**;
  - dbt unit tests for complex transformations;
  - compare row counts and key aggregates before and after.
- **Plain SQL repos:** apply views to a dev schema, and assert key uniqueness and freshness.

## Commands

- **Safe:** `dbt deps`, `dbt compile`, `dbt parse`, and `sqlfluff lint` when configured.
- **Reads the target (fine in dev):** `dbt test`.
- **Unsafe** (writes to the target, so confirm the target first):
  - `dbt build`, `dbt run`, `dbt seed`, `dbt snapshot`;
  - schemachange, flyway or snowsql deploy scripts.

## Entry points (scan mode)
- `dbt_project.yml`, `models/`, `macros/`;
- Snowflake tasks, streams and pipes;
- stored procedures;
- grants.
