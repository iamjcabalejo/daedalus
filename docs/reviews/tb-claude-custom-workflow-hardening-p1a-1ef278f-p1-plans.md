## Argus review

The three P1 plans map all 16 assigned roadmap ACs and their code citations hold at 1ef278f, but a non-git workspace above a nested repository still gets TL3, so its committed `commands` overrides skip the trust store, and the critical tier's `scan` step has no output kind or gate; not covered by a stack pack: Markdown plans.

**Done well:** P1b's PF-1 makes the source fingerprint depend only on the files present in the working tree, with no tombstones and modes taken from `lstat`. Staged and unstaged deletions therefore hash the same. `U-fp-01`…`-14` pins this (equal hashes for staged and unstaged deletions and edits, and the index is never written), and `G-fingerprint-repro-01` recomputes on Linux CI a digest computed on macOS (`docs/plans/daedalus-hardening-p1b.md:44`, `:192-198`, `:324`).

**1. [important · security] A non-git workspace above a nested repo is TL3, so its committed `commands` overrides skip the trust store**
§3.8 trusts TL3 `commands` overrides without the store, and TL3 is any non-git strict ancestor of the target. Extract an archive whose root holds a `.workflow/config.yml` `test` override above a nested `app/.git`, start the session there, and that command enters `admit`'s runnable set and runs unasked. §3.4 and roadmap §6.5 say trust comes from TL2.
- Fix: in §3.8 and AC-9, trust only TL2 overrides outright, as §3.4 and roadmap §6.5 already say. A TL3 override needs the store, like a TL4 one. Add `PT-trust-workspace-01`: a non-git folder holding a `commands` override above a nested git repository resolves as untrusted until `trust record`.
- Where: `docs/plans/daedalus-hardening-p1a.md:229`; `docs/plans/daedalus-hardening-p1a.md:62`; `docs/plans/daedalus-hardening-p1a.md:114`; `docs/plans/daedalus-hardening-p1a.md:137`; `docs/plans/daedalus-hardening-roadmap.md:918`
- Cost: users of a real multi-repo workspace confirm its overrides once with `/setup`.
<!-- argus-finding:1ef278f-1 -->

**2. [important · correctness] Critical-tier `scan` has no output kind or gate, so `finish scan` can't validate and its findings never block**
A `Security: critical` plan runs the critical tier, where G1 needs a `done` `scan`. `finish` validates the reply by the step's kind, but P1b's registry has no scan kind (`/argus-scan` writes Markdown; severities `critical|high`), §3.5 has no `finish scan` row, and G3 reads only the review. The run never reaches `ready`, or a `high` finding never blocks it.
- Fix:
  - Add a scan kind to P1b §3.3: the scan-mode JSON with `critical|high` severities, assembled like `review`.
  - Map `finish scan` to that kind.
  - Add `reviewing` rows for `finish scan`: any critical or high finding → rework.
  - Extend G3 and G6 to the latest scan.
  - Regression test `SM-complete-15`: a critical-tier run whose scan holds one `high` finding is refused.
- Where: `docs/plans/daedalus-hardening-p1c.md:197`; `docs/plans/daedalus-hardening-p1c.md:209`; `docs/plans/daedalus-hardening-p1c.md:211`; `docs/plans/daedalus-hardening-p1c.md:299`; `docs/plans/daedalus-hardening-p1b.md:109-121`
- Cost: one schema, two table rows and a gate clause; `/argus-scan` gains a JSON output.
<!-- argus-finding:1ef278f-2 -->

**3. [consider · correctness] The banner either flags re-detected `script` commands as untrusted forever, or never counts a forged one**
Fast mode marks every `script`/`derived` entry unverified, and `trust record --pending` stores only full-mode untrusted entries, so reproduced ones never reach the store. If unverified counts as untrusted, every repo with an `npm test` entry shows the untrusted line each session and `/setup` can't clear it; if not, OQ-2's forged entry is never counted.
- Fix: decide it in §3.8, with one of two options:
  - fast mode counts only entries that need the store (`user`, confirmed, TL3/TL4 overrides), and OQ-2 expects the count from `config commands`; or
  - `trust record --pending` also stores the digests of reproduced entries, so fast mode can match them.

  Either way, add `U-trust-effective-11`: a repo with only reproduced `script` entries and an empty store shows no untrusted line.
- Where: `docs/plans/daedalus-hardening-p1a.md:237`; `docs/plans/daedalus-hardening-p1a.md:60`; `docs/plans/daedalus-hardening-p1a.md:64`; `docs/plans/daedalus-hardening-p1a.md:398`
- Cost: the second option adds one store write per `/setup`.
<!-- argus-finding:1ef278f-3 -->

**4. [consider · reliability] `init` over a crashed run opens a second run: `admit` hits `E_RUN_AMBIGUOUS` and reconciliation is skipped**
`init` refuses only a run with a live lease. Once a crashed run's lease is stale (OQ-6's kill), `/project-manager docs/plans/demo.md` without `--resume` starts a second run whose baseline already holds the partial edits; every `admit` without `--run` then gets `E_RUN_AMBIGUOUS`, and adding `--run` skips R-AC-47's continue/discard choice.
- Fix: `init` refuses while any non-terminal run exists, whether its lease is live or stale (`E_RUN_ACTIVE`, fix: `--resume <id>` or `cancel`). Phase 0 runs `status` first and offers resume. Add `U-store-14`: a non-terminal run with a stale lease makes `init` refuse and name that run.
- Where: `docs/plans/daedalus-hardening-p1c.md:118`; `docs/plans/daedalus-hardening-p1c.md:296`; `docs/plans/daedalus-hardening-p1c.md:467`
- Cost: an abandoned run needs one explicit `cancel`.
<!-- argus-finding:1ef278f-4 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p1a:1ef278fb64e45e66238ca8402ec88d9546c9cc2c -->

<details><summary>Run notes</summary>

- **Config:** domain `ticketboat` from `/Users/fullscale/.workflow/config.yml`; tickets.system `linear` from `/Users/fullscale/.workflow/config.yml`. No ticket key matched, so there is no linked ticket; the plans were graded against the P1 section of the roadmap.
- **Scope:** `/argus --local HEAD~1`, so the diff is commit 1ef278f only (11 Markdown files, 1,892 diff lines). Uncommitted working-tree changes were not reviewed. `prior.md` was seeded with r8 of the P1 plan reviews (`tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r8.md`).
- **Id collision (added by the command):** these ids are numbered independently of the working-tree review [`tb-claude-custom-workflow-hardening-p1a-1ef278f.md`](tb-claude-custom-workflow-hardening-p1a-1ef278f.md) (and its r2–r5), which also uses `1ef278f-N` for other issues. **1ef278f-1 here is the same root cause as that review's 1ef278f-3.** Rework-1 already fixed it in the uncommitted `p1a.md` (TL3 overrides now need the store in §3.8 and AC-9), but the committed text at 1ef278f still has it. Findings 2–4 are still open in the working tree: `p1b.md` and `p1c.md` are unchanged, and the `p1a.md` edits touch only the AC-9 and §3.8 rows.
- **Packs:** the `## Review` sections of the profile packs `ci-cd`, `go`, `iac` and `python` were read. No pack's `detect.files` matches the 11 changed Markdown files, so `failure-modes.md` and `_generic.md` applied.
  - **Domain:** `ticketboat` was loaded. None of its invariants (sales, inventory, money, staging, Flyway) fits this generic hub, so none applied.
  - **House rules:** none.
  - **Graph:** none.
- **Read:** every changed file was read at 1ef278f with `git show`: the three plans and all eight review files.
  - **Roadmap (at 1ef278f):** §5 ACs, §5.19 matrix, §6.2–6.5, §6.10, §6.21, §9 P1, and threat model T3.
  - **Cited code (at 1ef278f):** `detect-stack.py`, `session-init.sh`, `project-profile/SKILL.md`, `argus/SKILL.md`, `project-manager.md`, `argus.md` (command and agent), `test-runner.md`, `implementer.md`, `manual-test.md`, `argus-scan.md`, `argus-bundle.sh`, `build-plugin.sh`, `install.sh`, `test-all.sh`, `check.yml`, `workflow-config.example.yml`. Every spot-checked citation matches.
- **Prior reconciliation:** `prior.md` (r8) had no open ids, and none of a663546-1…-22 is reopened.
  - 1ef278f-1 is a new scenario next to a663546-2. That finding's case (the target folder itself outside git) stays fixed. The rule "TL3 overrides are always trusted" survived its fix.
  - **Ownership check:** the plans' "Review:" lines cover ids 1–22. The commit message's "all 22 fixed, final pass clean" matches r8.
- **AC (roadmap P1 plus cross-cutting, 16):**
  - Met: R-AC-13, 14 (benchmark probes moved to P2 by D29, flagged in PF-5), 15, 25, 26, 27, 42, 44, 46, 47, 48, 49, 57, 66.
  - Not met: R-AC-43 (the critical tier's table is incomplete, finding 2) and R-AC-61 (the TL3 override channel, finding 1).
- **Severity:** 1ef278f-1 would be critical in code (the threat model rates T3 Critical). As a plan it's important.
- **Below the bar (notes, not findings):**
  - **Preference changes do invalidate evidence.** P1a §3.6 says they don't, but `.workflow/config.yml` stays in the full fingerprint (G6–G8), and P1c's PF-8 drift exclusions omit it. A mid-run config edit therefore makes evidence stale and also asks for `adopt_baseline`.
  - **Rev-mode fingerprint.** P1b's rev mode says "steps 2, 5", and step 2 drops files that are missing from the working tree. In P1 this reaches no gate, because the project-manager always uses `--working-tree`.
  - **Runtime config inputs.** P1c's runtime CLI has no `--workspace` (P1a AC-7 requires it for config consumers), and the manifest doesn't persist TL5 `--set` options. In P1, later resolves only differ in preferences or produce a one-time policy-drift event.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r2.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r3.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r4.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r5.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r6.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r7.md", "docs/reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r8.md"],
 "domain": "ticketboat",
 "ac": {"met": 14, "not_met": 2, "not_visible": 0},
 "findings": [
  {"id": "1ef278f-1", "severity": "important", "category": "security", "family": "FM-13", "title": "A non-git workspace above a nested repo is TL3, so its committed commands overrides skip the trust store", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 229, "new": true},
  {"id": "1ef278f-2", "severity": "important", "category": "correctness", "family": "FM-10", "title": "Critical-tier scan has no output kind or gate, so finish scan can't validate and its findings never block", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 197, "new": true},
  {"id": "1ef278f-3", "severity": "consider", "category": "correctness", "family": "FM-17", "title": "The banner either flags re-detected script commands as untrusted forever, or never counts a forged one", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 237, "new": true},
  {"id": "1ef278f-4", "severity": "consider", "category": "reliability", "family": "FM-07", "title": "init over a crashed run opens a second run: admit hits E_RUN_AMBIGUOUS and reconciliation is skipped", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 118, "new": true}
 ],
 "not_reviewed": [],
 "pack_suggestions": [
  {"stack": "markdown-plans", "family": "FM-13", "signal": "A trust level granted by folder position (a non-git ancestor) treated as 'the user's own', when downloaded content can occupy that position"},
  {"stack": "markdown-plans", "family": "FM-10", "signal": "A tier table requires a step whose output kind, transition rows and gate are defined in no sibling plan"}
 ]}
```

</details>
