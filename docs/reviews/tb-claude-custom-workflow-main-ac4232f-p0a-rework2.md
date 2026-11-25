## Argus review

Rework 2 does what RW-23 to RW-27 ask: no prompt, argv, mount or `.git` file names the task to either arm. Two risks remain. Sandbox scoring still needs the agent's OS user to read the hub's hidden tests. A1 doesn't prove the PostToolUse attribution that C1 and C2 decide on. Not reviewed in full: metrics.py, budget.py, run-probes.sh. Not covered by a stack pack: JSON, shell, Markdown.

**Done well:** `test_every_dev_prompt_argv_and_path_is_neutral` (`bench/selftest/test_bench.py:475-518`). For every dev task it renders each real arm's step, resume and review prompts and argv, through both the docker and sandbox boundaries. It allows only the identity words the arm's own template already holds. So a review prompt that says "review" passes, but a slug or branch that names the task fails.

**Since the last revision:** 3 earlier findings verified fixed, 1 still open (partly fixed).

**1. [consider · correctness] A task that declares `"set": "selftest"` skips the identity check wherever it lives**
`_identity_errors` returns early when `task.set` is `selftest`, and the task sets that field itself. A held-out task copied from `st-safety` keeps `"set": "selftest"`. `validate --heldout` and `run --set heldout` then never check its slug, lure commit or resume text, and a slug that names the lure reaches only the Daedalus arm.
- Fix:
  - Exempt only tasks on a `selftest:` seed repo (`task.repo_url.startswith("selftest:")`), which no real task can use.
  - Have `check_task` reject `set: selftest` on any other repo.
  - Test: a copy of `st-build` with `set: selftest`, a real-looking `repo.url` and `plan_slug: safety-tags` fails validation.
- Where: `bench/lib/tasks.py:353-354`; `bench/lib/tasks.py:106-108`; `bench/lib/tasks.py:416-420`
- Cost: none for the fixtures, since all four selftest tasks already use `selftest:calc`.
<!-- argus-finding:ac4232f-15 -->

**2. [consider · correctness] Sandbox runs put the workspace inside the hub: both arms load its CLAUDE.md and can read hidden tests**
The tools part is fixed. Scoring isn't: sandbox `score_command` runs `cp -R <hub>/bench/…/hidden/. .` as `BENCH_SANDBOX_USER`, which is the agent's own user. So the README's T0 check (that user can't read `bench/`) and scoring can't both pass. All runs also share one raw root that this user can read, so the second arm on a task can open the first arm's `work/`, `streams/` and `score/`.
- Fix:
  - In sandbox runs, have the host copy `task.dir/<hidden.path>` into the run's `score/` folder after the agent exits, and pass that copy to `score_command`.
  - After each run, `chmod 0700` the host-owned run folder so later agents can't enter it.
  - Correct `bench/README.md:85` ("needs no access to the hub at all").
  - Test: a sandbox `score_command` names no path under the hub, and a finished run folder's mode is 0700.
- Where: `bench/lib/boundary.py:120-122`, `:169-172`; `bench/run.py:380-388`, `:432`; `bench/lib/budget.py:36`; `bench/README.md:85-88` (still open from an earlier revision)
- Cost: one copy of the hidden folder per sandbox run.
<!-- argus-finding:B:ac4232f-2 -->

**3. [consider · correctness] A1 proves `agent_type` only on PreToolUse, so C1 and C2 can still confirm a Bash block when Bash ran**
C1 and C2 decide on `bash-not-run`: no PostToolUse for `echo C1` whose `agent_type` ends in the agent's name. A1, their gate, asserts `agent_type` only on a PreToolUse. Take a host that leaves `agent_type` off PostToolUse, or fires no PostToolUse inside subagents. A1 is confirmed, the agent's Bash runs, the absence holds trivially, and C1 reads `confirmed`.
- Fix:
  - Add an A1 assert on the PostToolUse of `echo A1` (`field: agent_type`, `expect: equals`, `value_by_install` as in `agent-type`), so the gate also proves what C1 and C2 filter on.
  - Test: a C1 run where A1's PreToolUse is attributed and the agent's `echo C1` PostToolUse isn't must not end `confirmed` after gating.
- Where: `scripts/probes/cases/A1.json:98-121`; `scripts/probes/cases/C1.json:93-115`; `scripts/probes/cases/C2.json:93-115`; `scripts/probes/README.md:102`
- Cost: on such a host A1 turns `contradicted`, which holds all seven dependents inconclusive, not only C1 and C2.
<!-- argus-finding:ac4232f-16 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@main:ac4232f1dd1ea87a47b85791bd0c25b097841fce+wt-rework2 -->

<details><summary>Prior findings (4)</summary>

| Id | Status | Evidence |
|---|---|---|
| ac4232f-12 | fixed | `{slug}` is `task.plan_slug` (`run.py:217-223`; `tasks.py:135-141`); validation `tasks.py:338-361`; neutral run folders and containers (`run.py:197-200`, `:432`); `track_origin` removes FETCH_HEAD (`workspace.py:287-299`); tests `test_bench.py:475-518`, `:520-543`, `:587-612` |
| B:ac4232f-2 | **partly fixed** | Tools fixed (`arms.py:319-326`; `boundary.py:39-40`, `:95-97`, `:228-231`); still open through sandbox scoring and the shared raw root (finding 2) |
| ac4232f-13 | fixed | `score.py:116-142`; `metrics.py:242-244`; tests `test_bench.py:649-677` |
| ac4232f-14 | fixed | `agent_type` filters on C1–C4, F3, F4 and I1; A1 gate `probelib.py:666-712`; tests `test-probes.sh:951-1160`. The proof gap that remains is finding 3 |

</details>

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override). Packs: `python` and `ci-cd` from the profile, plus `iac` from the diff (Dockerfile).
- **AC:** RW-23 to RW-27 all met.
- **Implementer-named items, judged not material:**
  - `DAEDALUS_NONINTERACTIVE=1` is visible to both arms and names neither the task nor the benchmark.
  - The unsalted `run_name` can't be inverted without the task-id list.
  - `/arm` holds only the plugin under test.
- **Bundle:** built by hand from the working tree, because `argus-bundle.sh --local` reviews only `merge-base..HEAD` (findings document, correction C-5).

</details>

```json
{"stacks": ["python", "ci-cd", "iac"],
 "domain": "none",
 "ac": {"met": 5, "not_met": 0, "not_visible": 0},
 "findings": [
  {"id": "ac4232f-15", "severity": "consider", "category": "correctness", "family": "FM-13", "title": "A task that declares `\"set\": \"selftest\"` skips the identity check wherever it lives", "path": "bench/lib/tasks.py", "line": 353, "new": true},
  {"id": "B:ac4232f-2", "severity": "consider", "category": "correctness", "family": "FM-13", "title": "Sandbox runs put the workspace inside the hub: both arms load its CLAUDE.md and can read hidden tests", "path": "bench/lib/boundary.py", "line": 120, "new": false},
  {"id": "ac4232f-16", "severity": "consider", "category": "correctness", "family": "FM-18", "title": "A1 proves `agent_type` only on PreToolUse, so C1 and C2 can still confirm a Bash block when Bash ran", "path": "scripts/probes/cases/A1.json", "line": 98, "new": true}
 ]}
```
