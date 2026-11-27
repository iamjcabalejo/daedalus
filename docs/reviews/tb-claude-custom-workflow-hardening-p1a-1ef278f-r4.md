## Argus review

Rework-3 closes 1ef278f-5. A line break or a control or format character in a root, name or `cmd` now makes the record malformed in both channels and at every level, text-mode `trust` and `config commands` escape whatever remains, and test-trust passes 56/56. AC-15 (operational QA) has not run. Not reviewed: README.md, ARCHITECTURE.md. Not covered by a stack pack: bash.

**Done well:** `test_U_trust_effective_12_hidden_characters_make_entries_malformed_in_both_channels` first stores digests of the raw ESC texts (`config:.:test`, `profile:.:esc`) and still finds both records untrusted. `cli_text` reads stdout as bytes, so `assertVisible` checks every character of each text output against `HIDDEN_CATEGORIES` and a carriage return can't pass as a line end.

**Since the last revision:** 1 earlier finding verified fixed.

No material findings. Architecture, security, performance, cost, reliability and correctness all look sound for this change.

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p1a:1ef278fb64e45e66238ca8402ec88d9546c9cc2c+worktree-r4 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override: generic hub, as in earlier hub reviews). No ticket; the plans are the ticket: parent AC-1…AC-15, RW1-AC-1…4, RW2-AC-1…4, RW3-AC-1…6. Packs loaded (`## Review`): `ci-cd`, `go`, `iac`, `python`; bash has no pack.
- **Scope:** fourth pass over the uncommitted working tree on `feat/hardening-p1a` over `1ef278f` (temporary-index diff, 10,445 lines, 137 files). Focus: rework-3. Excluded: `plugins/**` (generated, byte-compared only), `audit.log`, `docs/reviews/**`, and the token-diet session's files and its edits in shared files.
- **Prior findings:** 1ef278f-5 is verified fixed. Evidence:
  - `_shape_problem` (`.claude/scripts/lib/trust.py:662-669`) is used by both `_profile_problem` (`:672-687`) and `_config_candidate` (`:719-732`).
  - `_decide` returns untrusted for a malformed record before the TL1/TL2 branches (`:834-835`).
  - `_text` (`:946-950`) is the single text-output chokepoint (`format_commands`, `_emit`).
  - `_one_command` refuses malformed records through `_malformed_refusal` (`:1049-1069`).
  - The hook imports `lib/text.py` in `load_lib` (`.claude/hooks/session-init.sh:71-82`), and `U-trust-banner-09` asserts that rule has one definition.
  - Overall: 1ef278f-1…-5 fixed, 0 answered, 0 open.
- **Test-runner observations, weighed; none raised:**
  1. **Raw config-error snippet.** `_snippet` (`wfconfig.py:147-149`) puts up to 40 non-space characters on stderr and in the banner's `config_error_line`. Nothing becomes trusted: `config commands` exits 3 and the line says to ask. The banner is model context. A human sees raw escapes only by running `workflow.py` in a terminal on a hostile repo, which is the same exposure as `cat`. Optional hardening: `escape_hidden` in `_report` and in `config_error_line`.
  2. **Raw override names in text `config resolve` / `explain` / `get commands`.** These print no command text and no trust prompt reads them.
  3. **`--json` with `ensure_ascii=False`.** A command's `cmd`, root and name can no longer carry these characters. The raw fields left are the repo path and remote, which a repository doesn't ship. This pass also found two more:
     - A committed profile entry's `source` and `declared.confidence` keep U+202E raw. Reproduced in `trust pending --json`. /setup step 6 doesn't display those fields.
     - A lone surrogate (`"\ud800"`) in `source` makes `trust pending --json` and `config commands --json` exit 1 with a `UnicodeEncodeError` traceback. This fails closed: no list is printed and consumers ask. The text modes still exit 0.
     - `ensure_ascii=True` in `trust._emit` and `wfconfig._emit` would close both.
  4. **Python 3.8 treats newer characters as `Cn`.** A command using one is untrusted on 3.8, which fails closed.
- **Also weighed:** /setup step 6 doesn't say that items with `recordable: false` are left out of "trust all listed commands". Their `reason` says so, and `trust record` lists them under `skipped`. This is UX only and has been the case since rework-2.
- **AC:** 28 met, 0 not met, 1 not visible (AC-15, operational QA). Parent AC-1…14 show no regression from rework-3. RW1 and RW2 are all met, and RW3-AC-1…6 are met. RW3-AC-6 partly rests on the test-runner's runs: test-all 10/10 and `build-plugin --check` 0 of 97 out of date. The reviewer did not re-run the detector output comparison.
- **Reviewer runs:**
  - `scripts/test-trust.sh`: 56/56 in a scratch copy (31 s), with a temporary `DAEDALUS_HOME` and `HOME`.
  - CLI probes: ESC in a TL4 override `cmd` is malformed and the text outputs are clean; U+202E in `source` and `confidence` is raw in the JSON output only; a lone surrogate in `source` makes the JSON outputs fail with a traceback.
  - Warm hook: 0.18–0.21 s.
  - Plugin copies of `lib/text.py`, `trust.py`, `wfconfig.py` and `session-init.sh` are byte-identical to the sources.
- **Severity mapping (project-manager):** no findings and no Critical items, so operational QA (AC-15) is next.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"],
 "uncovered": [".claude/hooks/session-init.sh", "scripts/test-trust.sh", "scripts/test-config.sh", "scripts/test-all.sh", "scripts/build-plugin.sh"],
 "domain": "none",
 "ac": {"met": 28, "not_met": 0, "not_visible": 1},
 "findings": [],
 "not_reviewed": ["README.md", "ARCHITECTURE.md", ".claude/scripts/lib/wfconfig.py (only _snippet, _resolve_commands, _commands_problem and the CLI emitters re-read)", "scripts/test-config.sh (not re-read)", "scripts/fixtures/**", "plugins/** (generated; byte-compared only)", "token-diet files (out of scope)"],
 "pack_suggestions": [{"stack": "python", "family": "FM-08", "signal": "print(json.dumps(..., ensure_ascii=False)) on values read from a repository file raises UnicodeEncodeError for a lone surrogate (\"\\ud800\" in JSON input), so one forged field crashes the whole command; use ensure_ascii=True for machine output or drop Cs characters first."},
                      {"stack": "_generic", "family": "FM-13", "signal": "A trust check that rejects hidden characters only in the approved fields (cmd, root, name) still prints sibling fields (source, confidence) raw beside them in the same prompt; check every field a trust prompt shows, not only the hashed ones."}]}
```

</details>
