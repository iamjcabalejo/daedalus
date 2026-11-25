## Argus review

The harness does what AC-1 and AC-3 ask offline: `--dry-run` makes no host call, and publishing waits for a clean isolation diff and leak scan. The main risk: E1–E5 and H2 can record a definite status for runs where the host never ran or never tried the call, which would give D9 a false answer. Not reviewed in full: testdata, agent templates, probe schemas. Not covered by a stack pack: Bash, JSON.

**Done well:** `finish()` stages everything under `$TMPDIR` and publishes only after `isolation.compare` and `redact.scan_paths` both come back clean. `test_dry_run_leaves_home_and_the_hub_untouched` proves this end to end, using sentinel `claude`/`agent`/`codex` binaries and a fake HOME checked by the harness's own snapshot.

**1. [important · correctness] E1–E5 and H2 record confirmed/contradicted when the host never ran or never attempted the probed call**
E variants assert only `marker` (absent means blocked) and keep `hook-ran` as `record`; `observe_run` just notes `host not run`. If T0 drops `--plugin-dir`, every plugin run skips `host`, yet E1–E4 `on-failure-block` and both E5 variants come out `confirmed`, and the E defaults and H2 come out `contradicted`. An early CLI exit does the same. README:164 says these stay inconclusive.
- Fix:
  - In `observe_run`, force `inconclusive` when `not state.host_ran` or the host timed out.
  - Make `hook-ran` a `precondition` in E1–E3 and E5.
  - Give E4 a `stream` check that a Bash `tool_use` was issued, because its hook can never record.
  - C1–C3 have the same gap: `spawned` only proves the spawn was requested, so a failed spawn (for example a wrong `probe:` name) passes `bash-not-run` / `fewer-than-five`. Add a `SubagentStart` precondition there.
  - Regression test: run E1 `on-failure-block` through `execute_run(..., skip=("host",))` and assert `inconclusive`.
- Where: `scripts/probes/probelib.py:518-524`; `scripts/probes/probelib.py:764`; `scripts/probes/cases/E1.json:175-205` (same shape in E2–E5); `scripts/probes/cases/C3.json:57-75`; `scripts/probes/README.md:164`
- Cost: E4 needs a new `stream` check kind (tool_use names from assistant events), and its stream-json shape has to be verified in T0.
<!-- argus-finding:ac4232f-1 -->

**2. [consider · correctness] `safe_remove` deletes the probe root, or `$TMPDIR`, when the target ends in `..`**
`location = target.parent.resolve() / target.name` leaves a trailing `..` unresolved. So `safe_remove(root/'ts'/'..', root)` passes both checks, and `rmtree` deletes the whole `daedalus-probes` root; `root/'ts'/'..'/'..'` deletes `$TMPDIR`. No caller builds such a path today (`INSTALLED_PATHS` are constants), and the test only covers a `..` in the middle of the path.
- Fix: Refuse any target with `'..' in target.parts` before the checks. Add `root/'run'/'..'` and `root/'run'/'..'/'..'` to `test_safe_remove_stays_inside_the_probe_root`. While there, reject `/` and `..` in variant ids in `validate_case`: they flow into the workspace path (`probelib.py:304`), which `mkdir` and `render` write to before any containment check.
- Where: `scripts/probes/isolation.py:97-98`; `scripts/test-probes.sh:703`
<!-- argus-finding:ac4232f-2 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@main:ac4232f1dd1ea87a47b85791bd0c25b097841fce+wt-A -->

<details><summary>Run notes</summary>

- **Config:** domain `none`, overridden by `/project-manager` (the personal default `ticketboat` from `~/.claude/argus.yml` targets product repos; this is the generic hub). `tickets.system` from `~/.claude/argus.yml`; the ticket is the P0 plan's acceptance criteria.
- **Scope:** part A of 3 (probe harness). The diff is the uncommitted working tree vs `ac4232f`, built by hand, because `argus-bundle.sh --local` reviews only `merge-base..HEAD`.
- **AC grading (this part):** AC-1 met; AC-2 met for P0a (finding 1 limits how far the statuses can be trusted); AC-3 tooling met; AC-12 not visible.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["python", "ci-cd"],
 "uncovered": ["scripts/probes/run-probes.sh", "scripts/test-probes.sh", "scripts/probes/cases/*.json", "scripts/probes/templates/**/*.json", "scripts/probes/templates/**/*.md", "bench/schema/probe-*.schema.json", "scripts/probes/testdata/**/*.json", "scripts/probes/README.md", "scripts/probes/fixtures/README.md", "scripts/probes/testdata/README.md"],
 "domain": "none",
 "ac": {"met": 3, "not_met": 0, "not_visible": 1},
 "findings": [
  {"id": "ac4232f-1", "severity": "important", "category": "correctness", "family": "FM-18", "title": "E1–E5 and H2 record confirmed/contradicted when the host never ran or never attempted the probed call", "path": "scripts/probes/probelib.py", "line": 518, "new": true},
  {"id": "ac4232f-2", "severity": "consider", "category": "correctness", "family": "FM-09", "title": "safe_remove deletes the probe root, or $TMPDIR, when the target ends in ..", "path": "scripts/probes/isolation.py", "line": 97, "new": true}
 ]}
```

</details>
