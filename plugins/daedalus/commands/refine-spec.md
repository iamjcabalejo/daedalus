---
description: Read a ticket (Linear, Jira or GitHub Issues, through the ticket adapter), refine its spec per token-policy (tight brief + optional XML), ask or suggest when ambiguous, and update the ticket when unblocked; no product code.
argument-hint: [ticket-id]
disable-model-invocation: true
---

**Scope:** Refine a **ticket** into a **prompt-shaped spec** so developers and implementation agents do not burn context re-deriving scope. This is the **planning** step where missing requirements, acceptance criteria, constraints, and out-of-scope boundaries belong.

## Claude Code: spec only

Do not change application code, add implementation files, refactor, or run builds, tests, or installs. Updating the ticket (description, optional title) through the ticket adapter is allowed. PLAN behavior: `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/claude-code.md`.

If the user asks you to implement or edit code, decline and point them to **project-manager** / feature agents after the ticket spec is complete.

## Token policy (mandatory)

Apply **`${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/token-policy.md`** before you write the final spec:

1. **Ingest** the issue: title, description, relations, and comments.
2. **Refine** into: one clear **objective**; **in / out of scope**; **constraints** and **forbidden** (negative rules) where they matter; testable **acceptance criteria**; **assumptions** only when you must ship a draft and ambiguity remains.
3. For **complex, ambiguous, or high-stakes** work, add a short **internal XML blueprint** (per token-policy: `<role>`, `<task>`, `<forbidden>`, `<error_handling>`, `<output_format>`, optional `<analysis>`) — see **“Issue body structure”** below. Skip the XML block only for trivial, fully specified one-line tickets.
4. **Hand off** in the issue body: the refined spec must be **scannable** (headings, lists) and **copy-pastable** into **/apply-ticket**, **/feature-plan** or **/project-manager** without a second clarification round.

**Responses in chat:** concise, no filler, no engagement bait. Match effort to ticket size; one-line tickets get a light touch.

## Ticket system (through the adapter)

Use the `ticket-adapters` skill (`${CLAUDE_PLUGIN_ROOT}/skills/ticket-adapters/SKILL.md`) to resolve `tickets.system` (Linear, Jira, GitHub Issues or none). Don't invent ticket content from memory.

### Required reads (in order)

1. **get** the ticket with its relations (and customer context when the system has it and it helps).
2. **comments**, paging as needed so no substantive comment is missed.

If **get** fails: stop, report the error, and ask once for a valid id. With `tickets.system: none` (or the tool unavailable), ask the user to paste the ticket text, refine it, and print the result instead of saving it.

## Ticket id (mandatory)

**Arguments:** `$ARGUMENTS`

- One ticket id: a key matching `tickets.key` (for example `ENG-123`), a GitHub issue number or URL, or a UUID.
- If **empty** or implausible: don't call a tool with a guess. Ask once: _"Provide the ticket id (for example ENG-123 or #42)."_

## When the ticket is ambiguous

**Goal:** make the work legible, not to stall forever.

- If **blocking** information is missing (e.g. no success criteria, no user/system boundary, no repro for a bug, conflicting comments), do **not** **update** the description yet. Output **3–6 concrete questions** (numbered) or **suggested options** the team can pick from. You may still output a **draft** refined structure with an **“Open questions”** section so the next run is fast.
- If the ticket is only **mildly** thin, add an **Assumptions** subsection (short, labeled bullets) and proceed to update; note in chat that those assumptions can be revisited.
- If **relations** (blocks, related) change scope, call them out in **In scope** / **Out of scope** and in **Dependencies**.

## Refined spec content (what “good” includes)

The updated description (and your chat summary) should cover, as applicable:

- **Objective** — one sentence.
- **Problem / goal** — plain language.
- **In scope / out of scope** — explicit.
- **Constraints** — time, performance, security, feature flags, backwards compatibility, locales, etc.
- **Forbidden** — what not to do (per token-policy negative rules) when it reduces implementation drift.
- **User / system impact** — who is affected.
- **Acceptance criteria** — numbered, testable (AC-1, AC-2, …; Given/When/Then or checklist as fits).
- **Definition of done** — observable outcomes.
- **Technical notes** — API touchpoints, data, migrations, feature areas (high level only; no product code in this command).
- **Risks / open questions** — only what still matters after refinement.

## Ticket body structure (markdown)

Use this order so humans and **AI** can parse the ticket reliably:

1. **Summary** — 1–2 sentences.
2. **Refined spec** — sections from “Refined spec content” above, as apply.
3. **Implementation brief (for agents)** — for non-trivial work, a **fenced** block ` ```xml ` … ` ``` ` (or a clearly labeled `### XML blueprint` section) containing the **token-policy** internal blueprint. Keep it **short**; the checklist in token-policy applies. Include `<error_handling>` for “if data is missing, do not invent” when relevant.
4. **Source** — one line: “Refined from: original title/description & N comments; relations: …” if useful for audit (optional, brief).

**Title:** if the current title is vague, propose a **clearer, action-oriented** title. Update the title together with the description only if the new title is strictly better and not a scope change the team did not ask for; otherwise only update `description`.

## Saving to the ticket

- If there are **no blocking open questions** (or the user explicitly asked to **apply the draft** with its assumptions), run the adapter's **update** operation with the full refined markdown (and the title, per above). Report the identifier and URL the tool returned.
- If **blocking questions** remain, **don't** overwrite the team's description: output the questions and the draft. Use the adapter's **comment** operation with a short note and the questions **only** if the team wants a record on the ticket before answering (sparingly).
- `tickets.system: none`: print the refined text; save nothing.

## Handoff (chat, closing lines)

- Tell the user the ticket is ready for **/apply-ticket** (read the ticket → plan), then **/project-manager** for Code → Review → QA.
- If an XML block was added, state that it is for **downstream agent prompts** and matches **token-policy**.

## Cross-command relationship

- **create-ticket** — file new work.
- **refine-spec** (this) — **spec quality gate**; align the description with token-policy before heavy planning.
- **apply-ticket** — read the ticket and write the repo plan (the ticket is unchanged).
