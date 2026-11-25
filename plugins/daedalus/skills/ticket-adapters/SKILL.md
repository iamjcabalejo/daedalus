---
name: ticket-adapters
description: >-
  How workflow commands read, create and update tickets (Linear, Jira, GitHub Issues or none) and
  read chat and calendar activity (Microsoft Teams, Slack or none), chosen from .workflow/config.yml
  and the project profile. Use from /create-ticket, /refine-spec, /apply-ticket, /daily-report and
  /argus whenever a ticket or chat source is involved.
---

# Ticket and chat adapters

Commands never call a ticket or chat tool directly. They name an **operation** below, and this skill maps it to the configured system.

## 1. Resolve the systems

Read config key by key, nearest first (the same chain Argus uses): `<repo>/.workflow/config.yml`, `<workspace>/.workflow/config.yml`, `~/.workflow/config.yml`. A missing or `null` value falls through; an explicit value wins.

| Setting | Values | When unset |
|---|---|---|
| `tickets.system` | `linear`, `jira`, `github`, `none`, `auto` | the profile's `integrations.tickets.system`, then `auto` |
| `tickets.key` | a regex for ticket keys in titles, branches and commits | the profile's `integrations.tickets.key`, then `[A-Z][A-Z0-9]+-\d+` |
| `tickets.team` | default team or project for new tickets | ask once when creating |
| `chat` | `teams`, `slack`, `none` | `none` |

**`auto`** resolves in this order: `linear` if a key matches and a Linear MCP is connected; `jira` if a key matches and a Jira MCP is connected; `github` if the profile's `integrations.code_host.kind` is `github` and `gh` is signed in; otherwise `none`.

**Unavailable tools:** if the resolved system's tool isn't available (no Linear or Jira MCP, `gh` not installed or not signed in, no Teams or Slack MCP), print one line, for example `Tickets: jira is configured but no Jira MCP is connected; continuing without tickets.`, and continue as `none`. Never guess tool calls.

Tool names differ per install (MCP servers get prefixes). Match on the tool's base name, and read its schema before the first call.

## 2. Ticket operations

| Operation | `linear` (MCP) | `jira` (MCP) | `github` (`gh`) | `none` |
|---|---|---|---|---|
| **get** a ticket | `get_issue` (`includeRelations: true`), plus `list_comments` | the issue-get tool, plus comments | `gh issue view <N> -R <repo> --json number,title,body,url,state,labels,comments` | skip; say "no ticket system" |
| **find** keys in text | regex `tickets.key` | regex `tickets.key` | `#\d+` and `close[sd]?\|fix(e[sd])?\|resolve[sd]? #N` | — |
| **list mine** in a window | `list_issues` assignee `me` with `updatedAt` / `completedAt` / `state` filters | a JQL search: `assignee = currentUser() AND updated >= <date>` | `gh search issues --assignee=@me --updated=">=<date>"` and `gh search prs --author=@me --updated=">=<date>"` | skip |
| **create** a ticket | `save_issue` (needs `team`; `list_teams` if unknown; never pass `id`) | the issue-create tool (needs a project key) | `gh issue create -R <repo> --title … --body-file <tmp>` | print the draft; create nothing |
| **update** the description | `save_issue` with `id` (or `patch`) | the issue-edit tool | `gh issue edit <N> -R <repo> --body-file <tmp>` | print the new text |
| **comment** | `save_comment` | the comment tool | `gh issue comment <N> -R <repo> --body-file <tmp>` | print the comment |

- **Repo for `github`:** the profile's `integrations.code_host.repo`, or `gh repo view --json nameWithOwner`.
- **Bodies:** pass real newlines, not `\n` escapes. For `gh`, write the body to a temp file and use `--body-file`.
- **Ticket fields used by plans:** title, description, acceptance criteria (a checklist in the body), labels, status, URL, and the comments that change scope.

## 3. Chat and calendar operations (`/daily-report`)

| Operation | `teams` (Microsoft 365 MCP) | `slack` (Slack MCP) | `none` |
|---|---|---|---|
| **who am I** | `get_me` | the user-info / auth-test tool | — |
| **my messages** in a window | `chat_message_search` query `*`, `sender` = me, `afterDateTime` | message search `from:@me after:<date>` | skip |
| **blocker mentions** | `chat_message_search` for `blocked OR blocker OR "waiting on" OR stuck OR "need access"` | message search with the same words | skip |
| **meetings** | `outlook_calendar_search` for the window and the next working day | a connected calendar MCP, if any; otherwise skip | skip |

Messages may be in any language; summarize in the report's language.

## 4. Safety

- **Reads** are fine whenever a command needs them.
- **Writes** (create, update, comment) happen only when the running command is itself the user's request to write (`/create-ticket`, `/refine-spec` once unblocked), and only to the ticket the user named. Report the identifier and URL that the tool returned; never claim success without it.
- **Chat is read-only.** Never post to Teams or Slack. If the user asks afterwards, show the exact text and target and wait for their yes.
- Never put personal data in URLs or query strings beyond what the tool requires.
