## Argus review

The eighth revision fixes a663546-22 with one rule shared by P1b and P1c (a trusted, safe `build` is always runnable and an untrusted or `unsafe` one stays outside the check), it adds no new inconsistency at `admit test` or `finish`, and it meets ticket AC-1 to AC-6 with no material risk left open; not covered by a stack pack: Markdown plans.

**Done well:** The `build` rule takes no input from the brief and is stated the same way in both plans (`docs/plans/daedalus-hardening-p1b.md:148`, `docs/plans/daedalus-hardening-p1c.md:320`). Each branch has its own extract case: `U-artifacts-extract-16` rejects a trusted safe `build` reported `skipped`, and `-17` accepts an absent `unsafe` `build` (`docs/plans/daedalus-hardening-p1b.md:318`). The rule also matches the test-runner's existing order, which runs `build` last (`.claude/agents/test-runner.md:30`).

**Since the last revision:** 1 earlier finding verified fixed.

No material findings. Architecture, security, performance, cost, reliability and correctness all look sound for this change.

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). The ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** eighth pass over the three untracked plans, after r1–r7 in this folder. Diff built by hand (C-5). `prior.md` held r7.
- **Prior findings:** verified fixed: a663546-22. All 22 findings across the eight passes are now fixed.
- **AC:** met: AC-1 to AC-6.
- **Below the bar (reviewer notes, not findings):** P1b's wording says `UNSAFE_RE` "matches names like `release` or `prod`", but the regex runs on the command text and body (`detect-stack.py:38`, `:151`); behavior is unaffected because the plan keys on the `unsafe` flag. A `test` command flagged `unsafe` blocks the run until `rerun_blocked` or `abort`; that follows from -21's scope and P1a's trust rules, not from this fix.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": [], "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"], "domain": "none",
 "ac": {"met": 6, "not_met": 0, "not_visible": 0},
 "findings": [],
 "not_reviewed": [],
 "pack_suggestions": [{"stack": "markdown-plans", "family": "FM-19", "signal": "A contract that two plans share (here the context lists that admit test stores and finish reads) must be stated with the same rule in both plans and have a test case for each branch"}]}
```

</details>
