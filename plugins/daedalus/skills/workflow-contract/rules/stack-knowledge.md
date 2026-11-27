# Stack knowledge (always on)

Stack-specific guidance lives in **packs**, not in rules:
- the packs are in `${CLAUDE_PLUGIN_ROOT}/skills/stacks/<pack>.md` (the `stacks` skill);
- the universal bug families are in `${CLAUDE_PLUGIN_ROOT}/skills/stacks/failure-modes.md`.

**Before planning, coding, testing or reviewing:**
1. **Read the profile.** `.workflow/profile.json` (the `project-profile` skill) says which root a file belongs to, that root's `packs`, and its commands. If it's missing, run `/setup`, or `detect-stack.py --stdout` for a read-only look.
2. **Load the packs for that root, and only the sections your role needs:**
   - implementer: `## Build` and `## Test`;
   - test-runner: `## Test` and `## Commands`;
   - reviewer: `## Review`;
   - scan: `## Entry points (scan mode)`.
3. **No packs for the root?** Use `_generic.md` plus the repo's own conventions, and say which files had no pack.
4. **Repo rules win.** The repo's own config and `house_rules` in `.workflow/config.yml` override pack defaults.
5. **Commands:** run only the commands `workflow.py config commands --json` reports `trusted: true` and `unsafe: false` (the `project-profile` skill); ask the user before any other, or run `/setup`. Never run an `unsafe: true` command without asking.

Never copy profile values or pack content into other rules: they change as the repo changes.
