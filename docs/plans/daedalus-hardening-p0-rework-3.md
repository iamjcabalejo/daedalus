# Daedalus hardening P0: rework 3

- **Type:** Rework of P0a (offline build), third round
- **Plan:** [daedalus-hardening-p0.md](daedalus-hardening-p0.md); previous rounds: [rework-1](daedalus-hardening-p0-rework-1.md), [rework-2](daedalus-hardening-p0-rework-2.md)
- **Sources:**
  - the [rework-2 re-review](../reviews/tb-claude-custom-workflow-main-ac4232f-p0a-rework2.md), with three "consider" findings;
  - the final test-runner report after rework 2, with two source notes.
- **Why now:** P0a was already production ready. The user chose to close these Suggestions before P0b, because each one affects whether a live P0b result can be trusted.

## Rework criteria

| RW | From | Required change | Where |
|---|---|---|---|
| **RW-28** | Re-review `ac4232f-15` | The identity-check exemption is keyed on the task's origin, not on a field the task declares about itself:<br>• exempt only tasks whose `repo.url` starts with `selftest:`;<br>• `check_task` rejects `set: selftest` on any other repo.<br>Test: a copy of `st-build` with `set: selftest`, a real-looking `repo.url` and `plan_slug: safety-tags` fails validation; the four real selftest tasks still pass | `bench/lib/tasks.py:106-108`, `:353-354`, `:416-420`; `bench/selftest/test_bench.py` |
| **RW-29** | Re-review `ac4232f-16` | A1 also proves attribution on the event C1 and C2 decide on: an assert that the **PostToolUse** of `echo A1` carries `agent_type` (same `value_by_install` as the PreToolUse assert). Test: A1 with an attributed PreToolUse and an unattributed PostToolUse is `contradicted`, and a C1 that would read `confirmed` is gated to `inconclusive`. README note updated | `scripts/probes/cases/A1.json:98-121`; `scripts/probes/README.md`; `scripts/test-probes.sh` |
| **RW-30** | Re-review `B:ac4232f-2` (open since review B); test-runner source note | **Sandbox runs never expose the hub or other runs to the agent user:**<br>• after the agent exits, the host copies the task's hidden tests into the run's `score/` folder, and `score_command` uses that copy, naming no path under the hub;<br>• when a run finishes (and on failure), the host-owned run folder is set to mode `0700`;<br>• the sandbox agent gets a sanitized environment: a `PATH` built from system and toolchain folders that refuses any entry inside the hub or containing `bench`, and `TMPDIR` set to a folder inside the run;<br>• `bench/README.md:85-88` is corrected.<br>Tests: the sandbox `score_command` names no hub path; a finished run folder is `0700`; the sandbox agent env has no hub path or `bench` in `PATH` or `TMPDIR` | `bench/lib/boundary.py:52`, `:105`, `:120-122`, `:169-172`; `bench/run.py:380-388`, `:432`; `bench/lib/budget.py:36` (if the worst-case charge needs the copy); `bench/README.md`; `bench/selftest/test_bench.py` |
| **RW-31** | Test-runner source note | `bench/run.py` sets `sys.dont_write_bytecode = True` before importing `bench.lib`, as `run-probes.sh` does. Test: running `run.py validate` in a scratch copy without `PYTHONDONTWRITEBYTECODE` leaves no `__pycache__` | `bench/run.py`; `bench/selftest/test_bench.py` |

## Ownership

| Round | Role | Items | Files |
|---|---|---|---|
| 1a | implementer | RW-28, RW-30, RW-31 | `bench/lib/**`, `bench/run.py`, `bench/selftest/**`, `bench/README.md` |
| 1b | implementer | RW-29 | `scripts/probes/cases/A1.json`, `scripts/probes/README.md`, `scripts/test-probes.sh` (and `scripts/probes/*.py` only if needed) |

**Then:** test-runner (including the repeated flake runs) → focused Argus re-review of RW-28–RW-31 → final P0a status.

## Outcome

- **RW-28–RW-31:** met. The [rework-3 re-review](../reviews/tb-claude-custom-workflow-main-ac4232f-p0a-rework3.md) verified all 3 earlier findings fixed. The test-runner passed 13 of 13 flake runs (`test-bench.sh` 120 tests, `test-probes.sh` 95).
- **Deferred, conditional on plan §11 Q3 (is Docker available?):**

  | Item | Why deferred | Must be done |
  |---|---|---|
  | `ac4232f-17`: processes a sandbox agent leaves running outlive the run | Affects only the sandbox fallback; Docker, the default boundary, kills its containers | **Before P0b**, if the sandbox becomes the boundary |
  | Per-folder access for the sandbox user (the sandbox user writes `work/` but not the run folder), and dropping macOS ACLs in `seal` | No static mode or inherited ACL can produce that layout; it needs harness code | **Before P0b**, if the sandbox becomes the boundary |
  | The sandbox `PATH` keeps entries under the operator's home, which shows the username | Names neither the task nor the benchmark | T0 checklist |
