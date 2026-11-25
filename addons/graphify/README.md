# Graphify add-on (optional)

The full `/graphify` skill (build, `--update`, wiki, hooks), kept out of the core workflow because a code graph is optional (AC-13) and the skill is long (about 700 lines, above the 500-line guidance for always-available skills).

The core workflow only needs the `graphify` CLI for `query`, `path` and `explain`, through the `graphify-navigation` skill. Install this add-on when you want Claude to build or refresh graphs itself.

## Install

- **Script install:** `./install.sh --user --addon graphify` (or `--project <path>`), or copy `skills/graphify/` into the `.claude/skills/` folder you installed the workflow into.
- **Plugin install:** copy `skills/graphify/` into `~/.claude/skills/`.
- **Then:** set `graph: graphify` (or leave `graph: auto`) in `.workflow/config.yml`, and build once per root with `/graphify .` or `graphify extract . --code-only`.

Upstream: https://github.com/Graphify-Labs/graphify
