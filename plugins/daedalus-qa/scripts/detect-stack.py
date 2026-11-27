#!/usr/bin/env python3
"""Detect a project's stacks, commands and integrations, and write .workflow/profile.json.

Read-only toward the project: it reads files and runs only `git` read commands
(remote, branch, log). It never executes project code, installs packages or uses the network.
Python 3.8+, standard library only.

Usage:
  detect-stack.py [--root DIR] [--stdout] [--timeout S] [--max-depth N]
  detect-stack.py --check   [--root DIR]            exit 0 = profile fresh, 1 = missing or stale
  detect-stack.py --ensure --summary [--root DIR]   refresh if stale, then print a short summary
  detect-stack.py --summary [--root DIR]            print the summary of the existing profile
  detect-stack.py --set ROOT:NAME=CMD ... | --confirm ROOT:NAME ...   (used by /setup)
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Only this file's own folder goes on sys.path (PF-2): lib/ is the hub's, never the scanned project's.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from lib.unsafe import UNSAFE_BODY_RE, UNSAFE_RE  # noqa: E402

GENERATOR = "detect-stack@2"
SCHEMA_VERSION = 1
HUB = Path(__file__).resolve().parent.parent
PACK_DIRS = [HUB / "skills" / "stacks", HUB / "skills" / "argus" / "stacks"]
PROFILE_REL = Path(".workflow") / "profile.json"
WALK_DEPTH = 8
MANIFEST_DEPTH = 4
FILE_CAP = 40000
READ_CAP = 256 * 1024
UNSAFE_PATH = Path(__file__).resolve().parent / "lib" / "unsafe.py"

SKIP_DIRS = {
    "node_modules", ".venv", "venv", "env", "vendor", "dist", "build", "target", "out", ".next", ".nuxt",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "coverage", ".terraform",
    ".gradle", "obj", ".idea", ".vscode", ".workflow", "graphify-out", ".cache", "Pods", ".dart_tool",
    "site-packages", "bower_components", ".serverless", ".aws-sam", "cdk.out", "archive",
}
KEEP_HIDDEN = {".github", ".circleci", ".gitlab"}
PRIMARY_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "go.mod", "Cargo.toml",
    "Gemfile", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json", "mix.exs", "Package.swift",
    "dbt_project.yml",
}
PRIMARY_PATTERNS = ["*.csproj", "*.sln", "*.fsproj"]
MANIFEST_NAMES = PRIMARY_NAMES | {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "pnpm-workspace.yaml", "setup.cfg",
    "poetry.lock", "uv.lock", "Pipfile.lock", "tox.ini", "pytest.ini", "manage.py", "alembic.ini", "go.work",
    "settings.gradle", "serverless.yml", "serverless.yaml", "template.yaml", "template.yml", "cdk.json",
    "Chart.yaml", "Makefile", "Taskfile.yml", "justfile", "docker-compose.yml", "docker-compose.yaml",
    "compose.yaml", "flyway.conf", "nest-cli.json", "angular.json", "turbo.json", "nx.json", "lerna.json",
    ".gitlab-ci.yml", "bitbucket-pipelines.yml", "Jenkinsfile", "azure-pipelines.yml", "tsconfig.json",
    "mypy.ini", ".flake8", "ruff.toml", ".golangci.yml", ".golangci.yaml", ".rubocop.yml", "conftest.py",
}
MANIFEST_PATTERNS = PRIMARY_PATTERNS + [
    "requirements*.txt", "Dockerfile*", "vite.config.*", "next.config.*", "jest.config.*", "vitest.config.*",
    "playwright.config.*", "cypress.config.*", ".eslintrc*", "eslint.config.*",
]
EXT_LANG = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
    ".mjs": "javascript", ".cjs": "javascript", ".go": "go", ".cs": "csharp", ".fs": "fsharp", ".rs": "rust",
    ".rb": "ruby", ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift", ".php": "php",
    ".ex": "elixir", ".exs": "elixir", ".sql": "sql", ".tf": "hcl", ".scala": "scala", ".dart": "dart",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".vue": "vue", ".svelte": "svelte", ".sh": "shell",
    ".ps1": "powershell", ".lua": "lua", ".clj": "clojure", ".erl": "erlang", ".hs": "haskell",
}
LANG_PACKS = {
    "python": {"python"}, "typescript": {"node-js", "web-frontend"}, "javascript": {"node-js", "web-frontend"},
    "vue": {"web-frontend"}, "svelte": {"web-frontend"}, "go": {"go"}, "csharp": {"csharp-dotnet"},
    "fsharp": {"csharp-dotnet"}, "sql": {"sql-migrations", "data-warehouse"}, "hcl": {"iac"},
    "shell": None, "powershell": None,
}
FRAMEWORKS = {
    # dependency name (lowercase) -> framework label
    "react": "react", "vue": "vue", "svelte": "svelte", "@sveltejs/kit": "sveltekit", "@angular/core": "angular",
    "next": "next", "nuxt": "nuxt", "vite": "vite", "astro": "astro", "@remix-run/react": "remix",
    "express": "express", "fastify": "fastify", "koa": "koa", "@nestjs/core": "nestjs", "hono": "hono",
    "@tanstack/react-query": "tanstack-query", "antd": "antd", "@mui/material": "mui", "tailwindcss": "tailwind",
    "jotai": "jotai", "@reduxjs/toolkit": "redux", "zustand": "zustand", "prisma": "prisma",
    "@prisma/client": "prisma", "typeorm": "typeorm", "sequelize": "sequelize", "mongoose": "mongoose",
    "knex": "knex", "drizzle-orm": "drizzle", "bullmq": "bullmq",
    "fastapi": "fastapi", "django": "django", "flask": "flask", "starlette": "starlette", "pydantic": "pydantic",
    "sqlalchemy": "sqlalchemy", "celery": "celery", "boto3": "boto3", "pandas": "pandas", "dbt-core": "dbt",
    "github.com/gin-gonic/gin": "gin", "github.com/labstack/echo": "echo", "github.com/go-chi/chi": "chi",
    "github.com/gofiber/fiber": "fiber", "gorm.io/gorm": "gorm", "github.com/aws/aws-lambda-go": "aws-lambda",
    "microsoft.net.sdk.web": "aspnetcore", "microsoft.entityframeworkcore": "efcore", "dapper": "dapper",
    "amazon.lambda.core": "aws-lambda",
    "rails": "rails", "sinatra": "sinatra", "sidekiq": "sidekiq",
    "axum": "axum", "actix-web": "actix", "rocket": "rocket", "tokio": "tokio", "sqlx": "sqlx", "diesel": "diesel",
    "spring-boot-starter-web": "spring-boot", "laravel/framework": "laravel", "symfony/framework-bundle": "symfony",
}
API_FRAMEWORKS = {"fastapi", "django", "flask", "starlette", "express", "fastify", "koa", "nestjs", "hono",
                  "aspnetcore", "gin", "echo", "chi", "fiber", "rails", "sinatra", "axum", "actix", "rocket",
                  "spring-boot", "laravel", "symfony"}
UI_FRAMEWORKS = {"react", "vue", "svelte", "sveltekit", "angular", "next", "nuxt", "astro", "remix"}
TEST_FRAMEWORKS = {"jest": "jest", "vitest": "vitest", "mocha": "mocha", "@playwright/test": "playwright",
                   "cypress": "cypress", "pytest": "pytest", "xunit": "xunit", "nunit": "nunit",
                   "mstest.testframework": "mstest", "rspec": "rspec", "rspec-rails": "rspec", "minitest": "minitest",
                   "github.com/stretchr/testify": "testify", "junit": "junit"}
DATABASES = {"pg": "postgres", "postgres": "postgres", "psycopg": "postgres", "psycopg2": "postgres",
             "psycopg2-binary": "postgres", "asyncpg": "postgres", "npgsql": "postgres", "github.com/lib/pq": "postgres",
             "github.com/jackc/pgx": "postgres", "mysql2": "mysql", "pymysql": "mysql", "mongoose": "mongodb",
             "mongodb": "mongodb", "pymongo": "mongodb", "redis": "redis", "ioredis": "redis",
             "snowflake-connector-python": "snowflake", "snowflake-sdk": "snowflake", "sqlite3": "sqlite",
             "better-sqlite3": "sqlite", "@aws-sdk/client-dynamodb": "dynamodb"}
KEY_DENY = re.compile(r"^(UTF|SHA|ISO|RFC|HTTP|TLS|AES|PG|V|X|ES|CVE|GPT|COVID|MD|IPV|H|ARM|AMD|WIN|NET|REVERT|RELEASE|"
                      r"HOTFIX|FEATURE|FEAT|FIX|BUGFIX|CHORE|DEPENDABOT|RENOVATE|MERGE|PR|ISSUE|STEP|PHASE|TEST|DEV|V2|NODE)$")


# ---------- small helpers ----------

def strip_prefix(text: str, prefix: str) -> str:
    return text[len(prefix):] if text.startswith(prefix) else text


def read_text(path: Path, cap: int = READ_CAP) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read(cap).decode("utf-8", "replace")
    except OSError:
        return ""


def git(root: Path, *args: str) -> str:
    """Run a read-only git command; return stdout or '' on any failure."""
    try:
        res = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=2)
        return res.stdout if res.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def cmd(command: str, source: str, confidence: str, body: str = "") -> dict:
    """A command entry. `body` is what the command actually runs (script body, recipe) for the unsafe check."""
    entry = {"cmd": command, "source": source, "confidence": confidence}
    if UNSAFE_RE.search(command) or (body and UNSAFE_BODY_RE.search(body)):
        entry["unsafe"] = True
    return entry


_GLOB_CACHE: dict = {}


def compile_glob(pattern: str):
    """Return a predicate(files_index) -> bool for one glob, with fast paths for common shapes."""
    if pattern in _GLOB_CACHE:
        return _GLOB_CACHE[pattern]
    ext = re.fullmatch(r"\*\*/\*(\.[\w.]+)", pattern)
    base = re.fullmatch(r"\*\*/([^*?/\[\]]+)", pattern)
    if ext:
        suffix = ext.group(1)
        pred = lambda idx: any(name.endswith(suffix) for name in idx["exts"].get(suffix.rsplit(".", 1)[-1], ()))
    elif base:
        name = base.group(1)
        pred = lambda idx: name in idx["basenames"]
    else:
        rx = re.compile(fnmatch.translate(pattern))
        rx2 = re.compile(fnmatch.translate(strip_prefix(pattern, "**/"))) if pattern.startswith("**/") else None
        pred = lambda idx: any(rx.match(p) or (rx2 is not None and rx2.match(p)) for p in idx["paths"])
    _GLOB_CACHE[pattern] = pred
    return pred


def index_files(paths: list) -> dict:
    exts: dict = {}
    basenames = set()
    for p in paths:
        name = p.rsplit("/", 1)[-1]
        basenames.add(name)
        if "." in name:
            exts.setdefault(name.rsplit(".", 1)[-1], []).append(name)
    return {"paths": paths, "basenames": basenames, "exts": exts}


def matches_any(idx: dict, patterns: list) -> bool:
    return any(compile_glob(p)(idx) for p in patterns)


# ---------- discovery ----------

def walk(root: Path, deadline: float) -> tuple:
    files = []
    timed_out = False
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and (not d.startswith(".") or d in KEEP_HIDDEN))
        if depth >= WALK_DEPTH:
            dirnames[:] = []
        prefix = "" if rel == "." else rel.replace(os.sep, "/") + "/"
        files.extend(prefix + f for f in sorted(filenames))
        if len(files) > FILE_CAP or time.monotonic() > deadline:
            timed_out = True
            break
    return files, timed_out


def is_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if path.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
        return True
    if path.count("/") >= MANIFEST_DEPTH:
        return False
    return name in MANIFEST_NAMES or any(fnmatch.fnmatch(name, p) for p in MANIFEST_PATTERNS) or name.endswith(".tf")


def is_primary(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in PRIMARY_NAMES or any(fnmatch.fnmatch(name, p) for p in PRIMARY_PATTERNS)


def parent_dir(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def workspace_members(root: Path, rel: str) -> set:
    """Members declared by npm/pnpm/yarn workspaces, go.work and Cargo workspaces under one root."""
    base = root if rel == "." else root / rel
    patterns = []
    pkg = load_json(base / "package.json")
    ws = pkg.get("workspaces") if isinstance(pkg, dict) else None
    if isinstance(ws, dict):
        ws = ws.get("packages")
    if isinstance(ws, list):
        patterns += [w for w in ws if isinstance(w, str)]
    patterns += re.findall(r"^\s*-\s*['\"]?([^'\"\n#]+)", read_text(base / "pnpm-workspace.yaml"), re.M)
    patterns += re.findall(r"^\s*(?:use\s+)?\.?/?([\w./-]+)\s*$", block(read_text(base / "go.work"), "use"), re.M)
    patterns += re.findall(r"['\"]([^'\"]+)['\"]", block(read_text(base / "Cargo.toml"), "members"))
    members = set()
    for pat in patterns:
        pat = pat.strip().rstrip("/")
        if not pat or pat.startswith("!"):
            continue
        for match in sorted(base.glob(pat)):
            if match.is_dir() and match.name not in SKIP_DIRS:
                members.add(str(match.relative_to(root)).replace(os.sep, "/"))
    return members


def block(text: str, key: str) -> str:
    """Extract a parenthesised or bracketed block after `key` (go.work `use (...)`, Cargo `members = [...]`)."""
    m = re.search(re.escape(key) + r"\s*=?\s*[\(\[](.*?)[\)\]]", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"^" + re.escape(key) + r"\s+(\S+)", text, re.M)
    return m.group(1) if m else ""


def find_roots(root: Path, files: list) -> list:
    primaries = sorted({parent_dir(f) for f in files if is_primary(f) and f.count("/") <= 2})
    if "." in primaries:
        roots = {"."}
        for member in workspace_members(root, "."):
            if any(parent_dir(f) == member for f in files if is_primary(f)):
                roots.add(member)
        for f in files:
            d = parent_dir(f)
            if is_primary(f) and re.match(r"^(apps|packages|services|libs)/[^/]+$", d):
                roots.add(d)
        return sorted(roots, key=lambda r: (r != ".", r))
    candidates = [p for p in primaries if p.count("/") <= 1]
    roots = [c for c in candidates if not any(c != o and c.startswith(o + "/") for o in candidates)]
    if not roots or any(not owned_by(f, roots) for f in files if f.endswith(".tf") or f.startswith(".github/")):
        roots = ["."] + roots
    return roots


def owned_by(path: str, roots: list) -> bool:
    return any(r == "." or path.startswith(r + "/") for r in roots)


def files_for_root(rel: str, roots: list, files: list) -> list:
    nested = [r for r in roots if r != rel and (rel == "." or r.startswith(rel + "/"))]
    out = []
    for f in files:
        if rel != "." and not f.startswith(rel + "/"):
            continue
        if any(f.startswith(n + "/") for n in nested):
            continue
        out.append(f if rel == "." else f[len(rel) + 1:])
    return out


# ---------- packs ----------

def load_json(path: Path):
    try:
        return json.loads(read_text(path)) if path.is_file() else {}
    except ValueError:
        return {}


def flow_list(frontmatter: str, key: str) -> list:
    m = re.search(r"^\s*" + re.escape(key) + r":\s*(\[.*?\])\s*(?:#.*)?$", frontmatter, re.M)
    if not m:
        return []
    try:
        value = json.loads(m.group(1))
        return [v for v in value if isinstance(v, str)]
    except ValueError:
        return []


def load_packs() -> dict:
    packs: dict = {}
    for pack_dir in PACK_DIRS:
        if not pack_dir.is_dir():
            continue
        for path in sorted(pack_dir.glob("*.md")):
            if path.name.startswith("_") or path.stem in packs:
                continue
            parts = read_text(path).split("---")
            fm = parts[1] if len(parts) > 2 else ""
            if not re.search(r"^detect:\s*$", fm, re.M):
                continue  # SKILL.md, failure-modes.md and other non-pack docs live next to the packs
            packs[path.stem] = {k: flow_list(fm, k) for k in ("files", "weak", "signals")}
    return packs


_SIGNAL_CACHE: dict = {}


def signal_found(signal: str, text: str) -> bool:
    """Token match: 'express' must not match 'expression'; signals ending in '/' or '(' match as prefixes."""
    rx = _SIGNAL_CACHE.get(signal)
    if rx is None:
        lead = r"(?<![\w-])" if signal[:1].isalnum() else ""
        trail = r"(?![\w-])" if signal[-1:].isalnum() else ""
        rx = _SIGNAL_CACHE[signal] = re.compile(lead + re.escape(signal) + trail, re.I)
    return bool(rx.search(text))


def detect_packs(packs: dict, idx: dict, signal_text: str) -> tuple:
    loaded = []
    for name, spec in packs.items():
        strong = matches_any(idx, spec["files"]) or any(signal_found(s, signal_text) for s in spec["signals"])
        if strong:
            loaded.append(name)
    covered = set()
    for name in loaded:
        for pattern in packs[name]["files"] + packs[name]["weak"]:
            covered.add(pattern)
    return sorted(loaded), covered


# ---------- per-root facts ----------

def root_texts(base: Path, rel_files: list) -> dict:
    texts = {}
    for f in rel_files:
        name = f.rsplit("/", 1)[-1]
        if f.count("/") > 1 and not f.startswith(".github/"):
            continue
        if is_manifest(f) and not name.endswith((".lock", ".lockb", "-lock.json", "lock.yaml")):
            texts[f] = read_text(base / f)
    sampled = [f for f in rel_files if f.endswith(".sql")][:40]
    for f in sampled:
        texts[f] = read_text(base / f, 64 * 1024)
    return texts


def dependencies(texts: dict) -> set:
    deps = set()
    pkg = json_or_empty(texts.get("package.json", ""))
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps |= {d.lower() for d in (pkg.get(key) or {})}
    for name, text in texts.items():
        base = name.rsplit("/", 1)[-1]
        if base.startswith("requirements") or base in ("Pipfile", "setup.py", "setup.cfg", "pyproject.toml"):
            deps |= {m.lower() for m in re.findall(r"(?m)^\s*['\"]?([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*[=<>~!;,'\"\n]", text)}
            deps |= {m.lower() for m in re.findall(r"['\"]([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*(?:[=<>~!][^'\"]*)?['\"]", text)}
        elif base == "go.mod":
            deps |= {m.lower() for m in re.findall(r"(?m)^\s*(?:require\s+)?([a-z0-9.\-]+\.[a-z]+/[\w.\-/]+)\s+v", text)}
        elif base.endswith((".csproj", ".fsproj")):
            deps |= {m.lower() for m in re.findall(r'(?:Include|Sdk)="([\w.]+)"', text)}
        elif base == "Gemfile":
            deps |= {m.lower() for m in re.findall(r"(?m)^\s*gem\s+['\"]([\w\-]+)['\"]", text)}
        elif base == "Cargo.toml":
            deps |= {m.lower() for m in re.findall(r"(?m)^\s*([\w\-]+)\s*=", block_after(text, "dependencies"))}
        elif base == "composer.json":
            deps |= {d.lower() for d in (json_or_empty(text).get("require") or {})}
        elif base in ("pom.xml", "build.gradle", "build.gradle.kts"):
            deps |= {m.lower() for m in re.findall(r"(?:artifactId>|['\":])(spring-boot-starter-web|junit[\w\-]*)", text)}
    return deps


def block_after(text: str, header: str) -> str:
    out, active = [], False
    for line in text.splitlines():
        if line.strip().startswith("["):
            active = header in line
            continue
        if active:
            out.append(line)
    return "\n".join(out)


def json_or_empty(text: str) -> dict:
    try:
        value = json.loads(text) if text else {}
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def languages(rel_files: list) -> list:
    counts: dict = {}
    for f in rel_files:
        ext = os.path.splitext(f)[1].lower()
        lang = EXT_LANG.get(ext)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    total = sum(counts.values()) or 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [{"name": k, "files": v} for k, v in ranked if v >= 3 or v / total >= 0.05][:6]


def package_manager(names: set) -> str:
    order = [("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("package-lock.json", "npm"),
             ("poetry.lock", "poetry"), ("uv.lock", "uv"), ("Pipfile.lock", "pipenv"), ("Pipfile", "pipenv"),
             ("go.mod", "go"), ("Cargo.toml", "cargo"), ("Gemfile", "bundler"), ("pom.xml", "maven"),
             ("build.gradle", "gradle"), ("build.gradle.kts", "gradle"), ("composer.json", "composer")]
    for marker, pm in order:
        if marker in names:
            return pm
    if "package.json" in names:
        return "npm"
    if any(n.startswith("requirements") for n in names) or "pyproject.toml" in names or "setup.py" in names:
        return "pip"
    if any(n.endswith((".csproj", ".sln")) for n in names):
        return "dotnet"
    return None


# ---------- commands ----------

COMMAND_NAMES = ("install", "test", "lint", "typecheck", "build", "dev", "format")


def recipe(text: str, target: str, kind: str, depth: int = 0) -> str:
    """Lines a task-runner target runs, plus one level of its prerequisites (Makefile `build: lint test`)."""
    lines = text.splitlines()
    head = {"Makefile": re.compile(r"^" + re.escape(target) + r"\s*:(?!=)(.*)$"),
            "justfile": re.compile(r"^" + re.escape(target) + r"(?:\s+[^:]*)?\s*:(.*)$"),
            "Taskfile.yml": re.compile(r"^  " + re.escape(target) + r"\s*:\s*()$")}[kind]
    for i, line in enumerate(lines):
        m = head.match(line)
        if not m:
            continue
        body, prereqs = [], m.group(1).split() if kind != "Taskfile.yml" else []
        indent = "    " if kind == "Taskfile.yml" else ("\t", " ")
        for nxt in lines[i + 1:]:
            if nxt.strip() == "":
                continue
            if not nxt.startswith(indent):
                break
            body.append(nxt.strip())
        if depth == 0:
            body += [recipe(text, p, kind, 1) for p in prereqs if re.fullmatch(r"[\w\-]+", p)]
        return "\n".join(body)
    return ""


def task_runner_commands(texts: dict) -> dict:
    out = {}
    runners = [("Makefile", r"(?m)^([A-Za-z][\w\-]*):(?!=)", "make {}"),
               ("Taskfile.yml", r"(?m)^  ([A-Za-z][\w\-]*):\s*$", "task {}"),
               ("justfile", r"(?m)^([A-Za-z][\w\-]*)\s*:", "just {}")]
    aliases = {"test": ("test", "tests"), "lint": ("lint",), "typecheck": ("typecheck", "type-check", "types"),
               "build": ("build",), "dev": ("dev", "run", "serve", "start"), "format": ("format", "fmt")}
    for fname, rx, template in runners:
        text = texts.get(fname, "")
        targets = set(re.findall(rx, text))
        for name, options in aliases.items():
            hit = next((t for t in options if t in targets), None)
            if hit and name not in out:
                out[name] = cmd(template.format(hit), f"{fname}#{hit}", "script", body=recipe(text, hit, fname))
    return out


def script_body(scripts: dict, name: str) -> str:
    """A package.json script plus one level of `npm|pnpm|yarn|bun run X` it calls (pre/post hooks included)."""
    body = [str(scripts.get(name, "")), str(scripts.get("pre" + name, "")), str(scripts.get("post" + name, ""))]
    for own in list(body):
        for called in re.findall(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?([\w:\-]+)", own):
            if called in scripts and called != name:
                body.append(str(scripts[called]))
    return "\n".join(b for b in body if b)


def node_commands(texts: dict, pm: str, names: set) -> dict:
    pkg = json_or_empty(texts.get("package.json", ""))
    scripts = pkg.get("scripts") or {}
    run = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun run"}.get(pm, "npm run")
    out = {}
    install = {"pnpm": "pnpm install --frozen-lockfile", "yarn": "yarn install --frozen-lockfile",
               "bun": "bun install", "npm": "npm ci" if "package-lock.json" in names else "npm install"}
    out["install"] = cmd(install.get(pm, "npm install"), "lockfile", "derived")
    aliases = {"test": ("test", "test:unit", "unit"), "lint": ("lint", "lint:check"),
               "typecheck": ("typecheck", "type-check", "tsc", "check-types", "types"), "build": ("build",),
               "dev": ("dev", "start", "serve"), "format": ("format", "fmt", "prettier")}
    for name, options in aliases.items():
        hit = next((s for s in options if s in scripts), None)
        if hit:
            if hit == "test" and pm in ("npm", None):
                value = "npm test"
            else:
                value = f"{run} {hit}"
            out[name] = cmd(value, f"package.json#scripts.{hit}", "script", body=script_body(scripts, hit))
    if "typecheck" not in out and "tsconfig.json" in texts:
        out["typecheck"] = cmd("npx tsc --noEmit", "tsconfig.json", "inferred")
    return out


def python_commands(texts: dict, deps: set, rel_files: list, names: set) -> dict:
    out = {}
    pyproject = texts.get("pyproject.toml", "")
    if "poetry.lock" in names or "[tool.poetry]" in pyproject:
        out["install"] = cmd("poetry install", "poetry", "derived")
    elif "uv.lock" in names:
        out["install"] = cmd("uv sync", "uv.lock", "derived")
    elif "Pipfile" in names:
        out["install"] = cmd("pipenv install --dev", "Pipfile", "derived")
    else:
        req = next((f for f in sorted(texts) if f.rsplit("/", 1)[-1].startswith("requirements")), None)
        if req:
            out["install"] = cmd(f"pip install -r {req}", req, "derived")
    has_tests = any(re.search(r"(^|/)(test_[^/]+|[^/]+_test)\.py$", f) for f in rel_files)
    if "pytest" in deps or "pytest.ini" in texts or "conftest.py" in texts or "[tool.pytest" in pyproject:
        out["test"] = cmd("pytest", "pytest config/dependency", "derived")
    elif "manage.py" in texts:
        out["test"] = cmd("python manage.py test", "manage.py", "derived")
    elif has_tests:
        out["test"] = cmd("python -m pytest", "test files", "inferred")
    if "ruff" in deps or "[tool.ruff" in pyproject or "ruff.toml" in texts:
        out["lint"] = cmd("ruff check .", "ruff config/dependency", "derived")
        out["format"] = cmd("ruff format --check .", "ruff", "derived")
    elif "flake8" in deps or ".flake8" in texts:
        out["lint"] = cmd("flake8", "flake8", "derived")
    if "black" in deps and "format" not in out:
        out["format"] = cmd("black --check .", "black", "derived")
    if "mypy" in deps or "[tool.mypy" in pyproject or "mypy.ini" in texts:
        out["typecheck"] = cmd("mypy .", "mypy config/dependency", "derived")
    dev = python_dev_command(texts, deps, rel_files)
    if dev:
        out["dev"] = dev
    return out


def python_dev_command(texts: dict, deps: set, rel_files: list):
    if "manage.py" in texts:
        return cmd("python manage.py runserver", "manage.py", "derived")
    if "fastapi" in deps or "starlette" in deps:
        for candidate in ("main.py", "app/main.py", "src/main.py", "src/app/main.py", "app.py"):
            if candidate in rel_files:
                module = candidate[:-3].replace("/", ".")
                return cmd(f"uvicorn {module}:app --reload", candidate, "inferred")
    if "flask" in deps:
        return cmd("flask run", "flask dependency", "inferred")
    return None


def other_ecosystem_commands(names: set, texts: dict, deps: set, rel_files: list) -> dict:
    out = {}
    if "go.mod" in names:
        out.update(install=cmd("go mod download", "go.mod", "derived"), test=cmd("go test ./...", "go.mod", "derived"),
                   build=cmd("go build ./...", "go.mod", "derived"), typecheck=cmd("go vet ./...", "go.mod", "derived"))
        if ".golangci.yml" in names or ".golangci.yaml" in names:
            out["lint"] = cmd("golangci-lint run", ".golangci.yml", "derived")
    if any(n.endswith((".csproj", ".sln")) for n in names):
        out.update(install=cmd("dotnet restore", "*.csproj", "derived"), build=cmd("dotnet build", "*.csproj", "derived"))
        if any(re.search(r"tests?\.csproj$", f, re.I) for f in rel_files) or deps & {"xunit", "nunit", "mstest.testframework"}:
            out["test"] = cmd("dotnet test", "test project", "derived")
    if "Cargo.toml" in names:
        out.update(test=cmd("cargo test", "Cargo.toml", "derived"), build=cmd("cargo build", "Cargo.toml", "derived"),
                   lint=cmd("cargo clippy", "Cargo.toml", "derived"), format=cmd("cargo fmt --check", "Cargo.toml", "derived"))
    if "Gemfile" in names:
        out["install"] = cmd("bundle install", "Gemfile", "derived")
        if "rspec" in deps or "rspec-rails" in deps or any(f.startswith("spec/") for f in rel_files):
            out["test"] = cmd("bundle exec rspec", "Gemfile/spec", "derived")
        elif "rails" in deps:
            out["test"] = cmd("bin/rails test", "rails", "derived")
        if ".rubocop.yml" in names:
            out["lint"] = cmd("bundle exec rubocop", ".rubocop.yml", "derived")
        if "rails" in deps:
            out["dev"] = cmd("bin/rails server", "rails", "derived")
    if "pom.xml" in names:
        out.update(test=cmd("mvn test", "pom.xml", "derived"), build=cmd("mvn package", "pom.xml", "derived"))
    elif names & {"build.gradle", "build.gradle.kts"}:
        out.update(test=cmd("./gradlew test", "build.gradle", "derived"), build=cmd("./gradlew build", "build.gradle", "derived"))
    if "dbt_project.yml" in names:
        out.update(test=cmd("dbt test", "dbt_project.yml", "derived"), build=cmd("dbt build", "dbt_project.yml", "derived", body="dbt build"))
    if any(n.endswith(".tf") for n in names) and "lint" not in out:
        out["lint"] = cmd("terraform fmt -check -recursive && terraform validate", "*.tf", "inferred")
    return out


CI_PATTERNS = {
    "test": re.compile(r"^(pytest\b.*|python -m pytest\b.*|npm (?:run )?test\b.*|pnpm (?:run )?test\b.*|yarn test\b.*|go test\b.*|dotnet test\b.*|cargo test\b.*|bundle exec rspec\b.*|make test\b.*)$"),
    "lint": re.compile(r"^(ruff check\b.*|npm run lint\b.*|pnpm (?:run )?lint\b.*|yarn lint\b.*|golangci-lint run\b.*|flake8\b.*|npx eslint\b.*|make lint\b.*)$"),
    "build": re.compile(r"^(npm run build\b.*|pnpm (?:run )?build\b.*|yarn build\b.*|dotnet build\b.*|go build\b.*|make build\b.*)$"),
}


def ci_commands(texts: dict) -> dict:
    """Pick test/lint/build commands from CI step lines (line scan only; no multi-line regex)."""
    out = {}
    for name, text in sorted(texts.items()):
        if not (name.startswith(".github/workflows/") or name.rsplit("/", 1)[-1] in (".gitlab-ci.yml", "bitbucket-pipelines.yml")):
            continue
        for raw in text.splitlines():
            line = re.sub(r"^\s*(?:-\s*)?(?:run:\s*)?", "", raw).strip().strip("'\"")
            if not line or len(line) > 200:
                continue
            for key, rx in CI_PATTERNS.items():
                if key not in out and rx.match(line):
                    out[key] = cmd(line, name, "inferred")
    return out


def merge_commands(*layers: dict) -> dict:
    merged = {}
    for layer in layers:
        for name, value in layer.items():
            merged.setdefault(name, value)
    return {k: merged[k] for k in COMMAND_NAMES if k in merged}


# ---------- ui, tests, data, infra, layer ----------

def ui_facts(packs: list, frameworks: set, texts: dict, rel_files: list, base: Path) -> dict:
    present = "web-frontend" in packs or bool(frameworks & UI_FRAMEWORKS)
    if not present:
        return {"present": False, "dev_url": None, "router": None}
    port = None
    for f in rel_files:
        if re.fullmatch(r"(vite|next|nuxt|astro)\.config\.\w+", f):
            m = re.search(r"port\s*:\s*(\d{2,5})", read_text(base / f, 32 * 1024))
            if m:
                port = int(m.group(1))
                break
    scripts = " ".join((json_or_empty(texts.get("package.json", "")).get("scripts") or {}).values())
    m = re.search(r"--port[ =](\d{2,5})|-p (\d{2,5})", scripts)
    if port is None and m:
        port = int(m.group(1) or m.group(2))
    if port is None:
        port = 3000 if frameworks & {"next", "nuxt", "remix"} else 4200 if "angular" in frameworks else 4321 if "astro" in frameworks else 5173 if "vite" in frameworks else None
    deps = {d for d in (json_or_empty(texts.get("package.json", "")).get("dependencies") or {})}
    router = next((r for r in ("react-router-dom", "react-router", "@tanstack/react-router", "vue-router", "@angular/router") if r in deps), None)
    if router is None and "next" in frameworks:
        router = "next"
    return {"present": True, "dev_url": f"http://localhost:{port}" if port else None, "router": router}


def test_facts(deps: set, rel_files: list) -> dict:
    frameworks = sorted({label for dep, label in TEST_FRAMEWORKS.items() if dep in deps})
    checks = [("**/*.test.ts", r"\.test\.ts$"), ("**/*.test.tsx", r"\.test\.tsx$"), ("**/*.test.js", r"\.test\.jsx?$"),
              ("**/*.spec.ts", r"\.spec\.tsx?$"), ("**/__tests__/**", r"(^|/)__tests__/"), ("**/test_*.py", r"(^|/)test_[^/]+\.py$"),
              ("**/*_test.py", r"_test\.py$"), ("**/*_test.go", r"_test\.go$"), ("**/*Tests.csproj", r"Tests?\.csproj$"),
              ("spec/**/*_spec.rb", r"^spec/.*_spec\.rb$"), ("test/**/*_test.rb", r"^test/.*_test\.rb$"), ("tests/**/*.rs", r"^tests/.*\.rs$")]
    patterns = [glob for glob, rx in checks if any(re.search(rx, f) for f in rel_files)]
    if not frameworks:
        if any(p.endswith("_test.go") for p in patterns):
            frameworks = ["go test"]
        elif "tests/**/*.rs" in patterns:
            frameworks = ["cargo test"]
    return {"frameworks": frameworks, "patterns": patterns}


def data_facts(deps: set, rel_files: list, names: set) -> dict:
    databases = sorted({db for dep, db in DATABASES.items() if dep in deps})
    if any(f.endswith(".sql") and "snowflake" in f.lower() for f in rel_files) or "snowflake" in " ".join(rel_files[:2000]).lower():
        databases = sorted(set(databases) | {"snowflake"})
    migrations = None
    checks = [("flyway", r"(^|/)V\d[\w.]*__[^/]+\.sql$"), ("alembic", r"(^|/)alembic\.ini$"), ("prisma", r"(^|/)prisma/schema\.prisma$"),
              ("rails", r"^db/migrate/"), ("django", r"(^|/)migrations/\d{4}_[^/]+\.py$"), ("ef-core", r"(^|/)Migrations/[^/]+\.cs$"),
              ("liquibase", r"changelog[^/]*\.(xml|ya?ml)$"), ("dbt", r"(^|/)dbt_project\.yml$")]
    for tool, rx in checks:
        hit = next((f for f in rel_files if re.search(rx, f)), None)
        if hit:
            migrations = {"tool": tool, "path": parent_dir(hit)}
            break
    return {"databases": databases, "migrations": migrations}


def infra_facts(rel_files: list, names: set, texts: dict) -> dict:
    iac = set()
    if any(f.endswith(".tf") for f in rel_files):
        iac.add("terraform")
    if names & {"serverless.yml", "serverless.yaml"}:
        iac.add("serverless")
    if "cdk.json" in names:
        iac.add("cdk")
    if any(re.search(r"AWSTemplateFormatVersion|Transform:\s*AWS::Serverless", t) for n, t in texts.items() if n.endswith(("template.yaml", "template.yml"))):
        iac.add("cloudformation")
    if "Chart.yaml" in names or any(f.startswith(("k8s/", "kubernetes/", "helm/")) for f in rel_files):
        iac.add("kubernetes")
    ci = set()
    if any(f.startswith(".github/workflows/") for f in rel_files):
        ci.add("github-actions")
    for marker, label in ((".gitlab-ci.yml", "gitlab-ci"), ("bitbucket-pipelines.yml", "bitbucket-pipelines"),
                          ("Jenkinsfile", "jenkins"), ("azure-pipelines.yml", "azure-pipelines")):
        if marker in names:
            ci.add(label)
    if any(f.startswith(".circleci/") for f in rel_files):
        ci.add("circleci")
    containers = sorted({"docker"} if any(n.startswith("Dockerfile") for n in names) else set()) + (
        ["compose"] if names & {"docker-compose.yml", "docker-compose.yaml", "compose.yaml"} else [])
    return {"iac": sorted(iac), "ci": sorted(ci), "containers": containers}


def is_cli(names: set, rel_files: list, texts: dict) -> bool:
    pkg = json_or_empty(texts.get("package.json", ""))
    pyproject = texts.get("pyproject.toml", "")
    return ("src/main.rs" in rel_files or bool(pkg.get("bin")) or "[project.scripts]" in pyproject
            or "[tool.poetry.scripts]" in pyproject or "[[bin]]" in texts.get("Cargo.toml", ""))


def layer_for(packs: list, frameworks: set, ui: dict, infra: dict, data: dict, names: set, cli: bool) -> str:
    has_primary = any(is_primary(n) for n in names)
    if ui["present"]:
        return "ui"
    if frameworks & API_FRAMEWORKS:
        return "api"
    if "serverless-queues" in packs or "aws-lambda" in frameworks or "serverless" in infra["iac"]:
        return "worker"
    if (packs and set(packs) <= {"sql-migrations", "data-warehouse", "ci-cd"} and set(packs) - {"ci-cd"}
            or (data["migrations"] or {}).get("tool") in ("flyway", "liquibase", "dbt")):
        return "data"
    if cli:
        return "cli"
    if not has_primary and (infra["iac"] or (packs and set(packs) <= {"iac", "ci-cd"})):
        return "infra"
    return "lib"


# ---------- integrations ----------

def code_host(root: Path) -> dict:
    url = git(root, "remote", "get-url", "origin").strip()
    if not url:
        return {"kind": None, "repo": None}
    m = re.search(r"(github\.com|gitlab\.com|bitbucket\.org|dev\.azure\.com)[:/](.+?)(?:\.git)?$", url)
    kinds = {"github.com": "github", "gitlab.com": "gitlab", "bitbucket.org": "bitbucket", "dev.azure.com": "azure-devops"}
    if not m:
        return {"kind": "other", "repo": None}
    return {"kind": kinds[m.group(1)], "repo": m.group(2)}


def ticket_facts(repo_dirs: list) -> dict:
    subjects, branches = [], []
    for d in repo_dirs[:10]:
        subjects += git(d, "log", "--format=%s", "-200").splitlines()
        branches += git(d, "for-each-ref", "--format=%(refname:short)", "--count=300", "refs/heads", "refs/remotes").splitlines()
    counts: dict = {}
    for text in subjects + branches:
        for prefix in re.findall(r"\b([A-Za-z][A-Za-z0-9]{1,9})-\d+\b", text):
            up = prefix.upper()
            if not KEY_DENY.match(up) and not up.isdigit():
                counts[up] = counts.get(up, 0) + 1
    keys = [k for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v >= 3][:8]
    linear_branches = sum(1 for b in branches if re.search(r"(^|/)[\w.-]+/[a-z][a-z0-9]{1,9}-\d+-", b))
    gh_refs = sum(1 for s in subjects if re.search(r"\(#\d+\)|#\d+\b", s))
    if keys:
        system = "linear" if linear_branches >= 3 else "unknown"
        evidence = f"{sum(counts[k] for k in keys)} key mentions in commits/branches; {linear_branches} Linear-style branch names"
        return {"system": system, "key": r"\b(" + "|".join(keys) + r")-\d+\b", "evidence": evidence}
    if gh_refs >= 5:
        return {"system": "github", "key": r"#\d+", "evidence": f"{gh_refs} commit subjects reference #N"}
    return {"system": "none", "key": None, "evidence": "no ticket keys found in recent history"}


# ---------- build profile ----------

def describe_root(root: Path, rel: str, rel_files: list, packs: dict) -> dict:
    base = root if rel == "." else root / rel
    names = {f.rsplit("/", 1)[-1] for f in rel_files if f.count("/") == 0} | {f for f in rel_files if f.startswith(".github/")}
    texts = root_texts(base, rel_files)
    deps = dependencies(texts)
    signal_text = "\n".join(texts.values())
    pack_names, _ = detect_packs(packs, index_files(rel_files), signal_text)
    frameworks = {label for dep, label in FRAMEWORKS.items() if dep in deps}
    pm = package_manager(names)
    commands = merge_commands(
        task_runner_commands(texts),
        node_commands(texts, pm, names) if "package.json" in names else {},
        python_commands(texts, deps, rel_files, names) if names & {"pyproject.toml", "setup.py", "Pipfile", "manage.py"} or any(n.startswith("requirements") for n in names) else {},
        other_ecosystem_commands(names, texts, deps, rel_files),
        ci_commands(texts),
    )
    ui = ui_facts(pack_names, frameworks, texts, rel_files, base)
    data = data_facts(deps, rel_files, names)
    infra = infra_facts(rel_files, names, texts)
    return {
        "path": rel, "name": base.name if rel != "." else root.name,
        "layer": layer_for(pack_names, frameworks, ui, infra, data, names, is_cli(names, rel_files, texts)),
        "languages": languages(rel_files), "frameworks": sorted(frameworks), "packs": pack_names,
        "package_manager": pm, "commands": commands, "test": test_facts(deps, rel_files),
        "ui": ui, "data": data, "infra": infra,
    }


def propagate_unsafe(top: dict, members: list) -> None:
    """Workspace-root scripts usually fan out (turbo, nx, lerna, pnpm -r, npm --workspaces): if any member's
    same-named command is unsafe, the root's is too."""
    for name, entry in top["commands"].items():
        if name != "install" and any((m["commands"].get(name) or {}).get("unsafe") for m in members):
            entry["unsafe"] = True


def adjust_workspace(roots: list) -> None:
    """Members inherit the workspace package manager; a workspace root without its own sources is tooling ('lib')."""
    top = next((r for r in roots if r["path"] == "."), None)
    members = [r for r in roots if r["path"] != "."]
    if top is None or not members:
        return
    pm = top.get("package_manager")
    js_pms = {"pnpm": ("pnpm", "pnpm install --frozen-lockfile"), "yarn": ("yarn", "yarn install --frozen-lockfile"), "bun": ("bun run", "bun install")}
    top_install = (top["commands"].get("install") or {}).get("cmd")
    for member in members:
        if pm in js_pms and member.get("package_manager") == "npm":
            member["package_manager"] = pm
            runner, install = js_pms[pm]
            for name, entry in member["commands"].items():
                if name == "install":
                    entry.update(cmd=install, source="workspace lockfile")
                elif entry["cmd"].startswith("npm run ") or entry["cmd"] == "npm test":
                    entry["cmd"] = entry["cmd"].replace("npm run ", runner + " ", 1).replace("npm test", f"{runner.split()[0]} test", 1)
        elif pm == "npm" and top_install == "npm ci" and (member["commands"].get("install") or {}).get("cmd") == "npm install":
            # npm workspaces keep package-lock.json only at the root: members install from it too.
            member["commands"]["install"].update(cmd="npm ci", source="workspace lockfile")
    propagate_unsafe(top, members)
    for member in members:
        if member["layer"] == "ui" and sum(l["files"] for l in member["languages"]) < 5:
            member["layer"] = "lib"  # config/tooling package (eslint, tailwind, tsconfig presets)
            member["ui"] = {"present": False, "dev_url": None, "router": None}
    own_sources = any(l["files"] >= 5 for l in top["languages"]) and top["layer"] in ("api", "worker", "cli")
    if not own_sources:
        top["layer"] = "lib"
        top["ui"] = {"present": False, "dev_url": None, "router": None}


def gaps_for(roots: list) -> list:
    gaps = []
    lang_gaps: dict = {}
    for r in roots:
        label = f"root '{r['path']}'"
        member_of_workspace = r["path"] != "." and any(o["path"] == "." for o in roots)
        if r["layer"] in ("ui", "api", "worker", "lib", "cli") and "test" not in r["commands"] and not (r["layer"] == "lib" and member_of_workspace):
            gaps.append(f"{label}: no test command found")
        if r["layer"] in ("ui", "api", "worker", "cli") and "lint" not in r["commands"]:
            gaps.append(f"{label}: no lint command found")
        if r["ui"]["present"] and "dev" not in r["commands"]:
            gaps.append(f"{label}: UI detected but no dev command")
        total = sum(l["files"] for l in r["languages"]) or 1
        for lang in r["languages"]:
            wanted = LANG_PACKS.get(lang["name"], set())
            if wanted is None or lang["files"] / total < 0.15:
                continue
            if not wanted or not (wanted & set(r["packs"])):
                lang_gaps.setdefault(lang["name"], []).append(r["path"])
    for lang, paths in sorted(lang_gaps.items()):
        shown = ", ".join(paths[:3]) + (f", +{len(paths) - 3} more" if len(paths) > 3 else "")
        gaps.append(f"{lang} has no stack pack, generic rules apply (roots: {shown})")
    return gaps


def manifest_hash(root: Path, manifests: list) -> str:
    h = hashlib.sha256()
    for rel in sorted(manifests):
        h.update(rel.encode())
        h.update(hashlib.sha256(read_text(root / rel, 1024 * 1024).encode()).digest())
    h.update("|".join(sorted(shallow_manifest_names(root))).encode())
    return "sha256:" + h.hexdigest()


def shallow_manifest_names(root: Path) -> list:
    """Manifest-named files at depth <= 2: cheap to list, so new top-level manifests mark the profile stale."""
    out = []
    try:
        for entry in os.scandir(root):
            if entry.is_file() and is_manifest(entry.name):
                out.append(entry.name)
            elif entry.is_dir() and entry.name not in SKIP_DIRS and (not entry.name.startswith(".") or entry.name in KEEP_HIDDEN):
                try:
                    out += [f"{entry.name}/{e.name}" for e in os.scandir(entry.path) if e.is_file() and is_manifest(f"{entry.name}/{e.name}")]
                except OSError:
                    continue
    except OSError:
        pass
    return out


def build_profile(root: Path, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    files, timed_out = walk(root, deadline)
    packs = load_packs()
    roots_rel = find_roots(root, files)
    roots = []
    for rel in roots_rel:
        if time.monotonic() > deadline:
            timed_out = True
            break
        roots.append(describe_root(root, rel, files_for_root(rel, roots_rel, files), packs))
    adjust_workspace(roots)
    repo_dirs =[root] if (root / ".git").exists() else [root / r["path"] for r in roots if (root / r["path"] / ".git").exists()]
    manifests = [f for f in files if is_manifest(f)]
    hosts = [code_host(d) for d in repo_dirs[:10]]
    host = hosts[0] if hosts and all(h["kind"] == hosts[0]["kind"] for h in hosts) else {"kind": "mixed" if hosts else None, "repo": None}
    gaps = gaps_for(roots)
    if timed_out:
        gaps.insert(0, f"detection stopped early (time or file budget, {int(timeout)}s); run /setup --refresh")
    if not packs:
        gaps.insert(0, "no stack packs found next to the detector; pack detection skipped")
    return {
        "schema": SCHEMA_VERSION, "generator": GENERATOR,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "manifest_hash": manifest_hash(root, manifests), "rules_digest": rules_digest(), "manifests": sorted(manifests),
        "roots": roots,
        "integrations": {"code_host": host, "tickets": ticket_facts(repo_dirs),
                         "graph": {"graphify": any((root / r["path"] / "graphify-out" / "graph.json").is_file() for r in roots) or (root / "graphify-out" / "graph.json").is_file()}},
        "gaps": gaps, "confirmed": False,
    }


def carried_user_entry(entry: dict):
    """A committed `user` entry as carried over: known fields only, nothing about trust, and `unsafe`
    recomputed from the command text and never cleared by a committed `unsafe: false`."""
    command = entry.get("cmd")
    if not isinstance(command, str) or not command.strip():
        return None
    source = entry.get("source")
    kept = {"cmd": command, "source": source if isinstance(source, str) else "/setup", "confidence": "user"}
    if entry.get("confirmed") is True:
        kept["confirmed"] = True
    if entry.get("unsafe") is True or UNSAFE_RE.search(command):
        kept["unsafe"] = True
    return kept


def carry_over(new: dict, old: dict) -> dict:
    """Keep /setup confirmations and user-set commands across regeneration. Trust is never recorded here:
    a committed entry runs unasked only through the user's trust store (lib/trust.py)."""
    old_roots = {r["path"]: r for r in old.get("roots", []) if isinstance(r, dict) and isinstance(r.get("path"), str)}
    for root in new["roots"]:
        prev = old_roots.get(root["path"], {}).get("commands", {})
        for name, entry in (prev.items() if isinstance(prev, dict) else ()):
            if not isinstance(entry, dict):
                continue
            if entry.get("confidence") == "user":
                kept = carried_user_entry(entry)
                if kept is not None:
                    root["commands"][name] = kept
            elif entry.get("confirmed") and root["commands"].get(name, {}).get("cmd") == entry.get("cmd"):
                root["commands"][name]["confirmed"] = True
                if entry.get("unsafe") is True:
                    root["commands"][name]["unsafe"] = True
    if old.get("confirmed") and [r["path"] for r in new["roots"]] == list(old_roots):
        new["confirmed"] = True
    return new


# ---------- summary, check, edits ----------

def summary(profile: dict, path_shown: str) -> str:
    state = "confirmed" if profile.get("confirmed") else "unconfirmed: run /setup to confirm"
    lines = [f"Project profile ({path_shown}, {profile.get('generator')}, {state}):"]
    roots = profile.get("roots", [])
    for r in roots[:8]:
        bits = [f"- {r['name'] if r['path'] == '.' else r['path']} [{r['layer']}]"]
        if r.get("frameworks"):
            bits.append(", ".join(r["frameworks"][:4]))
        bits.append("packs: " + (", ".join(r["packs"]) or "none (generic)"))
        for name in ("test", "lint", "build", "dev"):
            entry = r["commands"].get(name)
            if entry:
                bits.append(f"{name}: {entry['cmd']}" + ("" if entry.get("confirmed") or entry["confidence"] != "inferred" else " (inferred)"))
        if r["ui"].get("dev_url"):
            bits.append(r["ui"]["dev_url"])
        lines.append(" · ".join(bits))
    if len(roots) > 8:
        lines.append(f"- …and {len(roots) - 8} more roots (see the profile)")
    integ = profile.get("integrations", {})
    tickets = integ.get("tickets", {})
    lines.append(f"Tickets: {tickets.get('system')}" + (f" ({tickets.get('key')})" if tickets.get("key") else "") +
                 f" · Code host: {integ.get('code_host', {}).get('kind')} · Graph: {'graphify' if integ.get('graph', {}).get('graphify') else 'none'}")
    if profile.get("gaps"):
        lines.append("Gaps: " + "; ".join(profile["gaps"][:3]) + (f" (+{len(profile['gaps']) - 3} more)" if len(profile["gaps"]) > 3 else ""))
    return "\n".join(lines[:12])


def rules_digest() -> str:
    """Digest of the detection rules (this file, lib/unsafe.py and every pack's frontmatter): a hub upgrade marks
    profiles stale."""
    h = hashlib.sha256(GENERATOR.encode())
    h.update(read_text(Path(__file__).resolve(), 4 * 1024 * 1024).encode())
    h.update(read_text(UNSAFE_PATH, 4 * 1024 * 1024).encode())
    for pack_dir in PACK_DIRS:
        for path in sorted(pack_dir.glob("*.md")) if pack_dir.is_dir() else []:
            parts = read_text(path).split("---")
            h.update(path.name.encode())
            h.update((parts[1] if len(parts) > 2 else "").encode())
    return "sha256:" + h.hexdigest()


def is_fresh(root: Path) -> bool:
    profile = load_json(root / PROFILE_REL)
    if not profile or profile.get("schema") != SCHEMA_VERSION or profile.get("rules_digest") != rules_digest():
        return False
    return manifest_hash(root, profile.get("manifests", [])) == profile.get("manifest_hash")


def same_but_timestamp(old, new: dict) -> bool:
    """True when `new` differs from the profile on disk only in `generated_at` (or not at all)."""
    if not isinstance(old, dict):
        return False
    strip = lambda p: {k: v for k, v in json.loads(json.dumps(p)).items() if k != "generated_at"}
    return strip(old) == strip(new)


def write_profile(root: Path, profile: dict) -> bool:
    """Write the profile atomically; leave the file (bytes and mtime) alone when only `generated_at` would change,
    so /setup on an unchanged repository doesn't change the source fingerprint (AC-10)."""
    target = root / PROFILE_REL
    if same_but_timestamp(load_json(target), profile):
        return True
    try:
        target.parent.mkdir(exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, target)
        return True
    except OSError:
        return False


def apply_edits(root: Path, sets: list, confirms: list) -> int:
    profile = load_json(root / PROFILE_REL)
    if not profile:
        print("no profile yet; run detect-stack.py first", file=sys.stderr)
        return 2
    by_path = {r["path"]: r for r in profile["roots"]}
    for spec in sets:
        target, _, value = spec.partition("=")
        path, _, name = target.rpartition(":")
        if path not in by_path or name not in COMMAND_NAMES or not value:
            print(f"bad --set {spec!r}", file=sys.stderr)
            return 2
        entry = cmd(value, "/setup", "user")
        entry["confirmed"] = True
        by_path[path]["commands"][name] = entry
    for spec in confirms:
        path, _, name = spec.rpartition(":")
        entry = by_path.get(path, {}).get("commands", {}).get(name)
        if not entry:
            print(f"bad --confirm {spec!r}", file=sys.stderr)
            return 2
        entry["confirmed"] = True
    pending = [1 for r in profile["roots"] for e in r["commands"].values() if e["confidence"] == "inferred" and not e.get("confirmed")]
    profile["confirmed"] = not pending
    return 0 if write_profile(root, profile) else 1


class HardTimeout(Exception):
    """Raised by SIGALRM so a pathological repo can never hang a session hook."""


def arm_hard_timeout(seconds: float) -> None:
    try:
        import signal

        def _raise(_signum, _frame):
            raise HardTimeout()

        signal.signal(signal.SIGALRM, _raise)
        signal.alarm(max(1, int(seconds)))
    except (ImportError, AttributeError, ValueError):
        pass  # no SIGALRM (e.g. Windows) or not the main thread: the soft deadline still applies


def main(argv: list) -> int:
    try:
        return run(argv)
    except HardTimeout:
        print("detect-stack: hard timeout; profile not updated (run /setup --refresh)", file=sys.stderr)
        return 0


def run(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ap.add_argument("--stdout", action="store_true", help="print the profile; write nothing")
    ap.add_argument("--check", action="store_true", help="exit 0 if the profile is fresh, 1 otherwise")
    ap.add_argument("--ensure", action="store_true", help="regenerate only when missing or stale")
    ap.add_argument("--summary", action="store_true", help="print a short summary of the profile")
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("WORKFLOW_DETECT_TIMEOUT", "5")))
    ap.add_argument("--set", dest="sets", action="append", default=[], metavar="ROOT:NAME=CMD")
    ap.add_argument("--confirm", dest="confirms", action="append", default=[], metavar="ROOT:NAME")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    arm_hard_timeout(args.timeout + 3)
    if args.check:
        return 0 if is_fresh(root) else 1
    if args.sets or args.confirms:
        return apply_edits(root, args.sets, args.confirms)
    if args.summary and not args.ensure and not args.stdout:
        profile = load_json(root / PROFILE_REL)
        print(summary(profile, str(PROFILE_REL)) if profile else "No project profile yet: run /setup.")
        return 0
    if args.ensure and is_fresh(root):
        profile = load_json(root / PROFILE_REL)
    else:
        profile = carry_over(build_profile(root, args.timeout), load_json(root / PROFILE_REL))
        if not args.stdout:
            write_profile(root, profile)
    if args.stdout:
        print(json.dumps(profile, indent=2))
    elif args.summary:
        print(summary(profile, str(PROFILE_REL)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
