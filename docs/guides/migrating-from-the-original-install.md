# Migrating from the original install

The original version of this workflow was built for the Ticketboat stack: fixed backend and frontend roles, per-stack rules, Linear and Teams wired into commands, and an Argus reviewer with a Ticketboat domain pack in the tree. The plug-and-play version keeps all of that behavior, but splits it into a generic hub plus a private **ticketboat overlay**.

## What changed

| Original | Now | Notes |
|---|---|---|
| `backend-architect`, `frontend-architect` | `implementer` | Spawned once per affected layer; stack idioms come from the packs |
| `backend-reviewer`, `frontend-reviewer` | `argus` (via `/argus --local`) | Accessibility checks moved into the `web-frontend` pack's Review section |
| — | `test-runner` | Runs the profile's safe checks after the implementers |
| `rules/python-backend.md`, `api-routes-python.md`, `csharp-backend.md`, `api-routes-csharp.md`, `react-frontend.md`, `typescript.md` | `skills/stacks/<pack>.md` → Build and Test | Loaded by the files you touch, through the profile |
| `/api-new`, `/api-test` | `/scaffold endpoint <name>`, `/test-gen <target>` | Work in any detected framework |
| Backend / C# Backend / Frontend task blocks in plans | `### Layer: <layer> (<packs>)` blocks | `/project-manager` still reads old plans and maps them to layers |
| Linear and Teams in commands | the `ticket-adapters` skill + `tickets.system` / `chat` in config | The overlay sets `linear` and `teams` |
| `skills/argus/domains/ticketboat.md` in the tree | `overlays/ticketboat/skills/argus-rubric/domains/ticketboat.md` | Private |
| `skills/argus/` (`SKILL.md` and templates) | `skills/argus-rubric/` | Renamed so `/argus` runs the command, not a skill of the same name. Domain packs left in `skills/argus/domains/` are still read |
| `skills/trace-flow/` | `skills/flow-tracing/` | Renamed so `/trace-flow` runs the command |
| `.argus.yml`, `~/.claude/argus.yml` | `.workflow/config.yml`, `~/.workflow/config.yml` | The old files are still read, merged key by key after the new ones |
| Graphify required | optional (`graph: auto`) | Used only when a graph exists |
| `skills/graphify` (build skill) | `addons/graphify/` | `install.sh --addon graphify` |

## Steps

1. **Have the overlay.** It's the gitignored `overlays/ticketboat/` folder in your clone of this repo, or your team's encrypted backup (restore steps: `overlays/_template/README.md`).
2. **Install over the old files**, with a dry run first:

   ```bash
   ./install.sh --user --overlay overlays/ticketboat --prune-legacy --dry-run
   ```

   ```bash
   ./install.sh --user --overlay overlays/ticketboat --prune-legacy
   ```

   - **`--prune-legacy`** backs up and removes the retired files listed above, so old roles and rules don't load next to the new ones.
   - **Overwrites:** files the install overwrites (for example `agents/argus.md`) are backed up too.
   - **Hooks:** older hook entries in `~/.claude/settings.json` that point at `${CLAUDE_PROJECT_DIR}/.claude/hooks/…` are replaced by `~/.claude/hooks/…` paths, which also work in projects that don't have their own `.claude/hooks/`.
   - **Workspace installs:** if you used a workspace-level install (`<workspace>/.claude`), run the same command with `--project <workspace>` instead of `--user`.
3. **Plugin instead?** Install `daedalus` (and `daedalus-qa` for the admin UI), copy `overlays/ticketboat/` to `~/.claude/overlays/ticketboat/`, put its `config.yml` keys in `~/.workflow/config.yml`, and copy the domain pack to `~/.claude/skills/argus-rubric/domains/`. Then remove the old files by hand: the paths in the table, under `~/.claude`.
4. **Run `/setup` once per repo** (admin-frontend, admin-api-python, admin-api-csharp, the data repos). Confirm the commands, and commit `.workflow/`.
5. **Compare once.** Run `/feature-plan` for a small change in one repo and `/argus --local` on a known branch, then check the plan sections and the review against what the old install produced (this is AC-11's parity check).

## Behavior notes

- **Domain pack in other repos:** `domain: ticketboat` in your personal config applies to every repo you open, including non-Ticketboat ones. Set `domain: none` in those repos' `.workflow/config.yml`.
- **Browser QA:** QA reads the admin frontend's sign-in signals from the overlay's `qa/auth.md` instead of from the skill.
- **Daily report:** `/daily-report` reads the overlay's `daily-report/sources.md` for the git roots (`~/Documents/TicketBoat`), Linear and Teams.
- **No Go, Rust or other toolchain installed?** The test runner reports those checks as BLOCKED (env) instead of failing the change.

## Rolling back

`./install.sh --uninstall --user` removes the new install and restores every file it backed up or pruned. To go back to the original workflow in this repo, check out a commit from before the plug-and-play work (`58e9fcc`, "Rename NRD reviewer to Argus and make the rubric stack-agnostic") and install from there the old way.
