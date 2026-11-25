#!/usr/bin/env bash
# Validation matrix for .claude/scripts/detect-stack.py (Phase 1, AC-1..AC-6).
#
#   scripts/test-detector.sh            run every row; exit 1 on any mismatch
#   scripts/test-detector.sh --print    print observed facts as JSON (to review before freezing fixtures)
#   scripts/test-detector.sh A G        run only these rows
#
# Rows come from docs/validation/matrix.json:
#   kind "git"   -> shallow-fetched at the pinned sha into $WORKFLOW_MATRIX_CACHE (default: $TMPDIR/workflow-matrix)
#   kind "synthetic" -> files written to a fresh temp dir (unit-style cases, e.g. unsafe script bodies)
#   kind "local" -> {"path", "expect"} from docs/validation/matrix.local.json (gitignored; private repos, so
#                   their paths and expectations never reach the public hub); skipped when absent
# Detection always runs with --stdout, so nothing is ever written into the scanned repos.
# Each row also audits subprocess use (only read-only git) and the 5s budget.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HUB
exec python3 - "$@" <<'PY'
import importlib.util, io, json, os, subprocess, sys, tempfile, time
from contextlib import redirect_stdout
from pathlib import Path

hub = Path(os.environ["HUB"])
args = [a for a in sys.argv[1:] if not a.startswith("--")]
printing = "--print" in sys.argv
matrix = json.loads((hub / "docs/validation/matrix.json").read_text())
local_file = hub / "docs/validation/matrix.local.json"
local = json.loads(local_file.read_text()) if local_file.is_file() else {}
cache = Path(os.environ.get("WORKFLOW_MATRIX_CACHE") or Path(tempfile.gettempdir()) / "workflow-matrix")

spec = importlib.util.spec_from_file_location("detect_stack", hub / ".claude/scripts/detect-stack.py")
ds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds)
ALLOWED_GIT = {"remote", "log", "for-each-ref", "rev-parse", "branch"}


def checkout(row):
    target = cache / row["id"]
    if (target / ".git").is_dir():
        return target
    target.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(["git", "-C", str(target), *a], check=True, capture_output=True)
    run("init", "-q")
    run("remote", "add", "origin", f"https://github.com/{row['repo']}.git")
    run("fetch", "-q", "--depth", "1", "origin", row["sha"])
    run("checkout", "-q", "FETCH_HEAD")
    return target


def detect(path):
    calls = []
    real = ds.subprocess.run

    def audited(argv, *a, **k):
        calls.append(list(argv))
        return real(argv, *a, **k)

    ds.subprocess.run = audited
    buf = io.StringIO()
    start = time.monotonic()
    try:
        with redirect_stdout(buf):
            ds.run(["--root", str(path), "--stdout"])
    finally:
        ds.subprocess.run = real
    return json.loads(buf.getvalue()), time.monotonic() - start, calls


def facts(profile):
    pick = lambda r, n: (r["commands"].get(n) or {}).get("cmd")
    return {"roots": {r["path"]: {"packs": r["packs"], "layer": r["layer"], "test": pick(r, "test"),
                                  "lint": pick(r, "lint"), "build": pick(r, "build"), "dev": pick(r, "dev"),
                                  "ui": r["ui"]["present"]} for r in profile["roots"]},
            "tickets": profile["integrations"]["tickets"]["system"]}


def compare(expect, got):
    diffs = []
    roots = expect.get("roots")
    if roots is not None and sorted(roots) != sorted(got["roots"]):
        diffs.append(f"roots: expected {sorted(roots)}, got {sorted(got['roots'])}")
    for path, exp in (roots or {}).items():
        obs = got["roots"].get(path)
        if not obs:
            continue
        for key in ("packs", "layer", "test", "lint", "build", "dev", "ui"):
            if key in exp and exp[key] != obs[key]:
                diffs.append(f"{path}.{key}: expected {exp[key]!r}, got {obs[key]!r}")
    for key in ("tickets",):
        if key in expect and expect[key] != got[key]:
            diffs.append(f"{key}: expected {expect[key]!r}, got {got[key]!r}")
    return diffs


failures, observed = 0, {}
for row in matrix["rows"]:
    if args and row["id"] not in args:
        continue
    if row["kind"] == "local":
        entry = local.get(row["id"]) or {}
        entry = {"path": entry} if isinstance(entry, str) else entry
        path = entry.get("path")
        if not path or not Path(path).is_dir():
            print(f"SKIP {row['id']:3} {row['label']} (no local path in matrix.local.json)")
            continue
        path = Path(path)
        row = dict(row, expect=entry.get("expect") or {"roots": {}})
    elif row["kind"] == "synthetic":
        path = Path(tempfile.mkdtemp(prefix=f"workflow-synth-{row['id']}-"))
        for rel, content in row["files"].items():
            (path / rel).parent.mkdir(parents=True, exist_ok=True)
            (path / rel).write_text(content)
    else:
        path = checkout(row)
    before = set(os.listdir(path))
    profile, elapsed, calls = detect(path)
    got = facts(profile)
    observed[row["id"]] = got
    problems = [] if printing else compare(row["expect"], got)
    for rpath, cmds in (row.get("commands") or {}).items():
        actual = {r["path"]: r["commands"] for r in profile["roots"]}.get(rpath, {})
        for name, want in cmds.items():
            have = actual.get(name) or {}
            for field, value in want.items():
                if have.get(field, False if field == "unsafe" else None) != value:
                    problems.append(f"{rpath}.commands.{name}.{field}: expected {value!r}, got {have.get(field)!r}")
    bad_calls = [c for c in calls if c[:1] != ["git"] or len(c) < 4 or c[3] not in ALLOWED_GIT]
    if bad_calls:
        problems.append(f"non-read-only subprocess: {bad_calls[:2]}")
    if elapsed > 5:
        problems.append(f"took {elapsed:.2f}s (budget 5s)")
    if set(os.listdir(path)) != before:
        problems.append("the scan changed the repo's top-level entries")
    status = "INFO" if printing else ("PASS" if not problems else "FAIL")
    failures += bool(problems) and not printing
    print(f"{status} {row['id']:3} {row['label']:44} {elapsed:5.2f}s  git calls: {len(calls)}")
    for p in problems:
        print(f"       - {p}")

if printing:
    print(json.dumps(observed, indent=2))
sys.exit(1 if failures else 0)
PY
