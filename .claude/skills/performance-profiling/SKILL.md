---
name: performance-profiling
description: Measure before optimizing; identify bottlenecks with data. Use when optimizing performance, profiling, or running /code-optimize. The stack pack's FM-06 / FM-16 lines name the stack's own profilers and budgets.
---

# Performance Profiling

## Rule: Measure First
Never optimize without profiling. Identify the actual bottleneck before changing code.

## Client (browser UI)
- **Lighthouse / Web Vitals:** LCP, INP, CLS, TTI
- **Browser DevTools:** Performance tab, network throttling
- **Bundle:** the bundler's analyzer (for example vite-bundle-visualizer, webpack-bundle-analyzer, `next build` output)
- **Framework profiler:** for example the React Profiler or Vue DevTools, matching the profile's frameworks

## Server
- **Response time:** P50, P95, P99 from the project's APM or metrics (whatever the repo uses)
- **Database:** slow query log; `EXPLAIN (ANALYZE, BUFFERS)` or the engine's equivalent; the ORM's query logging
- **CPU and memory profilers:** the stack's own (for example py-spy or cProfile for Python, `--prof` or clinic for Node, pprof for Go, dotnet-trace for .NET)
- **Concurrency:** blocking calls on async paths; connection-pool saturation

## Critical Path
- What does the user do first?
- What blocks the initial render?
- What blocks the primary action?

## Before/After
- Record baseline metrics before changes
- Re-measure after each optimization
- Compare before claiming improvement

## Optimization Order
1. Measure and identify bottleneck
2. Fix the biggest impact first
3. Validate with metrics
4. Document the change
