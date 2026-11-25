---
description: Draft my daily report (what I did, what I'll do next working day, blockers) from local git commits and pushes, the ticket system and chat (through the ticket and chat adapters). Read-only.
argument-hint: [48h | 3d | since <date time> | next=<YYYY-MM-DD>]
disable-model-invocation: true
---

**Scope:** Read-only. Gather my activity from local git, the configured ticket system and the configured chat, then print a paste-ready report. Never post to chat, edit tickets, or run `git fetch`/`push`. If I ask afterward to post it, show the exact text and target and wait for my yes.

**Token policy:** `.claude/rules/token-policy.md`. Fetch in parallel, keep only the fields you need, no raw dumps in the reply.

**Sources:** `tickets.system` and `chat` resolve per the `ticket-adapters` skill (`.claude/skills/ticket-adapters/SKILL.md`). If an overlay is installed and has `daily-report/sources.md` (under `<.claude>/overlays/<overlay>/` or `~/.claude/overlays/<overlay>/`), read it too: it names extra sources, team conventions and the report's target format.

## 1. Resolve the window

From `$ARGUMENTS`:

| Input | Window |
|---|---|
| empty | last 24 hours |
| `48h`, `3d` | that many hours or days back |
| `since <date time>` | from that local time to now |
| `next=<YYYY-MM-DD>` | overrides the next working day |

- **Shift date:** today's local date, or yesterday's if it's before 12:00 local (covers shifts that run past midnight).
- **Next working day:** the next Mon–Fri after the shift date.
- If the default window turns up nothing in every source, widen to 72 hours once (covers Monday after a weekend) and say so in the footer.

## 2. Gather (one parallel batch)

**Git (local repos):** run `scripts/daily-git-activity.sh --since "<window start>"` from the `.claude/` folder this command was loaded from (`~/.claude/` for a user-level install, else `<workspace root>/.claude/`; in a plugin install, `"${CLAUDE_PLUGIN_ROOT}/scripts/daily-git-activity.sh"`). It lists, per repo one level under each root, my commits (all branches, merges included), pushes from the remote-tracking reflog, the current branch, uncommitted file count and unpushed commits. Roots come from `DAILY_REPORT_ROOTS` (colon-separated; pass the roots the overlay's `sources.md` names, if any), else the workspace root holding that `.claude/` folder, or the current folder for a user-level install. It only sees pushes made from this machine.
If `gh` is on PATH and signed in, also run `gh search prs --author=@me --updated=">=<date>"` and `gh search prs --reviewed-by=@me --updated=">=<date>"`. Otherwise skip; merged PRs still show as merge commits.

**Tickets** (the adapter's operations; skip when `none`):
- **list mine** updated in the window, completed in the window, in progress (carries into tomorrow), and the top 25 not started (candidates for tomorrow). Keep: id, title, status, priority, due date, labels, project, URL, updated and completed times.
- **get** any ticket whose key (from `tickets.key`) appears in commit subjects or branch names and isn't loaded yet.
- **comments** on up to 8 tickets updated in the window, to find blocker or hand-off notes.

**Chat** (the adapter's operations; skip when `none`):
- **who am I**, then **my messages** in the window (page once more if there's more).
- **blocker mentions** in the window; keep only those in my conversations that involve me or my tickets.
- **meetings** between the window start and now, and on the next working day (from 12:00 to 12:00 the day after, since evening shifts cross midnight).
- Messages may be in any language. Summarize in English.

If a source fails or isn't connected, continue with the rest and name it in the footer. Don't retry the same failing call.

## 3. Correlate and classify

- Group everything by ticket key. A branch like `<user>/eng-464-...` means ENG-464. Work with no key groups under its repo name.
- **What I did:** tickets completed or moved to a new status; commits and pushes summarized as outcomes per ticket (not a commit list); merged PRs as `repo#N`; chat threads where I unblocked, reviewed or coordinated; notable meetings (skip routine stand-ups).
- **Next working day:** in-progress tickets with the remaining step inferred from the latest commit or WIP; branches with uncommitted or unpushed work; PRs awaiting review or merge; top not-started tickets by due date, then priority; meetings that day; follow-ups I promised in chat ("I'll check tomorrow").
- **Blockers:** tickets with a Blocked status or label, or blocked-by relations; comments or messages saying I'm waiting on someone (review, access, deploy, data, decision). Name who or what it waits on. If nothing qualifies, write `None`.
- Every bullet must trace to a source item. Don't invent work, owners or dates. Mark guesses with `(inferred)`.

## 4. Output

Print only this block, ready to paste into chat. Max 6 bullets per section, one line each, plain language, no commit hashes:

```markdown
**Daily Report: <Ddd, Mon D, YYYY (shift date)>**

**What I did today**
- ENG-123 <Ticket title>: <outcome>. <PR / status, e.g. merged repo#106, moved to In Review>

**What I'll do next working day (<Ddd, Mon D>)**
- ENG-124 <Ticket title>: <next step>

**Blockers**
- None
```

Then, below a `---`, one footer line: the window used, item counts per source (`tickets n, git n commits / n pushes, chat n messages / n meetings`), and any source that was unavailable or skipped.
