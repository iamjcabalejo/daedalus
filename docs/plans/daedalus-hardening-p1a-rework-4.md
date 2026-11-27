# Daedalus hardening P1a — rework 4

- **Parent plan:** [daedalus-hardening-p1a.md](daedalus-hardening-p1a.md) (contract); previous rounds [rework-1](daedalus-hardening-p1a-rework-1.md), [rework-2](daedalus-hardening-p1a-rework-2.md), [rework-3](daedalus-hardening-p1a-rework-3.md) (done)
- **Source:** [operational QA run 1](../qa/daedalus-hardening-p1a-qa-1.md), observations 1 and 2 (Suggestions). **Scope decision (maintainer):** fix both before the interactive OQ-7/OQ-8. Observation 3 (plugin `project-manager` path lookup) is out of scope
- **Layer:** lib (root `.`, packs `python`, `ci-cd`). No graph
- **Shared tree:** don't edit the token-diet files (`.claude/skills/stacks/**`, `.claude/agents/argus.md`, `.claude/commands/argus*.md`, `.claude/skills/argus/**`, `.claude/scripts/argus-bundle.sh`, `.claude/scripts/lib/config_keys.py`, `README.md`, `LICENSE`, `docs/assets/**`)

## Problem

On the plugin install the setup command is `/daedalus:setup`, but two texts the user sees say `/setup`:
1. The banner's header line: `.claude/hooks/session-init.sh:248` hardcodes `"unconfirmed: run /setup to confirm"`, while the `Trust:` line in the same banner uses `SETUP` (`:39`, `/daedalus:setup` when `PLUGIN_ROOT` is set). QA OQ-1 P showed both on one banner.
2. The companion plugin's `/daedalus-qa:manual-test`: `plugins/daedalus-qa/commands/manual-test.md:40` (generated from `.claude/commands/manual-test.md:40`) says "run `/setup` to trust the command", and OQ-13 relayed "/setup" to the user. `scripts/build-plugin.sh`'s `rewrite` (`:56-87`) maps `.claude/…` paths, not slash-command names, and a `/daedalus-qa:manual-test` session can't count on the main plugin's name table. It is the only bare main-plugin slash name in the companion plugin's Markdown today.

## Acceptance criteria

| AC | Criterion | Verification |
|---|---|---|
| **RW4-AC-1** | **Every banner line names the install's setup command.** `session-init.sh:248` uses `SETUP`, so the plugin install's header reads `unconfirmed: run /daedalus:setup to confirm` and the script install's is unchanged (`unconfirmed: run /setup to confirm`). Amended after implementation: the `FAILED` and `TIMED_OUT` lines (`:63-64`, "detection failed / timed out; run /setup.") use `SETUP` too. The script-install contract line (`:45`) stays `/setup`. `detect-stack.py`'s own `--summary` (`:977`) is unchanged | `U-trust-banner-10`: unconfirmed profile → plugin banner holds `/daedalus:setup to confirm` and no bare `run /setup`; script banner unchanged. Plus an assertion that `FAILED`/`TIMED_OUT` name `/daedalus:setup` when the hook runs as the plugin and `/setup` otherwise |
| **RW4-AC-2** | **The companion plugin names main-plugin commands with their prefix.** `build-plugin.sh` rewrites a bare slash reference to a main-plugin command (`/setup`, and any other main-plugin command stem) in the **companion** plugin's generated Markdown to `/daedalus:<name>`. The match is bounded: preceded by start, whitespace, `` ` ``, `(` or `"`, and followed by end, whitespace, `` ` ``, `)`, `,`, `.`, `;`, `:` (when not followed by another name character) or ` -`; it never touches paths (`docs/setup.md`, `.claude/commands/setup.md`, already handled by `REF`), already prefixed names (`/daedalus:setup`) or the companion plugin's own commands. The script install's text and the main plugin's output are unchanged (the main plugin keeps relying on its banner line and the workflow-contract name table). `plugins/daedalus-qa/commands/manual-test.md:40` then says `/daedalus:setup` | A test next to the existing build-plugin test (`scripts/test-config.sh:~1142`, which builds into a temp `--out`): the built companion `manual-test.md` holds `/daedalus:setup` and no bare `` `/setup` ``; the built main plugin's files are byte-identical to a build without the new rule (or: its `/setup` mentions are unchanged); a direct unit check of the rewrite on edge strings (`/setup --refresh`, `` `/setup` ``, `(/setup)`, `docs/setup.md`, `/daedalus:setup`, `/setup-x`) |
| **RW4-AC-3** | **Everything green.** `bash scripts/test-all.sh` all PASS; `plugins/**` regenerated with `build-plugin.sh` and `--check` 0 out of date; warm hook ≤ 0.25 s; detector outputs unchanged | `test-all.sh` summary |

## File changes (root `.`)

- **Modify:** `.claude/hooks/session-init.sh` (`:248`); `scripts/build-plugin.sh` (`rewrite` or a companion-only pass after it); `scripts/test-trust.sh`; `scripts/test-config.sh` (build-plugin test); generated `plugins/**` (expected: `plugins/daedalus/scripts/session-init.sh`, `plugins/daedalus-qa/commands/manual-test.md`).
- **Not touched:** `.claude/commands/manual-test.md` (the source keeps `/setup` for the script install), `.claude/scripts/detect-stack.py`, the parent plan's not-touched list, and the token-diet files above.

## Commands

As rework-3: `bash scripts/test-all.sh`, each `scripts/test-*.sh`, `bash scripts/build-plugin.sh` (regenerate) and `--check`, `bash scripts/lint-packs.sh`, `bash scripts/check-generic.sh`, `bash -n`, the hook against temp folders. Always a temporary `DAEDALUS_HOME`; nothing reads or writes the real `~/.workflow` or `~/.claude`.

## Manual QA

N/A (no UI). The maintainer's OQ-7 on the plugin install shows the new header; the QA run-1 folders hold older plugin copies, so rebuild those copies from `plugins/` first if the header matters there.
