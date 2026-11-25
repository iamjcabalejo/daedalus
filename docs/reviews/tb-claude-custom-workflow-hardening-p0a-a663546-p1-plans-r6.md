## Argus review

The sixth revision fixes a663546-20 and meets ticket AC-1 to AC-6, but the fix requires every runnable or untrusted command of a test root to be reported, and blocks the run on any of them, so a normal profile with `dev`, `install` or `format` sends nearly every test step to BLOCKED (env); not covered by a stack pack: Markdown plans.

**Done well:** P1c §3.12 (`daedalus-hardening-p1c.md:320`) stores the `runnable` and `untrusted` lists on the attempt at `admit test`, so `finish` checks against the same lists. The `<root>:<name>` keys (`daedalus-hardening-p1b.md:148`) stop a command that is runnable in one root from counting for another. `U-artifacts-extract-13` and `-14` (`:318`) test the untrusted-`skipped` case and the left-out-command case.

**Since the last revision:** 1 earlier finding verified fixed.

**1. [important · correctness] Test reports must mark every non-check command blocked, so most runs stall in BLOCKED (env)**
Both lists hold all of a test root's commands, with no filter by name. The profile's `COMMAND_NAMES` are install, test, lint, typecheck, build, dev and format. The test-runner doesn't run `dev` (a long-running server), `install` or `format`. `skipped` is now refused for them, so they must be `blocked`, which makes the verdict `blocked`. An `unsafe` `install` stays untrusted for good, so `rerun_blocked` can never clear it.
- Fix: in P1b §3.5 and P1c §3.12, limit `context["runnable"]` and `context["untrusted"]` to the check commands the test step owns (`test`, `lint`, `typecheck`, plus `build` if the plan says so). Accept any other name as `skipped` or leave it out. Have the brief list the untrusted check names (name only, no command text) so the role can report them `blocked`. Add a `U-artifacts-extract` case: a trusted `dev` and an `unsafe` `install` absent from the report are accepted, and the verdict stays `pass`.
- Where: `docs/plans/daedalus-hardening-p1b.md:148`; `docs/plans/daedalus-hardening-p1c.md:320`; `docs/plans/daedalus-hardening-p1c.md:298`; `.claude/scripts/detect-stack.py:452`
- Cost: one named constant of check-command names, shared by P1b and P1c.
<!-- argus-finding:a663546-21 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). The ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** sixth pass over the three untracked plans, after r1–r5 in this folder. Diff built by hand (C-5). `prior.md` held r5; `replies.md` the author's change note.
- **Prior findings:** verified fixed: a663546-20. New: -21 (introduced by the -20 fix).
- **AC:** met: AC-1 to AC-6.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": [], "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"], "domain": "none",
 "ac": {"met": 6, "not_met": 0, "not_visible": 0},
 "findings": [{"id": "a663546-21", "severity": "important", "category": "correctness", "family": "FM-09", "title": "Test reports must mark every non-check command blocked, so most runs stall in BLOCKED (env)", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 148, "new": true}],
 "not_reviewed": [],
 "pack_suggestions": []}
```

</details>
