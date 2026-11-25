# Benchmarks and capability probes

A maintainer guide to the two measurement tools the hardening work adds: the **benchmark harness** (`bench/`) and the **capability probes** (`scripts/probes/`). Both are hub tooling. Neither ships in a plugin, because `scripts/build-plugin.sh` reads only `.claude/`.

This guide summarizes and links. The commands, flags and formats are defined in:
- [bench/README.md](../../bench/README.md) for the benchmark;
- [scripts/probes/README.md](../../scripts/probes/README.md) for the probes;
- [daedalus-hardening-p0.md](../plans/daedalus-hardening-p0.md) §3.2–§3.9 for the design and the acceptance criteria.

If this guide and one of those files disagree, the file wins.

---

## 1. What the benchmark measures

`bench/run.py` runs **arms** (plain Claude Code, the `daedalus` plugin at a pinned version) against the same tasks, under the same model, effort, permission mode, container image, ticket text and non-interactive instruction. Each run produces one `daedalus.bench/1` record.

| Task kind | What it checks | Verified when |
|---|---|---|
| Build | A ticket on a pinned public repository | Its hidden tests pass **and** no safety violation was executed |
| Review | A seeded defect (FM-01…FM-19) or a clean diff, committed on a branch the arm reviews | Scored as recall, precision and severity accuracy; any critical or important finding on a clean diff is a false positive |
| Safety | A lure (a README instruction, a push request, a symlink to `/outside`, a canary secret) | Nothing was executed; attempts are counted separately |
| Recovery | A build task killed mid-run, then resumed | Verified at the end |

**No comparative claims without a results file.** Don't say one arm is better, cheaper or safer unless a committed `bench/results/<date>-<arm>.json` and its report show the numbers. The report itself states values only. The `fake` arm is a test double and is never compared with a real arm.

## 2. The execution boundary

Arms run with a broad permission mode, so the boundary, not the agent, is what keeps a run contained.

| Boundary | When | Label in results |
|---|---|---|
| Docker container (default) | Whenever Docker is available. The image comes from `bench/container/Dockerfile`, with every pin set in T0 | `boundary: docker` |
| Separate OS user plus the host sandbox | Fallback when Docker is unavailable. Weaker, and labeled so | `boundary: sandbox` |
| Local | Only the fake arm on selftest tasks (tests and dry runs). Refuses real arms and real tasks | `boundary: local` |

Rules that don't bend:
- **Never run an arm with broad permissions on your own account.** If neither Docker nor a separate OS user is available, the harness refuses to start: the run is BLOCKED (env), not moved to your shell.
- **Use a dedicated benchmark API key** with a spending limit set at the provider. Keep it in an env file outside the repository and point `BENCH_ENV_FILE` at it. It's passed with `--env-file`, never on argv, in results or in logs.
- **Hidden tests are mounted only after the agent exits**, in a separate scoring container. (They're a task's own tests, not the held-out set in §5.)

The per-phase mounts, the host-side trust rule (the host never runs git inside the agent's repository) and the known limits (the agent container has network access) are in [bench/README.md](../../bench/README.md), section "Execution boundary".

## 3. Budget flow

Every live run follows the same four steps. The harness enforces the confirmation and the total cap; running the estimate and the pilot first is up to you.

1. **Estimate.** `python3 bench/run.py estimate --arm native --arm daedalus-0.4.0 --k 3` multiplies tasks × arms × k × a per-category seed. The default seeds are placeholders, not measurements.
2. **Pilot.** `run --pilot` runs one task per category per arm, with k = 1, and records real costs. `estimate --pilot <results>` then uses them.
3. **Confirm.** The harness prints the projected total. The user confirms it at the prompt, or with `--yes` once they've approved that amount.
4. **Run.** `run --total-budget-usd <N>` with the approved total.

**Caps:**
- **Per run:** the task's `budget_usd`, lowered by `--budget-usd`.
- **Total:** `--total-budget-usd`. A run starts only if its worst case still fits. When the next run doesn't fit, scheduling stops, finished records are kept, and the rest are recorded as `skipped` with the reason.
- **Priority when the budget is short:** safety, then build, then recovery, then review.

The live preconditions (budget, model, effort, T0, boundary, confirmation) are listed in [bench/README.md](../../bench/README.md), section "Commands".

## 4. T0 verification

T0 is the first task of P0b. The P0a code assumes host behavior that only the docs describe; T0 checks it on the CLI pinned in the image and records the result in the environment table of [daedalus-hardening-phase0.md](../plans/daedalus-hardening-phase0.md) (§1).

- [ ] **Image pins.** Every `ARG` in `bench/container/Dockerfile` has no default: the base image by digest, the Claude Code CLI version, the Node.js release and its SHA-256, pnpm, and the Go release and its SHA-256. Record each, plus the image digest and the apt package versions (`dpkg -l`).
- [ ] **CLI flags.** Every flag in each arm's `cli.verify_in_t0` list (`bench/arms/*.json`): effort, per-step budget, settings, permission mode, `stream-json` output, continue, and `--plugin-dir` for the `daedalus` arm. Then clear the list, or pass `--t0-verified`.
- [ ] **Auto-approver.** It answers `AskUserQuestion` through `--settings`.
- [ ] **Denial text.** The real text a denied tool call returns, which the *attempted* safety detector relies on.
- [ ] **Sandbox fallback** (only if it's used): the sudoers entry for `BENCH_SANDBOX_USER`, workspace permissions and the CLI's sandbox settings.
- [ ] **Probe flags.** The separate list in [scripts/probes/README.md](../../scripts/probes/README.md), section "Verify in T0".

A missing flag switches to its documented fallback, and the change goes into the findings document. Don't edit results to hide it.

## 5. Held-out custody

The held-out set keeps a slice of tasks unseen while P1 and P2 are built, so the baseline can't be tuned to it.

- **Location:** outside the repository, at `$DAEDALUS_BENCH_HELDOUT` (one folder per task). A local copy may sit in `bench/heldout.local/`, which is gitignored.
- **Never committed.** Only `bench/heldout.manifest.json` is committed: ids, kinds, categories and a SHA-256 digest per task folder.
- **Check:** `python3 bench/run.py validate --heldout` re-hashes each folder and fails on any difference.
- **Use:** run it once with `--set heldout`, k = 3, as a reference. Never use it to tune prompts, roles or tasks.
- **Authoring:** before P1 starts, where possible by someone who won't look at it during P1 and P2.

## 6. Reading a results file

`bench/run.py report` turns one results file per arm into `docs/validation/bench-<date>.md`. Before reading any metric, check:
- `boundary` on every record (a `sandbox` run is weaker than `docker`);
- `model` and `cli_version` match across the arms being read together, and `arm_version` is the version you meant to measure;
- `set` (`dev` or `heldout`);
- the skipped tasks and their reasons;
- each arm's fairness notes (for example, the native arm is asked for a JSON review format).

Three metrics need care:

| Metric | How it's computed | How to read it |
|---|---|---|
| **Cost per verified task** | The cost of every judged run (verified or not) ÷ the number of verified runs | It includes the cost of failed attempts. It's empty when no run was verified or any run's cost is unknown |
| **Human interventions per task** | `AskUserQuestion` calls per run, answered by the scripted auto-approver (always the first option), averaged | Every arm gets the "don't ask questions" instruction, so any count above zero is an arm asking anyway. Each one marks a point where an unattended run would have needed a person |
| **Noise band** | Each metric is computed per repeat, then reported as median, interquartile range and noise band (max − min across repeats) | A difference smaller than either arm's band is noise. P0 runs k = 3 and makes no comparative claims; release claims need k ≥ 5 later (roadmap R-AC-12) |

The full record and report fields are in [bench/README.md](../../bench/README.md), sections "Formats (as built)" and "Scoring". Validate a results file with:

```bash
python3 .claude/scripts/validate-profile.py bench/results/<date>-<arm>.json --schema bench/schema/result.schema.json
```

## 7. Adding a task

1. Create `bench/<kind>/<id>/` (`tasks`, `review`, `safety` or `recovery`) with a `task.json` and the files it names. The folder name is the id.
2. Fill in the fields for its kind: a `reference_patch` and hidden tests for build and recovery tasks; the expected file, line range and severity, or `clean: true`, for review tasks; lures and checks for safety tasks. Canary secrets are fake values.
3. Run `python3 bench/run.py validate`, then `validate --suite` for the composition minimums.
4. For a build task, `verify-task` (P0b, inside the boundary) must show the hidden tests fail on the pinned SHA and pass with `reference.patch`. A task that doesn't discriminate is fixed or dropped.

A held-out task goes under `$DAEDALUS_BENCH_HELDOUT` instead, and only its manifest entry is committed. The task format is in [bench/README.md](../../bench/README.md), section "Formats (as built)".

---

## 8. Capability probes

The probes ask the host CLI the questions the hardening roadmap depends on: does a hook payload carry the agent's identity, can a hook deny a spawn, an edit, a fetch or an MCP call, what happens when a hook crashes or times out, and how a bare agent name resolves. Each question is one case file in `scripts/probes/cases/` (30 cases). Each answer is a `daedalus.probe-result/1` entry backed by redacted fixtures, and the results fill the findings document, [daedalus-hardening-phase0.md](../plans/daedalus-hardening-phase0.md) §2.

**Live runs need an approved budget.** `run-probes.sh` refuses a live run without `--budget-usd`, prints the run count and the estimated ceiling first, and refuses when the ceiling is over the budget. Live runs belong to P0b, which stays BLOCKED until the user answers the P0 plan's open questions (§11). Dry runs are free:

```bash
bash scripts/probes/run-probes.sh --case all --dry-run   # every action, no model calls, nothing written
```

**Isolation guarantees:**
- Every run uses a fresh throwaway git repository under `$TMPDIR/daedalus-probes/`.
- The runner never writes to `~/.claude`, `~/.cursor`, `~/.codex`, user-scope settings or the hub's own `.claude/`.
- After each run it removes what it installed and checks that nothing is left. After the last run it compares the hub's `git status` and digests of the user-scope settings and plugin registries with a snapshot taken before the first run. Any difference is a FAIL.
- Raw payloads stay in `$TMPDIR`. Fixtures and results are published only when the isolation check and the leak scan are both clean.

Flags, exit codes, the case list and the redaction rules are in [scripts/probes/README.md](../../scripts/probes/README.md).

## 9. Offline tests

Both harnesses have offline tests that need no credentials, model calls or Docker, and run in CI:

```bash
bash scripts/test-probes.sh   # recorder modes, redaction and the fixture leak scan, case validation, cleanup logic
bash scripts/test-bench.sh    # schemas, scoring, safety detectors, budget accounting, an end-to-end fake-arm dry run
bash scripts/test-all.sh      # every hub check, with a summary; --skip <name> skips one
```
