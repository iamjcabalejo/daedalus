---
description: Create one ticket (Linear, Jira or GitHub Issues, through the ticket adapter) with a crystal-clear description; clarify vague input first.
argument-hint: [title]
disable-model-invocation: true
---

**Scope:** Create **one new ticket** with a description anyone can follow (clear structure, no unexplained jargon). Use the `ticket-adapters` skill (`${CLAUDE_PLUGIN_ROOT}/skills/ticket-adapters/SKILL.md`) to resolve `tickets.system` and run its **create** operation. Never claim a ticket was created without a successful tool response.

With `tickets.system: none` (or the tool unavailable), say so, and print the finished ticket as markdown for the user to file.

## Workflow

1. **Understand the ask.** `$ARGUMENTS` is the user's raw intent: a title idea, a paragraph, or a half-baked note.
2. **Clarify** anything critical with short, concrete follow-ups before creating. Minimum bar:
   - **What** is wrong, or what are we building?
   - **Who** is affected (user role or system)?
   - **Done means** what (1–3 observable outcomes)?
   - For bugs: **steps to reproduce**, **expected vs actual**, **environment** if known.
   - **Where it goes:** the team (Linear), project (Jira) or repository (GitHub), if the user didn't say and `tickets.team` doesn't set it.
3. **Resolve the destination.** Linear needs a `team` (list teams if unknown and offer 3–5 sensible options); Jira needs a project key; GitHub uses the profile's `integrations.code_host.repo` unless the user names another.
4. **Create** with:
   - **title:** specific and action-oriented (no "Fix stuff");
   - **description:** the template below, with real newlines;
   - optional fields only when the user asked and the system supports them: priority, project, labels, assignee (`me` when they said "assign to me"), due date, links.

   Don't pass an `id` on create (that's for updates).

## Description template

```markdown
## Summary
[One or two sentences: what this ticket is about.]

## Why it matters
[Business or user impact in plain language.]

## Context
[Background, links, related tickets.]

## What to do
[Numbered steps or bullets; implementation hints welcome.]

## Acceptance criteria
- [ ] ...
- [ ] ...

## Out of scope
- ...

## Notes
[Optional: risks, rollbacks, data considerations.]
```

After the create call succeeds, echo the **identifier**, **title** and **URL** the tool returned, and one sentence on what was filed.

If creation fails, report the error and what you tried; don't pretend the ticket exists.
