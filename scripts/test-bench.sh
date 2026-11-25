#!/usr/bin/env bash
# Offline tests for the benchmark harness bench/run.py (P0: AC-8, AC-10, AC-11 report, AC-12).
#
#   scripts/test-bench.sh                 run every test; exit 1 on any failure
#   scripts/test-bench.sh -k Review       pass unittest options through (here: only matching tests)
#
# No credentials, no docker, no model and no network: the synthetic repos under bench/selftest/repos/ are
# committed into temporary git repos at test time, runs use the fake arm (bench/arms/fake.json) through the local
# boundary, and everything is written under a temporary folder. Covers schema validation, `validate` on the
# selftest tasks, every scoring rule (the ±3-line boundary, severity, precision, clean-diff false positives),
# the safety detectors on synthetic workspaces, stream-json usage parsing with missing fields, budget accounting
# and the cap stop, the report statistics, the docker argv, verify-task, recovery kill/resume, and an end-to-end
# `run --dry-run --arm fake`. Tests live in bench/selftest/test_bench.py.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HUB"
export PYTHONDONTWRITEBYTECODE=1
exec python3 -m unittest "$@" bench.selftest.test_bench
