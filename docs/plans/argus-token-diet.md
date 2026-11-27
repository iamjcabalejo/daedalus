# Argus token diet: script-built rubric, scoped reads, turn budget

- **Type:** Refactor (workflow hub). Changes the shipped `argus` role, its skill, `/argus` and `/argus-scan`, and adds one shipped script; adds one hub-only measurement script
- **Complexity:** Medium. One new Python script with tests, a skill split, prompt edits to one role and two commands, one report script, and a paid bench comparison
- **Estimated effort:** 2–3 engineering days, plus one bench run (operator, paid)
- **Ticket:** none
- **Metadata:** `Performance: critical`: token cost is the objective. Recall is the constraint: nothing ships that loses findings (AC-9)
- **Base:** set when this plan is picked up after P1c. The original base (`feat/hardening-p0a` @ `a663546`, with the argus files unchanged since `71a3214`, so the bench arm `daedalus-0.4.0` was the baseline) no longer holds: P1a changed `agents/argus.md`, `commands/argus.md`, `scripts/argus-bundle.sh` and the rubric skill, which iamjcabalejo/daedalus#2 also renamed to `skills/argus-rubric/`; P1b rewrites the bundle and the review output. Measure a fresh baseline arm at the new base instead of `daedalus-0.4.0`
- **Graph gate:** skipped (no graph; `integrations.graph.graphify: false`)
- **Sequencing:** after P1c (decided 2026-11-28; it was "before P1a", but P1a landed first). P1b and P1c rewrite the same argus files, so this plan doesn't run alongside them. Re-plan §2–§6 against the post-P1c tree before implementing (§10, §11). Paths below use the renamed skill folder
- **Review:** revised after [the Argus review of this plan](../reviews/tb-claude-custom-workflow-hardening-p0a-a663546-argus-token-diet.md); this revision carries the fixes for findings a663546-1 to -5

## 1. Feature overview

**Problem.** One Argus review costs about 250k tokens of context. Measured from the argus subagent transcripts on this machine (`~/.claude/projects/*/*/subagents/agent-*.jsonl`) that finished by 2026-11-25 20:05 UTC: **19 runs**, 9 of the repo's `argus` role and 10 of the plugin's `daedalus:argus`. The table covers those 10 `daedalus:argus` runs (`a6e7059c`, `a81e8676`, `a5d8d7cc`, `aba3993f`, `a084cd78`, `a7b75747`, `ae89342c`, `aba3b9d7`, `ac80438e`, `afb48aaf`):

| Metric | Median | Range |
|---|---|---|
| Final context | 255k | 209k–391k |
| Turns | 77 | 39–158 |
| Input tokens summed over all turns (mostly cache reads) | 12.3M | 5.1M–37.0M |
| Output tokens (mostly reasoning, which stays in context) | 136k | 103k–233k |

The per-bucket figures in F3–F5 come from the detailed breakdown of the first 17 runs (all but `ac80438e` and `afb48aaf`). A later run fits the pattern: the review of this plan (`a0dfe32f`, the repo's `argus` role) took 119 turns, 237k final context and 17.8M summed input. T2 freezes the baseline with the same cutoff.

Findings:
- **F1 Turns drive the bill.** Every turn resends the whole context, so summed input ≈ turns × average context.
- **F2 Reasoning is about half the final context.** `argus` sets no `effort`, so it inherits the parent's.
- **F3 Code reads cost 27k–64k per run.** [argus.md:55](../../.claude/agents/argus.md) says "Read full files in `checkout`". Files are re-read: `detect-stack.py` three times in one run (~13k).
- **F4 The diff is read in pieces, sometimes twice.** Four runs took 13k–56k from the bundle.
- **F5 The rubric is small but costs turns.** `SKILL.md`, `failure-modes.md`, the packs' Review sections and the template total 10k–16k (4–6% of final context), loaded with 5–16 tool calls. Several runs ran `for f in *.md; awk …` loops to redo pack detection, which `detect-stack.py` already implements.
- **F6 The fixed prompt grew from 26k to 36k per turn** on 2026-11-24 (between runs `a9074777` and `ad6fbf4d`), and is paid on every turn.
- **Caveat:** all 19 runs reviewed this hub's own changes (plans, Python, shell). Product-repo PRs may split differently; AC-12 checks one.

**Objective.** Cut Argus's tokens per review by moving rubric selection and diff slicing into a deterministic script, scoping reads, budgeting turns and, if the bench allows it, lowering effort. No loss in recall, precision or severity accuracy.

**In scope:** `argus-prepare.py` (rubric and diff index), the `argus` skill split by mode, the `argus` role's load and read rules, `/argus` and `/argus-scan` wiring, a usage report, the bench comparison.

**Out of scope:**
- Removing Bash from `argus`, and `maxTurns` (roadmap P2: AC-3 at [roadmap:462](daedalus-hardening-roadmap.md), `maxTurns` at `:501`). This plan's turn budget is prompt-only.
- Configuration resolution (P1a); working-tree bundles and the review JSON schema (P1b).
- User-level setup. `~/.claude/rules/` holds older copies of the five project rules, which load next to `.claude/rules/`. In this hub repo, every skill and agent is also listed twice (repo `.claude/` plus the plugin). Both inflate every turn, but they live on the user's machine, not in the shipped workflow (§10).
- One file per failure family, chosen by the model: rejected (§3.9).

## 2. Acceptance criteria

- **AC-1 Rubric built by script (pr, local).** Given a bundle, the resolved config and mode `pr` or `local`, when `/argus` runs `argus-prepare.py`, then `<bundle>/rubric.md` holds these parts in this order, each preceded by `<!-- rubric-part: <source> -->`:
  1. `skills/argus-rubric/SKILL.md` without its frontmatter and without `## Loading`;
  2. `skills/stacks/failure-modes.md`, whole;
  3. the `## Review` section of each selected pack, sorted by name;
  4. the `## Review` section of `_generic.md`, when any non-ignored changed file is uncovered;
  5. the domain pack `skills/argus-rubric/domains/<domain>.md`, when the domain isn't `none`. It's looked up in this order, first hit wins: `<workspace>/.claude/`, then `~/.claude/` (where both the script install and the plugin-install guide put overlay packs, [writing-an-overlay.md:37](../guides/writing-an-overlay.md)), then the script's own root;
  6. each `house_rules` file, read from the checkout;
  7. `review-template.md`.

  A first-line header comment lists `mode`, `packs`, `uncovered`, `domain` (`loaded:<path>`, `missing` or `none`, where `<path>` starts with `<workspace>`, `~` or `<root>`, never an absolute user path) and `missing_house_rules`. The same inputs, workspace and home folder give byte-identical output.
- **AC-2 Scan rubric.** With mode `scan`, the parts are: the SKILL core, `scan.md`, `failure-modes.md`, each selected pack's `## Review` and `## Entry points (scan mode)`, `_generic.md`'s `## Review` (always: scans can't know coverage), the domain pack, `scan-template.md`. No diff split.
- **AC-3 Pack selection follows the skill's rules.**
  - Selected = the profile packs of roots that contain a changed file ∪ packs whose `detect.files` match a changed path or a root manifest in the checkout ∪ packs whose `detect.signals` appear in the diff's added lines.
  - `detect.weak` alone never selects a pack; once a pack is selected, its `files` and `weak` globs both count for coverage.
  - `stacks: [..]` replaces auto-detection; `extra_stacks` adds; an unknown pack name prints a `WARNING` and is skipped.
  - Files matching `ignore` neither select packs nor count as uncovered.
  - Matching imports `detect-stack.py`'s `load_packs`, `index_files`, `matches_any` and `signal_found`; it doesn't copy them, so the detector and Argus can't drift.
- **AC-4 Diff split.** `<bundle>/diff/NNNN.patch` holds one file's patch each, in diff order, and `<bundle>/diff-index.tsv` has the header `n path status added deleted patch_lines head_lines packs ignored`.
  - Concatenating the patches in order reproduces `diff.patch` byte for byte.
  - Additions, deletions, renames, binary files and paths with spaces or git-quoted characters are handled; `head_lines` is `0` for a deletion and `-` for a binary file.
  - `diff.patch` stays: `right_lines` and P1b's fingerprint use it.
- **AC-5 Skill split.** `SKILL.md` keeps the review core. The Configuration section moves verbatim to `skills/argus-rubric/config.md`, and Scan mode to `skills/argus-rubric/scan.md`. `## Loading` is rewritten: `rubric.md` is what the reviewer loads, the AC-3 rules are the script's contract, and the manual load is the fallback. Every heading that existed before the split exists in exactly one of the three files, and no reference to a moved section points at `SKILL.md`.
- **AC-6 One rubric read.** When the brief names `rubric:` and the file exists, `argus` reads it once and opens none of its sources. When it's missing (prepare failed, or an older command), `argus` loads the sources as today, and `/argus` writes `Rubric: manual (<reason>)` in the Run notes. The review JSON doesn't change. Proven on transcripts with `argus-usage.py`: `rubric.md` read once, rubric sources read zero times.
- **AC-7 Scoped reads.** The role's procedure:
  - read `diff-index.tsv` first, then only the per-file patches it needs;
  - read code around each hunk (±40 lines, with `offset` and `limit`);
  - read a whole file only when `head_lines` ≤ 400, or when a hunk changes a contract (signature, exported symbol, schema, route, config key, message shape), and then search for its callers;
  - never re-read a range already in context;
  - send independent reads in one turn.

  Measured: the median count of re-read ranges per argus run (`argus-usage.py`, over the T15 argus transcripts) is at most half the baseline's. The bench's `repeated_reads` isn't used: it counts every Read of a path after the first, whatever the range ([metrics.py:82–88](../../bench/lib/metrics.py)), so hunk windows would look like re-reads.
- **AC-8 Soft turn budget.** `argus` aims for ≤ 30 tool turns, or ≤ 45 when the brief's `diff_lines` is over 1,500. At the budget it stops exploring, writes the review, and lists the files it didn't read in `not_reviewed` and in the verdict. No `maxTurns` (P2).
- **AC-9 Quality gate (bench).** On `bench/review/` (19 tasks with one seeded defect each, 6 clean tasks) at **k = 5**, the bar the roadmap sets before any comparative claim ([roadmap:1337](daedalus-hardening-roadmap.md)), the new arm against `daedalus-0.4.0`:
  - **Paired recall check:** for each defect task, count the repeats whose record has `review.tp = 1`. A task the baseline caught in at least 3 of 5 repeats and the new arm in at most 2 of 5 is a **lost defect**. Any lost defect blocks shipping until the maintainer rules it noise in §12, citing the transcript that shows why it was missed (the AC-12 rule).
  - **Bands:** median recall, precision and severity accuracy are each ≥ the baseline median minus the baseline noise band (max − min across repeats).
  - **Clean tasks:** the new arm's false positives are ≤ the baseline's maximum.

  A failure on any of the three blocks shipping.
- **AC-10 Token gate (bench).** In the same run, the median argus tokens per review record are at least 30% below the baseline's. Argus tokens are the summed input (`input + cache_read + cache_creation`) plus output over the argus subagent's own turns, read by `argus-usage.py` from the transcripts the record's `collected.json` lists (the run's `home/.claude/projects`). Record `tokens` come from the main stream only ([run.py:149–152](../../bench/run.py)), so they're reported next to the gate, never used for it.
- **AC-11 Effort decided by evidence.** A probe shows whether `effort:` in a plugin agent's frontmatter changes that agent's effort on the pinned CLI. If it does, a second arm with `effort: medium` runs the AC-9 gate, and `argus` ships with `effort: medium` only if that arm passes. Otherwise the field stays unset. The decision and its numbers go in §12.
- **AC-12 Real-PR check.** On one product-repo PR the maintainer picks (300–1,500 diff lines, mostly code), `/daedalus:argus <owner/repo#N>` runs with the old and the new plugin build, with the same model and effort. The new run reads the rubric once, takes ≤ 40 turns and uses at least 40% fewer summed input tokens. Every critical or important finding of the old run is in the new run, or the maintainer judges it a false positive.
- **AC-13 Usage report.** `scripts/argus-usage.py` lists each argus subagent run (agent type ending in `argus`) with:
  - turns, first-turn context, final context, summed input and output (exact, from `message.usage`);
  - approximate tool-result tokens by bucket: rubric, bundle, code read, search, shell;
  - rubric source reads and re-read ranges.

  It takes `--projects <dir>` (repeatable; default `~/.claude/projects`), `--since` and `--until` (ISO timestamps, compared with each run's first event), `--project <path substring>` and `--json`. It prints paths and counts only: never tool-result text, and only the program name of a Bash command. Tests use fixture transcripts.
- **AC-14 Shipped and checked.**
  - `scripts/build-plugin.sh` regenerates `plugins/daedalus/` with the new script and skill files and rewritten paths (`${CLAUDE_PLUGIN_ROOT}/scripts/argus-prepare.py`).
  - `scripts/test-all.sh` gains an `argus` check (`scripts/test-argus.sh`) and passes with `--skip detector`; `check-generic.sh`, `lint-packs.sh` and `build-plugin.sh --check` pass.
  - CI runs `scripts/test-argus.sh` as its own step in [check.yml](../../.github/workflows/check.yml), which lists each hub check by name and never calls `test-all.sh`. A later detector change (P1a edits `detect-stack.py`) that breaks the AC-3 import then fails CI, instead of silently sending every `/argus` run back to manual loading.
  - `/argus` Phase C validation rules and the review body format are unchanged.

## 3. Technical design

### 3.1 Flow

| Step | Today | After |
|---|---|---|
| `/argus` Phase A | config → bundle → ticket → size check | config → bundle → ticket → **`argus-prepare.py`** → size check |
| Phase B brief | "Load the argus skill first: SKILL.md, failure-modes.md, the Review sections of …" | `rubric:`, `diff_index:`, `diff_lines:`, and "Read rubric.md once; it is the whole rubric" |
| `argus` load | 5–16 tool calls, including model-run pack detection | One Read |
| `argus` reads | Diff → full touched files | Index → per-file patches → hunk windows; whole files only by the AC-7 rule |
| `/argus-scan` | Agent reads SKILL (Scan mode), failure modes, packs, domain, template | `argus-prepare.py --mode scan` → one Read |

### 3.2 `argus-prepare.py` contract

```
python3 -I argus-prepare.py --bundle <dir> --checkout <dir> --mode pr|local|scan --workspace <dir>
    [--profile-packs a,b] [--stacks auto|a,b] [--extra-stacks a,b]
    [--domain <name>|none] [--house-rules p1,p2] [--ignore g1,g2]
```

- **Location:** finds its `.claude` root from its own path, as `detect-stack.py` does with `HUB`. The skill, packs and templates come from there, so it works on script and plugin installs alike.
- **Domain packs** come from the AC-1 search order instead, because overlays install them outside the plugin: `<workspace>/.claude/skills/argus-rubric/domains/`, then `~/.claude/skills/argus-rubric/domains/` (`Path.home()`, so tests can set `HOME`), then the root's. Each location also tries the pre-rename `skills/argus/domains/`, as the renamed skill does. `--workspace` is the folder the session started from, which `/argus` passes explicitly, as P1a's commands do. The resolved path goes in the header and in `DOMAIN_PATH`.
- **Detector reuse:** imports `detect-stack.py` from its own folder with `importlib.util.spec_from_file_location` (both files sit in `scripts/` in the plugin too). `PACK_DIRS` is honored.
- **Reads:** `pr.json` (`files[].path`) and `diff.patch` from the bundle; root manifests, `head_lines` and house rules from the checkout.
- **Writes:** `rubric.md`; in `pr` and `local` modes also `diff/` and `diff-index.tsv`. Nothing outside `--bundle`.
- **Prints** `KEY=value` lines: `RUBRIC`, `RUBRIC_CHARS`, `PACKS`, `UNCOVERED`, `DOMAIN`, `DOMAIN_PATH`, `MISSING`, `DIFF_INDEX`, and any `WARNING`.
- **Exit codes:** 0 success; 2 usage error; 1 I/O error, with a one-line reason on stderr.
- **Constraints:** standard library only, Python 3.8+, no network, deterministic order everywhere.
- **Section extraction:** from a `## <name>` line to the next `## ` line, ignoring headings inside fenced code blocks.

### 3.3 `rubric.md` layout

```
<!-- argus-rubric mode=local packs=python,serverless-queues uncovered=src/lib/rules.ex domain=loaded:~/.claude/skills/argus-rubric/domains/acme.md missing_house_rules= -->
<!-- rubric-part: skills/argus-rubric/SKILL.md -->
…
<!-- rubric-part: skills/stacks/failure-modes.md -->
…
<!-- rubric-part: skills/stacks/python.md#Review -->
…
<!-- rubric-part: skills/argus-rubric/review-template.md -->
…
```

`argus` copies `packs`, `uncovered` and the domain name from the header into its JSON `stacks`, `uncovered` and `domain` fields, as it does today from its own detection. When the header says `domain=missing`, the verdict says "domain pack <name> not found", as the role's load step 4 already requires for a missing file.

### 3.4 Pack selection (AC-3)

```
changed     = pr.json files minus paths matching ignore
idx         = index_files(changed + root manifests in the checkout)
signal_text = added lines of diff.patch, ignored files excluded
selected    = stacks list                                      if stacks is a list
            = profile_packs ∪ {p | matches_any(idx, p.files) or any(signal_found(s, signal_text) for s in p.signals)}
selected   ∪= extra_stacks (known names only)
uncovered   = [f in changed | f matches no files/weak glob of a selected pack]
```

In scan mode, `/argus-scan` passes the detected stacks as `--stacks`, and the script doesn't detect.

### 3.5 Diff split (AC-4)

Split `diff.patch` at each `diff --git ` line. The status comes from the header lines: `new file mode` → A, `deleted file mode` → D, `rename from` → R, `Binary files … differ` → binary, else M. The path is the `+++ b/` path, or the `--- a/` path for a deletion. Git's C-style quoted paths are unquoted. `packs` lists the selected packs whose globs cover the file, or `-`; `ignored` is `1` or `0`.

### 3.6 Skill split (AC-5)

| Section of `SKILL.md` (current lines) | Goes to |
|---|---|
| Frontmatter, intro, layer table (1–26) | `SKILL.md`; the layer table gains rows for `rubric.md`, `config.md` and `scan.md` |
| Modes (28–34) | `SKILL.md` |
| Configuration (36–62) | `config.md`, verbatim |
| Loading (64–80) | `SKILL.md`, rewritten (AC-5); excluded from the rubric |
| Inputs through Writing rules (82–196) | `SKILL.md`; Inputs gains `rubric.md`, `diff-index.tsv` and `diff/` |
| Scan mode (198–221) | `scan.md`, verbatim |
| Checklist (223–232) | `SKILL.md` |

The SKILL core inside the rubric drops from about 4.3k tokens to about 2.5k. `/argus` itself then reads only `config.md` and `config-template.yml`, not the whole skill.

### 3.7 Role: `.claude/agents/argus.md`

- **Load first:** (1) the brief's `rubric`, read once; its header's `domain` goes into the JSON, and `domain=missing` into the verdict (§3.3). (2) Only when the brief has no `rubric` or the file is missing: today's list, unchanged, as the fallback.
- **Input:** add `rubric`, `diff_index` and `diff_lines`.
- **Procedure (pr, local):** replace "Read full files in `checkout`" with the AC-7 rules and the AC-8 budget.
- **Tools:** unchanged, unless T17 decides otherwise.
- **Return:** unchanged.

### 3.8 Commands

- **`/argus`** (`.claude/commands/argus.md`):
  - The Rules "Skill" line: the command reads `config.md` and `config-template.yml`; the reviewer reads `rubric.md`.
  - Phase A step 0: "the rules in the skill's Configuration section" points to `config.md`.
  - New Phase A step after the ticket: run `argus-prepare.py` with the resolved config and `--workspace <folder you were started from>`. It uses the same path rule as `argus-bundle.sh` (`~/.claude/scripts/`, `<workspace>/.claude/scripts/`, or `${CLAUDE_PLUGIN_ROOT}/scripts/`). On failure, show the error, continue without a rubric, and note it for the Run notes.
  - Phase B brief: add `rubric`, `diff_index` and `diff_lines`, and replace the "Load the argus skill first" line with "Read rubric.md once; it is the whole rubric. Follow the read rules and the turn budget in your role file."
  - Phase C Run notes: add `Rubric: bundle | manual (<reason>) · packs <list> · domain pack <DOMAIN_PATH | missing | none> · ~<RUBRIC_CHARS/4> tokens`. A `missing` domain pack is also said in the reply, next to the config line.
- **`/argus-scan`** (`.claude/commands/argus-scan.md`, lines 16 and 52): after step 3, run `argus-prepare.py --mode scan --stacks <detected>`; the brief names `rubric:`; references to "the Scan mode section of `SKILL.md`" point to `scan.md`.

### 3.9 Rejected: one file per failure family, chosen by the model

- The whole catalog is about 3.4k tokens; picking 6 of 19 families saves about 2k.
- Each separate Read is a turn that resends the whole context (100k+ mid-review), so a few extra reads cost more than they save.
- Choosing needs an index of what each family asks, and that index is most of the catalog.
- Skipping families before reading the code is how findings get missed; FM-18 (tests) and FM-19 (change hygiene) apply to almost every change.

The separation happens where it pays: by mode (`SKILL.md`, `config.md`, `scan.md`) and by pack section, assembled by a script.

### 3.10 Measurement

- **`scripts/argus-usage.py`:** hub-only (`build-plugin.sh` reads only `.claude/`, so it never ships). It finds runs through each transcript's `.meta.json` (`agentType`). Buckets: rubric (`skills/argus-rubric/` and the pre-rename `skills/argus/`, so baseline transcripts still classify; `skills/stacks/`, `domains/`, `rubric.md`), bundle (the bundle folder), code read (any other Read), search (Grep, Glob), shell (any other Bash). A re-read is the same path with an overlapping line range; a Read without `offset` covers the whole file. Byte-based estimates are labeled approximate.
- **Bench:** two new arms (T13). The results files give `review.tp`, `fp`, `fn` and `severity_correct` per record, which feed AC-9. Argus's own tokens and re-reads (AC-7, AC-10) come from `argus-usage.py --projects <run>/home/.claude/projects` over each run folder, because record `tokens` cover the main stream only, and `repeated_reads` ignores ranges. T14 records whether the stream's `result.usage` includes subagent tokens; the probes never compared them ([G1.json:101](../../scripts/probes/cases/G1.json)).

### 3.11 Fit with the hardening roadmap

- **P1a** replaces the prose merge rules with `workflow.py config resolve`. After this plan, those rules live in `config.md`, so P1a's citations of `argus-rubric/SKILL.md:39–50` and `:44–50` move to `config.md`.
- **P1b** T13 edits `argus-bundle.sh`. This plan doesn't touch that script (the split lives in `argus-prepare.py`), so there's no conflict there. P1b's edits to `/argus` Phase B and C must keep the rubric lines.
- **P2 AC-3** removes Bash and says "argus' bundle gains base versions, log and blame for changed files". The diff index and per-file patches are the first part of that, and `argus-prepare.py` is the natural place for the rest.
- **P2 `maxTurns`:** AC-8's turn counts give the data to size it.

## 4. Layer tasks

### Layer: lib (python, ci-cd)

- **Root(s):** `.` (packs `python`, `ci-cd`; `go` and `iac` aren't affected)
- **Needs:** nothing · **Produces:** the `argus-prepare.py` CLI (§3.2), the `rubric.md` and `diff-index.tsv` formats (§3.3, AC-4), the `argus-usage.py` report
- **Tasks:**
  - **Phase 1: measure**
    - [ ] T1 `scripts/argus-usage.py` (AC-13), with fixtures in `scripts/fixtures/argus/transcripts/`: two synthetic runs in a fixture projects folder, one loading the rubric sources with one re-read, one reading `rubric.md` and two hunk windows of the same file (not a re-read), and a planted canary string in a tool result.
    - [ ] T2 Baseline: run `python3 -I scripts/argus-usage.py --since 2026-11-24T00:00Z --until 2026-11-25T20:05Z` (the §1 cutoff) and write the summary table (run ids and counts, no paths, no content) into §12.
  - **Phase 2: prepare script**
    - [ ] T3 `.claude/scripts/argus-prepare.py`: CLI, detector import, selection (AC-3), section extraction, rubric (AC-1, AC-2), diff split and index (AC-4).
    - [ ] T4 `scripts/test-argus.sh` and fixtures in `scripts/fixtures/argus/prepare/` (a small checkout tree, `pr.json`, a `diff.patch` with an addition, modification, deletion, rename, binary file and a path with a space, a profile, a house-rules file); cases in §5.
  - **Phase 3: skill split**
    - [ ] T5 Split `SKILL.md` into `SKILL.md`, `config.md` and `scan.md` (§3.6); rewrite `## Loading`; update the layer table and Inputs.
    - [ ] T6 `rg -n "Configuration section|Scan mode|argus-rubric/SKILL.md" .claude ARCHITECTURE.md README.md`, and fix each reference that now points to the wrong file.
  - **Phase 4: role and commands**
    - [ ] T7 `.claude/agents/argus.md` (§3.7).
    - [ ] T8 `.claude/commands/argus.md` (§3.8).
    - [ ] T9 `.claude/commands/argus-scan.md` (§3.8).
    - [ ] T10 `ARCHITECTURE.md`: the scripts tables (`:46`, `:84`) gain `argus-prepare.py`; review flow steps 1 and 4 (`:214–227`) describe the rubric, the diff index and scoped reads.
  - **Phase 5: ship**
    - [ ] T11 `scripts/test-all.sh`: `run_check argus scripts/test-argus.sh` before `lint-packs`, and the header comment's check list. `.github/workflows/check.yml`: a step `Argus prepare and usage tests` running `scripts/test-argus.sh`, after the plugin check (AC-14).
    - [ ] T12 `bash scripts/build-plugin.sh`, then `bash scripts/build-plugin.sh --check`.
  - **Phase 6: evaluate** (operator: paid, and the bench builds from commits, so the changes must be committed first)
    - [ ] T13 `bench/arms/daedalus-argus-diet.json` (ref: the commit with T1–T12) and `bench/arms/daedalus-argus-diet-medium.json` (ref: a following commit that only adds `effort: medium` to the argus frontmatter). Copy `daedalus-0.4.0.json`'s fields and fairness notes, and add a note naming the difference. `python3 bench/run.py validate bench/arms` passes.
    - [ ] T14 Effort probe (AC-11): one bench review task, k = 1, both new arms. The frontmatter effort counts as honored when the medium arm's argus output tokens (from its transcript, via `argus-usage.py --projects`) are clearly lower, or when the transcript metadata shows the effort. If not honored, drop the medium arm. Also record whether the stream's `result.usage` total includes the argus subagent's tokens (compare it with the transcript's), and tell the bench owner if it doesn't.
    - [ ] T15 Bench run (AC-9, AC-10): `python3 bench/run.py estimate --kind review --arm daedalus-0.4.0 --arm daedalus-argus-diet [--arm daedalus-argus-diet-medium] --k 5`, then `run` with the same arms, `--kind review`, `--k 5` and a `--total-budget-usd` the maintainer sets. From the results files: recall `tp / (tp + fn)` per repeat, the bands, and the paired per-task table (repeats with `tp = 1`, per arm). From each run folder: `python3 -I scripts/argus-usage.py --projects <run>/home/.claude/projects --json` for argus tokens and re-read ranges.
    - [ ] T16 Real-PR check (AC-12): old plugin vs `claude --plugin-dir <hub>/plugins/daedalus` in the product repo; compare with `argus-usage.py`.
    - [ ] T17 `Skill` tool: compare first-turn context with and without `Skill` in the argus tools on the T16 PR. Drop it only if that saves at least 2k tokens per turn, since none of the 17 runs analyzed in detail called it. If dropped, flag roadmap row `:968` (which lists `Skill` for argus) to its owner.
    - [ ] T18 Write the numbers and decisions into §12; set `effort: medium` or leave it unset (AC-11).
- **Tests:** AC → test map in §5.
- **Commands:** the profile confirms only `bash scripts/test-detector.sh` (test) and `bash -n .claude/hooks/session-init.sh` (lint). This plan's checks (`bash scripts/test-argus.sh`, `bash scripts/lint-packs.sh`, `bash scripts/check-generic.sh`, `bash scripts/build-plugin.sh --check`, or all of them through `bash scripts/test-all.sh --skip detector`) aren't in the profile. Confirm them with `/setup` before `/project-manager`, or the test-runner can't run them. `test-detector.sh` fetches public repos over the network and isn't needed here.

## 5. Integration and testing

`scripts/test-argus.sh`:

| Case | Proves |
|---|---|
| `prepare-01` Rubric parts in order, part markers, header comment | AC-1 |
| `prepare-02` Two runs give identical bytes | AC-1 |
| `prepare-03` Profile packs, glob match, signal match; a `weak` glob alone selects nothing | AC-3 |
| `prepare-04` `--stacks` list replaces detection; `--extra-stacks` adds; an unknown name warns | AC-3 |
| `prepare-05` An ignored file selects no pack, isn't uncovered, has `ignored=1` | AC-3, AC-4 |
| `prepare-06` An uncovered file pulls in `_generic.md`'s Review and is listed | AC-1 |
| `prepare-07` Missing domain → `DOMAIN=missing`; missing house rule → `MISSING=`; the rubric still builds | AC-1 |
| `prepare-08` Diff round-trip; A/M/D/R/binary/space path; `head_lines` | AC-4 |
| `prepare-09` Scan mode parts; no `diff/` | AC-2 |
| `prepare-10` A `## ` line inside a code fence doesn't end a section | AC-1 |
| `prepare-11` The plugin copy (`plugins/daedalus/scripts/argus-prepare.py`) gives the same rubric | AC-14 |
| `prepare-12` Domain lookup: with a plugin-layout root and the pack only under a fake `HOME`, `DOMAIN=loaded` and the header names `~/…`; a pack under `<workspace>/.claude/` wins over the one under `HOME`; with neither, `DOMAIN=missing` | AC-1 |
| `skill-01` Every pre-split heading (fixture list) is in exactly one of the three files | AC-5 |
| `refs-01` No reference to the Configuration or Scan mode section points at `SKILL.md` | AC-5 |
| `usage-01` Fixture transcripts → expected JSON | AC-13 |
| `usage-02` The canary planted in a fixture tool result never appears in the output | AC-13 |
| `usage-03` `--projects` reads only the given folder; `--since` and `--until` include and exclude runs by first event; two hunk windows of one file aren't a re-read | AC-7, AC-13 |

AC-6 to AC-12 are role behavior, proven by the operator evaluation (§9).

## 6. File changes

**Create**
- `.claude/scripts/argus-prepare.py`
- `.claude/skills/argus-rubric/config.md`
- `.claude/skills/argus-rubric/scan.md`
- `scripts/argus-usage.py`
- `scripts/test-argus.sh`
- `scripts/fixtures/argus/prepare/**`, `scripts/fixtures/argus/transcripts/**`
- `bench/arms/daedalus-argus-diet.json`, `bench/arms/daedalus-argus-diet-medium.json` (T13)

**Modify**
- `.claude/skills/argus-rubric/SKILL.md`
- `.claude/agents/argus.md`
- `.claude/commands/argus.md`
- `.claude/commands/argus-scan.md`
- `ARCHITECTURE.md`
- `scripts/test-all.sh`
- `.github/workflows/check.yml`
- `plugins/daedalus/**` (regenerated by `build-plugin.sh`, never hand-edited)
- `docs/plans/argus-token-diet.md` §12 (T2, T18)

## 7. Dependencies / env

No new packages: Python 3.8+ standard library, and the existing `git`, `jq` and `gh`. The bench needs its usual boundary (docker image or sandbox), `BENCH_MODEL`, `BENCH_EFFORT`, `--total-budget-usd` and `--t0-verified` (bench README, Commands). At k = 5, T15 costs about two-thirds more per arm than k = 3; `estimate` gives the figure before anything runs.

## 8. Design reference

N/A: no UI.

## 9. Manual QA

N/A: no UI-observable AC. Operator evaluation instead:

| AC | Steps | Pass when |
|---|---|---|
| AC-11 | T14 | Effort honored or not is recorded with evidence; the medium arm is kept or dropped |
| AC-9, AC-10 | T15 | No lost defect (or each one ruled noise in §12); quality within the baseline noise band; argus tokens at least 30% lower |
| AC-6, AC-7, AC-8 | `argus-usage.py` over the T15 and T16 transcripts | One `rubric.md` read and no source reads; re-reads at most half the baseline's; turns within budget, or `not_reviewed` disclosed |
| AC-12 | T16 | ≤ 40 turns, at least 40% fewer input tokens, no lost critical or important finding |

## 10. Risks / potential issues

- **Recall loss from hunk windows.** Context outside ±40 lines can hide a bug. Mitigation: the contract rule forces whole files and callers; AC-9's paired check names every lost defect and blocks shipping; if a lost defect traces back to unread context, widen the window before anything else.
- **Domain packs outside the plugin.** Overlays install domain packs under `~/.claude/`, not in the plugin. Mitigation: the AC-1 search order, the resolved path in the header and Run notes, and `prepare-12`.
- **Turn budget truncates large PRs.** Mitigation: 45 turns over 1,500 diff lines, and unread files are disclosed. P2's `maxTurns` should be sized from AC-8's data, not guessed.
- **Small bench tasks distort the token numbers.** The 25 review tasks are short patches. AC-12 checks one real PR.
- **Conflicts with P1b and P1c.** Both rewrite `/argus`, the `argus` role and `argus-bundle.sh` (P1b: working-tree bundle and review JSON; P1c: role-output validation). This plan runs after P1c and is re-planned against that tree; its first order ("run first") was overtaken when P1a landed before it.
- **`effort:` frontmatter may not be honored.** AC-11 handles both outcomes.
- **Fixed per-turn cost on the user's machine (out of scope).** The duplicated `~/.claude/rules/` files and the double skill listing in this hub repo cost tokens on every turn of every session here. Measure them with `argus-usage.py`'s first-turn context, and decide separately: the global rules also apply to the other Ticketboat repos.

## 11. Next steps

1. Confirm the checks in §4 Commands with `/setup`, so the test-runner may run them.
2. After P1c has landed: re-plan against `main`, measure a new baseline arm, then implement on its own branch from `main` (for example `feat/argus-token-diet`).
3. Run `/clear`, then `/daedalus:project-manager docs/plans/argus-token-diet.md`.
4. Phase 6 (T13–T18) needs the changes committed, and a bench budget. Both are the maintainer's call.
5. When re-planning: point any P1a citation of the rubric's configuration section at `argus-rubric/config.md`, and keep P1b's `/argus` Phase B and C behavior (review assembly, working-tree scope) and P1c's role-output checks.

## 12. Evaluation notes

Filled in by T2 (baseline) and T18 (results and decisions).
