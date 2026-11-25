#!/usr/bin/env bash
# Capability probes for host hooks, agents and install types (plan P0 §3.2-§3.3; AC-1, AC-2, AC-3).
#
#   scripts/probes/run-probes.sh --case <id>|all [--install script|plugin|both] [--host claude|cursor|codex]
#                                [--budget-usd N] [--dry-run]
#
# Each run gets a fresh throwaway git repo under $TMPDIR/daedalus-probes/<UTC-ts>/<case>[.<variant>]/<install>/ and
# installs the probe templates there: the project's .claude/ for script installs, or a generated probe-plugin/ loaded
# with --plugin-dir for plugin installs (verify in T0; fallback: a project-scope local marketplace install, removed
# after, done by hand). It runs the host CLI once with the case's stimulus, evaluates the observations, redacts the
# captured payloads, and removes everything it installed.
#
# It never writes to ~/.claude, ~/.cursor, ~/.codex or the hub's .claude/. After the last run it compares the hub's
# git status and digests of the user-scope settings and plugin registries with a snapshot taken before the first.
# Fixtures and results reach scripts/probes/{fixtures,results}/ only when that check and the leak scan are clean.
#
# Live runs spend money. They need --budget-usd, print the run count and the estimated ceiling first, refuse when
# the ceiling exceeds the budget, and pass --model haiku, --max-budget-usd and --max-turns on every claude call.
# --dry-run prints every action, makes no model calls and writes nothing.
# Exit: 0 ok; 1 FAIL (harness, cleanup, isolation or leak); 2 refused or BLOCKED (usage, budget, missing CLI or flag).
set -euo pipefail
PROBES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PROBES
exec python3 -B - "$@" <<'PY'
from __future__ import annotations  # Python 3.8+
import argparse
import os
import signal
import sys

sys.dont_write_bytecode = True  # importing the probe modules must not leave __pycache__ in the hub
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # `run-probes.sh --dry-run ... | head` exits quietly
sys.path.insert(0, os.environ["PROBES"])
import isolation  # noqa: E402
import probelib as lib  # noqa: E402


def parse_args(argv: list) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="run-probes.sh", description="Run the daedalus capability probes.")
    ap.add_argument("--case", required=True, help="a case id (A1 ... K2) or all")
    ap.add_argument("--install", choices=("script", "plugin", "both"), default="both")
    ap.add_argument("--host", choices=lib.HOSTS, default="claude")
    ap.add_argument("--budget-usd", type=float, help="total budget for a live run (required unless --dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="print every action; no model calls, no writes")
    return ap.parse_args(argv)


def print_plan(runs: list, skipped: list, cases: list, args: argparse.Namespace, ceiling: float) -> None:
    installs = ", ".join(lib.installs_for(args.install))
    enforced = "enforced per call by --max-budget-usd" if args.host == "claude" else \
        "not enforced by the host CLI; the per-run timeout is the only cap"
    print(f"plan: {len(runs)} run(s) from {len(cases)} case(s); host {args.host}; install {installs}; "
          f"estimated ceiling ${ceiling:.2f} ({enforced})")
    for case_id, install, reason in skipped:
        print(f"skip {case_id} ({install}): {reason}")
    selected = {case["id"] for case in cases}
    for case in cases:
        for required in case.get("requires", []):
            if required not in selected:
                print(f"note: {case['id']} requires {required} confirmed in the same run; {required} isn't "
                      f"selected, so {case['id']} will be inconclusive")


def print_preflight(host: str) -> None:
    binary = lib.HOST_BINARIES[host]
    if host == "claude":
        required = ", ".join(lib.REQUIRED_FLAGS["claude"])
        optional = ", ".join(lib.OPTIONAL_FLAGS["claude"])
        print(f"preflight: would check `{binary}` on PATH (missing: BLOCKED), run `{binary} --version` and "
              f"`{binary} --help` (required: {required}; optional, with fallbacks: {optional})")
    else:
        print(f"preflight: would check `{binary}` on PATH; when it is missing every run is recorded as "
              "docs-only [D]; signed-in state and flags: verify in T0")
    user_files = ", ".join(f"~/{rel}" for rel in isolation.USER_SCOPE_FILES)
    listing = " and the output of `claude plugin list`" if host == "claude" else ""
    print(f"isolation: would snapshot the hub's git status and digests of {user_files}{listing}")


def dry_run(runs: list, args: argparse.Namespace, run_root) -> int:
    print("[dry-run] no model calls and no writes; actions in order:")
    print_preflight(args.host)
    staging = run_root / "staged"
    for run in runs:
        try:
            actions = lib.build_actions(run, "unknown", staging)
        except lib.CaseError as err:
            print(f"cannot plan {run.label}: {err}", file=sys.stderr)
            return 2
        print(f"run {run.label}")
        for number, action in enumerate(actions, 1):
            print(f"  {number:2}. {action.kind}: {action.detail}")
    version = "<version>"
    print("isolation: would compare a fresh snapshot with the first one; any difference is a FAIL")
    print(f"leak scan: would scan {staging} with redact.py before anything is published")
    print(f"publish: would copy {staging}/fixtures/{args.host}-{version}/ into scripts/probes/fixtures/ and merge "
          f"results into scripts/probes/results/{args.host}-{version}.json, replacing every earlier fixture folder "
          "and entry of each run's (case, variant, install), all or nothing")
    print("[dry-run] done: no model calls were made")
    return 0


def main(argv: list) -> int:
    args = parse_args(argv)
    try:
        cases = lib.load_cases(args.case)
    except lib.CaseError as err:
        print(f"invalid case selection or definition:\n{err}", file=sys.stderr)
        return 2
    run_root = lib.probe_root() / lib.utc_stamp()
    runs, skipped = lib.plan_runs(cases, lib.installs_for(args.install), args.host, run_root)
    ceiling = lib.estimate_ceiling(runs)
    print_plan(runs, skipped, cases, args, ceiling)
    if not runs:
        print("nothing to run for this host and install selection")
        return 0
    try:
        lib.check_budget(args.dry_run, args.budget_usd, ceiling)
    except lib.GuardError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    if args.dry_run:
        return dry_run(runs, args, run_root)
    return lib.run_live(runs, args.host, args.budget_usd, run_root)


sys.exit(main(sys.argv[1:]))
PY
