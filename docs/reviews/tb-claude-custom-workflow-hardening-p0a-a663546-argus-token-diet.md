## Argus review

The plan answers the request with measured reasons (script-built rubric, scoped reads, turn budget; per-family files rejected on turn cost), but AC-9 can pass a diet that loses findings and plugin installs would drop overlay domain packs from every rubric; not covered by a stack pack: docs/plans/argus-token-diet.md (Markdown; failure modes and _generic applied).

**Done well:** AC-3 has `argus-prepare.py` import `detect-stack.py`'s `load_packs`, `index_files`, `matches_any` and `signal_found` instead of copying them. They exist at `detect-stack.py:179–338`, and the `__main__` guard at `:1105` means importing the file runs nothing. So the reviewer's pack selection can't drift from the detector's.

**1. [important · correctness] AC-9 lets recall fall by the baseline's full 3-repeat spread, so a diet that loses findings still ships**
Recall is one value per repeat over 19 seeded defects (about 5.3 points each). Baseline repeats of 12, 15 and 16 of 19 give a median of 15 and a band of 4, so a new arm that finds 12 of 19 passes. That contradicts line 7's "nothing ships that loses findings", and roadmap:1337 asks for k ≥ 5 before any release or comparative claim.
- Fix: Run T15 at k = 5 (roadmap:1337). Add a paired check to AC-9: list each seeded defect that the baseline caught in most repeats and the new arm missed. Any entry blocks shipping until the maintainer rules it noise, as AC-12 does. Keep the band rule for precision and severity accuracy.
- Where: `docs/plans/argus-token-diet.md:76`; `docs/plans/argus-token-diet.md:7`; `docs/plans/daedalus-hardening-roadmap.md:1337`; `bench/lib/metrics.py:239`
- Cost: k = 5 is about two-thirds more bench spend per arm. The paired check reuses each record's `review.tp` and `fn`.
<!-- argus-finding:a663546-1 -->

**2. [important · reliability] On plugin installs the rubric drops the overlay domain pack, so its invariants vanish from every review**
§3.2 reads `domains/` from the script's own root. For `/daedalus:argus` that is `${CLAUDE_PLUGIN_ROOT}`, which ships only `_template.md`, while the overlay guide tells plugin users to put packs in `~/.claude/skills/` (writing-an-overlay.md:37). With `domain: <name>` set, the rubric builds without it, argus opens no source (AC-6), and no step surfaces `DOMAIN=missing`.
- Fix: Look for `skills/argus/domains/<domain>.md` in `<workspace>/.claude/`, then `~/.claude/`, then the script's root (the overlay install targets), and write the resolved path into the header. Have argus copy `domain` into its JSON and verdict, and have `/argus` add it to the Run notes. Add `prepare-12`: with a plugin-layout root and the pack only under a fake `HOME`, the script gives `DOMAIN=loaded`.
- Where: `docs/plans/argus-token-diet.md:111`; `docs/plans/argus-token-diet.md:134`; `docs/plans/argus-token-diet.md:253`; `docs/guides/writing-an-overlay.md:37`
- Cost: The rubric then depends on `HOME` and the workspace. Recording the resolved path in the header keeps runs comparable.
<!-- argus-finding:a663546-2 -->

**3. [consider · ownership] §1's run count and "8 most recent" label don't match the measurements it cites, so AC-2 isn't met**
measurements.txt lists 19 argus runs (10 `daedalus:argus`); §1 says 17, and its table is the first 8 listed, not the latest: it omits ac80438e and afb48aaf, which ran after aba3b9d7 (with them, turns 39–158, summed input 4.6M–37.0M). §3.11 and §11 also move a P1a citation, `SKILL.md:36–62`, that P1a doesn't have (it cites `:39–50` and `:44–50`).
- Fix: State 19 runs (10 `daedalus:argus`) and either recompute the table over all 10 or name the 8 runs it uses. Drop `:36–62` from §3.11 and §11.
- Where: `docs/plans/argus-token-diet.md:14-21`; `docs/plans/argus-token-diet.md:202`; `docs/plans/argus-token-diet.md:320`
<!-- argus-finding:a663546-3 -->

**4. [consider · correctness] AC-7 and AC-10 read bench fields that don't measure the argus subagent the way the gates assume**
`repeated_reads` counts every Read of a path after the first, whatever the offset (metrics.py:82), so AC-7's hunk windows look like re-reads. Record `tokens` come from the main stream only (run.py:149); if `result.usage` omits subagents (G1 never compared them), AC-10 measures `/argus`, not argus. AC-13 gives argus-usage.py no input folder to fall back on.
- Fix: Give argus-usage.py a `--projects <dir>` option (default `~/.claude/projects`). Score AC-7 (re-read ranges) and AC-10 (stream plus argus-transcript tokens) from each T15 run's `home/.claude/projects`. Drop `repeated_reads` from AC-7, and have T14 record whether `result.usage` includes subagent tokens. T2 should also run the script as `python3 -I` (ticket AC-6).
- Where: `docs/plans/argus-token-diet.md:74`; `docs/plans/argus-token-diet.md:77`; `docs/plans/argus-token-diet.md:85`; `bench/lib/metrics.py:82-88`; `bench/run.py:149-152`; `scripts/probes/cases/G1.json:101`
- Cost: One CLI option and a loop over run folders in T15; no extra bench spend.
<!-- argus-finding:a663546-4 -->

**5. [consider · reliability] test-argus.sh runs in test-all.sh but not in CI, so a detector change can break argus-prepare.py unseen**
`.github/workflows/check.yml` runs each hub check by name and never calls `test-all.sh`; every existing check is listed there. T11 adds `test-argus.sh` only to `test-all.sh`. P1a edits `detect-stack.py` next; if that breaks the import AC-3 relies on, CI stays green and every `/argus` run falls back to manual loading, losing the savings.
- Fix: In T11, add a `scripts/test-argus.sh` step to `.github/workflows/check.yml`, and list that file under Modify.
- Where: `docs/plans/argus-token-diet.md:229`; `.github/workflows/check.yml:19-32`
<!-- argus-finding:a663546-5 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` from a caller override (`~/.claude/argus.yml` sets `ticketboat`, which targets product repos; this is the generic hub); `tickets.system` `linear` from `~/.claude/argus.yml`. No ticket key matched, so the ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** the untracked plan `docs/plans/argus-token-diet.md` only. The diff was built by hand (a new-file diff of the plan), because `argus-bundle.sh --local` reviews only `merge-base..HEAD`, and that 772-file diff from `71a3214` is the committed P0 history, already reviewed and out of scope.
- **Evidence:** `measurements.txt` in the bundle was the output of the analysis scripts the plan cites, rerun when the bundle was built. It picked up runs that finished after the plan's analysis (hence 19 runs, against 17 in the plan).
- **AC:** met: AC-1, AC-3. Not met: AC-2 (finding 3), AC-4 (finding 1: k = 3 against roadmap:1337), AC-5 (findings 1 and 4), AC-6 (finding 4: T2 without `-I`).
- **Packs:** profile packs loaded (ci-cd, go, iac, python) plus `_generic.md`'s Review; none matches Markdown plans, so the failure modes applied alone.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["ci-cd", "go", "iac", "python"], "uncovered": ["docs/plans/argus-token-diet.md"], "domain": "none",
 "ac": {"met": 2, "not_met": 4, "not_visible": 0},
 "findings": [
  {"id": "a663546-1", "severity": "important", "category": "correctness", "family": "FM-18", "title": "AC-9 lets recall fall by the baseline's full 3-repeat spread, so a diet that loses findings still ships", "path": "docs/plans/argus-token-diet.md", "line": 76, "new": true},
  {"id": "a663546-2", "severity": "important", "category": "reliability", "family": "FM-15", "title": "On plugin installs the rubric drops the overlay domain pack, so its invariants vanish from every review", "path": "docs/plans/argus-token-diet.md", "line": 111, "new": true},
  {"id": "a663546-3", "severity": "consider", "category": "ownership", "family": "FM-19", "title": "§1's run count and \"8 most recent\" label don't match the measurements it cites, so AC-2 isn't met", "path": "docs/plans/argus-token-diet.md", "line": 14, "new": true},
  {"id": "a663546-4", "severity": "consider", "category": "correctness", "family": "FM-18", "title": "AC-7 and AC-10 read bench fields that don't measure the argus subagent the way the gates assume", "path": "docs/plans/argus-token-diet.md", "line": 74, "new": true},
  {"id": "a663546-5", "severity": "consider", "category": "reliability", "family": "FM-18", "title": "test-argus.sh runs in test-all.sh but not in CI, so a detector change can break argus-prepare.py unseen", "path": "docs/plans/argus-token-diet.md", "line": 229, "new": true}
 ],
 "not_reviewed": [],
 "pack_suggestions": [
  {"stack": "markdown-plans", "family": "FM-18", "signal": "Ship gate 'median >= baseline median - (max - min)' at k = 3, which tolerates a regression as large as the baseline's spread"},
  {"stack": "markdown-plans", "family": "FM-15", "signal": "A script resolves user- or overlay-supplied packs only from its own install root, while plugin-install docs put them under ~/.claude"}
 ]}
```

</details>
