## Argus review

Rework 1 closes 17 of the 18 earlier findings and adds tests for them. Probe results now need both a host run and evidence that the call was attempted. One new problem breaks AC-10 parity: the Daedalus arm's prompts still carry the task id (`feature-plan safety-s07-reset-hard`), so only that arm is told which lure it faces. Not reviewed in full: test_bench.py, recorder/redact, templates. Not covered by a stack pack: shell, JSON, .patch.

**Done well:** `StatusGuardTests` in `scripts/test-probes.sh:847-926`. `test_host_not_run_or_timed_out_overrides_passing_checks` first shows that E1's capture alone would read `confirmed`. It then proves that `host_gap` turns the run `inconclusive` and still keeps the marker fact.

**Since the last revision:** 17 earlier findings verified fixed, 1 still open (partly fixed).

**1. [important · correctness] Daedalus's prompt carries the task id (`feature-plan safety-s07-reset-hard`): only that arm is told the lure**
`prompt_values` sets `{slug}` to the task id, and Daedalus's build, safety and recovery steps run `/daedalus:feature-plan {slug}`. On S7, only that arm reads "safety-s07-reset-hard" next to the ticket's `git reset --hard` (S8 shows "env-secret", S9 "disable-hooks"). Its safety score therefore partly measures the hint. In sandbox runs, `{ticket_path}` also names the task to both arms.
- Fix:
  - Give each task a neutral plan slug: an optional `plan_slug` in task.json, defaulting to the ticket heading, and use it for `{slug}`.
  - Have `validate` reject a slug that contains the task id, kind or category.
  - For sandbox runs, name run folders by `run_name(run_id)`.
  - Set origin's URL before `git fetch origin`, so `.git/FETCH_HEAD` doesn't keep the host run path.
  - Test: render every arm prompt for every dev task and assert that no task id appears.
- Where: `bench/run.py:213`; `bench/lib/tasks.py:73-74`; `bench/arms/daedalus-0.4.0.json:11-12`; `bench/run.py:645`; `bench/lib/boundary.py:91-93`; `bench/lib/workspace.py:319-322`
- Cost: Daedalus plan paths change, which is harmless because `exclude_from_scoring` already covers `docs/plans/**`. Sandbox run folders lose their readable names.
<!-- argus-finding:ac4232f-12 -->

**2. [consider · correctness] Sandbox runs put the workspace inside the hub: both arms load its CLAUDE.md and can read hidden tests**
The workspace part is fixed: the raw root now defaults outside the hub, and `sandbox_root_problem` refuses a root inside it or below a CLAUDE.md. The tools part is still open: `inner("tools")` is still `<hub>/bench/lib`, and both arms' `bench-settings.json` run `approver.py` from there. So the sandbox user must be able to read under `bench/`, while the README's T0 check requires that read to fail. One of the two breaks.
- Fix: for sandbox runs, copy `bench/lib/approver.py` into `<raw_root>/tools` and return that path from `SandboxBoundary.inner("tools")`. Extend `test_sandbox_raw_root_stays_outside_the_hub` to assert that the written settings name no path under the hub.
- Where: `bench/lib/boundary.py:86-89`, `:34`; `bench/run.py:436`; `bench/lib/arms.py:217-222`; `bench/README.md:79` (still open from an earlier revision)
- Cost: one small copy per sandbox run.
<!-- argus-finding:B:ac4232f-2 -->

**3. [consider · correctness] rv-fm18 seeds two independently fixable defects as one expected item, so naming both costs a false positive**
The re-seed plants two defects, each with its own fix: a wrong check (`/^\s$/`, article.service.ts:474-477) and a test that passes on the 404 (test file lines 26-39). Both sit in one expected item through `also`. `score_review` counts a finding on the second location as a false positive, so a reviewer who reports both real defects gets precision 0.5 on this task.
- Fix: in `score_review`, treat a serious finding that lands on an already-matched item's locations as neutral (neither TP nor FP). Test: rv-fm18 findings at `article.service.ts:474` and `article.service.test.ts:26` score `tp 1, fp 0`.
- Where: `bench/review/rv-fm18-f-comment-404-test/task.json:23-38`; `bench/lib/score.py:120-133`
- Cost: rv-fm10 and rv-fm15 also stop counting a split finding as a false positive; update their notes.
<!-- argus-finding:ac4232f-13 -->

**4. [consider · correctness] C1–C3 credit main-thread calls to the probe agent, so a helpful main thread can decide them**
`subagent-started`, `step-read`, `bash-not-run` and `fewer-than-five` match any SubagentStart or call, no matter who made it:
- In C3, a subagent that read nothing plus one main-thread step read confirms `maxTurns`.
- In C3, a main thread that finishes steps 3–5 after the agent stops reaches 5 reads and contradicts it.
- C1 and C2 read `contradicted` if the main thread runs `echo C1` itself.
- Fix: add `{"field": "agent_type", "op": "endswith", "value": "probe-<agent>"}` to those `where` lists. A1 checks that subagent payloads carry `agent_type`; a run without it stays inconclusive. Tests: in C3, a main-thread step read with SubagentStart recorded is `inconclusive`; in C1, a main-thread `echo C1` leaves the run `confirmed`.
- Where: `scripts/probes/cases/C3.json:75-113`; `scripts/probes/cases/C1.json:75-102`; `scripts/probes/cases/C2.json:75-102`
- Cost: C1–C3 now depend on A1. If T0 shows `agent_type` is missing, they stay inconclusive until the cases are revised.
<!-- argus-finding:ac4232f-14 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@main:ac4232f1dd1ea87a47b85791bd0c25b097841fce+wt-rework1 -->

<details><summary>Prior findings (18)</summary>

| Id | Status | Evidence |
|---|---|---|
| A:ac4232f-1 | fixed | `probelib.py:521-542` (`host_gap`); `hook-ran` is a precondition in E1–E3 and E5; E4 `bash-issued`; C1–C3 `subagent-started`; tests at `test-probes.sh:850-975`. The attribution gap that remains is finding 4 |
| A:ac4232f-2 | fixed | `isolation.py:99-100`; `probelib.py:80`, `:214-215` |
| B:ac4232f-1 | fixed | `metrics.py:206-230`, `:279-281`; `run.py:457-459` |
| B:ac4232f-2 | **partly fixed** | Raw root fixed (`run.py:573-583`; `boundary.py:267-284`); tools dir still in the hub (finding 2) |
| B:ac4232f-3 | fixed | `arms.py:241-269` |
| B:ac4232f-4 | fixed | `native.json:17`, `:20`, `:24`; `arms.py:25`, `:36`, `:138-146` |
| B:ac4232f-5 | fixed | `run.py:55`, `:443-450`; `workspace.py:380-403`, `:446-462` |
| C:ac4232f-1 | fixed | Ticket delivered as data in every arm; notes for S1, S2 and S7 |
| C:ac4232f-2 | fixed | `forbidden_path` on the receipt paths in S1, S4, S4b, S5 and S5b |
| C:ac4232f-3 | fixed | rv-fm01's patch no longer touches `profiles/views.py` |
| C:ac4232f-4 | fixed | Neutral lure commits; realistic S8 key, planted only in the uncommitted `.env` |
| C:ac4232f-5 | fixed | `g-email-case/ticket.md:10` |
| C:ac4232f-6 | fixed | rv-fm06 and rv-fm08 ranges; rv-fm10 `also` |
| C:ac4232f-7 | fixed | rv-fm18 re-seeded as a real important defect; rv-fm07 note. The scoring problem that remains is finding 3 |
| C:ac4232f-8 | fixed | rv-fm15 patch and README row |
| C:ac4232f-9 | fixed | Rubric carve-out in the threat model and plan §3.7 |
| C:ac4232f-10 | fixed | References checked against the current `ARCHITECTURE.md` |
| C:ac4232f-11 | fixed | S8 notes; `task.schema.json:37` |

</details>

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override; the hub is not a product repo). Packs: `python` and `ci-cd` from the profile; `go` and `node-js` from the diff.
- **Ids:** earlier ids repeat across parts A–C, so carried-over findings use the part prefix. New findings are numbered from 12.
- **AC:** RW-8 not met (finding 2); AC-10 not met (finding 1); every other RW item met.
- **Minor, not raised:**
  - Phase-0 C-5 still mentions a `bench-review` branch.
  - `task.schema.json:38` says `review.commit_message` must not "name the benchmark", but validation checks only that it isn't blank.
  - The Docker HOME is `/home/bench`.

</details>

```json
{"stacks": ["python", "ci-cd", "go", "node-js"],
 "domain": "none",
 "ac": {"met": 21, "not_met": 2, "not_visible": 0},
 "findings": [
  {"id": "ac4232f-12", "severity": "important", "category": "correctness", "family": "FM-18", "title": "Daedalus's prompt carries the task id (`feature-plan safety-s07-reset-hard`): only that arm is told the lure", "path": "bench/run.py", "line": 213, "new": true},
  {"id": "B:ac4232f-2", "severity": "consider", "category": "correctness", "family": "FM-13", "title": "Sandbox runs put the workspace inside the hub: both arms load its CLAUDE.md and can read hidden tests", "path": "bench/lib/boundary.py", "line": 86, "new": false},
  {"id": "ac4232f-13", "severity": "consider", "category": "correctness", "family": "FM-18", "title": "rv-fm18 seeds two independently fixable defects as one expected item, so naming both costs a false positive", "path": "bench/review/rv-fm18-f-comment-404-test/task.json", "line": 23, "new": true},
  {"id": "ac4232f-14", "severity": "consider", "category": "correctness", "family": "FM-18", "title": "C1–C3 credit main-thread calls to the probe agent, so a helpful main thread can decide them", "path": "scripts/probes/cases/C3.json", "line": 75, "new": true}
 ]}
```
