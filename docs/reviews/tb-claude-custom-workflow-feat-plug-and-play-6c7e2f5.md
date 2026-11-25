## Argus review

Phase 1 mostly does what it claims (AC-3, AC-4 and AC-6 met; AC-5 not run end to end), but the unsafe gate only reads the wrapper (`npm run X`, `make X`), so scripts that migrate or deploy look safe to auto-run, and AC-1's failure notice and AC-2's lint/build/dev clause are unmet; not covered by a stack pack: shell, Markdown, JSON; not reviewed: the plan's Phase 2–4 design sections.

**Done well:** `scripts/test-detector.sh` wraps `ds.subprocess.run`, fails any row that calls anything other than an allow-listed read-only `git` subcommand, and checks that the scanned repo's top-level entries are unchanged. That is runnable evidence for AC-6, not just a claim.

**1. [important · reliability] The unsafe check only reads the wrapper (`npm run build`), so scripts that migrate or deploy look safe to auto-run**
`cmd()` runs `UNSAFE_RE` on the wrapper it emits (`npm run build`, `make test`). For declared scripts that can never match, because the script body is never read. A Prisma repo with `"build": "prisma migrate deploy && next build"` gets `confidence: script` and no `unsafe` flag. The skill and the hook contract let agents run that without asking, which applies migrations to the `.env` database.
- Fix: in `node_commands`, also run `UNSAFE_RE` on `scripts[hit]`, following one level of `npm run X`. In `task_runner_commands`, run it on the target's recipe lines. Set `unsafe` when either matches, and treat `dbt build` (derived, and it writes to the profiles.yml target) the same way. Add a fixture whose `scripts.build` contains `prisma migrate deploy` and assert `commands.build.unsafe`. This should land before Phase 3's test-runner starts auto-running script commands; at that point this becomes critical.
- Where: `.claude/scripts/detect-stack.py:140-144`; `.claude/scripts/detect-stack.py:468-478`; `.claude/scripts/detect-stack.py:446-456`; `.claude/skills/project-profile/SKILL.md:36-43`; `docs/plans/plug-and-play-workflow.md:604`
- Cost: scanning bodies will also flag builds that only mention `production` (`--mode production`, `NODE_ENV=production`). Either leave `prod|production` out of the body scan, or accept one more `/setup` confirmation per repo.
<!-- argus-finding:6c7e2f5-1 -->

**2. [consider · reliability] The hook says nothing when detection crashes, and its 12s inner timeout outlives the 10s hook budget**
The hook only prints a notice on `TimeoutExpired`. A detector traceback, or a `HardTimeout` that `main()` catches, leaves stdout empty, so nothing tells the user detection failed (AC-1). The subprocess timeout and the SIGALRM are both 12s, above the hook's 10s budget in `settings.json`. A slow scan therefore gets the whole hook killed, and the session loses the contract as well.
- Fix: keep the inner budget under the hook's: pass `--timeout 4` and set the subprocess timeout to about 8s, in line with §3.4's `timeout 5`. When `res.returncode != 0` or stdout is empty, emit `Project profile: detection failed; run /setup.`
- Where: `.claude/hooks/session-init.sh:33-39`; `.claude/settings.json:9`; `.claude/scripts/detect-stack.py:989-994`; `.claude/scripts/detect-stack.py:1012`
<!-- argus-finding:6c7e2f5-2 -->

**3. [consider · correctness] Profile freshness ignores the detector and pack versions, so hub upgrades never refresh existing profiles**
`is_fresh` checks only `schema` and the manifest hash. Hub updates change pack `detect` globs or detector rules: this commit does it for three packs, and Phase 2 moves and extends them. After such an update, existing and committed profiles still count as fresh with the old `packs` and commands, until someone edits a manifest or runs `/setup --refresh`. The hook summary gives no hint.
- Fix: fold `GENERATOR` and a digest of the loaded pack frontmatter (or of the detector file) into `manifest_hash`, or store them and compare them in `is_fresh`. Bump `GENERATOR` whenever detection rules change.
- Where: `.claude/scripts/detect-stack.py:824-830`; `.claude/scripts/detect-stack.py:926-930`; `.claude/scripts/detect-stack.py:29`
- Cost: one forced re-detection per hub upgrade. In repos that commit the profile, teammates on different hub versions will regenerate it back and forth until they align.
<!-- argus-finding:6c7e2f5-3 -->

**4. [consider · correctness] `npm ci` and `uv sync` can never be chosen because lockfiles are filtered out of `texts`**
`root_texts` drops files ending in `-lock.json` or `.lock`. But `node_commands` tests `"package-lock.json" in texts`, and `python_commands` tests `"uv.lock" in texts`. As a result, every npm root gets `npm install`, which is derived and so auto-runnable, and can rewrite `package-lock.json` into the diff. A uv root reports `package_manager: uv` but gets no install command, or gets `pip install -r` into whatever Python is active.
- Fix: pass `names` into `node_commands` and `python_commands` and check for lockfiles there. Add fixtures asserting `commands.install.cmd == "npm ci"` with a `package-lock.json` and `"uv sync"` with a `uv.lock`.
- Where: `.claude/scripts/detect-stack.py:358`; `.claude/scripts/detect-stack.py:466`; `.claude/scripts/detect-stack.py:487-490`
- Cost: `npm ci` removes `node_modules` first, so installs are slower.
<!-- argus-finding:6c7e2f5-4 -->

**5. [consider · ownership] AC-2's lint/build/dev clause has no fixtures and no check, yet the results doc and the plan mark AC-2 passed**
`compare()` only checks packs, layer, test, ui and tickets, and `matrix.json` has no lint, build or dev expectations. `gaps_for` never reports a missing `build`, and only reports a missing `dev` on UI roots: Python roots never get a build, and Go and Cargo roots never get a dev. So AC-2's "match, or are listed in gaps" fails, while `results-2026-11-25.md` and §4 mark Phase 1 done.
- Fix: either add `build`/`dev` gaps for api, worker and cli roots (and `lint` for lib roots), plus lint/build/dev in `facts()`, `compare()` and the fixtures, or narrow AC-2 in the plan to the fields that are actually checked.
- Where: `scripts/test-detector.sh:68-89`; `.claude/scripts/detect-stack.py:799-810`; `docs/validation/results-2026-11-25.md:7-21`
- Cost: extra gaps make summaries noisier for libraries. Narrowing the AC is the cheaper option.
<!-- argus-finding:6c7e2f5-5 -->

_Disagree with a finding? Reply on it or in a PR comment; replies are read on the next run._

_Reviewed with Claude Code (`/argus`). Findings weigh tradeoffs, not style — an empty review means nothing material was found._

<!-- argus-review:tb-jcabalejo/tb-claude-custom-workflow@feat/plug-and-play:6c7e2f51ab91c9de0dd39fcfd31124bccf840a91 -->

<details><summary>findings.json and run notes (not posted)</summary>

- **Run:** local mode, base `v1-ticketboat` → `6c7e2f5`; 17 files, 2,837 diff lines.
- **Config:** `~/.claude/argus.yml`, with `domain: none` for this hub review.
- **Format:** all Phase C checks pass. The verdict runs slightly over the 400-character guideline.
- **Verified by the caller:**
  - finding 1: `cmd()` checks only the wrapper string;
  - finding 2: settings.json SessionStart timeout is 10, while the subprocess timeout and SIGALRM are 12;
  - finding 4: `root_texts` filters `-lock.json` and `.lock`, which `node_commands` and `python_commands` then look up.
- **Rework mapping:** finding 1 (important) → Critical (`docs/plans/plug-and-play-workflow-rework-1.md`); findings 2–5 → Suggestion.

```json
{"stacks": ["python"], "domain": "none",
 "ac": {"met": 3, "not_met": 2, "not_visible": 1},
 "findings": [
  {"id": "6c7e2f5-1", "severity": "important", "category": "reliability", "family": "FM-03", "path": ".claude/scripts/detect-stack.py", "line": 140, "new": true},
  {"id": "6c7e2f5-2", "severity": "consider", "category": "reliability", "family": "FM-08", "path": ".claude/hooks/session-init.sh", "line": 33, "new": true},
  {"id": "6c7e2f5-3", "severity": "consider", "category": "correctness", "family": "FM-12", "path": ".claude/scripts/detect-stack.py", "line": 824, "new": true},
  {"id": "6c7e2f5-4", "severity": "consider", "category": "correctness", "family": "FM-11", "path": ".claude/scripts/detect-stack.py", "line": 358, "new": true},
  {"id": "6c7e2f5-5", "severity": "consider", "category": "ownership", "family": "FM-18", "path": "scripts/test-detector.sh", "line": 68, "new": true}
 ],
 "not_reviewed": ["plan sections 3.5-7, 9-13 (Phase 2-4 design)", "phase0 findings (partly)", "matrix rows I/J (skimmed)"],
 "pack_suggestions": [
  {"stack": "shell", "family": "FM-06", "signal": "hook wrapper whose inner timeout exceeds the hook's configured timeout"},
  {"stack": "python", "family": "FM-12", "signal": "generated artifact freshness hash omits generator/rule-file versions"},
  {"stack": "agent-tooling", "family": "FM-03", "signal": "safe/unsafe classifier applied to the wrapper instead of the script body"}
 ]}
```
</details>
