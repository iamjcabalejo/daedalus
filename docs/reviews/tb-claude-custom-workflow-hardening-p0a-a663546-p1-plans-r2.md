## Argus review

The revision fixes 11 of the 12 earlier findings and keeps every roadmap AC mapped, but the plans still can't be implemented without guessing (ticket AC-1 not met; AC-2 to AC-6 met): P1a's fail-closed git check makes TL3 unreachable, P1c's blocked-test path never reaches `rerun_blocked`, and the QA plugin still lacks the schemas `qa-assemble` needs. Not covered by a stack pack: Markdown plans.

**Done well:** P1c's `SM-complete-13` tests the exact collision behind a663546-5: plans `demo` and `demo-rework-1` each have an AC-1, only `demo:AC-1` is covered, and the result must be `E_COMPLETE_AC_UNCOVERED`. P1b's `^[a-z0-9][a-z0-9.-]*:AC-[0-9]+$` pattern also rejects bare ids at extraction.

**Since the last revision:** 11 earlier findings verified fixed, 1 still open.

**1. [important · correctness] The fail-closed work-tree check counts every non-repository folder as inside, so TL3 never applies**
TL3 needs `git -C <workspace> rev-parse --is-inside-work-tree` to say false, and any git error counts as inside. Outside a repository git never says false: it exits 128 ("not a git repository"). So no workspace reaches TL3. If `DAEDALUS_HOME` and the trust store reuse that check, a `$TMPDIR` home is ignored (tests hit the real `~`) and `~/.workflow/trust.json` is refused.
- Fix: decide "inside a work tree" without git's error path. Walk the folder and its ancestors in Python looking for a `.git` entry (directory or file). Count an unreadable component, or a set `GIT_DIR`/`GIT_WORK_TREE`, as inside. Call git only to confirm a `.git` the walk found; an error there (dubious ownership, say) still counts as inside. Use one helper for TL3, `DAEDALUS_HOME` and the trust store. Add positive cases to `U-trust-sources-*` and `U-trust-store-*`: a non-git ancestor workspace resolves TL3, and a `DAEDALUS_HOME` under a non-git temporary folder is honored.
- Where: `docs/plans/daedalus-hardening-p1a.md:114`; `docs/plans/daedalus-hardening-p1a.md:55`; `docs/plans/daedalus-hardening-p1a.md:304`
- Cost: one shared helper of about 15 lines; no new dependency.
<!-- argus-finding:a663546-13 -->

**2. [important · reliability] A `blocked` test report goes through `finish`, so G1 or G4 fires before G2 and `rerun_blocked` is never offered**
§3.11 A2 calls only `finish test`, and nothing turns a `blocked` report into a BLOCKED (env) step. If `finish` marks the step done, G4 sends it to rework, which is the sham round PF-10 meant to remove. If it marks it blocked, G1 fails first and returns to `testing`, rerunning test and review without asking. P1a makes this common: committed `user` test commands start untrusted.
- Fix: state that `finish test` with `verdict: blocked` records the step as `blocked` (env, with the reason taken from the report's blocked commands), exactly as `block` does. Have G1 count a `blocked` step as attempted so that G2 decides, and say so in §3.11 A2. Add `SM-complete-14`: a blocked report goes through `finish`, then `complete` returns `E_COMPLETE_BLOCKED_ENV` with `rerun_blocked`, never rework.
- Where: `docs/plans/daedalus-hardening-p1c.md:291`; `docs/plans/daedalus-hardening-p1c.md:158`; `docs/plans/daedalus-hardening-p1c.md:202-205`; `docs/plans/daedalus-hardening-p1c.md:183`
- Cost: one reducer rule and one SM case.
<!-- argus-finding:a663546-14 -->

**3. [important · reliability] On plugin installs, `/daedalus-qa:manual-test` has no runnable path to `artifacts.py qa-assemble`**
The build now copies `artifacts.py` and `scripts/lib/` into daedalus-qa, but not the schemas `qa-assemble` validates against. Those live in `skills/workflow-artifacts/schemas/`, which ships only in the daedalus plugin (P1b AC-14), and the QA plugin's `skills/` holds only `manual-qa`. So `qa-assemble` still fails there, and `U-build-qa-scripts-02` only compares bytes.
- Fix: have `build-plugin.sh` also copy `skills/workflow-artifacts/schemas/` into daedalus-qa, kept identical by `--check`. Make `U-build-qa-scripts-02` run `qa-assemble` on a fixture from the built QA plugin folder instead of comparing bytes.
- Where: `docs/plans/daedalus-hardening-p1b.md:71`; `docs/plans/daedalus-hardening-p1b.md:94`; `docs/plans/daedalus-hardening-p1a.md:296` (still open from an earlier revision)
- Cost: a second copy of about 20 small schema files in the QA plugin.
- On your reply: PF-6 and PF-9 give `/manual-test` a real path to `artifacts.py`, which fixes half of the problem. But `qa-assemble` validates `qa-cases` and `qa` against the registry's schema files. Today `plugins/daedalus-qa/skills/` holds only `manual-qa`, and neither plan adds `workflow-artifacts` there.
<!-- argus-finding:a663546-4 -->

**4. [consider · reliability] A role running past the 30-minute TTL makes a live lease stale, so a second session can reconcile its step**
§3.3 calls a lease stale when `host_pid` is gone or when the heartbeat is older than `runtime.lease_ttl_minutes` (30). Only mutating calls refresh the heartbeat, and none runs during a synchronous spawn. After a 40-minute implementer or QA pass, a second session's `resume` can take the lease and offer `continue` or `discard_partial` on files the first agent is still writing.
- Fix: while `host_pid` is set and alive on the same host, treat the lease as live whatever the heartbeat says. With `host_pid: null`, have `resume` ask before reconciling an attempt admitted less than a role ceiling ago (for example 2× the TTL). Name this as a deviation from roadmap §6.3. Add a `U-store` case: a live `host_pid` with a heartbeat older than the TTL is not stale.
- Where: `docs/plans/daedalus-hardening-p1c.md:130`; `docs/plans/daedalus-hardening-p1c.md:126`; `docs/plans/daedalus-hardening-roadmap.md:855`
- Cost: when no host pid is found, a crashed session's run waits for the user's confirmation instead of for the TTL.
<!-- argus-finding:a663546-15 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). `tickets.system` from `~/.claude/argus.yml`; no ticket key matched, so the ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** re-review of the three untracked plans `docs/plans/daedalus-hardening-p1{a,b,c}.md` after the first review ([tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans.md](tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans.md)). The diff was built by hand (new-file diffs of the revised plans), because `argus-bundle.sh --local` reviews only `merge-base..HEAD` (C-5). `prior.md` held the first review; `replies.md` held the author's per-finding change notes. The head SHA is unchanged (uncommitted plans), so new findings are numbered from a663546-13.
- **Prior findings:** verified fixed: a663546-1, -2, -3, -5, -6, -7, -8, -9, -10, -11, -12. Still open: a663546-4 (schemas missing from the QA plugin).
- **AC:** met: AC-2 to AC-6. Not met: AC-1 (findings 1–3).
- **Packs:** profile packs loaded (ci-cd, go, iac, python); none matches Markdown plans, so failure modes alone applied.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"],
 "domain": "none",
 "ac": {"met": 5, "not_met": 1, "not_visible": 0},
 "findings": [
  {"id": "a663546-13", "severity": "important", "category": "correctness", "family": "FM-02", "title": "The fail-closed work-tree check counts every non-repository folder as inside, so TL3 never applies", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 114, "new": true},
  {"id": "a663546-14", "severity": "important", "category": "reliability", "family": "FM-05", "title": "A `blocked` test report goes through `finish`, so G1 or G4 fires before G2 and `rerun_blocked` is never offered", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 291, "new": true},
  {"id": "a663546-4", "severity": "important", "category": "reliability", "family": "FM-10", "title": "On plugin installs, `/daedalus-qa:manual-test` has no runnable path to `artifacts.py qa-assemble`", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 71, "new": false},
  {"id": "a663546-15", "severity": "consider", "category": "reliability", "family": "FM-07", "title": "A role running past the 30-minute TTL makes a live lease stale, so a second session can reconcile its step", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 130, "new": true}
 ],
 "not_reviewed": [],
 "pack_suggestions": [{"stack": "design-docs", "family": "FM-02", "signal": "a fail-closed rule that counts every error of a probe command as the unsafe answer, when the tool reports the safe answer itself as an error (git rev-parse outside a repository exits 128)"}]}
```

</details>
