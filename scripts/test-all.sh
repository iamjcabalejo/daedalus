#!/usr/bin/env bash
# Run every hub test (P0 AC-12; roadmap R-AC-42). Continues past failures, prints a summary, and exits 1 if any
# check failed or is missing. CI (.github/workflows/check.yml) runs this script as its one test step.
#
#   scripts/test-all.sh                     run every check
#   scripts/test-all.sh --skip detector     skip a check by name (repeatable); shown as SKIP, never a failure
#
# Checks, in order: detector (test-detector.sh: fetches public matrix repos into $WORKFLOW_MATRIX_CACHE when they
# aren't cached), probes (test-probes.sh), bench (test-bench.sh), config (test-config.sh), trust (test-trust.sh),
# shell-syntax (bash -n on every hub shell script), py38-syntax (every .claude/scripts/**/*.py parses as
# Python 3.8), lint-packs, check-generic, build-plugin (build-plugin.sh --check).
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

run_step() { # run_step <name> <command...>: run one check, time it and record the result
  local name="$1" start status
  shift
  echo "==> $name: $*"
  start=$SECONDS
  if "$@"; then
    summary+=("PASS     $name ($((SECONDS - start))s)")
  else
    status=$?
    summary+=("FAIL     $name (exit $status, $((SECONDS - start))s)")
    failed=$((failed + 1))
  fi
  echo
}

skipped() { # skipped <name>: true (and recorded) when --skip named this check
  if [[ "$skip" == *" $1 "* ]]; then
    summary+=("SKIP     $1")
    return 0
  fi
  return 1
}

run_check() { # run_check <name> <script> [args...]
  local name="$1" script="$2"
  shift 2
  skipped "$name" && return 0
  if [ ! -f "$script" ]; then
    summary+=("MISSING  $name ($script not found)")
    failed=$((failed + 1))
    return 0
  fi
  run_step "$name" bash "$script" "$@"
}

run_inline() { # run_inline <name> <function>: a check defined in this file
  skipped "$1" && return 0
  run_step "$1" "$2"
}

hub_files() { # hub_files <pathspec...>: tracked or new, unignored files, NUL-separated
  # (no `:!` exclude pathspec here: combined with --others, git drops matching tracked files)
  git ls-files -z --cached --others --exclude-standard -- "$@"
}

shell_syntax() { # bash -n on every hub shell script (parses only; never runs one)
  local file count=0 bad=0
  while IFS= read -r -d '' file; do
    case "$file" in plugins/*) continue ;; esac  # generated copies; build-plugin --check keeps them identical
    [ -f "$file" ] || continue
    count=$((count + 1))
    if ! bash -n "$file"; then
      echo "syntax error: $file"
      bad=$((bad + 1))
    fi
  done < <(hub_files '*.sh')
  echo "$count shell scripts, $bad with syntax errors"
  [ "$bad" -eq 0 ] && [ "$count" -gt 0 ]
}

py38_syntax() { # every .claude/scripts/**/*.py parses with Python 3.8's grammar (the hub's minimum, stdlib only)
  hub_files '.claude/scripts/*.py' | python3 -I -c '
import ast, sys
paths = [p for p in sys.stdin.read().split("\0") if p]
bad = 0
for path in paths:
    try:
        with open(path, encoding="utf-8") as handle:
            ast.parse(handle.read(), filename=path, feature_version=(3, 8))
    except SyntaxError as err:
        bad += 1
        print(f"not Python 3.8: {path}:{err.lineno}: {err.msg}")
print(f"{len(paths)} Python files, {bad} outside Python 3.8 syntax")
sys.exit(1 if bad or not paths else 0)
'
}

run_check detector scripts/test-detector.sh
run_check probes scripts/test-probes.sh
run_check bench scripts/test-bench.sh
run_check config scripts/test-config.sh
run_check trust scripts/test-trust.sh
run_inline shell-syntax shell_syntax
run_inline py38-syntax py38_syntax
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
