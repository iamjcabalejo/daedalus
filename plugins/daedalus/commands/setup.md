---
description: Detect this project's stacks, commands and integrations, fill the gaps from its docs, confirm the guessed commands with you, and write .workflow/profile.json, plus .workflow/config.yml only for choices you made. Read-only toward project code.
argument-hint: "[--refresh | --print] [repo path]"
disable-model-invocation: true
---

**Scope of this command:**
- **May write:** only `<repo>/.workflow/profile.json`, `<repo>/.workflow/config.yml`, and the user's trust store, through `workflow.py trust record` (step 6).
- **Never** runs project code, installs packages or runs tests. Detection only reads files and runs `git` read commands.
- `--print` writes nothing, including the trust store.

## Rules to follow

- **Token policy:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/token-policy.md`.
- **Skill:** `project-profile` (`skills/project-profile/SKILL.md` in the `.claude/` folder this command was loaded from). It defines confidence levels, unsafe commands and precedence.
- **Scripts:** `scripts/detect-stack.py`, `scripts/validate-profile.py` and `scripts/workflow.py` in that same folder: `~/.claude/scripts/` for a user-level install, otherwise `<workspace root>/.claude/scripts/`; plugin installs use `${CLAUDE_PLUGIN_ROOT}/scripts/`. Run them with `python3 -I`, and pass `--workspace <folder you were started from>` to every `workflow.py` call.

## Target

$ARGUMENTS

**Interpret the arguments as:**
- An optional path. The default is the current repo (`git rev-parse --show-toplevel`), or the folder you were started from.
- `--refresh` re-detects even when the profile is fresh.
- `--print` shows the result and writes nothing.

## Steps

1. **Detect.**
   - `--print`: run `python3 -I <scripts>/detect-stack.py --root <repo> --stdout`.
   - Otherwise: run `python3 -I <scripts>/detect-stack.py --root <repo>` (`--refresh` simply means running it without `--ensure`). Then read `<repo>/.workflow/profile.json`.
2. **Show the profile** as a table per root: path, layer, packs, frameworks, package manager, and each command with its confidence. Then show the UI dev URL, data and infra, tickets, code host and graph, followed by the `gaps`.
3. **Fill the gaps from the repo's own docs.** For each gap, and each missing command on an `api`, `ui`, `worker` or `lib` root, look in README*, CONTRIBUTING*, `docs/`, Makefile, Taskfile, justfile, `package.json` scripts and CI workflows.
   - Propose a value, citing `file:line`.
   - Don't invent commands, and don't run anything to test them.
4. **Confirm with the user.** Ask in one question round (AskUserQuestion; at most 4 questions, then a second round if needed).
   - **Ask about:** every `inferred` command, every proposed gap fill, every `unsafe: true` command, and the ticket system unless detection says `linear`. (`linear` needs both repeated ticket keys and Linear-style branch names. `github` can come from PR numbers alone, since squash and merge commits add `(#N)`.) For the ticket system, offer "leave unset (inherit)" first, so a workspace or home setting still applies; name what it would inherit from `python3 -I <scripts>/workflow.py config explain tickets.system --repo <repo> --workspace <folder you were started from>`.
   - **Options:** "confirm", "change it" (Other = the user's command) or "leave unset".
5. **Record the answers** with the detector, never by hand-editing the JSON:
   - confirm: `python3 -I <scripts>/detect-stack.py --root <repo> --confirm "<root.path>:<name>"`;
   - set or replace: `python3 -I <scripts>/detect-stack.py --root <repo> --set "<root.path>:<name>=<command>"`;
   - then record trust for the command just confirmed or written: `python3 -I <scripts>/workflow.py trust record --repo <repo> --workspace <folder you were started from> --root "<root.path>" --name <name> --channel profile --json`. Exit code 3 → show its `fix` and say that command is not trusted.
6. **Trust the committed commands** (with `--print`, show the list only and never run `trust record`):
   - Run `python3 -I <scripts>/workflow.py trust pending --json --repo <repo> --workspace <folder you were started from>`.
   - Show every `pending` item, grouped by repository (`repo.root`, plus `repo.remote` when set), with its exact `cmd`, `root:name`, channel and level, and `reason`. A `commands` override from the repository (TL4) or the workspace folder (TL3) is listed too; only your own `~/.workflow/config.yml` and organization policy are trusted as they are. Flag each `unsafe: true` item: trusting it never lets it run unasked.
   - Empty list → say "no committed command needs trust", then still run the record command below with that empty list's `set_digest`, without asking: an empty set needs no confirmation. It stores the digests of the detected commands re-detection reproduced (the reply's `detected` list), so the session banner shows them instead of `(untrusted)`.
   - Otherwise ask once (AskUserQuestion): "trust all listed commands" or "trust none". On yes, run `python3 -I <scripts>/workflow.py trust record --pending --digest <set_digest> --repo <repo> --workspace <folder you were started from> --json` with the `set_digest` the list came with. It also stores the reproduced detected commands' digests; they aren't part of the list or its digest.
   - Exit code 3 (`E_TRUST_SET_CHANGED`, `E_TRUST_STORE_UNSAFE`, `E_TRUST_STORE_INVALID`) → show the error's `fix` line and don't claim any trust; for a changed set, show the new list and ask again.
7. **Write `.workflow/config.yml`** only if it doesn't exist. Never overwrite an existing one; show the diff of what you would add instead. If an existing file holds keys this step would no longer write (`stacks: auto`, `graph: auto`, or a `tickets` the user never chose), list them and suggest removing them, since they hide inherited settings.
   - **Write choices, not defaults.** An explicit value here (including `none`) wins over the same key in the workspace, `~/.workflow/config.yml` and the legacy `.argus.yml` files (`workflow.py config explain <key>` shows it). Write a key only when the user chose it in step 4, or when detection is unambiguous (today, only a `linear` ticket system).
   - **`tickets`:** write it without asking only when detection says `linear`. Otherwise write it only when the user picked a system in step 4: an explicit "this repo has no tickets" becomes `none`, and picking `github` writes `{system: github, key: '#\d+'}`. Write the profile's `key` only when it isn't null **and** belongs to the system being written: the pick matches the detected system, or detection was `unknown` (keys found, system unclear) and the pick is `linear` or `jira`. A `#\d+` key goes only with `github`. Otherwise leave `key` out so it is inherited (picking `linear` on a `github`-detected repo writes `{system: linear}`). When the user left the system unset, leave `tickets` out, key included.
   - **Never write defaults:** no `stacks: auto` and no `graph: auto`. Write `stacks: [..]` only when the user asks to pin packs.
   - **Nothing to write?** Don't create the file, and say that config is inherited.

   ```yaml
   # Workflow settings for this repo: choices only. Keys left out are inherited from the workspace
   # and user levels; `workflow.py config explain <key>` shows where a value comes from.
   tickets: {system: linear, key: '<regex from the profile>'}   # only for a detected linear, or a system the user picked
   ```

8. **Validate:** run `python3 -I <scripts>/validate-profile.py <repo>/.workflow/profile.json`, and fix any error by re-running the detector.
9. **Reply:**
   - the final table;
   - what was confirmed, set or left unset, and which commands are now trusted (or why trust wasn't recorded);
   - the remaining gaps;
   - a reminder to commit `.workflow/profile.json` and `.workflow/config.yml` so the team shares them, while personal overrides go in `~/.workflow/config.yml`.

Never commit or push. Never write outside `<repo>/.workflow/`, except the trust store through `workflow.py trust record`.
