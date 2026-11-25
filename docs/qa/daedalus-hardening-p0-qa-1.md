# Operational QA: Daedalus hardening P0 (run 1)

- **Plan:** [daedalus-hardening-p0.md](../plans/daedalus-hardening-p0.md), AC-13 (R-AC-66)
- **Date:** 2026-11-26 · **Host:** Claude Code 2.1.325, macOS · **Installs:** script and plugin
- **Scope:** P0b's live probe runs. The benchmark's end-to-end check is deferred to P2 (D29).
- **Verdict:** **FAIL** (redaction, row 3; corrected after review) **with one BLOCKED item** (F5 needs the maintainer in an interactive session). Superseded by [run 2](daedalus-hardening-p0-qa-2.md).

| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | The probes run end to end on both installs | **PASS** | Rerun of `--case all --install both`: exit 0; 65 runs (52 confirmed, 5 contradicted, 8 inconclusive); K1 and K2 docs-only (no Cursor or Codex CLI). Cost $0.66 (total P0b spend $1.31 of the $15 budget). Results: `scripts/probes/results/claude-2.1.325.json` |
| 2 | Cleanup and the isolation check (AC-1) | **PASS** | The harness publishes only after its post-run isolation check (hub `git status`, user settings, plugin registries and plugin list compared with a snapshot) and the leak scan both pass. Both live runs published. Afterwards the hub working tree shows only the intended changes (the published `fixtures/` and `results/`, plus this round's harness and doc edits) |
| 3 | Redaction review (AC-3) | **FAIL** (corrected after review [39cf56d-1](../reviews/tb-claude-custom-workflow-hardening-p0a-39cf56d-p0b.md): every fixture's `payload.scratchpad_dir` held the operator's dash-encoded temp folder and uid, which this check and the leak scan missed; fixed and re-checked in [run 2](daedalus-hardening-p0-qa-2.md)). The original wording follows | 474 fixture files. A spot check of 3 random files shows only placeholders (`<SESSION-1>`, `<HOME>`, `<PROJECT>`, `<WORKSPACE>`, `<REDACTED:prompt>`). A grep for personal and temp paths, emails, usernames and UUIDs over the fixtures and results: no hits. `test-probes.sh` (129 tests, including the committed-fixture leak scan) passes. The findings and threat-model documents mention only the generic `/private/var/…` form |
| 4 | Interactive `ask` (F5) | **BLOCKED** (needs the maintainer) | Needs a human at an interactive session. The steps are below |
| 5 | One benchmark task per arm end to end | **N/A**: deferred to P2 (D29) | — |

**Process notes, recorded for the findings:**
- **T0 found two host differences, both fixed in the harness before the clean rerun:**
  - `--max-turns` is accepted but hidden from `--help`; it's now confirmed with a no-model parse check.
  - Project `permissions.allow` is ignored in untrusted folders under `-p`; the rules are now passed with `--allowedTools`.
- **The first live run (2026-11-25 17:04 UTC) is superseded.** Every run in it ignored the project allow rules, so its results were replaced in full by the rerun (17:35 UTC).

## F5: interactive `ask` (maintainer steps)

1. In a throwaway folder (not a real project), create `.claude/settings.json` with a `PreToolUse` hook on `Bash` that prints `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "F5 probe"}}` and exits 0.
2. Start `claude` interactively there. Ask it to run `touch marker-F5`.
   - **Expected:** a permission prompt naming the hook's reason.
   - Approve it, and confirm `marker-F5` exists.
3. Repeat with a subagent: "use a general-purpose agent to run `touch marker-F5b`".
   - Note whether the prompt appears in the main session and names the subagent.
4. Repeat with a background subagent.
   - Note where the prompt surfaces.
5. Record the three outcomes in the findings document (§2, F5 row) and set this item to PASS or FAIL.
