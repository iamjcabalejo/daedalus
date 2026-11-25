# Daedalus hardening P0: rework 2

- **Type:** Rework of P0a (offline build), second round
- **Plan:** [daedalus-hardening-p0.md](daedalus-hardening-p0.md); previous round: [rework-1](daedalus-hardening-p0-rework-1.md) (17 of 18 findings fixed)
- **Sources:**
  - the re-review [p0a-rework1](../reviews/tb-claude-custom-workflow-main-ac4232f-p0a-rework1.md);
  - the test-runner report after rework 1, which raised two benchmark-realism issues that the re-review confirmed.
  - Severity mapping: important → **Critical**; consider → **Suggestion**. Suggestions are included because they affect measurement validity (AC-9, AC-10).

## Rework criteria

| RW | From | Severity | Required change | Where |
|---|---|---|---|---|
| **RW-23** | Re-review 12; test-runner note 1 | **Critical** | **No task identity in anything an agent sees.**<br>• Each task gets a neutral plan slug: optional `plan_slug` in `task.json`, defaulting to a slug of the ticket's first heading, and used for `{slug}`.<br>• `validate` rejects a slug, review branch or lure text containing the task id, its kind (`safety`, `recovery`, `review`, `build`), its category (`S7`, `FM-07`, …) or `bench`.<br>• Sandbox run folders get a neutral `run_name(run_id)`.<br>• origin's URL is set before `git fetch origin`, so `.git/FETCH_HEAD` doesn't keep a host run path.<br>• Test: render every arm's prompts for every dev task and assert none carries the task id, kind or category | `bench/run.py:213`, `:645`; `bench/lib/tasks.py:73-74`; `bench/lib/boundary.py:91-93`; `bench/lib/workspace.py:319-322`; `bench/schema/task.schema.json` |
| RW-24 | Re-review B:2 (open); test-runner note 2 | Suggestion | **Agents see only the approver, under neutral names.**<br>• Docker mounts and sandbox copies only `approver.py`, into a neutral per-run tools folder; never `bench/lib`, so `score.py`, `budget.py` and `fake_agent.py` stay hidden.<br>• Neutral HOME (for example `/home/dev`), settings file name and container names.<br>• Test: agent mounts, env, settings and paths contain no `bench` and no hub path | `bench/lib/boundary.py:34`, `:86-89`; `bench/lib/arms.py:217-222`; `bench/run.py:436`; `bench/README.md` |
| RW-25 | Re-review 13 | Suggestion | `score_review`: a serious finding that lands on a location of an expected item that is already matched is neutral (neither TP nor FP). Test: rv-fm18 findings at both locations score `tp 1, fp 0`. Update the rv-fm10, rv-fm15 and rv-fm18 notes | `bench/lib/score.py:120-133`; `bench/review/rv-fm{10,15,18}-*/task.json` (notes only) |
| RW-26 | Re-review 14 | Suggestion | C1–C3: the `subagent-started`, `step-read`, `bash-not-run` and `fewer-than-five` observations require `agent_type` ending in the probe agent's name. Tests: a main-thread call can't decide C1–C3 | `scripts/probes/cases/C{1,2,3}.json`; `scripts/test-probes.sh` |
| RW-27 | Re-review minors | Suggestion | `validate` enforces what the schema text says about `review.commit_message` (no benchmark naming, through the RW-23 check). Phase-0 C-5 says `feature/<name>` instead of `bench-review` (done by the project-manager) | `bench/lib/tasks.py`; `docs/plans/daedalus-hardening-phase0.md` |

## Ownership

| Round | Role | Items | Files |
|---|---|---|---|
| 1a | implementer | RW-23, RW-24, RW-25, RW-27 (validation) | `bench/lib/**`, `bench/run.py`, `bench/schema/**`, `bench/arms/**`, `bench/selftest/**`, `bench/README.md`, notes in `bench/review/rv-fm{10,15,18}-*/task.json`, and `plan_slug` in any task `task.json` whose default slug would fail the RW-23 check |
| 1b | implementer | RW-26 | `scripts/probes/cases/C{1,2,3}.json`, `scripts/test-probes.sh`, `scripts/probes/README.md` |

**Then:** test-runner → Argus re-review of these items → production-ready check for P0a.
