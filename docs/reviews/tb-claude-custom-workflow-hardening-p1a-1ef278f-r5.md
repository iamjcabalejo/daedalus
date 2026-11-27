## Argus review

Rework-4 does what RW4-AC-1…3 ask. On the plugin install every banner line now names `/daedalus:setup`. The companion's Markdown prefixes main-plugin commands through a bounded rewrite, and the main plugin's output stays byte-identical. Both new tests fail when their change is reverted. Not covered by a stack pack: bash.

**Done well:** `U-build-companion-names-01` runs the real `build-plugin.sh --out`. It then rebuilds in the exec'd namespace with `name_main_commands` stubbed to identity, and requires `plugins/daedalus/**` and `marketplace.json` to be byte-identical and only companion `.md` files to change. That proves "main plugin unchanged" by comparing builds rather than by checking strings. Reverting `render` in a scratch copy makes it fail with `'commands/manual-test.md' not found in []`.

No material findings. Architecture, security, performance, cost, reliability and correctness all look sound for this change.

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p1a:1ef278fb64e45e66238ca8402ec88d9546c9cc2c+worktree-r5 -->

<details><summary>Run notes</summary>

- **Config:** domain `none`. There is no ticket; the contract is [rework-4](../plans/daedalus-hardening-p1a-rework-4.md) (RW4-AC-1…3, with AC-1 amended to cover `FAILED`/`TIMED_OUT`), from observations 1 and 2 of [QA run 1](../qa/daedalus-hardening-p1a-qa-1.md). Packs loaded (`## Review`): `ci-cd`, `go`, `iac`, `python`. Bash has no pack, so the Python inside the hook and the build script was read with the python pack.
- **Scope:** only the rework-4 delta: 384 lines over 7 files, from the working tree before rework-4 to after it. Read in full: `.claude/hooks/session-init.sh` and `scripts/build-plugin.sh`. Read in the test files: the new tests and the helpers they use (`banner`, `summary_lines`, `install_copy`, `hook_summary_functions`, `build_plugin_functions`).
- **Prior findings:** [r4](tb-claude-custom-workflow-hardening-p1a-1ef278f-r4.md) had none. 1ef278f-1…-5 stay fixed. Rework-4 changes only strings in the hook, and U-trust-banner-07…09 still pass.
- **RW4 AC tally:** 3 met, 0 not met, 0 not visible.
  - **RW4-AC-1 met.** `render_summary` (`session-init.sh:249`) and `FAILED`/`TIMED_OUT` (`:63-64`) use `SETUP`, which is bound at `:39` before both. The script-install contract line (`:45`) and the detector's `--summary` are unchanged.
  - **RW4-AC-2 met.** `bare_commands` (`build-plugin.sh:95-100`) is applied only when `plugin == QA` (`:143-147`). The generated `manual-test.md` has five prefixed mentions (`/daedalus:setup` once, `/daedalus:project-manager` four times) and no bare main-plugin name left.
  - **RW4-AC-3 met.** Reviewer runs: test-trust 57/57, test-config 78/78, `--check` 0 of 97 out of date, warm hook ≤ 0.25 s. The detector is not in the diff. Project-manager's run: `test-all.sh` 10/10 PASS.
- **Regex boundaries:** 37 strings probed.
  - **Rewritten, correctly:** frontmatter values, lines in code fences, `` `/setup` ``, `(/setup)`, `"/setup"`, `| /setup |`, `/setup...`, `/setup:` at the end of a line.
  - **Left alone, correctly:** paths (`docs/setup.md`, `x/setup`, `~/setup`), URLs (`https://example.com/setup`), names that already have the prefix, longer names (`/argus-scan-x`).
  - **Missed, which leaves today's bare name:** `'/setup'`, `/setup?`, `**/setup**`, `[/setup]`, curly quotes, `/setup’s`.
  - **Possible false positives (not raised):** anything shaped like a command, such as a site-root link `[docs](/setup)`, `GET /setup`, `cd /scaffold`, or a web route written as `` `/setup` ``. None exists in the companion today, and the regenerated `plugins/` diff would show one if it appeared.
- **Frontmatter `description`:** rewriting it is right. The `/` menu shows it for `/daedalus-qa:manual-test`, and `/daedalus:project-manager` is the name a plugin user types. The rewrite inserts `daedalus:` followed by a name character, never `: `, so it can't add a YAML key. The `description` line parses as YAML before and after. The full frontmatter fails strict YAML in both the source and the output, because of `argument-hint: [plan-path] [AC-n ...] | …`; that predates this change.
- **Main plugin unchanged:** `render` returns `rewrite(text, MAIN)` unchanged for the main plugin; the byte comparison above; the delta's only main-plugin change is the byte copy of the hook.
- **Hook fail-open and budget:** `banner_summary` (`:268-275`) compares against the same `FAILED`/`TIMED_OUT` constants, so pass-through and the `FAILED` fallback behave as before. The change adds no I/O and no exception path. Warm runs took 0.189–0.193 s in both script and plugin mode and exited 0. The plugin banner reads `unconfirmed: run /daedalus:setup to confirm` and `…or run /daedalus:setup.`.
- **Tests fail without the change** (each mutation in its own scratch copy): hook header reverted → U-trust-banner-10 fails on the header; only `FAILED`/`TIMED_OUT` reverted → it fails with `['…detection failed; run /setup.'] != ['…run /daedalus:setup.']` (`TIMED_OUT` is asserted through `hook_summary_functions(setup)`, the exec'd source lines, not a real 8 s run); `render` reverted → U-build-companion-names-01 fails.
- **Weighed, not raised:**
  1. **The companion's own `/manual-test --login` stays bare** (`plugins/daedalus-qa/commands/manual-test.md:64`). RW4-AC-2 excludes the companion's own commands explicitly. UX only.
  2. **The QA plugin's byte-copied Python still says `/setup`.** `lib/trust.py` and `wfconfig.py` say "rerun /setup" in trust-store and profile error `fix` texts (for example `trust.py:284`, `wfconfig.py:1599`). `config commands --json` carries them as `store.error.fix`, so a `/daedalus-qa:manual-test` run on a broken trust store could relay a bare `/setup`. Rare error path, outside the Markdown-only RW4-AC-2; the main plugin has the same text.
  3. **The detector's own `--summary` header still says `/setup`,** as the plan requires. The hook never passes it through: it re-renders it, or replaces it with `FAILED`/`NOT_SHOWN`.
- **Reviewer runs:** all in scratch copies under the session scratchpad, with a temporary `DAEDALUS_HOME` and `HOME`. Nothing touched the real `~/.workflow` or `~/.claude`.
- **Severity mapping (project-manager):** no findings and no Critical items, so the interactive OQ-7/OQ-8 of AC-15 come next.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": [".claude/hooks/session-init.sh", "plugins/daedalus/scripts/session-init.sh", "scripts/build-plugin.sh", "scripts/test-config.sh", "scripts/test-trust.sh"],
 "domain": "none",
 "ac": {"met": 3, "not_met": 0, "not_visible": 0},
 "findings": [],
 "not_reviewed": ["scripts/test-trust.sh (outside U-trust-banner-10 and its helpers)", "scripts/test-config.sh (outside U-build-companion-names-01 and build_plugin_functions)", "scripts/test-all.sh (not re-run by the reviewer; project-manager's 10/10)"],
 "pack_suggestions": [{"stack": "bash", "family": "FM-11", "signal": "A regex that rewrites bare `/command` names in generated Markdown, with only start/whitespace/backtick/paren/quote as its left boundary, also rewrites site-root link targets `](/name)`, HTTP lines `GET /name` and shell `cd /name`; exclude `](` and verb/command contexts when the docs can contain routes."}]}
```

</details>
