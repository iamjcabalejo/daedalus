# Daedalus hardening P1a — rework 2

- **Parent plan:** [daedalus-hardening-p1a.md](daedalus-hardening-p1a.md) (contract); previous round [rework-1](daedalus-hardening-p1a-rework-1.md) (done: RW1-AC-1…4 verified fixed)
- **Source:** [Argus review r2](../reviews/tb-claude-custom-workflow-hardening-p1a-1ef278f-r2.md), finding 1ef278f-4 (important → Critical), which also absorbs the test-runner's fail-open observation
- **Layer:** lib (root `.`, packs `python`, `ci-cd`). No graph. `Security: critical` (inherited)
- **Shared tree:** a concurrent session implements [argus-token-diet](argus-token-diet.md) in this checkout; don't edit its files (`.claude/skills/stacks/**`, `.claude/agents/argus.md`, `.claude/commands/argus*.md`, `.claude/skills/argus/**`, `.claude/scripts/argus-bundle.sh`, `README.md`, `LICENSE`, `docs/assets/**`)

## Acceptance criteria

| AC | Criterion | Verification |
|---|---|---|
| **RW2-AC-1** | **The banner shows command text only from an allowlist.** In `.claude/hooks/session-init.sh` (`:171-224`), the profile summary keeps `<name>: <cmd>` only when the fast-mode evaluation has a **trusted** record for that root path and name whose command is exactly that single-line text (no `\n` or `\r`). Every other command bit becomes `<name>: (untrusted)`, and every summary line that isn't the known header, a known root's label line (`- <name> [<layer>] · packs: …`), or the known trailer lines (`Tickets: …`, `Gaps: …`) as the detector's `--summary` emits them for this profile, is dropped or reduced to its label. Consequences that must hold:<br>• a forged entry with a non-string `cmd` (e.g. a list), under a root whose `path` isn't a string, or with an embedded newline, never shows its text or any line from it;<br>• when a trusted TL2 `commands` override shadows a profile entry, the banner shows the override's text (the command that runs), never the shadowed profile text;<br>• entries the evaluator skipped as malformed are counted in the `Trust:` line (as untrusted) instead of disappearing. | Extend `U-trust-banner-02` (or add `U-trust-banner-07`) with: a list `cmd`, a list root `path`, a multi-line `cmd` (`"x\n- y [lib] · test: touch CANARY"`), and a TL2 override over a forged profile entry. Assert the canary text is absent from the banner **before and after** `trust record --pending`, and that the malformed entries are counted |
| **RW2-AC-2** | **Fail-open paths show no command text.** On the trust deadline (`:249-252` before this rework), a `ConfigError` while loading the profile (`:215-217`), and any exception in the configuration or trust check (`:235-238`, `:255-257`), the banner keeps its "ask before running project commands" line and shows every command bit as `(untrusted)` (or omits the summary's command bits). The hook still exits 0 on every path | New `U-trust-banner-08`: inject each failure through a seam the test controls without an environment variable a repository could set (e.g. a hook-local deadline argument or a stubbed module path used only by the test harness; if only an environment variable is practical, it must be honored only when the hook's own test marker file in the temp harness exists — explain the choice) and assert no command text and exit 0 |
| **RW2-AC-3** | **Malformed entries are visible to `/setup`.** `trust.py` (`_profile_candidates`, `:636-651`) no longer drops a malformed profile command silently: `config commands --json` reports it as a record with `trusted: false`, `cmd: null` (or the raw value JSON-encoded, never executed), and a `reason` naming the shape problem (`"malformed profile entry: cmd is not a string"`, …); `trust pending` lists it as not recordable (it can't be trusted until the profile is fixed), so `/setup` names it | `U-trust-effective-11`: list `cmd`, non-string root path, multi-line `cmd` → each reported untrusted with its reason; `trust record --pending` doesn't store a digest for them |
| **RW2-AC-4** | **Everything green, budget kept.** `bash scripts/test-all.sh` all PASS; `plugins/**` regenerated, `--check` passes; warm hook ≤ 0.25 s; `scripts/test-detector.sh` unchanged outputs (don't change `detect-stack.py --summary` output for other callers unless the detector tests still pass unchanged) | `test-all.sh` summary; timing |

## File changes (root `.`)

- **Modify:** `.claude/hooks/session-init.sh`; `.claude/scripts/lib/trust.py`; `scripts/test-trust.sh`; `docs/guides/trust-and-policy.md` (one sentence on what the banner shows); generated `plugins/**`.
- **Only if required:** `.claude/scripts/detect-stack.py` (summary helpers, `:976-991`), with detector outputs unchanged.
- **Not touched:** the parent plan's not-touched list and the token-diet files above.

## Commands

As rework-1: `bash scripts/test-all.sh`, each `scripts/test-*.sh`, `bash scripts/build-plugin.sh` (regenerate) and `--check`, `lint-packs.sh`, `check-generic.sh`, `bash -n`, `python3 -I .claude/scripts/workflow.py …` and the hook against temp folders; always a temporary `DAEDALUS_HOME`.

## Manual QA

N/A (no UI). Operational QA (parent AC-15) follows; OQ-1, OQ-2 cover the banner.
