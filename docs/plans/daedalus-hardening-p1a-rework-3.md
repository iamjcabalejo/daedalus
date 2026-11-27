# Daedalus hardening P1a — rework 3

- **Parent plan:** [daedalus-hardening-p1a.md](daedalus-hardening-p1a.md) (contract); previous rounds [rework-1](daedalus-hardening-p1a-rework-1.md) and [rework-2](daedalus-hardening-p1a-rework-2.md) (done, verified fixed)
- **Source:** [Argus review r3](../reviews/tb-claude-custom-workflow-hardening-p1a-1ef278f-r3.md), finding 1ef278f-5 (consider → Suggestion). **Scope decision (maintainer):** fix it before operational QA
- **Layer:** lib (root `.`, packs `python`, `ci-cd`). No graph. `Security: critical` (inherited)
- **Shared tree:** a concurrent session implements [argus-token-diet](argus-token-diet.md) in this checkout; don't edit its files (`.claude/skills/stacks/**`, `.claude/agents/argus.md`, `.claude/commands/argus*.md`, `.claude/skills/argus/**`, `.claude/scripts/argus-bundle.sh`, `.claude/scripts/lib/config_keys.py`, `README.md`, `LICENSE`, `docs/assets/**`)

## Problem

`trust.py` rejects only line breaks (`_LINE_BREAK` at `:56`, `_single_line` at `:660-661`, used by `_profile_problem` at `:664-680`). A committed command holding an escape sequence (`npm test\x1b[8m && touch X\x1b[28m`) or a bidi override (U+202E) is recordable. Text-mode `trust pending` (`_cli_pending`, `:973-995`) prints it raw, so the terminal shows only part of what the user approves with the `Trust them all` line. Config overrides (`_candidates`, `:709-721`) get no shape check at all, so a TL3/TL4 override written with `"\u001b"`, `"‮"` or `"\n"` (all accepted by the YAML reader's escapes, `wfconfig.py:476-489`) is recordable the same way. The hook already hides these characters in the banner (`session-init.sh:180`, `HIDDEN_CATEGORIES`; `:186-197`).

## Acceptance criteria

| AC | Criterion | Verification |
|---|---|---|
| **RW3-AC-1** | **One hidden-character rule, shared.** A new stdlib-only module in `.claude/scripts/lib/` (e.g. `lib/text.py`; not `unsafe.py`, whose bytes feed `rules_digest`) owns `HIDDEN_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")` and a predicate for "has a line break" and "has a hidden character" (every `_LINE_BREAK` character is in those categories; keep line breaks as their own reason so existing reasons stay). `trust.py` and `.claude/hooks/session-init.sh` import it; the hook's own tuple at `:180` is removed. The hook still runs under `python3 -I`, imports only from its own real `scripts` path, exits 0 on every path, and `U-trust-banner-08` still passes | `grep` shows one definition; `U-trust-banner-08`; warm hook timing |
| **RW3-AC-2** | **Profile channel: hidden characters make an entry malformed.** `_profile_problem` reports a root path, root name or command name, or a `cmd`, that holds any hidden character as malformed, with a reason distinct from line breaks (e.g. `cmd contains control or format characters`; `root path or name contains control or format characters`). As in rework-2: `trusted: false`, `cmd`/`key`/`digest` null, `recordable: false`, never run, never recorded, counted in the banner's `Trust:` line | Extend `U-trust-effective-11`: profile `cmd` with `\x1b[8m`, `cmd` with U+202E, `cmd` with a tab, a root `path` with U+202E, a command name with U+200B |
| **RW3-AC-3** | **Config channel: the same rule, every level.** A `commands` override (TL1–TL4) whose `root`, `name` or `cmd` holds a line break or a hidden character becomes a malformed record: untrusted whatever its level (a TL1/TL2 override with one is untrusted too, and `config commands` doesn't offer it), `cmd`/`key`/`digest` null, `recordable: false`, reason naming the config file to fix (e.g. `malformed config override: cmd contains control or format characters (fix <source>)`). `is_malformed` (`:608-611`) covers both channels; `trust record --root R --name N --channel config` refuses it with a clear message; `trust record --pending` stores no digest for it. The other resolved settings are unaffected (no `ConfigError` for this) | Extend `U-trust-effective-11` (or add `-12`): a TL4 override `cmd: "npm test\u001b[8m && touch X"`, a TL3 override with `"\n"`, a TL2 override with `"‮"`; each is reported untrusted with the reason, not recordable, and the canary never runs |
| **RW3-AC-4** | **Nothing hidden reaches a trust prompt.** Text-mode `trust pending` and `config commands` print no character in `HIDDEN_CATEGORIES` other than their own line ends, for any profile or config (malformed roots and names are shown JSON-escaped with `ensure_ascii=True`, as `_printable` does for multi-line text today, `:683-685`). The banner shows no text for these entries before and after `trust record --pending` | In the tests above, assert every character of the text output (split on `\n`) is outside `HIDDEN_CATEGORIES`, and that the banner holds no canary |
| **RW3-AC-5** | **No over-rejection.** Ordinary non-ASCII text stays trustable: a profile `cmd` such as `pytest -k "café"` or `echo ✓`, and a config override with the same text, are recordable and trusted after `trust record`, and show in the banner after it | New assertion in the same test |
| **RW3-AC-6** | **Everything green, budget kept.** `bash scripts/test-all.sh` all PASS; `plugins/**` regenerated, `build-plugin.sh --check` 0 out of date (the new lib module ships in both plugins if `lib/` is copied); warm hook ≤ 0.25 s; `scripts/test-detector.sh` outputs unchanged | `test-all.sh` summary; timing |

## File changes (root `.`)

- **Add:** `.claude/scripts/lib/text.py` (name is the implementer's choice; say it in the notes).
- **Modify:** `.claude/scripts/lib/trust.py` (`_LINE_BREAK`, `_single_line`, `_profile_problem`, `_printable`, `is_malformed`, `_candidates`, `_decide` only if the problem check must move, `_cli_record` refusal text); `.claude/hooks/session-init.sh` (import the shared rule, drop the local tuple); `scripts/test-trust.sh`; `docs/guides/trust-and-policy.md` (one sentence: commands holding control, format or bidi characters can't be trusted until rewritten); `.claude/commands/setup.md` only if it describes malformed entries as profile-only; generated `plugins/**`.
- **Not touched:** the parent plan's not-touched list (`install.sh`, `.claude/settings.json`, `.claude/hooks/audit.*`, `bench/**`, `scripts/probes/**`), `.claude/scripts/lib/unsafe.py`, `.claude/scripts/detect-stack.py`, and the token-diet files above.

## Commands

As rework-1 and rework-2: `bash scripts/test-all.sh`, each `scripts/test-*.sh`, `bash scripts/build-plugin.sh` (regenerate) and `--check`, `bash scripts/lint-packs.sh`, `bash scripts/check-generic.sh`, `bash -n`, `python3 -I .claude/scripts/workflow.py …` and the hook against temp folders. Always a temporary `DAEDALUS_HOME`; nothing reads or writes the real `~/.workflow` or `~/.claude`.

## Manual QA

N/A (no UI). Operational QA (parent AC-15) follows this rework; OQ-1, OQ-2 and OQ-12 cover these paths.
