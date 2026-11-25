## Argus review

The fifth revision fixes a663546-17 and meets ticket AC-1 to AC-6, but the -20 fix still lets a run reach `ready` without its test command having run: the project's untrusted test command can be reported `skipped`, or left out of the report, and G4 still passes; not covered by a stack pack: Markdown plans.

**Done well:** P1c AC-1 (`daedalus-hardening-p1c.md:60`) now gives the same ownership rule as §3.3 (`:128`, `:133`), §3.10 (`:290`) and §3.11 (`:307`): a matching token, or a live ancestor `host_pid`, counts as the owner whether or not the lease is stale. `U-store` (`:378`) tests the no-token, live-`host_pid`, old-heartbeat case, so a compacted project-manager carries on without `--force`.

**Since the last revision:** 1 earlier finding verified fixed, 1 still open.

**1. [consider · correctness] A test report with a failing or skipped command and empty `failures[]` passes G4 as `verdict: pass`**
The fail-without-entry case and the runnable-but-skipped case are now closed. The untrusted case is not. P1a AC-13 keeps untrusted commands out of every brief, so they are never in `context["runnable"]`, and §3.5 then accepts them as `skipped`. A report that leaves a command out of `commands[]` altogether is never checked. In both cases the verdict is `pass`, G4 passes, and the PF-10 path (BLOCKED, then `/setup`, then `rerun_blocked`) is bypassed.
- Fix: have P1c pass `context["untrusted"]` too: the untrusted or `unsafe` command names of the test roots, from `effective_commands`. `validate_obj` should require every runnable and untrusted command to appear in `commands[]`, and require untrusted ones to be `blocked`. Add `U-artifacts-extract` cases for an untrusted `test` reported `skipped` and for a runnable command left out of the report.
- Where: `docs/plans/daedalus-hardening-p1b.md:148`; `docs/plans/daedalus-hardening-p1c.md:50`; `docs/plans/daedalus-hardening-p1c.md:320`; `docs/plans/daedalus-hardening-p1a.md:66` (still open from an earlier revision)
- Cost: one more list in the `extract` context, which `admit test` already has from `effective_commands`.
- On your reply: the new rule accepts `skipped` for any command not in the brief's runnable list. Untrusted commands are never in that list (P1a AC-13), yet PF-10 says an untrusted committed test command stays BLOCKED until `/setup`. That untrusted case was the second scenario in the original finding. A runnable command left out of the report is still never checked.
<!-- argus-finding:a663546-20 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). The ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** fifth pass over the three untracked plans, after r1–r4 in this folder. Diff built by hand (C-5). `prior.md` held r4; `replies.md` the author's change notes.
- **Prior findings:** verified fixed: a663546-17. Still open: -20.
- **AC:** met: AC-1 to AC-6.
- **Reviewer notes:** no packs apply to Markdown plans. The flattened runnable-name list across roots can only refuse a valid report, never pass a bad one, so it wasn't raised.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": [], "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"], "domain": "none",
 "ac": {"met": 6, "not_met": 0, "not_visible": 0},
 "findings": [{"id": "a663546-20", "severity": "consider", "category": "correctness", "family": "FM-18", "title": "A test report with a failing or skipped command and empty failures[] passes G4 as verdict: pass", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 148, "new": false}],
 "not_reviewed": [],
 "pack_suggestions": []}
```

</details>
