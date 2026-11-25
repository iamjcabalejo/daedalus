---
name: stacks
description: >-
  Stack knowledge packs shared by every role: how to build, review and test code in a
  given technology (python, node-js, go, csharp-dotnet, web-frontend, sql-migrations,
  data-warehouse, iac, ci-cd, serverless-queues), plus a generic fallback and the
  universal failure modes. Use when planning, implementing, testing or reviewing files:
  load the packs that .workflow/profile.json lists for the root you're working in.
---

# Stack knowledge

There is one pack per technology. Every pack has the same sections, so each role reads only what it needs:

| Section | Read by | Holds |
|---|---|---|
| `## Build` | implementer, architect | Conventions and idioms to follow when writing code in this stack |
| `## Review` | argus (reviewer) | How the universal failure modes (`failure-modes.md`) show up here, plus stack-only checks |
| `## Test` | test-runner, implementer | Frameworks, layout, fixtures, what to mock, the regression-test pattern |
| `## Commands` | /setup, the detector, test-runner | How to find and confirm the install, test, lint, typecheck, build and dev commands |
| `## Entry points (scan mode)` | `/argus-scan` | Where an attacker or a request enters |

## Which packs to load
1. **The profile lists them.** `.workflow/profile.json` gives `roots[].packs` for the root that contains the file. Read the `project-profile` skill first.
2. **No profile, or a root with `packs: []`:** load [_generic.md](_generic.md) and infer idioms from the repo itself (README, lint and format config, existing tests, the surrounding code). Say which files had no pack.
3. **More than one pack** is normal. For example, a Python Lambda worker uses `python` plus `serverless-queues`, and a Next.js app uses `web-frontend` plus `node-js`. Apply all of them. When they conflict, the more specific pack wins (the framework over the language).
4. **Repo rules win.** `house_rules` in `.workflow/config.yml` and the repo's own lint config override a pack's defaults. Packs describe common good practice, not a house style.

## Files
- **The universal bug families**, used by every pack: [failure-modes.md](failure-modes.md) (FM-01…FM-19).
- **The fallback for unknown stacks:** [_generic.md](_generic.md).
- **The template for a new pack:** [_template.md](_template.md).
- **Packs:**
  - languages: `python.md`, `node-js.md`, `go.md`, `csharp-dotnet.md`;
  - frontend: `web-frontend.md`;
  - data: `sql-migrations.md`, `data-warehouse.md`;
  - platform: `iac.md`, `ci-cd.md`, `serverless-queues.md`.

A file is a pack only if its frontmatter has a `detect:` block. The detector (`scripts/detect-stack.py`) reads `detect.files`, `detect.weak` and `detect.signals` from it, so keep that frontmatter accurate when you edit a pack.
