## Argus review

The fourth revision fixes a663546-16, -18 and -19 and meets ticket AC-1 to AC-6, but P1c's AC-1 still says only the token proves lease ownership, and P1b's test-report check lets a command that failed or was skipped, with an empty `failures[]`, pass G4. Not covered by a stack pack: Markdown plans.

**Done well:** P1c §5 tests the full -19 path end to end: blocked test, then `/setup`, then `rerun_blocked`, then `complete` returns `ok` with no new review or QA. That path holds for two reasons. P1a's `U-detector-nowrite-01` checks that the profile's bytes and mtime don't change. And `trust.commands_digest` covers command definitions only, not trust state (`daedalus-hardening-p1a.md:240`), so recording trust doesn't make G6 or G8 stale.

**Since the last revision:** 3 earlier findings verified fixed, 1 still open.

**1. [consider · reliability] Saying the token alone decides ownership drops the host-pid proof a compacted run needs to avoid `--force`**
§3.3 now keeps the host-pid proof. AC-1 is the contract an implementer builds to, and it still says "a token the proof of ownership" and that a call without the token is refused while the lease is live. A build that follows AC-1 refuses a compacted project-manager whose ancestor `host_pid` is still live: it gets `E_RUN_LEASE_LIVE`, then needs `--force`. The new `U-store` case then contradicts its own AC.
- Fix: reword AC-1's lease bullet to "a call is own with the matching token, or without one when its ancestor `host_pid` is live (§3.3); any other call is refused while the lease is live."
- Where: `docs/plans/daedalus-hardening-p1c.md:60`; `docs/plans/daedalus-hardening-p1c.md:133` (still open from an earlier revision)
- On your reply: the reply cites only the §3.3 rewording and the new `U-store` case. AC-1 at line 60 still states the token-only rule.
<!-- argus-finding:a663546-17 -->

**2. [consider · correctness] A test report with a failing or skipped command and empty `failures[]` passes G4 as `verdict: pass`**
§3.5 derives the verdict only from `failures[]` and `blocked` commands. Two reports must therefore say `pass`, and G4 accepts both: `commands: [{name: "lint", status: "fail", exit: 1}]` with `failures: []`, and an untrusted `test` command reported `skipped` instead of `blocked`. The run then reaches `ready` with a failing or unrun check. The -18 fix cross-checks `blocked` but not `fail` or `skipped`.
- Fix: in `validate_obj`'s semantic check, reject a report where a command with status `fail` has no `failures[]` entry naming that command. Allow `skipped` only for a command missing from the brief's runnable list; otherwise require `blocked`. Add `U-artifacts-extract` cases for a `fail` command with empty `failures[]` and for a runnable `test` command reported `skipped`.
- Where: `docs/plans/daedalus-hardening-p1b.md:148`; `docs/plans/daedalus-hardening-p1b.md:142`; `docs/plans/daedalus-hardening-p1c.md:212`
- Cost: the check needs the brief's runnable command names. `admit test` already passes them (`daedalus-hardening-p1c.md:315`), but they have to reach `extract`.
<!-- argus-finding:a663546-20 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). `tickets.system` from `~/.claude/argus.yml`; the ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** fourth pass over the three untracked plans, after [r1](tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans.md), [r2](tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r2.md) and [r3](tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r3.md). Diff built by hand (C-5). `prior.md` held r3; `replies.md` the author's change notes.
- **Prior findings:** verified fixed: a663546-16, -18, -19. Still open: -17.
- **AC:** met: AC-1 to AC-6.
- **Body check:** the first answer's verdict was three sentences; one follow-up fixed it, nothing else changed.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": [], "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"], "domain": "none",
 "ac": {"met": 6, "not_met": 0, "not_visible": 0},
 "prior": {"verified_fixed": ["a663546-16", "a663546-18", "a663546-19"], "still_open": ["a663546-17"]},
 "findings": [
  {"id": "a663546-17", "severity": "consider", "category": "reliability", "family": "FM-07", "title": "Saying the token alone decides ownership drops the host-pid proof a compacted run needs to avoid --force", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 60, "new": false},
  {"id": "a663546-20", "severity": "consider", "category": "correctness", "family": "FM-18", "title": "A test report with a failing or skipped command and empty failures[] passes G4 as verdict: pass", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 148, "new": true}],
 "not_reviewed": [],
 "pack_suggestions": []}
```

</details>
