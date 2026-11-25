## Argus review

Rework 2 delivers RW2-1..RW2-3 (key-by-key config merge, profile-plus-diff pack union, three doc fixes; lint 10/0, matrix 19/19), but `/setup` still writes `tickets.system: none` and `stacks: auto`, which now count as explicit and beat home or legacy settings; not covered by a stack pack: shell, Markdown, JSON, YAML.

**Done well:** `commands/argus-scan.md:39` unions a fresh `detect-stack.py --stdout` run with the saved profile. `--stdout` really writes nothing: `main()` skips `write_profile` under that flag (`detect-stack.py:1096`). So a stale profile can't narrow a scan, and the scan can't dirty the target repo.

**Since the last revision:** 2 earlier findings verified fixed.

**1. [consider · reliability] After `/setup`, a detected `tickets.system: none` beats home `linear`, so `/argus` reviews without the ticket**
`ticket_facts` returns `system: none` when history has no keys (as here), and `setup.md` step 6 writes it without asking. An explicit `none` now wins, so a home `tickets.system: linear` is masked: the bundle still finds `ACME-12` via the inherited `key`, but step 2 skips the lookup and no AC are checked. `stacks: auto` masks a legacy `stacks:` list the same way.
- Fix: in `setup.md` step 6, write only values that were positively detected or that the user confirmed. Leave out `stacks: auto` (it is the default). When detection says `none` and the user didn't choose it, leave out `tickets`, or write `system: null`. Regression check: in this repo (where `detect-stack.py --stdout` gives `tickets.system: none`), run `/setup`, then `/argus --local` with `~/.claude/argus.yml` `tickets.system: linear`. The brief must resolve `tickets.system: linear`.
- Where: `.claude/commands/setup.md:44-49`; `.claude/skills/argus/SKILL.md:47`; `.claude/commands/argus.md:47-51`
- Cost: a repo that really has no ticket system inherits a home `linear`. That is harmless: no keys match, and the review says "no linked ticket". Treating `auto` as unset in the merge rules would fix `stacks` but not `tickets.system: none`.
<!-- argus-finding:phase2-rw2-1 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:tb-jcabalejo/tb-claude-custom-workflow@feat/plug-and-play:WORKTREE-phase2-rework2-over-6c7e2f5 -->

<details><summary>Run notes (not posted)</summary>

- **Prior findings:**
  - **phase2-1: verified fixed.** The key-by-key chain and merge rules agree across `SKILL.md`, `commands/argus.md`, `argus-scan.md` and `config-template.yml`.
  - **phase2-2: verified fixed.** The union of profile packs and diff matches is in `SKILL.md`, `agents/argus.md`, the `/argus` brief and `argus-scan.md`.
  - **The three earlier doc drifts are fixed.**
- **New finding:** phase2-rw2-1 has a different root cause from phase2-1. `/setup` writes a detection result as if it were a choice, and that only matters now that explicit values win.
- **New doc drift, below the bar:**
  - `SKILL.md:21` (layer table) reads as profile-or-globs.
  - `config-template.yml:13-14` describes `stacks: auto` as glob-only.
  - `README.md:94` still says "Configured by `.argus.yml`".
  - Plan lines 258 and 386 still say "fall back to `.argus.yml`".
- **Edge case, below the bar:** the merge rules don't say to lift a legacy top-level `severity`/`post` under `review:` before merging.
- **AC (rework-2 plan):** 8 met, 0 not met, 2 not visible:
  - the RW2-1 check scenario was verified by wording only;
  - no step produces the "file that supplied `domain`" run note.
- **Hub checks:**
  - lint-packs: 10 packs, 0 problems.
  - test-detector: 19/19 PASS.
  - `detect-stack.py --stdout --root .` gives `tickets.system: none`, which is the input behind finding 1.
  - `git status` was unchanged.
- **House rule (public hub):** the rework adds no private names.
- **Rework mapping:** phase2-rw2-1 (consider) maps to Suggestion. No Critical.
</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["python"],
 "domain": "none",
 "ac": {"met": 8, "not_met": 0, "not_visible": 2},
 "prior": {"phase2-1": "verified_fixed", "phase2-2": "verified_fixed"},
 "findings": [
  {"id": "phase2-rw2-1", "severity": "consider", "category": "reliability", "family": "FM-10", "title": "After `/setup`, a detected `tickets.system: none` beats home `linear`, so `/argus` reviews without the ticket", "path": ".claude/commands/setup.md", "line": 44, "new": true}
 ],
 "not_reviewed": ["docs/validation/matrix.local.json"],
 "loaded_files": [".claude/skills/argus/SKILL.md", ".claude/skills/stacks/failure-modes.md", ".claude/skills/stacks/python.md", ".claude/skills/stacks/_generic.md", ".claude/skills/stacks/SKILL.md", ".claude/skills/argus/review-template.md", ".claude/skills/project-profile/SKILL.md", "9 other packs (frontmatter only, for the diff glob check)"],
 "pack_suggestions": [
  {"stack": "agent-workflow (markdown prompts)", "family": "FM-10", "signal": "once a config reader treats explicit values (including `none` and defaults like `auto`) as overrides, every writer of the nearer file must stop emitting detected defaults or negative detections as explicit keys"}
 ]}
```
</details>
