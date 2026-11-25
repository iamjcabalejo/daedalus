## Argus review

Phase 2 moves the packs to `.claude/skills/stacks/` with every required section (lint-packs 10/0, matrix 19/19) and fixes rw2-1. But the new first-file-wins config lookup lets the `.workflow/config.yml` that `/setup` writes hide `.argus.yml` and `~/.claude/argus.yml`, which drops the domain and house rules. Not covered by a stack pack: shell, Markdown, JSON, YAML.

**Done well:** `scripts/lint-packs.sh` uses the same `^detect:\s*$` frontmatter test that `load_packs` in `detect-stack.py` uses to tell packs from docs. So `SKILL.md` and `failure-modes.md` can't leak into detection, and a pack with a malformed `detect:` line fails lint instead of silently dropping out of every profile.

**Since the last revision:** 1 earlier finding verified fixed.

**1. [important · reliability] After `/setup`, Argus skips `.argus.yml` and `~/.claude/argus.yml`, silently losing domain and house rules**
Config lookup is first-file-wins, and `<repo>/.workflow/config.yml` now comes first. `/setup`, which the session hook asks for, writes that file with only `stacks`, `tickets` and `graph`. Later `/argus` and `/argus-scan` runs never reach `.argus.yml` or `~/.claude/argus.yml`. `domain` becomes `none`, and house rules, ignores and severity overrides drop without any notice.
- Fix: resolve config per key, not per file. Read every file in the chain (repo `.workflow/config.yml` → repo `.argus.yml` → the workspace pair → `~/.workflow/config.yml` → `~/.claude/argus.yml`) and let the nearer file win key by key. This matches the layered precedence that `project-profile/SKILL.md:18-23` already describes. Change SKILL.md, `commands/argus.md`, `commands/argus-scan.md` and `config-template.yml` together. To check it: in a repo with `.argus.yml` `domain: X` plus a `/setup`-written config, the `/argus --local` brief must still carry `domain: X`.
- Where: `.claude/skills/argus/SKILL.md:38-42`; `.claude/commands/argus.md:34-39`; `.claude/commands/argus-scan.md:38`; `.claude/commands/setup.md:42-49`
- Cost: with a per-key merge, a repo has to write `domain: none` to opt out of a home-level domain. The other option, having `/setup` copy keys from `.argus.yml`, doesn't save `~/.claude/argus.yml` defaults.
<!-- argus-finding:phase2-1 -->

**2. [consider · correctness] Profile packs replace glob detection, so a PR that adds a new file type is reviewed without the pack for it**
`commands/argus.md` keeps only `profile.packs`. The profile shows the tree as it was at the last detection, and `.sql` or `lambda_handler.py` files aren't manifests, so adding them doesn't mark the profile stale. A Python repo's PR that adds its first `migrations/V1__init.sql` gets only the `python` Review section, and the verdict calls the SQL uncovered even though `sql-migrations` exists.
- Fix: load the union: the profile packs for the touched roots, plus every pack whose `detect.files` glob matches a changed path (the same rule as no-profile mode).
- Where: `.claude/commands/argus.md:40`; `.claude/skills/argus/SKILL.md:58`; `.claude/agents/argus.md:29-30`
- Cost: sometimes loads an extra pack's Review section.
<!-- argus-finding:phase2-2 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:tb-jcabalejo/tb-claude-custom-workflow@feat/plug-and-play:WORKTREE-phase2-over-6c7e2f5 -->

<details><summary>Run notes (not posted)</summary>

- **Scope:** the uncommitted working tree over `6c7e2f5` (37 files), including untracked files and excluding `docs/reviews/`. The previous review (rework1b) was passed as the prior review.
- **rw2-1: verified fixed.** With the hop reverted (`for own in body[:1]`) in a scratch copy of `detect-stack.py`, S6's `test.unsafe` drops to false. With the shipped code it is true.
- **Hub checks the reviewer ran:**
  - `scripts/lint-packs.sh`: 10 packs, 0 problems.
  - `scripts/test-detector.sh`: 19/19 PASS.
  - `detect-stack.py --stdout --root .`: packs `[python]`.
  - `git status` was unchanged after the runs.
- **No regression** in 6c7e2f5-1..5 or rw1-1..3.
- **AC-7:** Argus loaded `skills/stacks/failure-modes.md`, `skills/stacks/python.md` (from `.workflow/profile.json`), `skills/stacks/SKILL.md` and `skills/stacks/_generic.md` from the shared path. The body passed the `/argus` Phase C format validation on the first answer.
- **House rule (public hub):** no private repo names or partner terms in the new files.
- **Doc drift the reviewer noted, below the bar:**
  - `config-template.yml:6` omits `~/.workflow/config.yml`.
  - `results-2026-11-25.md:4` still says `detect-stack@1`.
  - `project-profile/SKILL.md:31` doesn't mention `_generic.md` for the no-pack case.
- **Rework mapping:** phase2-1 (important) maps to Critical; phase2-2 (consider) maps to Suggestion.
</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["python"],
 "uncovered": [".claude/agents/argus.md", ".claude/commands/argus-scan.md", ".claude/commands/argus.md", ".claude/hooks/session-init.sh", ".claude/scripts/argus-bundle.sh", ".claude/skills/argus/SKILL.md", ".claude/skills/argus/config-template.yml", ".claude/skills/argus/domains/_template.md", ".claude/skills/project-profile/SKILL.md", ".claude/skills/project-profile/profile.schema.json", ".claude/skills/stacks/*.md", ".claude/rules/stack-knowledge.md", "CLAUDE.md", "README.md", "docs/plans/plug-and-play-workflow.md", "docs/plans/plug-and-play-workflow-rework-1.md", "docs/validation/matrix.json", "docs/validation/results-2026-11-25.md", "scripts/test-detector.sh", "scripts/lint-packs.sh"],
 "domain": "none",
 "ac": {"met": 8, "not_met": 1, "not_visible": 1},
 "prior": {"rw2-1": "verified_fixed"},
 "findings": [
  {"id": "phase2-1", "severity": "important", "category": "reliability", "family": "FM-10", "title": "After `/setup`, Argus skips `.argus.yml` and `~/.claude/argus.yml`, silently losing domain and house rules", "path": ".claude/skills/argus/SKILL.md", "line": 38, "new": true},
  {"id": "phase2-2", "severity": "consider", "category": "correctness", "family": "FM-12", "title": "Profile packs replace glob detection, so a PR that adds a new file type is reviewed without the pack for it", "path": ".claude/commands/argus.md", "line": 40, "new": true}
 ],
 "not_reviewed": ["docs/validation/matrix.local.json"],
 "loaded_files": [".claude/skills/argus/SKILL.md", ".claude/skills/stacks/failure-modes.md", ".claude/skills/stacks/python.md", ".claude/skills/stacks/SKILL.md", ".claude/skills/stacks/_generic.md", ".claude/skills/project-profile/SKILL.md", ".claude/skills/argus/review-template.md"],
 "pack_suggestions": [
  {"stack": "csharp-dotnet", "family": "FM-15", "signal": "Commands says `dotnet ef database update` is unsafe, but detect-stack's UNSAFE_RE/UNSAFE_BODY_RE don't match it in a Makefile/justfile recipe; add `ef\\s+database\\s+update`"},
  {"stack": "agent-workflow (markdown prompts)", "family": "FM-10", "signal": "a config lookup order changed in one prompt file must change in every sibling (SKILL.md, commands, templates, the setup writer) and must not mask the legacy file it claims to fall back to"},
  {"stack": "shell", "family": "FM-06", "signal": "subprocess timeouts inside a session hook must sum below the hook runner's own timeout"}
 ]}
```
</details>
