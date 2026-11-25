## Argus review

The follow-up closes phase2-rw2b-1 as written: `/setup` now confirms every ticket system except a detected `linear`, offering "leave unset" first, and the merge depth is now specified. lint 10/0, matrix 19/19. Open risk: picking `linear` on a `github`-detected repo writes the detected `#\d+` key next to it. Not covered by a stack pack: shell, Markdown, JSON, YAML.

**Done well:** The note in `setup.md` step 4 matches the detector exactly. `linear` is returned only when both repeated keys and at least 3 Linear-style branches are present (`detect-stack.py:779-780`). So the one value written without asking is the only branch backed by two independent signals.

**Since the last revision:** 1 earlier finding verified fixed.

**1. [consider · correctness] Picking `linear` on a `github`-detected repo writes the `#\d+` key, so `/argus` never finds the ticket**
A squash-merge repo is detected as `github` with key `#\d+` (reproduced in a scratch repo with six `(#N)` subjects). Step 4 now asks, and the user picks `linear`. Step 6 writes "`key` only when it isn't null", which is the profile's `#\d+`, and that beats the home `tickets.key`. `argus-bundle.sh` then extracts `#42`, `get_issue` on `#42` fails, and every review says "no linked ticket".
- Fix: in `setup.md` step 6, write the profile's `key` only when the picked system matches the detected one, or when detection was `unknown` with keys and the pick is `linear` or `jira`. Otherwise leave `key` out so it is inherited, or ask for the key prefix. Regression check: in the six-`(#N)` scratch repo, pick `linear` in step 4. The written file must hold `tickets: {system: linear}` and no `#\d+`.
- Where: `.claude/commands/setup.md:44`; `.claude/commands/setup.md:51`; `.claude/scripts/detect-stack.py:783-784`; `.claude/commands/argus.md:46-49`
- Cost: one clause in step 6. With no home key, a `linear` pick falls back to the template default `[A-Z][A-Z0-9]+-\d+`. That pattern is broader but still finds Linear keys. Asking for the prefix instead costs one more question on these repos.
<!-- argus-finding:phase2-rw2c-1 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:tb-jcabalejo/tb-claude-custom-workflow@feat/plug-and-play:WORKTREE-phase2-rework2c-over-6c7e2f5 -->

<details><summary>Run notes (not posted)</summary>

- **Config:** domain `none` from the caller override (this hub repo). tickets.system `linear` from `~/.claude/argus.yml`.
- **Prior finding phase2-rw2b-1: verified fixed.**
- **New finding:** phase2-rw2c-1 is new behavior from the follow-up, which made `github` a question. A scratch repo with six `(#N)` subjects reproduces it.
- **Notes from the 2b run:**
  - The `SKILL.md` example, the README and `CLAUDE.md` `/setup` rows, the merge depth and the old `/setup` files are all fixed.
  - This hub's domain still depends on the caller override, which is below the bar.
- **Below the bar:**
  - The `SKILL.md` example pairs a `github` system with a home `ACME-\d+` key. This is harmless, because the `github` path ignores the key.
  - `config-template.yml` still shows `severity`/`post` in the legacy top-level shape, which relies on the lift.
- **AC:** 16 met, 0 not met, 1 not visible (the interactive `/setup` scenario, verified by wording only).
- **Hub checks:**
  - lint-packs: 10 packs, 0 problems.
  - test-detector: 19/19 PASS.
  - `git status` was unchanged.
- **House rule (public hub):** no private names added.
- **Rework mapping:** phase2-rw2c-1 (consider) maps to Suggestion. No Critical.
</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["python"],
 "domain": "none",
 "ac": {"met": 16, "not_met": 0, "not_visible": 1},
 "prior": {"phase2-rw2b-1": "verified_fixed"},
 "findings": [
  {"id": "phase2-rw2c-1", "severity": "consider", "category": "correctness", "family": "FM-11", "title": "Picking `linear` on a `github`-detected repo writes the `#\\d+` key, so `/argus` never finds the ticket", "path": ".claude/commands/setup.md", "line": 44, "new": true}
 ],
 "not_reviewed": [],
 "loaded_files": [".claude/skills/argus/SKILL.md", ".claude/skills/stacks/failure-modes.md", ".claude/skills/stacks/python.md (## Review)", ".claude/skills/stacks/_generic.md", ".claude/skills/argus/review-template.md", ".claude/skills/argus/config-template.yml", "other packs (frontmatter only)"],
 "pack_suggestions": [
  {"stack": "agent-workflow (markdown prompts)", "family": "FM-11", "signal": "a config writer that lets the user override a detected enum (ticket system) must drop the detected companion fields (key regex) that belong to the old value"}
 ]}
```
</details>
