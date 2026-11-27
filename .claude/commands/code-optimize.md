---
description: Analyze and optimize code for performance, memory and efficiency in the project's own stack (measure first)
argument-hint: [file]
disable-model-invocation: true
---

Optimize the following code for performance and efficiency.

## Code to optimize

$ARGUMENTS

## Rules to follow

- **Stack knowledge:** `.claude/rules/stack-knowledge.md`. Find the file's root in `.workflow/profile.json` and read its packs (`## Build`, and FM-06 / FM-16 under `## Review`) for the stack's budgets, blocking calls and profilers.
- **Skill:** `performance-profiling`: measure first, then optimize.
- **Roles:** apply the `agent-selection` skill: the `implementer` perspective for the change, the `argus-rubric` skill to self-check. When following a performance rework list, implement only those items and report before/after metrics.

## Strategy

1. **Measure first.** Find the real bottleneck with the stack's profiler or the database's query plan (for example `EXPLAIN ANALYZE`). Don't optimize prematurely; record a baseline.
2. **Server side:**
   - **Data access:** indexes for hot filters and joins, batching instead of N+1, pagination, connection pooling.
   - **Concurrency:** no blocking calls on async paths; timeouts and bounded retries on external calls; bounded parallelism.
   - **Caching:** only with a clear invalidation rule; cache keys include every input.
3. **Client side:**
   - **Rendering:** avoid needless re-renders (memoization where measured), virtualize long lists, debounce input-driven requests.
   - **Bundle:** route-level code splitting, dynamic imports for heavy libraries, tree-shaking.
   - **Data:** reuse the repo's data-fetching cache; don't refetch large sets on an interval.
4. **Verify.** Re-measure after each change, and run the root's `test` command (safe commands only).

## Output

- **Analysis:** the bottlenecks found (or rework items addressed), with the baseline
- **Optimized code**
- **What changed and why**
- **Before/after metrics** (or the expected improvement, when measuring isn't possible here)
- **Implementation notes** (in a cycle): done, deferred, assumptions

Never optimize without measuring first.
