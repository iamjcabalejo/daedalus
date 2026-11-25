## Argus review

Rework 3 does what RW-28 to RW-31 ask:
- only seed-repo tasks skip the identity check;
- A1 proves PostToolUse attribution;
- sandbox scoring and env name no hub path, and run folders are sealed;
- `run.py` writes no bytecode.

Open: sandbox processes the agent leaves running outlive the run. Not reviewed in full: metrics.py, probelib.py. Not covered by a stack pack: JSON, shell, Markdown.

**Done well:** `test_c1_c2_confirmed_on_a_pre_only_host_are_gated_inconclusive` (`scripts/test-probes.sh:1258-1276`). It first shows the hazard: on a host that attributes only PreToolUse, C1 or C2 alone reads `confirmed`. It then gates that result through an A1 that is `contradicted` and through one that is `inconclusive`, and runs a control with an attributed A1 that still reads `confirmed`. So the test proves the gate is what changed.

**Since the last revision:** 3 earlier findings verified fixed.

**1. [consider · reliability] Processes a sandbox agent leaves running outlive its run and share the next arm's run on the same task**
`SandboxBoundary` has no `kill_argv`, and nothing kills the agent user's processes after a step: `_terminate` signals only sudo's process group. A dev server or daemon the agent detaches survives scoring. Because `schedule` alternates arms on each task, it then runs through the other arm's unsealed run as the same user, able to read its folder and holding its ports.
- Fix:
  - Give `SandboxBoundary` a `kill_argv` that runs `kill -KILL -1` as that user through the existing `sudo -n -u <user> -- env …` path. This matches the docker boundary's `docker kill`.
  - Call it after every agent step, and again before collection and `stage_hidden`.
  - Skip the run if `pgrep -u <user>` still lists a process.
  - Replace the operator step in `bench/README.md:98`. Nobody can run a command between steps of an automated schedule.
  - Test: the sandbox `kill_argv` is the user-wide kill, and a fake-arm sandbox run calls it after the agent phase and before `stage_hidden`.
- Where: `bench/lib/boundary.py:142-143` (not overridden in `:193-249`); `bench/run.py:286-288`; `bench/run.py:414-419`; `bench/lib/budget.py:36`; `bench/README.md:87`, `:98`
- Cost: one sudo call per step. The sandbox user has to stay dedicated to the benchmark, because every process it owns gets killed.
<!-- argus-finding:ac4232f-17 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@main:ac4232f1dd1ea87a47b85791bd0c25b097841fce+wt-rework3 -->

<details><summary>Prior findings (3)</summary>

| Id | Status | Evidence |
|---|---|---|
| ac4232f-15 | fixed | The exemption needs both `set: selftest` and a `selftest:` URL (`tasks.py:117-120`, `:361`). `check_task` refuses `set: selftest` on any other repo (`:383-388`). The check runs in `validate`, `run` and `verify-task`. Test at `test_bench.py:541-559` |
| B:ac4232f-2 | fixed | The host stages the hidden tests (`boundary.py:132-140`; `run.py:383-389`); `overlay_tree` (`workspace.py:501-522`); seal in `finally` (`run.py:435-439`, `:737-740`); env (`boundary.py:207-222`); README `:83-98`. Process lifetime is a separate root cause (finding 1) |
| ac4232f-16 | fixed | `agent-type-after` (`A1.json:122-146`). With no PostToolUse, A1 is `inconclusive`. README updated; synthetic sample regenerated, with a guard test (`test-probes.sh:366-373`) |

</details>

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override). Packs: `python` and `ci-cd`.
- **AC:** RW-28 to RW-31 all met.
- **Residuals, correctly T0 items:**
  - macOS ACLs. T0 will need harness code that sets per-folder access, after which `seal` should also drop ACLs (`chmod -N` on darwin).
  - The `claude` check runs as the host user; the README's T0 item covers running it as the sandbox user.
- **Not material:** on Linux without `hidepid`, a sandbox agent can read the harness's argv through `ps`.
- **Bundle:** built by hand from the working tree.

</details>

```json
{"stacks": ["python", "ci-cd"],
 "domain": "none",
 "ac": {"met": 4, "not_met": 0, "not_visible": 0},
 "findings": [
  {"id": "ac4232f-17", "severity": "consider", "category": "reliability", "family": "FM-07", "title": "Processes a sandbox agent leaves running outlive its run and share the next arm's run on the same task", "path": "bench/lib/boundary.py", "line": 142, "new": true}
 ]}
```
