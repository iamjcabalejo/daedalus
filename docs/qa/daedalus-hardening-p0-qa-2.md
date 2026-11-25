# Operational QA: Daedalus hardening P0 (run 2)

- **Plan:** [daedalus-hardening-p0.md](../plans/daedalus-hardening-p0.md), AC-13 (R-AC-66) · **Previous:** [run 1](daedalus-hardening-p0-qa-1.md) (FAIL on redaction)
- **Date:** 2026-11-26 · **Host:** Claude Code 2.1.325, macOS · **Installs:** script and plugin
- **Why a second run:** the [P0b review](../reviews/tb-claude-custom-workflow-hardening-p0a-39cf56d-p0b.md) found that every published fixture leaked the operator's dash-encoded temp folder and uid in `payload.scratchpad_dir` (finding 39cf56d-1). The redaction rules and the leak scanner were extended, and the 474 published fixtures were re-redacted, with no new model runs.
- **Verdict:** **PASS with one BLOCKED item** (F5, which needs the maintainer). No FAIL.

| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | The probes run end to end on both installs | **PASS** (unchanged from run 1) | 65 runs: 52 confirmed, 5 contradicted, 8 inconclusive. K1 and K2 docs-only. Statuses unchanged by the re-redaction |
| 2 | Cleanup and the isolation check (AC-1) | **PASS** (unchanged from run 1) | Published only after the post-run isolation check and the leak scan |
| 3 | Redaction review (AC-3) | **PASS** | `redact.py rescan --fix` rewrote only `payload.scratchpad_dir` in the 474 fixtures (now `<TMP>/<PROJECT>/<SESSION-n>/scratchpad`); a second pass changed nothing. The extended leak scan (`encoded-temp-path`, `claude-temp-root`, `-Users-`, `-home-`) over fixtures, results and testdata finds 0. A separate search of all 492 files to be committed for the machine's real identifiers (per-user temp segment, `claude-<uid>`, username) finds 0. `test-probes.sh` passes (141 tests); `check-generic.sh` reports 0 problems |
| 4 | Interactive `ask` (F5) | **BLOCKED** (needs the maintainer) | Steps in [run 1](daedalus-hardening-p0-qa-1.md#f5-interactive-ask-maintainer-steps) |
| 5 | One benchmark task per arm end to end | **N/A**: deferred to P2 (D29) | — |
