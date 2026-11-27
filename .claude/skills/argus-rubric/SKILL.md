---
name: argus-rubric
description: >-
  Argus, the hundred-eyed PR and repo reviewer: a stack-agnostic rubric with material findings
  only, each with a failure scenario, location, fix and cost, graded
  critical / important / consider by outcome. A universal failure-mode catalog,
  auto-detected stack packs (any language or platform; core-only fallback for
  unknown stacks), optional domain packs and per-repo config. Use when running
  /argus or /argus-scan, when spawning the argus agent, or when the
  user asks for an Argus review. Calibrated on production code reviews.
---

# Argus (stack-agnostic core)

This rubric was calibrated on production code reviews across many stacks, plus security scan findings. It is organized in layers, so a new stack needs a short pack, not a rewrite.

| Layer | File | Scope |
|---|---|---|
| Core | this file | Procedure, materiality gate, severity, writing, re-review. Applies to every stack. |
| Failure modes | [../stacks/failure-modes.md](../stacks/failure-modes.md) | 19 universal bug families (FM-01…FM-19), each with its question, signals and grading. Shared with every role. |
| Stack packs | `../stacks/<name>.md` (the `stacks` skill) | How the families show up in one technology. Argus reads each pack's `## Review` section (and `## Entry points (scan mode)` in scans). Packs come from the project profile plus any pack whose `detect` globs match the diff (globs alone when there is no profile). |
| Domain pack | `domains/<name>.md` | Business invariants and sibling paths for one organization. Opt-in through config. |
| House rules | repo docs named in config | Team-specific checks for one repo. |
| Output | [review-template.md](review-template.md), [scan-template.md](scan-template.md) | Exact shapes. |

**Read-only.** This skill never edits code, never approves or requests changes, and never posts. Posting belongs to the command, and only when the user passes `--post`.

## Modes

| Mode | Input | Output |
|---|---|---|
| `pr` | One PR at one head SHA | Review body |
| `local` | Current branch diff against its base, before a PR exists | The same body. "PR description" checks use the plan doc or commit messages. |
| `scan` | A repo, or paths in it | Scan report |

## Configuration

The command resolves config with `workflow.py config resolve --json` and passes the result in the brief. The resolver reads every level (repository, workspace, user, organization), including the legacy `.argus.yml` files, and applies the merge rules in code; never read or combine config files yourself. `workflow.py config explain <key>` shows where a value came from and what was ignored.
- **Key placement.** In `.workflow/config.yml`, `stacks`, `extra_stacks`, `domain`, `tickets`, `ignore` and `house_rules` are top-level, and Argus-only settings live under `review:` (`header`, `max_findings`, `severity`, `post`). Legacy `.argus.yml` files keep `severity` and `post` top-level, with `header` and `max_findings` under `review:`; the resolver lifts them to `review.severity` / `review.post`.
- **Sources.** The brief lists the files the resolver read (`config.sources`), and the saved review's run notes name the file that supplied `domain` and `tickets.system` (or "default").

Every key is documented in [config-template.yml](config-template.yml).

Defaults when nothing is configured:
- `stacks: auto`
- `domain: none`
- `tickets.system: auto` (Linear if a key matches and the MCP is available, else GitHub `#N` closing refs, else none)
- `ignore`: lockfiles, vendored, generated and minified files, snapshots
- no severity overrides
- header "Argus review"

## Loading (do this before reviewing)

1. **Stacks.** Load the union of two sources:
   - **the profile:** with `.workflow/profile.json`, the `roots[].packs` of each root that contains a changed file (read the `project-profile` skill);
   - **the diff:** every pack whose `detect.files` globs match a changed path (or a manifest at the repo root). The profile reflects the tree at its last detection, and a new file type (a first `.sql` migration, a first Lambda handler) doesn't make it stale, so the diff check always runs.

   Without a profile, the diff check alone decides.
   - `detect.signals` (imports or keywords) also qualify a pack.
   - `detect.weak` globs (shared extensions such as `.ts`, `.sql`, `.yaml`) count only when one of the pack's `files` globs or `signals` also matches. Once the pack loads, it covers those files.
   - `stacks: [..]` in config replaces auto-detection.
   - `extra_stacks` adds packs on top.
2. **Unknown stacks.** If a changed file matches no pack, apply `../stacks/failure-modes.md` with `../stacks/_generic.md`. Infer idioms from the repo itself: README, CONTRIBUTING, lint or format config, existing tests, and the surrounding code. Then:
   - list the language under `not covered by a stack pack:` in the verdict;
   - add `pack_suggestions` to the JSON block (never to the posted body).
3. **Domain.** If `domain` is set, load `domains/<domain>.md`. If it isn't there, try the legacy `skills/argus/domains/<domain>.md` in the same `.claude/` folder. Its invariants and critical triggers extend this file.
4. **House rules.** Read each file listed in `house_rules`. They extend the checks; they never lower the materiality gate.
5. **Ignore.** Skip paths matching `ignore`, and mention them only if a finding depends on them.

## Inputs (the command builds this bundle)

- `pr.json`: title, body, base and head refs, head SHA, changed files.
- `diff.patch`: the unified diff at the head SHA.
- `checkout`: the repo at the head SHA. Read full files there, not only hunks.
- `ticket.md`: the linked issue (Linear, GitHub, Jira, …) with its acceptance criteria, or `none`.
- `prior.md`: earlier review bodies from this tool, with their `argus-finding` ids, or `none`.
- `replies.md`: author comments posted after the last review, or `none`.

If an input is missing, say so in the verdict ("ticket not found", "not reviewed: <file>"). Never guess its content.

## Procedure (pr / local)

1. **Ticket → AC list.** Number each acceptance criterion and requirement. After reading the code, mark each one met, not met, or not visible.
2. **Claims list.** Extract every behavioral claim from the PR description and test plan.
3. **Read the change.**
   - Start with the diff, then read the full touched files.
   - Read callers and callees when a hunk changes a contract.
   - Use a code graph or LSP for blast radius when one exists; plain search otherwise.
4. **Apply the failure modes.** For every changed path, ask each relevant family's question (FM-01…FM-19), using the loaded stack packs' signals, the domain invariants and the house rules.
5. **Follow sibling paths.** Every fix must reach every sibling path:
   - create, update, delete and transfer;
   - legacy and new request shapes;
   - every provider or handler variant;
   - maintenance routes and imports;
   - any sibling paths the domain pack lists.
6. **Weigh tests as evidence** (see Tests).
7. **Reconcile prior findings** (see Re-review).
8. **Apply the materiality gate**, grade severity, then apply any severity overrides from config.
9. **Write the body** from review-template.md, using the header from config.

## Materiality gate

Keep a finding only if **all** of these hold:

- **Scenario:** a concrete input, state or sequence leads to a wrong outcome: wrong data, a lost write, an open exploit, an outage, a misleading approval, or real cost. "Could be cleaner" fails.
- **Location:** a `path:line` or `path:start-end` at the head SHA, or "PR description" / "ticket" for ownership findings.
- **Fix:** the smallest change that closes it. Offer alternatives only when a product decision is needed.
- **Not style:** no naming, formatting, comment wording or import order, and no generic "add tests".
- **Not a duplicate:** one finding per root cause. Merge candidates that share a location and cause, keep the sharpest title, and grade at the highest severity any of them earned.
- **"Verify" asks:** a "confirm X" item with no concrete failing scenario in the diff is `consider` at most.

## Severity (by outcome, not by technology)

| Severity | Use when |
|---|---|
| `critical` | Merging causes harm right away, with no edge case needed: an open exploit, or a security fix that doesn't close what it claims; money or goods lost or duplicated; data or messages silently and permanently lost, or an audit trail removed; a broken deploy or production system; a live credential exposed; debug code that runs on every request or writes to disk in prod. |
| `important` | A wrong outcome under normal use: wrong or lost data; an unmet AC that changes data, money, access or what someone acts on; a write that fails after commit; a hot-path query or fan-out that grows with data; unbounded cost growth; duplicated logic that has already diverged; a description or test plan that would make an approver sign off on behavior that isn't there. |
| `consider` | A conditional edge case, an unmet AC whose impact is UX-only, moderate perf or cost, deploy ordering with low risk, duplication that may drift, or an assumption to verify. |

When unsure, pick the lower level and say what would raise it. Grade by outcome: the same root cause is `important` when wrong data persists, and `consider` when it only returns a generic error.

**Always critical, in any stack:**
- An alert or operator message that instructs the wrong action, such as "don't buy again" on a partly completed purchase.
- A rate limiter or claim that can grant twice.
- Financial totals that mix currencies, or treat a missing FX rate as 1.
- A route or job that fails on every call.
- Certain breakage on merge: an applied migration edited or re-versioned, invalid SQL, queue retention cut below the outage window, an invalid schedule expression.
- A live credential committed, including one deleted but still unrotated in history.

**Category thresholds:**

| Category | `important` when | `consider` otherwise |
|---|---|---|
| performance | An unbounded scan, per-row query, fan-out, or blocking call on a hot or async path | Moderate or occasional cost |
| cost | It grows without bound every run, or bypasses an external limiter | Bounded warehouse credits or object-store writes |
| architecture / pattern_fit | It breaks a ticket promise, or a duplicate copy has already diverged | Plain duplication, hard-coded limits |
| ownership | A description or test plan misleads an approver on a security fix, a merge blocker or a promised alarm | Most other description/diff gaps |
| debug scaffolding | A hard-coded local path, or a helper left in a shared file | Stray prints |
| secrets | Rotation is unverified (live values are `critical`) | Mutable CI tags, test-only CVEs, keys in URLs with no exposure shown |

**Calibration** (production code reviews): critical 2%, important 48%, consider 50%, and 39% of reviews are clean. Criticals are about 40% security, 39% correctness, 15% reliability and 7% ownership.

## Categories

Each finding gets one category. The failure modes map onto them as follows.

| Category | Covers | Main families |
|---|---|---|
| correctness | Wrong results, unmet AC, data semantics | FM-02, FM-03, FM-09, FM-11, FM-17, FM-18 |
| security | Authz, secrets, injection | FM-13, FM-14 |
| reliability | Failure handling, concurrency, budgets, deploys, config | FM-01, FM-04–FM-08, FM-10, FM-12, FM-15 |
| performance | Latency and throughput at scale | FM-06, FM-16 |
| cost | Spend that grows | FM-05, FM-16 |
| architecture | A layer that can't enforce, readers and writers out of step | FM-10, FM-13, FM-19 |
| pattern_fit | Duplicated or divergent logic | FM-19 |
| ownership | Description, ticket and scope truth, scaffolding | FM-19 |

## Tests

Tests are evidence, not a category. Never file "missing tests".

- **Praise** a test that proves behavior, and name it in **Done well**.
- **Flag** a test that doesn't exercise the path it claims to, never runs, or contradicts the description (FM-18).
- **In a Fix**, name the specific regression test that would fail before the fix.

## Re-review

When `prior.md` exists:

1. Classify each prior `argus-finding` id as **verified fixed**, **answered by your replies**, or **still open**.
2. Still-open findings keep their id and title, with `(still open from an earlier revision)` on **Where**.
3. If a reply doesn't resolve a finding, add **On your reply:** with the evidence it misses.
4. Print the non-zero counts on **Since the last revision**.
5. Never re-raise an open finding under a new title.

## Writing rules

- **Verdict:** one sentence, ≤400 chars. State whether the change does what it and its ticket claim, and name the main open risk. Add "not reviewed: …" and "not covered by a stack pack: …" when either applies.
- **Done well:** exactly one item, specific (a mechanism, file or test name).
- **Finding title:** ≤110 chars, stating the consequence, not the code smell.
- **Finding paragraph:** ≤370 chars, inputs → wrong outcome, using code identifiers.
- **Bullets:** `Fix` and `Where` always; `Cost` unless there is no trade-off; `On your reply` only on re-review.
- **Order:** severity, then the order in which the code runs.
- **No findings:** use the exact clean sentence from the template.

## Scan mode

Use [scan-template.md](scan-template.md). Walk the entry points that the loaded stack packs list under **Entry points (scan mode)**. For unknown stacks, walk:
- HTTP routes, webhooks, queue consumers, scheduled jobs and CLI mains;
- IaC, CI and config files.

Apply these families:

| Family | Rule ids | Evidence bar |
|---|---|---|
| `secrets.*` | `committed_live`, `in_logs_or_bundle` | The value grants access. Account ids, emails and queue URLs are **not** secrets. |
| `infrastructure.*` | `iam_wildcard`, `secrets_in_environment`, `public_resource`† | Cite the policy and the resources it actually reaches. |
| `injection.*` | `sql`, `command`†, `template`† | Show the untrusted source → string-built sink path. A bound parameter is **not** injection. |
| `authz.*` | `idor`, `missing_server_check`†, `role_bypass`† | Show the endpoint and the missing server-side check. |
| `biz.*` | `unauthenticated_webhook`, `race_money`, `no_rate_limit`, `workflow_skip` | Show the reachable entry point and the business effect. |
| `supply.*` | `unpinned_dependency`†, `secrets_in_environment` | Cite the manifest or build step. |

† Not seen in the calibration scans; added to round out a family. Prefer an observed id.

Scan severity is `critical` or `high` only.
- **Exploitability:** `unauthenticated remote`, `authenticated low priv` or `authenticated high priv`.
- **Data at risk:** `business data` or `credentials`.

Dedupe by location and cause. Redact secrets to their first 4 characters plus the length.

## Checklist

- [ ] Config resolved; stack packs detected; unknown stacks noted
- [ ] Domain pack and house rules loaded when configured
- [ ] Ticket AC listed and graded; description claims checked
- [ ] Full touched files read, plus callers when a contract changed
- [ ] Every relevant FM question asked; sibling paths followed
- [ ] Each finding passed the gate, with a scenario, Where and Fix
- [ ] One finding per root cause; prior ids reused
- [ ] Exactly one Done well; verdict ≤400 chars; unread files disclosed
