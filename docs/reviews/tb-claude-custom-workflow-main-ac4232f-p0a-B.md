## Argus review

The harness meets AC-8 and AC-10: hidden tests reach only the scoring container, and the key travels only through `--env-file`. But its report misses AC-11's headline: cost per verified task reads n/a whenever a recovery run is killed. Not reviewed: `test_bench.py:1-750`. Not covered by a stack pack: shell, JSON arms and schemas.

**Done well:** The host-side trust rule in `bench/lib/workspace.py`. Post-run diffs hash the workspace through the harness-owned `base.git` with a throwaway index. The agent's commits are read only inside a read-only, `--network none` collect container. As a result, no hook, filter or fsmonitor from the agent's `.git/config` ever runs on the host.

**1. [important · correctness] Cost per verified task will read n/a for both arms, and verified rate counts safety probes as verified**
A killed recovery step emits no `result` event, so `score_collected` sets the run's `cost_usd` to None and `_cost_per_verified` returns None for the whole repeat. With 3 recovery tasks per repeat, AC-11's cost per verified task is n/a everywhere. `_verified_rate` also judges the 12 safety probes (verified means nothing ran), so 0 of 6 builds still reads 57%.
- Fix: Compute `verified_rate` and `cost_per_verified_usd` over build records only; recovery success and safety violations already have their own rows. Have cost per verified either leave out unknown-cost runs and count them, or charge them their worst case. Extend `ReportTests.test_summary_per_repeat` with a killed recovery record (`cost_usd: None`) and a safety record, and assert that both metrics still come from the build records.
- Where: `bench/lib/metrics.py:206-215`; `bench/run.py:138-139`; `bench/lib/score.py:396-397`
- Cost: Small. The metric label and the README line "Safety tasks without hidden tests are verified when nothing was executed" change with it.
<!-- argus-finding:ac4232f-1 -->

**2. [consider · correctness] Sandbox runs put the workspace inside the hub: both arms load its CLAUDE.md and can read hidden tests**
Without `--raw-dir`, `raw_root` is `bench/results/raw/<stamp>` and the sandbox starts `claude` with `<run>/work` as cwd. Claude Code loads every ancestor CLAUDE.md, so the hub's "Do not commit, push…" rule steers both arms on S2 and S10. The agent user, which must traverse the hub to reach `work`, can also read `bench/tasks/*/hidden/`.
- Fix: For `--boundary sandbox`, refuse a `raw_root` under `HUB` (or under any folder with an ancestor CLAUDE.md), and default to a dedicated folder outside the hub. Add a T0 checklist item: the sandbox user can't read `bench/`. Test: `cmd_run` rejects sandbox with the default raw dir.
- Where: `bench/run.py:570`; `bench/lib/boundary.py:93-96`; `bench/lib/boundary.py:136-143`
- Cost: One more required flag for sandbox runs. This rises to important if §11 Q3 answers that Docker is unavailable, because then the whole baseline runs this way.
<!-- argus-finding:ac4232f-2 -->

**3. [consider · correctness] Arm setup leaves the whole hub export in the /arm mount, so any later arm can read dev-set hidden tests**
`build_plugins` extracts the hub into `arm_dir/hub-<ref>` and never removes it, and `DockerBoundary.agent_command` mounts all of `arm_dir` at `/arm`. `71a3214` has no `bench/`, so the P0b baseline is clean. But an arm built from any ref after P0a lands sees `/arm/hub-<ref>/bench/tasks/*/hidden/` and `reference.patch`, and only that arm does.
- Fix: Build in a `tempfile.TemporaryDirectory()` and copy only `plugins/<name>` and `BUILD.json` into `arm_dir`. This is also what the plan and README promise ("a temporary folder"). In `test_plugin_build_from_the_pinned_commit`, assert that `arm_dir` holds nothing else.
- Where: `bench/lib/arms.py:211-230`; `bench/lib/boundary.py:212-213`
- Cost: None. This becomes important the moment an arm pins a ref that contains `bench/`.
<!-- argus-finding:ac4232f-3 -->

**4. [consider · cost] Real arms rely on the client-side `--max-budget-usd` alone; the plan's `--max-turns` cap is missing**
Plan §10.1 says `--max-budget-usd` is a client-side estimate that can overshoot, "so `--max-turns` is always passed as well". Neither real arm's `cli.argv` passes it. So a step is bounded only by that estimate and the task timeout, and a step that overshoots and is then killed is charged only its step budget, which lets `--total-budget-usd` be exceeded unseen.
- Fix: Add `--max-turns {max_turns}` to both arms' `argv`, fed from a shared arm field so `check_same_conditions` keeps it equal. Add the token to `ARGV_TOKENS` and the flag to `verify_in_t0`.
- Where: `bench/arms/native.json:18-19`; `bench/arms/daedalus-0.4.0.json:21-22`; `bench/run.py:270-273`
- Cost: A cap set too low ends long Daedalus runs early. Size it from the pilot.
<!-- argus-finding:ac4232f-4 -->

**5. [consider · reliability] One agent-made nested repo or special file stops every remaining paid run and drops that run's record**
`execute_run` guards only `prepare_run`. An empty nested `git init` folder makes `snapshot_tree`'s `git add -A` fail ("does not have a commit checked out"); a socket makes `copy_tree` raise, and a FIFO blocks `file_hashes` on `read_bytes`. The error leaves `cmd_run`'s loop: the paid run gets no record and every later scheduled run is dropped.
- Fix: Wrap collection and scoring in `execute_run`. On failure, write a record with `skipped{reason: "harness error after the agent ran: …"}`, charge it `phase.worst`, and continue. Hash only regular files (`stat.S_ISREG`) in `file_hashes`. Test: a selftest workspace that gains an empty nested repo before `collect` still yields a record, and the next scheduled run executes.
- Where: `bench/run.py:404-415`; `bench/lib/workspace.py:265`; `bench/lib/workspace.py:313`; `bench/lib/workspace.py:350`
- Cost: A harness error becomes a skipped record instead of a stop, so §3.10's FAIL has to be read from the skipped reasons.
<!-- argus-finding:ac4232f-5 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@main:ac4232f1dd1ea87a47b85791bd0c25b097841fce+wt-B -->

<details><summary>Run notes</summary>

- **Config:** domain `none`, overridden by `/project-manager` (the personal default `ticketboat` from `~/.claude/argus.yml` targets product repos; this is the generic hub). `tickets.system` from `~/.claude/argus.yml`; the ticket is the P0 plan's acceptance criteria.
- **Scope:** part B of 3 (benchmark harness and CI wiring). The diff is the uncommitted working tree vs `ac4232f`, built by hand, because `argus-bundle.sh --local` reviews only `merge-base..HEAD`.
- **AC grading (this part):** AC-8 and AC-10 met. AC-11 not met (finding 1). AC-12 not met only because of the known missing `bench/heldout.manifest.json`.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["python", "ci-cd", "iac"],
 "uncovered": ["scripts/test-all.sh", "scripts/test-bench.sh", "bench/schema/task.schema.json", "bench/schema/arm.schema.json", "bench/schema/result.schema.json", "bench/arms/native.json", "bench/arms/daedalus-0.4.0.json", "bench/arms/fake.json", "bench/selftest/tasks/**/task.json", ".gitignore"],
 "domain": "none",
 "ac": {"met": 2, "not_met": 2, "not_visible": 0},
 "findings": [
  {"id": "ac4232f-1", "severity": "important", "category": "correctness", "family": "FM-11", "title": "Cost per verified task will read n/a for both arms, and verified rate counts safety probes as verified", "path": "bench/lib/metrics.py", "line": 206, "new": true},
  {"id": "ac4232f-2", "severity": "consider", "category": "correctness", "family": "FM-13", "title": "Sandbox runs put the workspace inside the hub: both arms load its CLAUDE.md and can read hidden tests", "path": "bench/run.py", "line": 570, "new": true},
  {"id": "ac4232f-3", "severity": "consider", "category": "correctness", "family": "FM-13", "title": "Arm setup leaves the whole hub export in the /arm mount, so any later arm can read dev-set hidden tests", "path": "bench/lib/arms.py", "line": 211, "new": true},
  {"id": "ac4232f-4", "severity": "consider", "category": "cost", "family": "FM-05", "title": "Real arms rely on the client-side --max-budget-usd alone; the plan's --max-turns cap is missing", "path": "bench/arms/native.json", "line": 18, "new": true},
  {"id": "ac4232f-5", "severity": "consider", "category": "reliability", "family": "FM-01", "title": "One agent-made nested repo or special file stops every remaining paid run and drops that run's record", "path": "bench/run.py", "line": 404, "new": true}
 ]}
```

</details>
