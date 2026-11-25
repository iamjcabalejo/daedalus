## Argus review

The seventh revision fixes a663546-21 and meets ticket AC-1 to AC-6, but one input is undefined: `build` joins the check lists "when the brief asks", and the brief is written after `admit test` has already stored the lists, so an implementer has to guess whether a skipped or `unsafe` build counts; not covered by a stack pack: Markdown plans.

**Done well:** `U-artifacts-extract-15` (`docs/plans/daedalus-hardening-p1b.md:318`) pins down the -21 regression: a trusted `dev` and an `unsafe` `install` missing from the report are accepted, and the verdict stays `pass`. It sits next to the -11/-13 cases, which still reject a skipped `test`.

**Since the last revision:** 1 earlier finding verified fixed.

**1. [consider · correctness] Build's place in the test check has no source at admit, so a skipped build passes or an unsafe build blocks the run for good**
`admit test` builds `context["runnable"]` and `context["untrusted"]` and stores them on the attempt. `admit` returns only facts. The project-manager writes the brief afterwards (§3.10), and no plan fence carries a build flag. If build is left out, a test-runner that skips a trusted build gets `pass` through G4. If build is put in, an `unsafe` build (UNSAFE_RE matches `release`/`prod`) stays `blocked`, and `rerun_blocked` can't clear it.
- Fix: decide build at admission from a recorded input, for example `workflow.py admit test --with-build`, journaled on the attempt and echoed in the brief. Or always count a trusted, non-`unsafe` build as runnable, and keep an untrusted or `unsafe` build out of the check. Add an extract case for each branch.
- Where: `docs/plans/daedalus-hardening-p1b.md:148`; `docs/plans/daedalus-hardening-p1c.md:320`; `docs/plans/daedalus-hardening-p1c.md:290`; `.claude/agents/test-runner.md:32`; `.claude/scripts/detect-stack.py:38`
- Cost: one flag or one sentence in each plan, plus a test case.
<!-- argus-finding:a663546-22 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). The ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** seventh pass over the three untracked plans, after r1–r6 in this folder. Diff built by hand (C-5). `prior.md` held r6.
- **Prior findings:** verified fixed: a663546-21.
- **Checked and sound (reviewer):** G4 still reads `verdict`; G7 freshness uses `commands_digest`, unchanged by the scoping; the PF-10 rerun path for untrusted `test`/`lint`/`typecheck` is intact; naming untrusted commands in the brief by name only is consistent with P1a AC-13.
- **AC:** met: AC-1 to AC-6.
- **Body check:** passed; the finding's title is about 124 characters, over the 110 the template asks for (not a Phase C rule).

</details>

<details><summary>findings.json</summary>

```json
{"stacks": [], "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"], "domain": "none",
 "ac": {"met": 6, "not_met": 0, "not_visible": 0},
 "findings": [{"id": "a663546-22", "severity": "consider", "category": "correctness", "family": "FM-09", "title": "Build's place in the test check has no source at admit, so a skipped build passes or an unsafe build blocks the run for good", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 148, "new": true}],
 "not_reviewed": [],
 "pack_suggestions": [{"stack": "markdown-plans", "family": "FM-09", "signal": "A gate input is said to depend on a later artifact (a brief written after admission) but is fixed at admission time"}]}
```

</details>
