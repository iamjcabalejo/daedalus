## Argus review

The rework closes 1ef278f-1, -2 and -3 (stored digests verify detected entries in fast mode, TL3 overrides need the store, subfolder sessions read the top-level profile) and all 10 test-all checks pass, but the banner still prints forged command text in other shapes, so AC-12 holds only for its fixtures; AC-15 not run. Not reviewed line by line: README.md, ARCHITECTURE.md; no stack pack: bash.

**Done well:** `_reproduced_records` in `.claude/scripts/lib/trust.py` stores re-detected `script`/`derived` digests on `trust record --pending` without touching the set digest. `U-trust-banner-04` proves both directions: an empty-set `/setup` brings `npm test` back to the banner, and a forged `script` in a fresh profile is hidden and counted again.

**Since the last revision:** 3 earlier findings verified fixed.

**4. [important · security] Banner still shows forged command text for multi-line, malformed or shadowed profile entries**
`hide_untrusted` hides only bits whose record `needs_trust`. Reproduced: a forged `test` with `cmd: ["touch X"]`, or under a root whose `path` isn't a string, is skipped by `_profile_candidates`, so it shows verbatim, uncounted, absent from `trust pending`, and after `/setup` with no Trust line. A `cmd` holding `\n- x [lib] · test: touch X` leaks its second line.
- Fix: Build the redaction as an allowlist from the evaluated records. Keep `<name>: <cmd>` only when a trusted record for that root path and name has exactly that single-line text. Every other command bit, and any line that isn't a known root's label, becomes `(untrusted)`. This also covers a trusted TL2 `commands` override: today the banner prints the forged profile text it shadows (reproduced) while `config commands` runs `make test`. On the deadline, ConfigError and exception paths, show no command text. Those paths already add an "ask before running" line, so they aren't material on their own. Regression test: extend `U-trust-banner-02` with a list `cmd`, a list root `path`, a multi-line `cmd` and a TL2 override over a forged entry, and assert CANARY is absent before and after `trust record --pending`.
- Where: `.claude/hooks/session-init.sh:171-224`; `.claude/scripts/lib/trust.py:636-651`; `.claude/scripts/detect-stack.py:976-991`
- Cost: Entries the hook can't verify lose their text until `/setup`. Root names and `gaps` stay free text, and a hostile repo can also ship a CLAUDE.md, so the banner remains defense in depth until P2's guard.
<!-- argus-finding:1ef278f-4 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p1a:1ef278fb64e45e66238ca8402ec88d9546c9cc2c+worktree-r2 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: generic hub, as in prior hub reviews); tickets.system `linear` from `~/.claude/argus.yml` (TL2, resolved with `workflow.py config resolve`), not used: the plans are the ticket (parent AC-1…AC-15 with AC-9 and §3.8 amended; rework-1 RW1-AC-1…4).
- **Scope:** second pass over the uncommitted working tree on `feat/hardening-p1a` over `1ef278f` (temporary-index diff, 133 files, ~9,100 lines). `prior.md` held [the first review](tb-claude-custom-workflow-hardening-p1a-1ef278f.md). A concurrent session is implementing `docs/plans/argus-token-diet.md` in the same tree: its-only files were excluded (`.claude/skills/stacks/**`, `.claude/agents/argus.md`, `.claude/scripts/argus-bundle.sh`, `LICENSE`, `docs/assets/**`), and its edits in shared files were out of scope. Also excluded: `plugins/**` (generated; `--check` passes), `audit.log`, `docs/reviews/**`.
- **Prior findings:** 1ef278f-1 fixed (`U-trust-banner-02`, `-04`, `-05`); 1ef278f-2 fixed (`U-trust-banner-03`, `-06`); 1ef278f-3 fixed (`PT-trust-workspace-archive-01`; `SELF_TRUSTED_LEVELS = ("TL1", "TL2")`). Fixed 3 · answered 0 · open 0.
- **AC:** AC-1…AC-11, AC-13, AC-14, RW1-AC-1…4 met; AC-12 not met (finding 4); AC-15 not visible (operational QA not run).
- **Test runs by the reviewer:** `test-all.sh` 10/10 PASS (`test-trust.sh` 45 OK); `build-plugin.sh --check` 95 files, 0 out of date; warm hook ≈ 0.19 s. The test-runner's fail-open flag (raw text on deadline / config-error / exception paths) is folded into finding 4's fix.
- **Severity mapping (project-manager):** finding 4 → Critical.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": [".claude/hooks/session-init.sh", "scripts/test-all.sh", "scripts/test-config.sh", "scripts/test-trust.sh", "scripts/build-plugin.sh", "**/*.md (prompts, docs)", "scripts/fixtures/**", "templates/workflow-config.example.yml", "overlays/_template/config.yml"],
 "domain": "none",
 "ac": {"met": 17, "not_met": 1, "not_visible": 1},
 "findings": [{"id": "1ef278f-4", "severity": "important", "category": "security", "family": "FM-13", "title": "Banner still shows forged command text for multi-line, malformed or shadowed profile entries", "path": ".claude/hooks/session-init.sh", "line": 171, "new": true}],
 "not_reviewed": ["README.md", "ARCHITECTURE.md", "scripts/test-config.sh (run, not read)", ".claude/scripts/lib/wfconfig.py outside _workspace_level/discover/load_profile (unchanged by the rework; read in the first pass)", "token-diet-only files excluded by the caller"],
 "pack_suggestions": [
  {"stack": "python", "family": "FM-13", "signal": "Output redaction built as a denylist over evaluated records while the text is rendered from the raw input: entries the evaluator skips (wrong type, embedded newline, shadowed by a trusted override) pass through verbatim"},
  {"stack": "bash", "family": "FM-08", "signal": "Hook wraps an embedded interpreter in `2>/dev/null || exit 0`: check that every fail-open branch still emits its warning line and withholds unverified content"}]}
```

</details>
