# Core Standards

**Context:** each project's stack is detected into `.workflow/profile.json` (languages, frameworks, layers, commands); stack-specific idioms live in the packs under `.claude/skills/stacks/` (see `stack-knowledge.md`). These standards apply in every stack. All timestamps and APIs use UTC. Configuration comes from the environment; no hard-coded secrets (use the project's secret manager, or a local, git-ignored `.env` for development). Prefer stateless services and disposable processes (12-factor).

## Type safety
- Use the strongest practical typing the language offers: explicit types at module and API boundaries, no escape hatches (`any`, untyped `object`, unchecked casts) unless unavoidable, and narrowing or type guards instead of assertions.
- Validate untrusted input at the boundary with the stack's schema tool (named in the pack's Build section).
- Run the project's type checker when one is configured (`typecheck` in the profile).

## Error handling
- Handle errors explicitly; never swallow them with empty catch blocks or bare excepts, and don't catch the broadest exception type unless you rethrow.
- Log before rethrowing, with context (operation, input summary). No secrets or personal data in logs; redact tokens and keys.
- Use small domain-specific error types when they make handling clearer.

## Function design
- Keep functions focused on one concern; extract when they pass about 30 lines.
- Prefer pure functions; keep side effects at the edges.
- Use early returns and guard clauses to reduce nesting.

## Naming
- Use meaningful names; avoid abbreviations except common ones (`id`, `url`, `err`, `req`, `res`).
- Booleans read as questions: `isLoading`, `hasError`, `canEdit` (in the language's case convention).
- Functions start with a verb: `fetchUser`, `validateInput`, `formatDate`.
- Follow the language's own conventions (for example snake_case in Python and Ruby, camelCase in JavaScript and Java, PascalCase for types).

## General
- Prefer immutable bindings and values; avoid magic numbers and strings (use named constants).
- Comment *why*, not *what*; code should explain itself.
- Validate all inputs at the boundary; encode or sanitize output that is re-rendered. Use parameterized queries only; never interpolate SQL.

## Session communication and context
- **Answer shape, handoff brevity, code citations vs pastes, and batched tool use** are defined in `token-policy.md`; follow it in every session. It also covers **refine → hand off** before commands, roles and skills, and **internal XML task blueprints** for complex work.
- **Codebase orientation:** `graphify.md` applies only when the project has a code graph; otherwise use narrow search.
- **Stack rules** come from the packs (`stack-knowledge.md`) and the repo's own conventions, and are additive. If something conflicts about how much to say or what to put in a diff, `token-policy.md` wins for the agent's own communication.
