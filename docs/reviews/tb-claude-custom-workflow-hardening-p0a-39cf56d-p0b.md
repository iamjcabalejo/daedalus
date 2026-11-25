## Argus review

P0b's harness fixes work as intended. The parse check can't reach a model, and `--allowedTools` goes last on the argv, one rule per argument, on both installs. The verdicts follow from the results. However, every published fixture still carries the operator's encoded temp folder, so AC-3 and the QA redaction PASS don't hold. Not covered by a stack pack: shell, JSON, Markdown.

**Done well:** `check_trust` and `check_denials` (`scripts/probes/probelib.py:604-636`) turn the first run's silent trust confound into explicit rules. In the rerun, I1's out-of-tree `touch` became `inconclusive` by rule instead of being read as sandbox coverage. `test_a_stream_tool_use_selector_catches_a_call_no_hook_saw` covers the E4 path, where no hook runs.

**1. [important · security] All 474 fixtures publish the operator's macOS temp folder and uid; the leak scan and QA PASS miss it**
2.1.325 adds `scratchpad_dir` to every hook payload, in a dash-encoded form that holds the operator's per-user temp folder and uid. `TMP_RE` and the `temp-path` leak pattern match only the slash form, so only the session id was replaced. §3.10 calls a redaction leak a FAIL, but QA row 3 says PASS.
- Fix: add the dash-encoded form to `TMP_RE`, and add `-var-folders-` and `/claude-\d+/` to the leak patterns. Re-redact the 474 fixtures before committing. Regression test: a payload with an encoded `scratchpad_dir` comes out clean, and the raw form fails the committed-fixture scan. Set QA row 3 to FAIL until this is done.
- Where: `scripts/probes/redact.py:51`; `scripts/probes/redact.py:70`; `docs/qa/daedalus-hardening-p0-qa-1.md:12`; every fixture's `payload.scratchpad_dir`
- Cost: one rule and a re-redaction pass. No rerun and no spend.
<!-- argus-finding:39cf56d-1 -->

**2. [consider · correctness] A denial the classifier can't place keeps the verdict, so a reworded host denial can confirm fail-closed**
`check_denials` downgrades only `PERMISSION` hits. Suppose a host release rewords its denial. The permission layer's denial of a probed call then classifies as `unknown`, the run stays `confirmed`, and a fail-closed check could pass on a confound.
- Fix: treat `unknown` on a probed call like `permission`, still exempting `expects_permission_denial`. Regression test: E1 `on-failure-block` with a probed-call denial in unmatched wording ends `inconclusive`.
- Where: `scripts/probes/probelib.py:629`; `scripts/probes/observe.py:348`
- Cost: a host that rewords hook denials too yields inconclusives until the markers are updated, which is the safe direction. No current entry changes.
<!-- argus-finding:39cf56d-2 -->

**3. [consider · correctness] A run that exhausts the budget deletes earlier fixtures and swaps their entries for "not run"**
`published_keys` counts every staged entry, including budget-skipped ones. So `publish` deletes those keys' fixtures, and a `confirmed` entry becomes `inconclusive`. If A1 is skipped, `requires` also downgrades its dependents.
- Fix: leave not-run entries out of `published_keys` and the merge (keep the existing entry). Regression test: a budget-skipped rerun of C1 keeps the earlier entry and fixtures.
- Where: `scripts/probes/probelib.py:1100`; `scripts/probes/probelib.py:956`
<!-- argus-finding:39cf56d-3 -->

**4. [consider · correctness] D9 calls every host from 2.1.325 up fail-closed verified; the evidence is one run on 2.1.325**
The findings document's D9 point 4 has `doctor` and the banner call "2.1.325 and later" verified, while point 5 and the threat model say each new version needs its own run.
- Fix: "verified on probed versions only (2.1.325); later versions [D] until E1–E5 pass on them".
- Where: `docs/plans/daedalus-hardening-phase0.md:369-373`; `docs/plans/daedalus-hardening-threat-model.md:26`
<!-- argus-finding:39cf56d-4 -->

**5. [consider · security] §8.2 publishes the maintainer's live repo-path hook setup and understates it: not SessionEnd only**
The operator's user-level settings run `${CLAUDE_PROJECT_DIR}/.claude/hooks/…` on several events, not only SessionEnd. Any repo that ships a file at that path runs code there, including before every tool call. Documenting the maintainer's specific setup while it's live is a disclosure.
- Fix: the maintainer switches those user hooks to absolute paths (or removes them) before pushing. Reword §8.2 and T3 generically, covering every event and the PreToolUse decision. Keep `doctor`'s check for all events.
- Where: `docs/plans/daedalus-hardening-phase0.md:624-625`; `docs/plans/daedalus-hardening-threat-model.md:241`
<!-- argus-finding:39cf56d-5 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:iamjcabalejo/daedalus@feat/hardening-p0a:39cf56d6c502dc65d3e86547487592d8a0a9ad24+wt-p0b -->

<details><summary>Run notes</summary>

- **Config:** domain `none` (caller override). Packs: python, ci-cd. `scripts/probes/fixtures/**` was ignored in the diff, but sampled.
- **AC:** met: AC-1, AC-2, AC-4, AC-5, AC-6 (as amended by D29). Not met: AC-3 (finding 1); AC-13 (F5 open; redaction row). Not visible: AC-7 (this review).
- **Also noted:** TC-42/43 say "verified" from a manual J1 reading. The P0 plan's AC-13 row and its file name (`-qa.md` vs `-qa-1.md`) are out of date.

</details>

```json
{"stacks": ["python", "ci-cd"],
 "domain": "none",
 "ac": {"met": 5, "not_met": 2, "not_visible": 1},
 "findings": [
  {"id": "39cf56d-1", "severity": "important", "category": "security", "family": "FM-14", "title": "All 474 fixtures publish the operator's macOS temp folder and uid; the leak scan and QA PASS miss it", "path": "scripts/probes/redact.py", "line": 51, "new": true},
  {"id": "39cf56d-2", "severity": "consider", "category": "correctness", "family": "FM-18", "title": "A denial the classifier can't place keeps the verdict, so a reworded host denial can confirm fail-closed", "path": "scripts/probes/probelib.py", "line": 629, "new": true},
  {"id": "39cf56d-3", "severity": "consider", "category": "correctness", "family": "FM-09", "title": "A run that exhausts the budget deletes earlier fixtures and swaps their entries for \"not run\"", "path": "scripts/probes/probelib.py", "line": 1100, "new": true},
  {"id": "39cf56d-4", "severity": "consider", "category": "correctness", "family": "FM-17", "title": "D9 calls every host from 2.1.325 up fail-closed verified; the evidence is one run on 2.1.325", "path": "docs/plans/daedalus-hardening-phase0.md", "line": 369, "new": true},
  {"id": "39cf56d-5", "severity": "consider", "category": "security", "family": "FM-13", "title": "§8.2 publishes the maintainer's live repo-path hook setup and understates it: not SessionEnd only", "path": "docs/plans/daedalus-hardening-phase0.md", "line": 624, "new": true}
 ]}
```
