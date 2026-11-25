# Graphify (optional code graph)

A [Graphify](https://github.com/Graphify-Labs/graphify) knowledge graph is an optional accelerator for orientation. **This rule applies only when a graph is in use:**
- `.workflow/config.yml` sets `graph: graphify`; or
- `graph: auto` (the default) and the profile shows `integrations.graph.graphify: true`, or `<root>/graphify-out/graph.json` exists.

With `graph: none`, or no graph on disk: skip this rule, use narrow search (Grep or Glob on the route, symbol or error), and read only what it points to. **Never tell the user to build a graph** unless they ask how.

Details: `${CLAUDE_PLUGIN_ROOT}/skills/graphify-navigation/SKILL.md`. Use the CLI (`graphify query` / `path` / `explain`) for orientation; building and refreshing graphs is the optional graphify add-on's job.

## Phase budget (when a graph is in use)

| Phase | Graph use |
|-------|-----------|
| **ASK / PLAN** (`/feature-plan`, `/apply-ticket`, discovery) | Query before broad search: `graphify query "…" --budget 1500` (or `path` / `explain`). Write concrete paths into the plan's File changes. |
| **Code** | Plan-first. Read the files the plan lists. Query only for gaps, neighbours or unclear blast radius. |
| **Review / Test** | Diff-first. Use the plan's AC, the diff and the implementation notes. Query only for dependency or blast-radius questions. |
| **Rework Code** | Prefer the rework plan's paths; query only if unclear. |
| **After substantive edits** | `graphify update .` in each modified root that has a graph (AST-only, no LLM); skip if the CLI isn't installed. |
| **Workflow files** (`.claude/`, `.cursor/`) | Skip. |

**Orchestrator tip:** `/project-manager` and `/apply-ticket` may run **one** scoped query per root and pass a short summary into role briefs, so roles don't each re-query the same scope.

## Graph gate (when the phase calls for orientation and a graph is in use)

1. Resolve the target root(s) from the profile.
2. From each root that has `graphify-out/graph.json` (or with `--graph <root>/graphify-out/graph.json`):
   - architecture or "where is X?" → `graphify query "<question>" --budget 1500`
   - A ↔ B relationship → `graphify path "<A>" "<B>"`
   - one symbol or concept → `graphify explain "<concept>"`
3. Roots without a graph: narrow search; don't walk the tree.
4. Then Read or Grep only the files the graph, the plan's File changes or the diff point to.

If `<root>/graphify-out/wiki/index.md` exists, navigate it for broad orientation. Read `GRAPH_REPORT.md` only when query, path and explain aren't enough. If the user opts out, or the graph is known to be stale, skip it.

Include a short, phase-appropriate graph line in role briefs only when a graph is in use.
