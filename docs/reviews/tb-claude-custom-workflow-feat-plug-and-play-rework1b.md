## Argus review

The follow-up closes rw1-1…rw1-3 in code, and RW-1…RW-6 still hold. One gap remains: S6 no longer proves the `pre`/`post` hop it is cited for. Not covered by a stack pack: shell, Markdown, JSON. Not reviewed: `docs/validation/matrix.local.json` (private fixtures).

**Done well:** S7 tests `propagate_unsafe` on its own. Neither the root's `turbo run build` body nor its `pnpm build` command contains an unsafe word, so `commands["."].build.unsafe` can only come from propagation. The root `lint` assertion checks the other direction: it stays safe.

**Since the last revision:** 3 earlier findings verified fixed.

**1. [consider · correctness] S6 still passes if the `pre`/`post` hop is reverted, so the rw1-1 hop fix has no regression guard**
S6's `"pretest": "npm run db:reset"` now matches `UNSAFE_BODY_RE` on the script name alone, because this change added `db:(…|reset|…)`. `npm test` gets flagged from the raw pre body, so the hop to `prisma migrate reset --force` never matters. Reverting `script_body` to hop only from `body[0]` still passes 19/19, yet the follow-up table cites S6 as proof of the hop.
- Fix: in S6, give the hopped script a name the regex can't match, for example `"pretest": "npm run fresh"` with `"fresh": "prisma migrate reset --force"`. Then `test.unsafe` holds only when `script_body` follows the hop out of the pre body. The previous review flagged the same trap for S2.
- Where: `docs/validation/matrix.json:596`; `.claude/scripts/detect-stack.py:43`; `.claude/scripts/detect-stack.py:497-500`
<!-- argus-finding:rw2-1 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:tb-jcabalejo/tb-claude-custom-workflow@feat/plug-and-play:WORKTREE-rework1b-over-6c7e2f5 -->

<details><summary>findings.json and run notes (not posted)</summary>

- **Run:** second re-review of the uncommitted working tree against `6c7e2f5` (11 files, 1,193 diff lines). The prior review is the rework-1 re-review (rw1-1…rw1-3).
- **Prior findings:** rw1-1, rw1-2 and rw1-3 are all verified fixed. No regression in the five `6c7e2f5-*` fixes.
- **Verified by the caller:** with the hop reverted (`for own in body[:1]`), the current S6 pretest is still flagged (it can't detect the regression). The proposed `pretest: npm run fresh` is flagged only with the hop fix.
- **Rework mapping:** rw2-1 is consider → Suggestion (test fixture only). No Critical items.

```json
{"prior": {"rw1-1": "verified_fixed", "rw1-2": "verified_fixed", "rw1-3": "verified_fixed"},
 "ac": {"met": 8, "not_met": 1, "not_visible": 0},
 "findings": [{"id": "rw2-1", "severity": "consider", "category": "correctness", "family": "FM-18", "path": "docs/validation/matrix.json", "line": 596, "new": true}]}
```
</details>
