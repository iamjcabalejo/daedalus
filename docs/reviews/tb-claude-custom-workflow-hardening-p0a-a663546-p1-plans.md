## Argus review

The plans map every assigned roadmap AC and their load-bearing code citations check out, but they aren't implementable without guessing yet (ticket AC-2 and AC-4 met; AC-1, AC-3, AC-5, AC-6 not): P1a's F1 fix misses sibling prompts and non-git folders, and P1c's lease, BLOCKED-test and trivial-tier rules stall runs or skip review. Not covered by a stack pack: Markdown plans.

**Done well:** P1a's PF-2 is a real catch. `session-init.sh:12` runs `python3 -` with the project as its working directory, so a repository `json.py` would run inside Daedalus' hook on every session start. The `python3 -I` fix, backed by the `U-config-consumers-01` grep, is the right shape.

**1. [important · security] Committed untrusted commands still run unasked through /test-gen, /scaffold and the always-on rules**
In P1, trust is prompt-followed, yet AC-13 rewires only `/project-manager`, implementer, test-runner and project-profile. `/test-gen`, `/scaffold`, `/code-cleanup`, the test-strategy skill, `stack-knowledge.md:16` and `CLAUDE.md:11` (an installed always-on rule) still say `user` and confirmed commands run unasked, so AC-12's canary still runs through `/test-gen`.
- Fix: add those files to T11/AC-13 and the §6 Modify list, along with the `session-init.sh:27` and `:38` contract strings and `README.md:12`. Widen `U-trust-consumers-01` to grep all of `.claude/**` plus `CLAUDE.md` for the confidence-table rule, and run `PT-trust-profile-01` through `/test-gen` too.
- Where: `docs/plans/daedalus-hardening-p1a.md:62`; `docs/plans/daedalus-hardening-p1a.md:342-344`; `.claude/commands/test-gen.md:27`; `install.sh:56`
- Cost: about eight more prompt files edited in P1a.
<!-- argus-finding:a663546-1 -->

**2. [important · security] A project folder outside git is read as TL3, so its own committed `commands` overrides are trusted**
AC-2 demotes a workspace to TL4 only when it sits inside a git work tree, and §3.8 always trusts TL3 overrides. A ZIP-downloaded project, or a repo that `git` refuses for dubious ownership, has no work tree. Its committed `.workflow/config.yml` `commands` therefore land at TL3 and run unasked. §3.3 never says what TL4 is without git.
- Fix: allow TL3 only for a folder that is a strict ancestor of the target's top level. With no git top level, treat the project folder as TL4, with `repo_id` from `realpath` and `remote: null`. Treat any `git` error as "inside a work tree" (fail closed). Add a test: a non-git fixture with a config override must resolve untrusted.
- Where: `docs/plans/daedalus-hardening-p1a.md:51`; `docs/plans/daedalus-hardening-p1a.md:110`; `docs/plans/daedalus-hardening-p1a.md:217`
- Cost: users outside git confirm their own overrides once with `/setup`.
<!-- argus-finding:a663546-2 -->

**3. [important · architecture] P1a and P1b are cleared to run in parallel, but they edit eight of the same files in one unisolated tree**
Both §12 sections say only `lib/__init__.py` and `test-all.sh` overlap. Both File changes lists also edit `commands/{argus,manual-test,feature-plan,apply-ticket}.md`, `agents/{implementer,test-runner}.md` and ARCHITECTURE §13, and both regenerate `plugins/**`. Two sessions in one checkout (there is no isolation before P3) overwrite each other, against roadmap §8.3's disjoint-files rule.
- Fix: run P1a, then P1b (or at least P1b's command, agent and doc edits after P1a merges). Alternatively, require separate worktrees with a stated merge order. Either way, correct both §12 lists.
- Where: `docs/plans/daedalus-hardening-p1a.md:406`; `docs/plans/daedalus-hardening-p1b.md:396`; `docs/plans/daedalus-hardening-p1a.md:8`
- Cost: up to P1b's 4–7 days added to the critical path if run sequentially, or one merge pass otherwise.
<!-- argus-finding:a663546-3 -->

**4. [important · reliability] On plugin installs, `/daedalus-qa:manual-test` has no runnable path to `artifacts.py qa-assemble`**
PF-6 relies on `build-plugin.sh:69`, but that rewrite turns a cross-plugin script reference into prose ("the daedalus plugin's scripts/…"), not a path. daedalus-qa ships no `scripts/`, and its `${CLAUDE_PLUGIN_ROOT}` points at the QA plugin. So `qa-assemble` can't run: P1c's `finish qa` gets no JSON, or the model hand-writes it, which PF-5 forbids.
- Fix: have `build-plugin.sh` copy `scripts/artifacts.py` and `scripts/lib/` into daedalus-qa, and reference `${CLAUDE_PLUGIN_ROOT}/scripts/artifacts.py`. Running OQ-5 on the plugin install proves it.
- Where: `docs/plans/daedalus-hardening-p1b.md:48`; `scripts/build-plugin.sh:69`
- Cost: a second copy of the library in the QA plugin, kept in step by `build-plugin.sh --check`.
<!-- argus-finding:a663546-4 -->

**5. [important · correctness] Rework AC ids collide with the main plan's, so G5 can pass with a rework AC untested**
P1b says P1c namespaces rework AC ids (`rework-1:AC-2`), but P1c never does. G5 and §3.9's reopening key on bare ids across all attached plans. Neither plan, nor P1c §3.12, defines the `ac_coverage`, verdict and pre-existing fields that G4 and G5 read. So a test for the main plan's AC-1 satisfies rework AC-1, and `complete` returns ok.
- Fix: P1c defines `<plan-slug>:AC-n` ids for every attached plan and passes them in `admit test`. P1b's `test-report.schema.json` fixes `ac_coverage[{ac, tests[]}]`, `verdict` and `failures[{id, pre_existing}]`. List both in §3.12. Add a test: two plans each with an AC-1, only one covered, must give `E_COMPLETE_AC_UNCOVERED`.
- Where: `docs/plans/daedalus-hardening-p1b.md:147`; `docs/plans/daedalus-hardening-p1c.md:188`; `docs/plans/daedalus-hardening-p1c.md:242`; `docs/plans/daedalus-hardening-p1c.md:283-300`
- Cost: a short schema section in P1b.
<!-- argus-finding:a663546-5 -->

**6. [important · correctness] A plan declaring `Tier: trivial` skips review and QA, though roadmap §6.11 lets a declared tier only raise**
§3.5 sets the tier to max(declared, critical if security), with `auto` meaning standard. A fence that says `trivial` (P1b's grammar lets `/feature-plan` write it) makes `reviewing` and `qa` unreachable, and G1 then needs only implement and test. `/project-manager` then declares production ready with no Argus review, which 0.4.0 always ran. The deviation isn't named.
- Fix: in P1, use max(standard, declared, critical if security). Refuse a declared `trivial` with `E_UNSUPPORTED_IN_VERSION` until P3's classifier exists, and add an `SM-guard` case for it.
- Where: `docs/plans/daedalus-hardening-p1c.md:174`; `docs/plans/daedalus-hardening-p1c.md:170`; `docs/plans/daedalus-hardening-roadmap.md:1137`
- Cost: small changes pay for a review until P3.
<!-- argus-finding:a663546-6 -->

**7. [important · reliability] With no `claude` ancestor found, the stated fallback, every call after `init` is refused as a foreign lease**
§3.3 makes a caller the owner only when `host_pid` is alive and is its ancestor; anything else that isn't stale gets `E_RUN_LEASE_LIVE`. When the walk finds no `claude` ancestor (PF-1 and OQ-8 allow `null`), the next `admit` from the same session counts as foreign until the 30-minute TTL. `--force` needs a user confirmation on every call.
- Fix: make the lease token the proof of ownership. `init` and `resume` return it, and every mutating call takes `--lease <token>`, which the project-manager passes. Keep `host_pid` only as a staleness hint. Add a test: `host_pid: null` with the same token counts as own.
- Where: `docs/plans/daedalus-hardening-p1c.md:120-123`; `docs/plans/daedalus-hardening-p1c.md:439`
- Cost: one more argument on each runtime call in `project-manager.md`.
<!-- argus-finding:a663546-7 -->

**8. [important · reliability] After a BLOCKED (env) test, nothing can rerun `test`, so G2 loops between awaiting_human and verifying**
`block` lets the run move on. G2, checked before G7, sends `complete` to `awaiting_human` with resume to `verifying`, and no table row admits `test` from `verifying` or `awaiting_human`. Once the blocker clears, the only exits are a sham rework round or `cancel`. P1a makes this common: committed `user` test commands stay BLOCKED until `/setup`. 0.4.0 simply reran A2.
- Fix: route G2 to the blocked step's phase through a `rerun_blocked` decision, and allow `admit` of a BLOCKED step as attempt + 1. Add an SM test.
- Where: `docs/plans/daedalus-hardening-p1c.md:161`; `docs/plans/daedalus-hardening-p1c.md:164`; `docs/plans/daedalus-hardening-p1c.md:167`; `docs/plans/daedalus-hardening-p1c.md:185`
- Cost: one table edge and one decision option.
<!-- argus-finding:a663546-8 -->

**9. [consider · reliability] The TL1 symlink rule rejects `/etc/daedalus/policy.yml` on macOS, the very path OQ-9 uses**
§3.3 fails the managed check on any symlink in the path, and macOS's `/etc` is a symlink to `/private/etc`. OQ-9 on the maintainer's Mac then shows `warn` from TL2 and FAILs, or an implementer drops the symlink rule to make it pass. An admin who uses the Linux path on macOS gets organization policy silently ignored.
- Fix: check the owner and mode of every component of `realpath(path)`, so root-owned symlinks such as `/etc` pass. Or make OQ-9 use `/Library/Application Support/Daedalus/policy.yml` on macOS, and have `explain` warn when an `/etc` policy fails the check.
- Where: `docs/plans/daedalus-hardening-p1a.md:108`; `docs/plans/daedalus-hardening-p1a.md:386`
<!-- argus-finding:a663546-9 -->

**10. [consider · reliability] §3.3 ranks legacy `.argus.yml` above `.workflow/config.yml` at TL2 and TL3, contradicting AC-4**
Sources are listed lowest first, and TL2 and TL3 list `config.yml` before the legacy file, so `.argus.yml` would win at those levels. AC-4, TL4's own order and `argus/SKILL.md:39–41` all put `config.yml` above it. A user with both files gets a different `domain` or `review.severity` depending on which line the implementer follows.
- Fix: list `.argus.yml` first at TL2 and TL3, and add a `U-config-merge` case with both files at TL2.
- Where: `docs/plans/daedalus-hardening-p1a.md:109-110`; `docs/plans/daedalus-hardening-p1a.md:53`
<!-- argus-finding:a663546-10 -->

**11. [consider · reliability] TL3 discovery assumes `CLAUDE_PROJECT_DIR` reaches Bash-tool commands, an untagged platform fact**
`<workspace>` comes from `CLAUDE_PROJECT_DIR`, which §7 calls host-set. No [V] or [D] finding says commands run through the Bash tool get it, and that is where `/argus`, `/setup` and P1c's `init` call the resolver. If only hooks get it, the banner and the commands resolve TL3 differently, which is the F9 symptom. Ticket AC-3 asks for exactly this tag.
- Fix: tag it unverified in §3.10, and add an OQ step that prints it from the Bash tool. Until it's verified, have consumers pass `--workspace` explicitly.
- Where: `docs/plans/daedalus-hardening-p1a.md:110`; `docs/plans/daedalus-hardening-p1a.md:363`
- Cost: one OQ step.
<!-- argus-finding:a663546-11 -->

**12. [consider · reliability] "Running" is never defined, and A1 calls `start` only after the implementer has already returned**
Reconciliation acts on `running` steps, `step_admitted` and `step_started` are separate events, and §3.11 calls `start` only after the synchronous spawn returns (A2, B and D never call it). If `step_started` is what marks a step running, a crash mid-implementer leaves an admitted step that resume skips. Scenario 2 then surfaces as drift, while `CR-recover-02` still passes.
- Fix: state that `admit` opens the attempt as running and that `start` only binds `agent_id` and `agent_type`. Make `CR-recover-02` kill a role that was admitted but never started.
- Where: `docs/plans/daedalus-hardening-p1c.md:271`; `docs/plans/daedalus-hardening-p1c.md:60`; `docs/plans/daedalus-hardening-p1c.md:238`
<!-- argus-finding:a663546-12 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain pack in `~/.claude/argus.yml` targets product repos; this is the generic hub). `tickets.system` from `~/.claude/argus.yml`; no ticket key matched, so the ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** the three untracked plans `docs/plans/daedalus-hardening-p1{a,b,c}.md` only. The diff was built by hand (new-file diffs of the three plans), because `argus-bundle.sh --local` reviews only `merge-base..HEAD` (C-5); its original 772-file HEAD diff was the committed P0 history, out of scope.
- **AC:** met: AC-2 (every assigned roadmap AC mapped), AC-4 (inconclusive probes flagged). Not met: AC-1 (findings 1–8), AC-3 (finding 11), AC-5 (finding 5), AC-6 (finding 6).
- **Packs:** profile packs loaded (ci-cd, go, iac, python); none matches Markdown plans, so failure modes alone applied.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": ["docs/plans/daedalus-hardening-p1a.md", "docs/plans/daedalus-hardening-p1b.md", "docs/plans/daedalus-hardening-p1c.md"],
 "domain": "none",
 "ac": {"met": 2, "not_met": 4, "not_visible": 0},
 "findings": [
  {"id": "a663546-1", "severity": "important", "category": "security", "family": "FM-13", "title": "Committed untrusted commands still run unasked through /test-gen, /scaffold and the always-on rules", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 62, "new": true},
  {"id": "a663546-2", "severity": "important", "category": "security", "family": "FM-13", "title": "A project folder outside git is read as TL3, so its own committed commands overrides are trusted", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 51, "new": true},
  {"id": "a663546-3", "severity": "important", "category": "architecture", "family": "FM-19", "title": "P1a and P1b are cleared to run in parallel, but they edit eight of the same files in one unisolated tree", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 406, "new": true},
  {"id": "a663546-4", "severity": "important", "category": "reliability", "family": "FM-15", "title": "On plugin installs, /daedalus-qa:manual-test has no runnable path to artifacts.py qa-assemble", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 48, "new": true},
  {"id": "a663546-5", "severity": "important", "category": "correctness", "family": "FM-10", "title": "Rework AC ids collide with the main plan's, so G5 can pass with a rework AC untested", "path": "docs/plans/daedalus-hardening-p1b.md", "line": 147, "new": true},
  {"id": "a663546-6", "severity": "important", "category": "correctness", "family": "FM-18", "title": "A plan declaring Tier: trivial skips review and QA, though roadmap §6.11 lets a declared tier only raise", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 174, "new": true},
  {"id": "a663546-7", "severity": "important", "category": "reliability", "family": "FM-07", "title": "With no claude ancestor found, the stated fallback, every call after init is refused as a foreign lease", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 120, "new": true},
  {"id": "a663546-8", "severity": "important", "category": "reliability", "family": "FM-05", "title": "After a BLOCKED (env) test, nothing can rerun test, so G2 loops between awaiting_human and verifying", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 161, "new": true},
  {"id": "a663546-9", "severity": "consider", "category": "reliability", "family": "FM-15", "title": "The TL1 symlink rule rejects /etc/daedalus/policy.yml on macOS, the very path OQ-9 uses", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 108, "new": true},
  {"id": "a663546-10", "severity": "consider", "category": "reliability", "family": "FM-15", "title": "§3.3 ranks legacy .argus.yml above .workflow/config.yml at TL2 and TL3, contradicting AC-4", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 109, "new": true},
  {"id": "a663546-11", "severity": "consider", "category": "reliability", "family": "FM-15", "title": "TL3 discovery assumes CLAUDE_PROJECT_DIR reaches Bash-tool commands, an untagged platform fact", "path": "docs/plans/daedalus-hardening-p1a.md", "line": 110, "new": true},
  {"id": "a663546-12", "severity": "consider", "category": "reliability", "family": "FM-18", "title": "Running is never defined, and A1 calls start only after the implementer has already returned", "path": "docs/plans/daedalus-hardening-p1c.md", "line": 271, "new": true}
 ],
 "not_reviewed": [],
 "pack_suggestions": [
  {"stack": "design-plans", "family": "FM-19", "signal": "Sibling plans claim parallel safety while their File changes lists share files"},
  {"stack": "design-plans", "family": "FM-13", "signal": "A trust rule rewired in a named consumer list while sibling commands and always-on rules keep the old rule"}
 ]}
```

</details>
