## Argus review

Revision 2 closes all five earlier findings (k = 5 with a paired lost-defect gate, a workspace → home → root domain lookup, transcript-scored AC-7 and AC-10, a CI step) and its other numbers and citations check out, but §1's F3–F5 attribution leaves AC-2 unmet; not covered by a stack pack: docs/plans/argus-token-diet.md (Markdown; no profile pack matches it).

**Done well:** AC-9's paired lost-defect check runs on data the bench already writes. Each of the 19 `rv-fm*` tasks expects exactly one finding, so `review.tp` is 0 or 1 per record. Records also carry `repeat` (`bench/run.py:102`), so building the per-task table needs no harness change.

**Since the last revision:** 5 earlier findings verified fixed.

**1. [consider · ownership] §1 credits F3–F5 to the first 17 runs, but their ranges fit only the 8 daedalus:argus runs; AC-2 stays unmet**
Line 24 was added for a663546-3 and credits F3–F5 to the first 17 runs. Across those 17, 9 runs read under 15k tokens of code (5 read none), not 27k–64k (F3). The rubric took 10k–22k at 4–14% of final context, not 10k–16k at 4–6% (F5; ad6fbf4d alone took 22.1k, 13.5%). The stated ranges hold only for the 8 daedalus:argus runs a6e7059c to aba3b9d7.
- Fix: Credit F3–F5 to the 8 daedalus:argus runs a6e7059c to aba3b9d7, or restate them over all 17 (code reads 0–64k; rubric 10k–22k, 4–14%). In line 15, change "finished by 20:05" to "started by 20:05", because T2's `--until` compares each run's first event.
- Where: `docs/plans/argus-token-diet.md:24`; `docs/plans/argus-token-diet.md:29`; `docs/plans/argus-token-diet.md:31`; `docs/plans/argus-token-diet.md:15`
<!-- argus-finding:a663546-6 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:a663546fa79fb1519bc6981ad8debe287ba66c27 -->

<details><summary>Run notes</summary>

- **Config:** domain `none` from a caller override (`~/.claude/argus.yml` sets `ticketboat`, which targets product repos; this is the generic hub); `tickets.system` `linear` from `~/.claude/argus.yml`. No ticket key matched, so the ticket is the planning task's acceptance criteria (AC-1…AC-6).
- **Scope:** re-review of the untracked plan `docs/plans/argus-token-diet.md` (revision 2) after the first review ([tb-claude-custom-workflow-hardening-p0a-a663546-argus-token-diet.md](tb-claude-custom-workflow-hardening-p0a-a663546-argus-token-diet.md)). The diff was built by hand (a new-file diff of the revised plan), because `argus-bundle.sh --local` reviews only `merge-base..HEAD`. `prior.md` held the first review; `replies.md` held the author's per-finding change notes; `measurements.txt` held the analysis scripts' output, re-run when the bundle was built. The head SHA is unchanged (uncommitted plan), so the new finding is numbered a663546-6.
- **Prior findings:** verified fixed: a663546-1, -2, -3, -4, -5.
- **AC:** met: AC-1, AC-3, AC-4, AC-5, AC-6. Not met: AC-2 (finding 1).
- **Validation:** the first answer's verdict was three sentences; one follow-up asked for a single sentence, and the second answer is saved here unchanged otherwise.
- **Packs:** profile packs (ci-cd, go, iac, python) and `_generic.md`'s Review loaded; none matches Markdown plans, so the failure modes applied alone.

</details>

<details><summary>findings.json</summary>

```json
{"stacks": ["_generic"], "uncovered": ["docs/plans/argus-token-diet.md"], "domain": "none",
 "ac": {"met": 5, "not_met": 1, "not_visible": 0},
 "findings": [{"id": "a663546-6", "severity": "consider", "category": "ownership", "family": "FM-19", "title": "§1 credits F3–F5 to the first 17 runs, but their ranges fit only the 8 daedalus:argus runs; AC-2 stays unmet", "path": "docs/plans/argus-token-diet.md", "line": 24, "new": true}],
 "not_reviewed": [],
 "prior": {"verified_fixed": ["a663546-1", "a663546-2", "a663546-3", "a663546-4", "a663546-5"], "answered": [], "still_open": []},
 "pack_suggestions": [{"stack": "markdown-docs", "family": "FM-19", "signal": "Plan or design doc that quotes measured ranges for a named run population, or path:line citations; check each range against that population and each citation against the file"}]}
```

</details>
