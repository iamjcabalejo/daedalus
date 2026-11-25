/**
 * Benchmark hidden-test support (overlaid at scoring time; not part of the upstream repository).
 *
 * Gives the API tests a real Postgres without a server: PGlite (Postgres compiled to WASM) runs in
 * process, and Drizzle's pg-proxy driver sends it every query. The tables are created from whatever the
 * Drizzle schema module exports at scoring time, so the tests don't assume column names. Foreign keys are
 * left out on purpose: the tests don't rely on them, and it keeps the DDL independent of table order.
 *
 * PGlite is installed outside the repository by the task's setup (BENCH_TESTKIT, default /deps/testkit).
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { is, SQL } from "drizzle-orm";
import * as pgCore from "drizzle-orm/pg-core";
import { getTableConfig, PgDialect, PgTable } from "drizzle-orm/pg-core";
import { drizzle } from "drizzle-orm/pg-proxy";

const TESTKIT = process.env.BENCH_TESTKIT ?? "/deps/testkit";
// Date and time values reach Drizzle as the raw text Postgres sends, as with node-postgres.
const RAW_TEXT_TYPES = [1082, 1083, 1114, 1184, 1186, 1266];
const dialect = new PgDialect();

interface QueryResult {
  rows: unknown[];
  fields?: unknown[];
  affectedRows?: number;
}

interface PGliteInstance {
  exec(query: string): Promise<unknown>;
  query(query: string, params?: unknown[], options?: Record<string, unknown>): Promise<QueryResult>;
  close(): Promise<void>;
}

interface PGliteModule {
  PGlite: { create(): Promise<PGliteInstance> } & (new () => PGliteInstance);
}

const pickExport = (node: unknown): string | undefined => {
  if (typeof node === "string") return node;
  if (node && typeof node === "object") {
    for (const key of ["import", "node", "default"]) {
      const found = pickExport((node as Record<string, unknown>)[key]);
      if (found) return found;
    }
  }
  return undefined;
};

async function loadPGlite(): Promise<PGliteModule["PGlite"]> {
  const packageDir = path.join(TESTKIT, "node_modules", "@electric-sql", "pglite");
  const manifest = JSON.parse(readFileSync(path.join(packageDir, "package.json"), "utf8")) as {
    exports?: Record<string, unknown>;
    module?: string;
    main?: string;
  };
  const exportsRoot = manifest.exports?.["."] ?? manifest.exports;
  const entry = pickExport(exportsRoot) ?? manifest.module ?? manifest.main ?? "dist/index.js";
  const loaded = (await import(pathToFileURL(path.join(packageDir, entry)).href)) as PGliteModule;
  return loaded.PGlite;
}

// Drizzle's snake_case conversion for columns whose name comes from their key.
const toSnakeCase = (input: string): string =>
  (input.replace(/['’]/g, "").match(/[\da-z]+|[A-Z]+(?![a-z])|[A-Z][\da-z]+/g) ?? [])
    .map((word) => word.toLowerCase())
    .join("_");

const quote = (name: string): string => `"${name.replace(/"/g, '""')}"`;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyColumn = any;

const columnName = (column: AnyColumn): string =>
  column.keyAsName ? toSnakeCase(String(column.name)) : String(column.name);

const literal = (value: unknown): string => {
  if (value === null) return "NULL";
  if (typeof value === "number" || typeof value === "bigint") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value instanceof Date) return `'${value.toISOString()}'`;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return `'${text.replace(/'/g, "''")}'`;
};

const sqlText = (value: unknown): string => {
  if (is(value, SQL)) return dialect.sqlToQuery((value as SQL).inlineParams()).sql;
  if (typeof value === "function") return sqlText((value as () => unknown)());
  return String(value);
};

function columnDdl(column: AnyColumn): string {
  const parts = [quote(columnName(column)), String(column.getSQLType())];
  if (column.generatedIdentity) {
    parts.push(`GENERATED ${column.generatedIdentity.type === "always" ? "ALWAYS" : "BY DEFAULT"} AS IDENTITY`);
  } else if (column.generated && column.generated.as !== undefined) {
    parts.push(`GENERATED ALWAYS AS (${sqlText(column.generated.as)}) STORED`);
  } else if (column.default !== undefined) {
    parts.push(`DEFAULT ${is(column.default, SQL) ? sqlText(column.default) : literal(column.default)}`);
  }
  if (column.primary) parts.push("PRIMARY KEY");
  else if (column.notNull) parts.push("NOT NULL");
  if (column.isUnique) parts.push("UNIQUE");
  return parts.join(" ");
}

function tableName(table: PgTable): string {
  const config = getTableConfig(table);
  return config.schema ? `${quote(config.schema)}.${quote(config.name)}` : quote(config.name);
}

function tableDdl(table: PgTable): string {
  const config = getTableConfig(table);
  const lines = config.columns.map(columnDdl);
  for (const primaryKey of config.primaryKeys) {
    lines.push(`PRIMARY KEY (${primaryKey.columns.map((c: AnyColumn) => quote(columnName(c))).join(", ")})`);
  }
  const prefix = config.schema ? `CREATE SCHEMA IF NOT EXISTS ${quote(config.schema)};\n` : "";
  return `${prefix}CREATE TABLE ${tableName(table)} (\n  ${lines.join(",\n  ")}\n);`;
}

export interface TestDatabase {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  db: any;
  query(text: string, params?: unknown[]): Promise<Record<string, unknown>[]>;
  reset(): Promise<void>;
  close(): Promise<void>;
}

export async function createTestDatabase(schema: Record<string, unknown>): Promise<TestDatabase> {
  const PGlite = await loadPGlite();
  const pg = typeof PGlite.create === "function" ? await PGlite.create() : new PGlite();
  const exported = Object.values(schema);
  // Read through the namespace so an older drizzle-orm without isPgEnum still loads.
  const isPgEnum = (pgCore as Record<string, unknown>).isPgEnum as ((value: unknown) => boolean) | undefined;
  const enums = exported.filter((value) => (isPgEnum ? isPgEnum(value) : false)) as AnyColumn[];
  const tables = exported.filter((value): value is PgTable => is(value, PgTable));
  const statements = [
    ...enums.map(
      (pgEnum) =>
        `CREATE TYPE ${quote(pgEnum.enumName)} AS ENUM (${(pgEnum.enumValues as string[]).map(literal).join(", ")});`,
    ),
    ...tables.map(tableDdl),
  ];
  await pg.exec(statements.join("\n"));

  const parsers = Object.fromEntries(RAW_TEXT_TYPES.map((oid) => [oid, (value: string) => value]));
  const db = drizzle(
    async (text: string, params: unknown[], method: "all" | "execute") => {
      const result = await pg.query(text, params, { rowMode: method === "all" ? "array" : "object", parsers });
      const rowCount = typeof result.affectedRows === "number" ? result.affectedRows : result.rows.length;
      // node-postgres style extras, for code that reads rowCount from a write without RETURNING.
      const rows = Object.assign(result.rows, { rowCount, fields: result.fields });
      return { rows, rowCount, fields: result.fields };
    },
    { schema, casing: "snake_case" },
  );

  return {
    db,
    query: async (text, params = []) => (await pg.query(text, params)).rows as Record<string, unknown>[],
    reset: async () => {
      for (const table of [...tables].reverse()) {
        await pg.exec(`DELETE FROM ${tableName(table)};`);
      }
    },
    close: () => pg.close(),
  };
}
