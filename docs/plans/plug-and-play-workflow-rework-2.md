# Rework 2: Phase 2 review findings

- **Source:** [Argus review of the Phase 2 working tree](../reviews/tb-claude-custom-workflow-feat-plug-and-play-phase2.md).
- **Plan:** [plug-and-play-workflow.md](plug-and-play-workflow.md) (Phase 2 → AC-7).
- **Branch:** `feat/plug-and-play`.

**Trigger:** phase2-1 is `important`, which maps to **Critical**. phase2-2 (a Suggestion) and three small doc drifts touch the same files, so they are folded in.

## Acceptance criteria
- **RW2-1 (phase2-1): config merges key by key.**
  - **Chain:** Argus reads every file that exists, nearest first: repo `.workflow/config.yml`, repo `.argus.yml`, the workspace pair, `~/.workflow/config.yml`, `~/.claude/argus.yml`, then the defaults.
  - **Merge:** the nearest file that sets a key wins. Mappings (`tickets`, `severity`, `review`, `post`) merge one level down, and lists are replaced whole. (The second follow-up refines this: mappings merge recursively.)
  - **Unset vs. explicit:** `null` or empty falls through, and an explicit `none` or `[]` wins.
  - **Check:** a repo with a `/setup`-written `.workflow/config.yml` (`stacks`, `tickets`, `graph`) plus `~/.claude/argus.yml` `domain: X` still resolves `domain: X`.
  - **Visibility:** the brief carries `config.sources`, and the run notes name the file that supplied `domain`.
- **RW2-2 (phase2-2): packs are a union.** The reviewer loads the profile's packs for the touched roots plus every pack whose `detect.files` globs match a changed path. `/argus-scan` unions a fresh `detect-stack.py --stdout` run with the saved profile.
- **RW2-3: doc drift.**
  - `config-template.yml` lists `~/.workflow/config.yml`;
  - the results doc says `detect-stack@2`;
  - `project-profile/SKILL.md` names `_generic.md` for roots with no pack.

## File changes
- `.claude/skills/argus/SKILL.md`: the Configuration section (chain, merge rules, example) and Loading step 1 (union).
- `.claude/commands/argus.md`: Phase A step 0 (chain, key-by-key merge, `config.sources`, `profile_packs`); the brief gains `sources` and `profile_packs`; the description is updated.
- `.claude/commands/argus-scan.md`: config is resolved key by key; stack detection is a union with a fresh `--stdout` run.
- `.claude/agents/argus.md`: Load step 3 (profile packs plus glob matches).
- `.claude/skills/argus/config-template.yml`: the lookup comment.
- `.claude/skills/project-profile/SKILL.md`, `README.md` (Config row), `docs/validation/results-2026-11-25.md`.

## Re-review follow-up
- **Source:** [Argus re-review](../reviews/tb-claude-custom-workflow-feat-plug-and-play-phase2-rework2.md). phase2-1 and phase2-2 were verified fixed; there was one new consider and some doc drift.

| Item | Fix |
|---|---|
| phase2-rw2-1: `/setup` wrote a detected `tickets.system: none` and `stacks: auto` as explicit values, which hid home and legacy settings | `setup.md` step 6 writes choices only: `tickets` only when detected positively or picked by the user, `key` only when non-null, and never `stacks: auto` or `graph: auto`. It skips creating the file when nothing is left. Step 4 also asks about a `none` ticket system, with "leave unset (inherit)" first |
| RW2-1 Visibility: nothing produced the config-source note | `/argus` Phase A notes which file supplied `domain` and `tickets.system`; Phase C writes a `Config:` line into the saved review's run notes; Phase F replies with it |
| Edge case: legacy top-level `severity`/`post` vs `review.*` | Lifted under `review:` before merging (`SKILL.md`, `commands/argus.md`, `config-template.yml`) |
| Doc drift | `SKILL.md` layer table, the `stacks: auto` comment in `config-template.yml`, the README `/argus` row, plan §4 table and the Phase 2 checklist |

## Second re-review follow-up
- **Source:** [Argus re-review 2b](../reviews/tb-claude-custom-workflow-feat-plug-and-play-phase2-rework2b.md). phase2-rw2-1 was verified fixed, and there was one new consider.

| Item | Fix |
|---|---|
| phase2-rw2b-1: a heuristic `github` ticket system (PR numbers alone, from squash merges) was written unasked and hid a home `linear` | `setup.md` step 4 asks about the ticket system unless detection says `linear` (which needs both keys and Linear-style branches), with "leave unset (inherit)" first. Step 6 writes `tickets` unasked only for `linear`, and leaves out the key too when the user leaves the system unset |
| Merge depth after the lift | Mappings merge recursively (`tickets`, `review`, `review.severity`, `review.post`), and lists are replaced whole wherever they sit, including `severity.overrides` and `critical_triggers` (`SKILL.md`, `commands/argus.md`, `config-template.yml`) |
| Config files from the old `/setup` | Step 6 lists keys it would no longer write (`stacks: auto`, `graph: auto`, an unchosen `tickets`) and suggests removing them |
| Doc drift | `SKILL.md` merge-rule example, the README `/setup` row, the `CLAUDE.md` `/setup` row and the `/setup` description: config is written only for choices |

## Third re-review follow-up
- **Source:** [Argus re-review 2c](../reviews/tb-claude-custom-workflow-feat-plug-and-play-phase2-rework2c.md). phase2-rw2b-1 was verified fixed, and there was one new consider.
- **Fix for phase2-rw2c-1:** picking `linear` on a `github`-detected repo no longer writes the `#\d+` key. `setup.md` step 6 writes the profile's key only when it belongs to the system being written: the pick matches the detected system, or detection was `unknown` and the pick is `linear` or `jira`. Otherwise the key is inherited.
- **Not re-reviewed, by choice.** Each follow-up in `/setup`'s ticket handling has surfaced a smaller consider, and Phase 2 has had no Critical since rework 2.

## Out of scope
- **The reviewer's pack suggestion** that the detector should flag `dotnet ef database update` as unsafe. It's tracked as a follow-up and isn't a finding.
