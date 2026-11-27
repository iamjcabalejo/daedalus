## Argus review

The rework closes 1ef278f-4. The hook now renders the summary from the evaluated profile and shows command text only for trusted single-line records. It counts malformed entries and shows no command text on fail-open paths, and test-trust passes 52/52. One trust-display gap remains (consider), and AC-15 has not run. Not reviewed line by line: README.md, ARCHITECTURE.md. Not covered by a stack pack: bash.

**Done well:** `U-trust-banner-08_nothing_a_repository_controls_reaches_the_seam` points every steering environment variable and repository-shipped module at a stub that would fail open, and proves the real hook never imports it. It then runs the stub as itself as a control, so the check can't pass vacuously.

**Since the last revision:** 1 earlier finding verified fixed.

**5. [consider · security] Escape and bidi characters let a committed command be trusted while `trust pending` hides part of it**
`_single_line` rejects only line breaks, so a committed `cmd` such as `npm test\x1b[8m && touch X\x1b[28m` can be recorded, and so can a TL4 override written with `\u001b`. Text-mode `trust pending` prints it raw, so a terminal shows only `npm test`. The user then runs the `Trust them all` line it prints, and `config commands` reports the command `trusted` and not `unsafe`. Reproduced with `\x1b[8m` and with U+202E.
- Fix: Reject the characters the hook already hides (`HIDDEN_CATEGORIES`: Cc, Cf, Zl, Zp and the rest) in both channels, the same way multi-line text is rejected now. Move the tuple into `lib/` and import it in the hook. Such a profile entry becomes malformed; such a config override becomes untrusted and not recordable. Regression test: extend `U-trust-effective-11` with `\x1b[8m` and U+202E profile commands and a TL4 override written with `\u001b`, and assert that `trust record --pending` stores no digest for any of them.
- Where: `.claude/scripts/lib/trust.py:660-680`; `.claude/scripts/lib/trust.py:712-718`; `.claude/scripts/lib/trust.py:983-986`
- Cost: A command containing a tab or another control character can't be trusted until it is rewritten; the banner already hides such text. This is only consider because `/setup` reads `--json`, which escapes control characters. It would be important if a raw U+202E in that JSON (`ensure_ascii=False`) can display deceptively when the model relays it.
<!-- argus-finding:1ef278f-5 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p1a:1ef278fb64e45e66238ca8402ec88d9546c9cc2c+worktree-r3 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: generic hub, as in prior hub reviews); tickets.system `linear` from `~/.claude/argus.yml` (TL2, resolved with `workflow.py config resolve`), not used: the plans are the ticket (parent AC-1…AC-15; rework-1; rework-2 RW2-AC-1…4).
- **Scope:** third pass over the uncommitted working tree on `feat/hardening-p1a` over `1ef278f` (temporary-index diff, ~9,600 lines). `prior.md` held [the second review](tb-claude-custom-workflow-hardening-p1a-1ef278f-r2.md). A concurrent session implements `docs/plans/argus-token-diet.md` in the same tree: its-only files excluded, its edits in shared files out of scope. Also excluded: `plugins/**`, `audit.log`, `docs/reviews/**`.
- **Prior findings:** 1ef278f-4 fixed (list `cmd`, list root path, multi-line `cmd`, TL2 override over a forged entry, deadline / ConfigError / exception paths; `U-trust-banner-07`, `-08`, `U-trust-effective-11`). Overall: 1ef278f-1…-4 fixed · answered 0 · open 0.
- **AC:** 18 met, 0 not met; AC-15 not visible (operational QA not run).
- **Reviewer runs:** `test-trust.sh` 52/52 in a scratch copy; `test-config.sh` 76/77 there (the one failure is the copy having no `.git` for `build-plugin`'s `git ls-files`, not the code; the project-manager's run in the real checkout passed 77/77 and `build-plugin.sh --check` 0 out of date). Warm hook 0.19–0.22 s; Python 3.8 grammar OK.
- **Severity mapping (project-manager):** finding 5 → Suggestion. No Critical items.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": [".claude/hooks/session-init.sh", "plugins/daedalus/scripts/session-init.sh", "scripts/test-trust.sh", "scripts/test-config.sh", "scripts/test-all.sh", "scripts/build-plugin.sh"],
 "domain": "none",
 "ac": {"met": 18, "not_met": 0, "not_visible": 1},
 "findings": [{"id": "1ef278f-5", "severity": "consider", "category": "security", "family": "FM-13", "title": "Escape and bidi characters let a committed command be trusted while `trust pending` hides part of it", "path": ".claude/scripts/lib/trust.py", "line": 660, "new": true}],
 "not_reviewed": ["README.md", "ARCHITECTURE.md", ".claude/scripts/lib/wfconfig.py (not re-read this pass)", "scripts/test-config.sh (run, not re-read)", "scripts/fixtures/**", "token-diet files (out of scope)"],
 "pack_suggestions": [{"stack": "_generic", "family": "FM-13", "signal": "Text shown to a human for a trust or approval decision is printed raw: escape (ESC) and bidi characters can hide part of what is approved. Reject or escape C0/C1/Cf characters before display and before recording."},
                      {"stack": "bash", "family": "FM-08", "signal": "Hook wraps Python in a heredoc with `2>/dev/null || exit 0`, so an uncaught exception outside its own try blocks silently drops all hook output. Keep rendering inside the guarded path."}]}
```

</details>
