---
description: Reverse-engineer a page or user action from route load through API calls, functions, database, and UI. Writes a trace with a simplified flowchart that names every hop.
---

**Scope of this command:** Read-only reverse engineering. Do not change application code, config, or tests. The only file you may create or update is the trace at `docs/traces/<slug>.md`.

## Rules to follow

- **Token policy:** Apply `.claude/rules/token-policy.md` first. Refine the argument into one entry point (page, route, or action), then trace. No filler in the trace or the chat reply.
- **Profile:** read `.workflow/profile.json` to find the UI root and the server roots (`roots[].layer`), their frameworks and data stores.
- **Orientation:** when a root has a graph, apply `.claude/rules/graphify.md` and the `graphify-navigation` skill for it; otherwise start from one narrow search (route path or page name). Don't walk the tree to orient.
- **Trace skill:** Apply `.claude/skills/trace-flow/SKILL.md` for the layer order, evidence rules, and flowchart. Write the artifact with `.claude/skills/trace-flow/output-template.md`.

## Target

$ARGUMENTS

**Interpret the arguments as:** a page, route, or user action (for example `opening the sales order page`, or `/sales-orders`). Derive `<slug>` in kebab-case (for example `sales-order-page`). If the user gives a path under `docs/traces/`, update that file. If arguments are empty, ask for the entry point and stop.

**Default scope:** the initial load — route match through the first successful data render, including every request that fires on mount. Expand click, submit, or filter handlers only when the user names that action or asks for the whole page including actions.

## Agent definitions (read-only perspective)

**Apply the agent-selection skill** (`.claude/skills/agent-selection/SKILL.md`): read the relevant definitions and use them to decide what to look for. Do not spawn them to implement or review a diff.

**Relevant roles:** `implementer` (its view of the ui layer — route, state, data fetching, render — and of the api and data layers — handler, service, query, tables) and `technical-writer` (trace doc shape).

## Output

1. **Write** `docs/traces/<slug>.md` using every section in the output template. Every API and function on the traced path appears in the flowchart node label and in the hop table. Cite `file:symbol` for each hop. Mark hops you could not open as **unverified**. Do not invent handler names, SQL, or table names.
2. **Reply** with the mermaid flowchart first, then the ordered process (one line per hop), then unverified hops. Point at the trace path.

Do not implement or modify application code.
