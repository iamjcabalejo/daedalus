---
description: Review a PR (or the current branch before a PR exists) with Argus, in any language or stack. Material findings only, graded critical / important / consider with Fix / Where / Cost, checked against the linked ticket. Stack packs come from the project profile plus the diff, and .workflow/config.yml (or the legacy .argus.yml) configures it. Saves docs/reviews/<repo>-<N>-<sha7>.md; posts to GitHub only with --post.
argument-hint: <owner/repo#N | PR URL | N> [--sha <commit>] [--compare] [--post] | --local [base-ref]
disable-model-invocation: true
---

**Scope of this command:** **AGENT (Review)**, read-only. Do not change application code, config, tests or plans.
- **Files you may create:** `docs/reviews/<repo>-<N>-<sha7>.md` (local mode: `docs/reviews/<repo>-<branch>-<sha7>.md`) in the folder you were started from.
- **Posting:** you post to GitHub only when the arguments include `--post`. When you do, the review is always a `COMMENT`, never `APPROVE` or `REQUEST_CHANGES`.

## Rules to follow

- **Token policy:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/token-policy.md`. Build the bundle, hand it off, and validate what comes back. Do not re-review the code yourself.
- **Graphify:** Diff-first (`${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/graphify.md`). The reviewer queries only for blast radius.
- **Skill:** `argus`, in `skills/argus/` of the same `.claude/` folder: the core `SKILL.md`, `domains/`, `review-template.md` and `config-template.yml`.

## Target

$ARGUMENTS

**Interpret the arguments as:**
- `owner/repo#N` or `https://github.com/owner/repo/pull/N` → PR mode.
- A bare `N` → PR mode in the repo of the current folder (`gh repo view --json nameWithOwner`).
- `--local [base-ref]` → review the current branch against `base-ref` (default `origin/<default branch>`), before a PR exists.
- `--sha <commit>` → review the PR at an earlier commit (calibration).
- `--compare` → after the review, compare it with the review that the GitHub account in `review.compare_with` (for example, another review bot) posted on the same commit.
- `--post` → post the review to the PR.

If the arguments are empty, ask for the PR and stop.

## Phase A — Config and bundle

0. **Resolve config.**
   - Run `python3 -I <scripts>/workflow.py config resolve --json --repo <repo> --workspace <folder you were started from>`, where `<scripts>` is the `scripts/` folder step 1 names and the repo is the checkout, or the current repo for `--local`. It reads every level, including the legacy `.argus.yml` files, and applies the merge rules; don't read or combine config files yourself.
   - Exit code 3 is a configuration error: show its code, file, line and fix, and stop.
   - Fill the brief's `config` from `values` (`stacks`, `extra_stacks`, `domain`, `ignore`, `house_rules`, `review.*`), and `config.sources` from `sources` (level and path). For Phase C, `provenance` names the file that supplied `domain` and `tickets.system` (its `source`, or "default"). Never create a config file in a product repo.
   - If `<repo>/.workflow/profile.json` exists, note the `packs` of each root that contains a changed file as `profile_packs` in the brief. The reviewer adds packs whose globs match the diff.
   - Keep the resolved `tickets.key`, and with `--compare` the resolved `review.compare_with`, for step 1.
1. Run `scripts/argus-bundle.sh` from the `.claude/` folder this command was loaded from: `~/.claude/` for a user-level install, otherwise `<workspace root>/.claude/`; in a plugin install, `"${CLAUDE_PLUGIN_ROOT}/scripts/argus-bundle.sh"`. Call it as `"$HOME/.claude/scripts/argus-bundle.sh"` (or the workspace path) from the folder you were started from, with the PR arguments: `<owner/repo> <N> [--sha …] [--workspace <folder you were started from>]`, or `--local [base]`. Keep the `KEY=value` lines it prints.
   - The script needs `gh` (signed in), `git` and `jq`.
   - Pass `ARGUS_TICKET_RE='<tickets.key>'` in the environment when config sets it.
   - With `--compare`, pass `ARGUS_COMPARE_WITH='<review.compare_with>'` in the environment when config sets it.
   - If the script fails, show its error and stop.
2. **Ticket**, through the `ticket-adapters` skill (it resolves `tickets.system`, including `auto`, and says what to do when a tool is missing):
   - **`linear`** or **`jira`:** **get** each key in `TICKET_KEYS` (title, description, URL).
   - **`github`:** find `close[sd]?|fix(e[sd])?|resolve[sd]? #N` refs in the PR body, then **get** each issue.
   - **`none`:** skip.
   - **A plan instead of a ticket** (`/project-manager` passes the plan path): use the plan's Acceptance criteria as the ticket.

   Write the first ticket that resolves to `<BUNDLE>/ticket.md` as `# <KEY>: <title>` followed by the description. If none resolve, leave `none` and note "no linked ticket".
3. **Size check.** If `DIFF_LINES` is over 6,000, tell the user, list the largest files from `pr.json`, and continue. The reviewer will disclose any files it could not read.

## Phase B — Review

Spawn **`argus`** with the Agent tool and this brief. Pass paths, not file contents:

```
mode: <pr|local>
bundle: <BUNDLE>
checkout: <CHECKOUT>
review_id: <REVIEW_ID>
sha7: <SHA7>
config:
  sources: [<level and path of each file config resolve read>]
  stacks: <auto | [..]>
  profile_packs: <[..] | none>
  extra_stacks: [..]
  domain: <name | none>
  ignore: [..]
  house_rules: [..]
  severity: {overrides: [..], critical_triggers: [..]}
  review: {header: "<header>", max_findings: <n>}
Load the argus skill first: SKILL.md, skills/stacks/failure-modes.md, the Review sections of profile_packs plus the packs whose detect globs match the diff, domains/<domain>.md, house rules, review-template.md. Diff-first graphify budget; plain search if no graph.
Return the review body, then the json block.
```

Never pass `<COMPARE>` or its contents to the reviewer.

## Phase C — Validate and save

1. **Check the body** against these rules:
   - It starts with `## <review.header>` (default `## Argus review`).
   - It has one verdict sentence and exactly one `**Done well:**`.
   - Every finding line matches `^\*\*\d+\. \[(critical|important|consider) · (correctness|security|reliability|performance|cost|architecture|pattern_fit|ownership)\] .+\*\*$`.
   - Every finding has `- Fix:` and `- Where:` and is followed by `<!-- argus-finding:… -->`.
   - It ends with the `argus-review` marker.
   - If there are no findings, the clean sentence is present.
2. **If a rule fails**, send the reviewer one follow-up via SendMessage naming the failures. Accept the second answer whatever it is, and note any remaining issue in the reply.
3. **Save** the body to `docs/reviews/<repo>-<N>-<sha7>.md`. Create `docs/reviews/` if needed. Put the json block under a `<details><summary>findings.json</summary>` at the end of the file. Before it, add a `<details><summary>Run notes</summary>` block with the line `Config: domain <value> from <file>; tickets.system <value> from <file>` (write "default" when no file set it). Neither block is posted.

## Phase D — Compare (only with `--compare`)

1. Read `<COMPARE>`.
   - `unconfigured`: say `--compare` needs `review.compare_with` (the GitHub login of the reviewer to compare with, such as `my-reviewer[bot]`) in `.workflow/config.yml` or an overlay, and skip this phase.
   - `none`: say that reviewer has not reviewed this PR, and skip this phase.
   - Otherwise, the first line names the reviewer and its commit. If `same_sha: false`, say which commit it reviewed.
2. Match findings by root cause: the same file and the same failure, with lines within about 20 of each other or the same symbol.
3. Append this to the saved file. It is never posted.

```markdown
## Comparison with <reviewer> (<reference sha7>)

| Reference finding | Ours | Match | Severity |
|---|---|---|---|
| [important · correctness] … | #2 … | yes / partial / missed | same / higher / lower |
| — | #3 … | extra | — |

Recall: <matched>/<reference total> · Extra: <n> · Severity agreement: <same>/<matched>
```

## Phase E — Post (only with `--post`)

1. **Pick inline comments.** For each finding with `"new": true` whose `path:line` is listed in `<RIGHT_LINES>`, build one inline comment from the template.
2. **Post one review:**

```bash
jq -n --arg sha "$SHA" --rawfile body <saved-body-without-details-or-comparison> --argjson comments '<[{path,line,side:"RIGHT",body}]>' \
  '{commit_id:$sha, event:"COMMENT", body:$body, comments:$comments}' \
| gh api -X POST "repos/$REPO/pulls/$N/reviews" --input -
```

3. **If GitHub rejects an inline line (422)**, post again without that comment and say so.
4. **Local mode has no PR**, so never post. Say: run again with the PR number after you open it.

## Phase F — Clean up and reply

1. Run the same `argus-bundle.sh` with `--cleanup <ROOT>`.
2. Reply in this order:
   1. The verdict sentence.
   2. One line per finding: `severity · category — title (path:line)`.
   3. Prior findings: fixed / answered / open counts.
   4. The config line: where `domain` and `tickets.system` came from.
   5. The comparison summary line, if `--compare` was used.
   6. The saved path, and "posted" or "not posted".

When `/project-manager` or a rework plan consumes the result, map **critical** and **important** to **Critical**, and **consider** to **Suggestion**.
