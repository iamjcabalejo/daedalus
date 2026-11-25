---
name: graphify-navigation
description: Optional graph-first orientation with the Graphify CLI (query / path / explain) when a project root has graphify-out/graph.json. Use from planning, implementation and review only when the profile shows a graph or .workflow/config.yml sets graph: graphify; otherwise use plain search.
---

# Graph navigation (optional)

A [Graphify](https://github.com/Graphify-Labs/graphify) knowledge graph can cut exploration cost by avoiding full-tree reads. It's an accelerator, never a requirement.

Phase budget authority: `.claude/rules/graphify.md`.

## When it applies

Use a graph only when **one** of these holds:
- `.workflow/config.yml` sets `graph: graphify`;
- `graph: auto` (the default) and the profile shows `integrations.graph.graphify: true`, or `<root>/graphify-out/graph.json` exists.

With `graph: none`, or no graph on disk, skip this skill: use narrow search (Grep or Glob on the route, symbol or error) and read only what it points to. **Never tell the user to build a graph** unless they ask how.

## Phase budget

| Phase | With a graph |
|---|---|
| **ASK / PLAN** (architecture, file mapping) | Query before broad search |
| **Code** (plan has concrete File changes) | Plan-first: read the listed files; query only for gaps or blast radius |
| **Review** (diff, AC and handoffs available) | Diff-first; query only for dependency or blast-radius questions |
| Editing only workflow files (`.claude/`, `.cursor/`) | Skip |

## Commands

From the root (or with `--graph <root>/graphify-out/graph.json`):
- "Where is X?" or architecture → `graphify query "<question>" --budget 1500`
- A ↔ B relationship → `graphify path "<A>" "<B>"`
- One symbol or concept → `graphify explain "<concept>"`

Then Read or Grep only the files the graph pointed to. If `<root>/graphify-out/wiki/index.md` exists, use it for broad orientation; read `GRAPH_REPORT.md` only when query, path and explain aren't enough.

## Subagent handoff

Only when a graph applies, give each role a phase-appropriate line:
- **Code:** "Graph: plan-first (File changes); query only for gaps or blast radius. Root: `<root>`. After edits: `graphify update .` if the CLI is available."
- **Review:** "Graph: diff-first; query only for dependency or blast radius. Root: `<root>`."

Prefer one scoped query per root in the orchestrator, and pass a short summary instead of having each role re-query.

## After code edits

In each modified root that has a graph: `graphify update .` (AST-only). Skip silently if `graphify` isn't on PATH, and note it in the implementation notes.

## Building a graph

Building, `--update`, wiki and hooks live in the optional graphify add-on (`addons/graphify/` in the workflow repo) or upstream. Don't load them for routine queries.
