#!/usr/bin/env bash
# Run every hub test (P0 AC-12; roadmap R-AC-42 pulled forward). Continues past failures, prints a summary,
# and exits 1 if any check failed or is missing.
#
#   scripts/test-all.sh                     run every check
#   scripts/test-all.sh --skip detector     skip a check by name (repeatable); shown as SKIP, never a failure
#
# Checks, in order: detector (test-detector.sh: fetches public matrix repos into $WORKFLOW_MATRIX_CACHE when they
# aren't cached), probes (test-probes.sh), bench (test-bench.sh), lint-packs, check-generic, build-plugin
# (build-plugin.sh --check).
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HUB"

skip=" "
while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip) [ "$#" -ge 2 ] || { echo "--skip needs a check name" >&2; exit 2; }; skip="$skip$2 "; shift 2 ;;
    -h|--help) sed -n '2,11p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

summary=()
failed=0

run_check() { # run_check <name> <script> [args...]
  local name="$1" script="$2" start status
  shift 2
  if [[ "$skip" == *" $name "* ]]; then
    summary+=("SKIP     $name")
    return 0
  fi
  if [ ! -f "$script" ]; then
    summary+=("MISSING  $name ($script not found)")
    failed=$((failed + 1))
    return 0
  fi
  echo "==> $name: bash $script $*"
  start=$SECONDS
  if bash "$script" "$@"; then
    summary+=("PASS     $name ($((SECONDS - start))s)")
  else
    status=$?
    summary+=("FAIL     $name (exit $status, $((SECONDS - start))s)")
    failed=$((failed + 1))
  fi
  echo
}

run_check detector scripts/test-detector.sh
run_check probes scripts/test-probes.sh
run_check bench scripts/test-bench.sh
run_check lint-packs scripts/lint-packs.sh
run_check check-generic scripts/check-generic.sh
run_check build-plugin scripts/build-plugin.sh --check

echo "Summary:"
printf '  %s\n' "${summary[@]}"
if [ "$failed" -gt 0 ]; then
  echo "$failed check(s) failed"
  exit 1
fi
echo "all checks passed (skipped ones listed above)"
