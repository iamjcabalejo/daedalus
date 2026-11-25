## Argus review

The follow-up closes phase2-rw2-1 as stated (`/setup` no longer writes `tickets.system: none`, `stacks: auto` or `graph: auto`) and adds the config-source run note; lint 10/0, matrix 19/19. Open risk: a detected `github`, which squash-merged GitHub repos produce, is still written unasked; not covered by a stack pack: shell, Markdown, JSON, YAML.

**Done well:** `setup.md` step 6 ("Write choices, not defaults" plus "Nothing to write? Don't create the file") fixes the problem at the only writer. Nothing else writes `.workflow/config.yml`: `detect-stack.py` and `session-init.sh` only produce the profile. For this repo (`tickets.system: none`, `key: null`), no file gets created, so the home settings apply.

**Since the last revision:** 1 earlier finding verified fixed.

**1. [consider · reliability] `/setup` still writes a detected `tickets.system: github` unasked, and PR numbers alone trigger it**
`ticket_facts` returns `github` with key `#\d+` once 5 commit subjects contain `#N`, which squash or merge-commit PRs add (a scratch repo with five `(#N)` subjects and no keys gives `github`). Step 4 asks only for `unknown`/`none`, so step 6 writes it; it beats a home `tickets.system: linear` and `key`, and `/argus` skips the Linear lookup.
- Fix: in `setup.md` step 4, also ask about the ticket system when detection says `github`, offering "leave unset (inherit)" first. In step 6, write `tickets` without asking only for `linear`, which needs both keys and Linear-style branches. Regression check: in a scratch repo with five `(#N)` subjects and no keys, run `/setup` and choose "leave unset". Then run `/argus --local` with `~/.claude/argus.yml` `tickets.system: linear`. The brief must resolve `tickets.system: linear`.
- Where: `.claude/commands/setup.md:37`; `.claude/commands/setup.md:44`; `.claude/scripts/detect-stack.py:778-784`
- Cost: one more `/setup` question on GitHub repos whose history has no ticket keys. Tightening the detector instead (counting only `closes|fixes #N`) would also work, but it touches detector output and fixtures.
<!-- argus-finding:phase2-rw2b-1 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:tb-jcabalejo/tb-claude-custom-workflow@feat/plug-and-play:WORKTREE-phase2-rework2b-over-6c7e2f5 -->

<details><summary>Run notes (not posted)</summary>

- **Config:** domain `none` from the caller override (this hub repo); tickets.system `linear` from `~/.claude/argus.yml`.
- **Prior finding phase2-rw2-1: verified fixed** for the trigger it named.
- **New finding:** phase2-rw2b-1 comes from the same write rule through a different detector branch (`gh_refs >= 5`). A scratch repo with five `(#N)` subjects reproduces it.
- **The two "not visible" AC from the last run:**
  - **Config-source run note: met.**
  - **RW2-1 check scenario: still verified by wording only.** `/setup` is interactive.
- **Follow-up table vs code:** all four items match.
- **Doc drift, below the bar:**
  - `SKILL.md:45` still describes a `/setup`-written file as holding `stacks`, `tickets` and `graph`.
  - `README.md:82` and `CLAUDE.md:18` say `/setup` writes `.workflow/config.yml`, but it may now write none.
- **Edge cases, below the bar:**
  - **Merge depth:** whether `review.severity.overrides` from different files merge or replace each other is unspecified.
  - **Old `/setup` files:** files written by the 6c7e2f5 `/setup` keep masking home settings. Nobody is affected yet: the branch is unmerged.
  - **This hub's domain:** under the merge rules this hub would inherit the home product domain unless a repo file sets `domain: none`.
- **AC:** 13 met, 0 not met, 1 not visible (the RW2-1 check scenario).
- **Hub checks:**
  - lint-packs: 10 packs, 0 problems.
  - test-detector: 19/19 PASS.
  - `git status` was unchanged.
- **House rule (public hub):** the follow-up adds no private names.
- **Rework mapping:** phase2-rw2b-1 (consider) maps to Suggestion. No Critical.
</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["python"],
 "domain": "none",
 "ac": {"met": 13, "not_met": 0, "not_visible": 1},
 "prior": {"phase2-rw2-1": "verified_fixed"},
 "findings": [
  {"id": "phase2-rw2b-1", "severity": "consider", "category": "reliability", "family": "FM-10", "title": "`/setup` still writes a detected `tickets.system: github` unasked, and PR numbers alone trigger it", "path": ".claude/commands/setup.md", "line": 37, "new": true}
 ],
 "not_reviewed": ["docs/validation/matrix.local.json"],
 "loaded_files": [".claude/skills/argus/SKILL.md", ".claude/skills/stacks/failure-modes.md", ".claude/skills/stacks/python.md", ".claude/skills/stacks/_generic.md", ".claude/skills/argus/review-template.md", ".claude/skills/project-profile/SKILL.md", ".claude/skills/argus/config-template.yml", "9 other packs plus stacks/SKILL.md and stacks/_template.md (frontmatter only)"],
 "pack_suggestions": [
  {"stack": "agent-workflow (markdown prompts)", "family": "FM-10", "signal": "a setup step that writes detector output into a config file that outranks home settings must confirm every heuristic result, not only negative or unknown ones"}
 ]}
```
</details>
