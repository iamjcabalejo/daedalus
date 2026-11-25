---
description: Review a PR (or the current branch before a PR exists) with Argus, in any language or stack. Material findings only, graded critical / important / consider with Fix / Where / Cost, checked against the linked ticket. Stack packs come from the project profile plus the diff, and .workflow/config.yml (or the legacy .argus.yml) configures it. Saves docs/reviews/<repo>-<N>-<sha7>.md; posts to GitHub only with --post.
argument-hint: <owner/repo#N | PR URL | N> [--sha <commit>] [--compare] [--post] | --local [base-ref]
disable-model-invocation: true
---

**Scope of this command:** **AGENT (Review)**, read-only. Do not change application code, config, tests or plans.
- **Files you may create:** `docs/reviews/<repo>-<N>-<sha7>.md` (local mode: `docs/reviews/<repo>-<branch>-<sha7>.md`) in the folder you were started from.
- **Posting:** you post to GitHub only when the arguments include `--post`. When you do, the review is always a `COMMENT`, never `APPROVE` or `REQUEST_CHANGES`.

## Rules to follow

- **Token policy:** `.claude/rules/token-policy.md`. Build the bundle, hand it off, and validate what comes back. Do not re-review the code yourself.
- **Graphify:** Diff-first (`.claude/rules/graphify.md`). The reviewer queries only for blast radius.
- **Skill:** `argus`, in `skills/argus/` of the same `.claude/` folder: the core `SKILL.md`, `domains/`, `review-template.md` and `config-template.yml`.

## Target

$ARGUMENTS

**Interpret the arguments as:**
- `owner/repo#N` or `https://github.com/owner/repo/pull/N` → PR mode.
- A bare `N` → PR mode in the repo of the current folder (`gh repo view --json nameWithOwner`).
- `--local [base-ref]` → review the current branch against `base-ref` (default `origin/<default branch>`), before a PR exists.
- `--sha <commit>` → review the PR at an earlier commit (calibration).
- `--compare` → after the review, compare it with NRD Sight's review of the same commit.
- `--post` → post the review to the PR.

If the arguments are empty, ask for the PR and stop.

## Phase A — Config and bundle

0. **Resolve config.**
   - Read **every** file that exists in this chain, nearest first (the repo is the checkout, or the current repo for `--local`):
     1. `<repo>/.workflow/config.yml`, then the legacy `<repo>/.argus.yml`;
     2. `<folder you were started from>/.workflow/config.yml`, then `<folder you were started from>/.argus.yml`;
     3. `~/.workflow/config.yml`, then `~/.claude/argus.yml`;
     4. the defaults in `config-template.yml`.
   - Merge **key by key** with the rules in the skill's Configuration section: the nearest file that sets a key wins; mappings merge recursively; lists are replaced whole; `null` or empty falls through; an explicit `none` or `[]` wins. A `.workflow/config.yml` that sets only some keys never hides the rest.
   - Lift a legacy top-level `severity` or `post` to `review.severity` / `review.post` before merging.
   - Record the files you read as `config.sources` in the brief, and note which file supplied `domain` and `tickets.system` (or "default") for Phase C. Read these files only; never create one in a product repo.
   - If `<repo>/.workflow/profile.json` exists, note the `packs` of each root that contains a changed file as `profile_packs` in the brief. The reviewer adds packs whose globs match the diff.
   - Keep the resolved `tickets.key` for step 1.
1. Run `scripts/argus-bundle.sh` from the `.claude/` folder this command was loaded from: `~/.claude/` for a user-level install, otherwise `<workspace root>/.claude/`; in a plugin install, `"${CLAUDE_PLUGIN_ROOT}/scripts/argus-bundle.sh"`. Call it as `"$HOME/.claude/scripts/argus-bundle.sh"` (or the workspace path) from the folder you were started from, with the PR arguments: `<owner/repo> <N> [--sha …] [--workspace <folder you were started from>]`, or `--local [base]`. Keep the `KEY=value` lines it prints.
   - The script needs `gh` (signed in), `git` and `jq`.
   - Pass `ARGUS_TICKET_RE='<tickets.key>'` in the environment when config sets it.
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
  sources: [<files read, nearest first>]
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

1. Read `<COMPARE>`. If it is `none`, say NRD Sight has not reviewed this PR and skip this phase. If `same_sha: false`, say which commit NRD reviewed.
2. Match findings by root cause: the same file and the same failure, with lines within about 20 of each other or the same symbol.
3. Append this to the saved file. It is never posted.

```markdown
## Comparison with NRD Sight (<nrd sha7>)

| NRD finding | Ours | Match | Severity |
|---|---|---|---|
| [important · correctness] … | #2 … | yes / partial / missed | same / higher / lower |
| — | #3 … | extra | — |

Recall: <matched>/<NRD total> · Extra: <n> · Severity agreement: <same>/<matched>
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
