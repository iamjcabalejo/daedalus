## Argus review

The third revision fixes all four open findings (a663546-4, -13, -14, -15) and meets ticket AC-1 to AC-6, leaving four consider-level gaps, chiefly that clearing a BLOCKED test with `/setup` still reruns review and QA, and that a home folder under git disables the trust store. Not covered by a stack pack: Markdown plans.

**Done well:** P1b's `U-build-qa-scripts-02` runs `qa-assemble` from the built `plugins/daedalus-qa/scripts/` folder, and requires `E_SCHEMA_DIR_MISSING` when the schema copy is removed. So a663546-4 is now proved by running the code, not by comparing bytes.

**Since the last revision:** 4 earlier findings verified fixed.

**1. [consider · correctness] A home folder under git refuses the trust store forever, so `/setup` records trust that never applies**
§3.7 refuses any store for which `inside_work_tree` is true, and that includes the home folder from the password database. With a dotfiles repository at `~/.git`, the walk finds it and git confirms `true`, so `~/.workflow/trust.json` is always `E_TRUST_STORE_UNSAFE`. `trust record` still writes, `/setup` reports success, and every committed command keeps asking.
- Fix: apply the work-tree test only to a store under `DAEDALUS_HOME`, the one channel a repository can influence. For the password-database home, keep the symlink, owner, mode and inside-the-target checks. Have `trust record` run the read checks before writing, and fail with the fix line instead of reporting success. Add a `U-trust-store` case: a home that is a git work tree holds a usable store.
- Where: `docs/plans/daedalus-hardening-p1a.md:214`; `docs/plans/daedalus-hardening-p1a.md:117-121`; `docs/plans/daedalus-hardening-p1a.md:64`
- Cost: a store inside a home-level repository could be committed by its owner. That repository is the user's own, not one Daedalus is working on.
<!-- argus-finding:a663546-16 -->

**2. [consider · reliability] Saying the token alone decides ownership drops the host-pid proof a compacted run needs to avoid `--force`**
§3.3 makes a call own when it has the token or, as a second proof, a live ancestor `host_pid` (also in §3.10 and §3.11 "Lost token"). It then says the token alone decides ownership. A live `host_pid` now keeps the lease live whatever the heartbeat says. So a build that checks only the token turns every context compaction into `E_RUN_LEASE_LIVE` plus `--force`, or `E_NEEDS_HUMAN` in headless runs.
- Fix: reword the last "Stale" bullet to "a matching token is own whether or not the lease is stale", and keep the host-pid proof. Add a `U-store` case: no token, a live ancestor `host_pid` and a heartbeat older than the TTL count as own.
- Where: `docs/plans/daedalus-hardening-p1c.md:133`; `docs/plans/daedalus-hardening-p1c.md:128`; `docs/plans/daedalus-hardening-p1c.md:307`
<!-- argus-finding:a663546-17 -->

**3. [consider · correctness] A test report with a real failure can declare `verdict: blocked` and go to review instead of rework**
P1b's semantic check only forbids `pass` when a failure isn't pre-existing; nothing ranks `fail` above `blocked`. Under P1c's new `finish test [verdict blocked] → reviewing` row, a report where lint fails and the untrusted `test` command is blocked can say `blocked`. The run then reviews and QAs failing code, waits on G2, and reaches rework only after the rerun.
- Fix: in P1b §3.5, also reject `verdict: blocked` when any `failures[]` entry has `pre_existing: false`. The order becomes fail > blocked > pass, the same rule `qa-assemble` computes for QA. Add a `U-artifacts-extract` case: a blocked report with a new failure.
- Where: `docs/plans/daedalus-hardening-p1b.md:148`; `docs/plans/daedalus-hardening-p1c.md:164`
<!-- argus-finding:a663546-18 -->

**4. [consider · cost] Clearing a BLOCKED test with `/setup` still reruns review and QA: `/setup` rewrites the profile in the fingerprint**
§3.11 names `/setup` as the fix for an untrusted test command. `/setup` runs the detector without `--ensure`, which always rewrites `.workflow/profile.json` with a new `generated_at` (`detect-stack.py:932`, `:1094-1097`). Drift ignores the profile (PF-8), but G6 and G8 compare the full fingerprint. So after `rerun_blocked`, the review and QA that row 181 calls "still fresh" are stale and run again.
- Fix: in P1a, have `/setup` leave an unchanged profile untouched: `write_profile` skips the write when only `generated_at` differs, or `/setup` uses `--ensure` when the profile is fresh. Extend `SM-guard-12` or the end-to-end test: blocked test, then `/setup` records trust, then `rerun_blocked`, then `complete` returns `ok` without a new review or QA.
- Where: `docs/plans/daedalus-hardening-p1c.md:181`; `docs/plans/daedalus-hardening-p1c.md:48`; `docs/plans/daedalus-hardening-p1c.md:214`; `docs/plans/daedalus-hardening-p1a.md:64`; `.claude/commands/setup.md:30`
- Cost: a few lines in the detector's writer. `--set` and `--confirm` still write when they change something.
<!-- argus-finding:a663546-19 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). `tickets.system` from `~/.claude/argus.yml`; no ticket key matched, so the ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** third pass over the three untracked plans `docs/plans/daedalus-hardening-p1{a,b,c}.md`, after [the first review](tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans.md) and [the second](tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r2.md). The diff was built by hand (new-file diffs of the revised plans), because `argus-bundle.sh --local` reviews only `merge-base..HEAD` (C-5). `prior.md` held the second review; `replies.md` held the author's per-finding change notes. New findings are numbered from a663546-16 (the head SHA is unchanged).
- **Prior findings:** verified fixed: a663546-4, -13, -14, -15 (and -1…-12 in the second review).
- **AC:** met: AC-1 to AC-6.
- **Body check:** the first answer's verdict was three sentences; one follow-up asked for a single sentence. The second answer fixed it and also shortened finding 2's title (the old one was over 110 characters); nothing else changed.
- **Packs:** profile packs loaded (ci-cd, go, iac, python); none matches Markdown plans, so failure modes alone applied.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"],
 "domain": "none",
 "ac": {"met": 6, "not_met": 0, "not_visible": 0},
 "findings": [
  {"id": "a663546-16", "severity": "consider", "category": "correctness", "family": "FM-17", "title": "A home folder under git refuses the trust store forever, so /setup records trust that never applies", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 214, "new": true},
  {"id": "a663546-17", "severity": "consider", "category": "reliability", "family": "FM-07", "title": "Saying the token alone decides ownership drops the host-pid proof a compacted run needs to avoid --force", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 133, "new": true},
  {"id": "a663546-18", "severity": "consider", "category": "correctness", "family": "FM-11", "title": "A test report with a real failure can declare verdict: blocked and go to review instead of rework", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 148, "new": true},
  {"id": "a663546-19", "severity": "consider", "category": "cost", "family": "FM-12", "title": "Clearing a BLOCKED test with /setup still reruns review and QA: /setup rewrites the profile in the fingerprint", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 181, "new": true}
 ],
 "not_reviewed": [],
 "pack_suggestions": []}
```

</details>
