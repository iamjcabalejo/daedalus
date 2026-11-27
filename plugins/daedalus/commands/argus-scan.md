---
description: Scan a repo (or paths in it), in any language or stack, for exploitable security and business-logic issues with Argus (codebase-scan format). Writes docs/scans/<repo>-<date>.md with rule ids, exploitability, blast radius and a paste-ready fix brief. Read-only. Creates tickets only when you confirm.
argument-hint: <repo folder | owner/repo> [paths ...] [--tickets]
disable-model-invocation: true
---

**Scope of this command:** Read-only security scan. Do not change code, config or tests.
- **File you may create:** `docs/scans/<repo>-<YYYY-MM-DD>.md` in the folder you were started from.
- **Tickets:** create them only after the user confirms the finding list in chat, and only when `--tickets` was passed.

## Rules to follow

- **Token policy:** `${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/token-policy.md`.
- **Graphify:** this is orientation, so the graph gate applies (`${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/graphify.md`) when a graph exists. Otherwise use narrow search. Query entry points before reading.
- **Skill:** `argus-rubric`, from the `.claude/` folder this command was loaded from:
  - the **Scan mode** section of `SKILL.md`;
  - `skills/stacks/failure-modes.md`;
  - the packs listed in `.workflow/profile.json` (or detected) from `skills/stacks/`, for their **Entry points (scan mode)**;
  - `scan-template.md`, for the report shape and evidence bar.

## Target

$ARGUMENTS

**Interpret the arguments as:**
- A local repo folder, or `owner/repo`.
  - For `owner/repo`, use a sibling folder with that name if one exists.
  - Otherwise run `gh repo clone <owner/repo> "$(mktemp -d)/repo" -- --depth 1` and remove the clone afterwards.
- Optional paths limit the scope.
- `--tickets` offers to create tickets in the configured system after the scan.

If the arguments are empty, ask which repo and stop.

## Steps

1. **Resolve the checkout and config.**
   - Record HEAD `sha7` and the `owner/repo` (`git remote get-url origin`).
   - Resolve config as `/argus` does: `python3 -I <scripts>/workflow.py config resolve --json --repo <checkout> --workspace <folder you were started from>` (`<scripts>`: where the `project-profile` skill says), and use its `values`. Exit code 3 → show the error and fix, and stop. Read only.
2. **Detect stacks.** Run `detect-stack.py --stdout --root <checkout>` (read-only and current even when the saved profile is stale) and take the union of its packs with those in `.workflow/profile.json`, if present. Without the detector, match the repo's files and root manifests against each pack's `detect.files`. Honor `config.stacks` and `extra_stacks`, and note languages that no pack covers (the detector's `gaps`).
3. **Write `scope.txt`** in a temp bundle folder:
   - the paths given, or the whole repo minus `config.ignore`, `node_modules`, `dist`, `build` and `.venv`;
   - the entry points from each detected pack's **Entry points (scan mode)**;
   - for uncovered languages: HTTP routes, webhooks, queue consumers, scheduled jobs, CLI mains, IaC, CI and config files.
4. **Spawn `argus`** with this brief:

   ```
   mode: scan
   bundle: <folder>
   checkout: <checkout>
   sha7: <sha7>
   config: {stacks: <detected>, extra_stacks: [..], domain: <name|none>, ignore: [..]}
   Read SKILL.md (Scan mode), skills/stacks/failure-modes.md, the detected skills/stacks/*.md, domains/<domain>.md and scan-template.md first.
   ```

5. **Validate the report:**
   - Every finding has Issue, Location, Rule, Exploitability, Data at risk, Evidence, Recommended fix.
   - Severity is `critical` or `high`.
   - Secrets are redacted.
   - No finding fails the evidence bar.

   Send one follow-up if anything fails.
6. **Save** the report to `docs/scans/<repo>-<YYYY-MM-DD>.md`.
7. **Reply:**
   - The summary table: severity, rule, location, issue.
   - Stacks covered and uncovered.
   - The saved path.
   - With `--tickets`: the proposed issue titles, followed by a request for confirmation.
8. **On confirmation:** create the issues with the `ticket-adapters` skill's **create** operation in the configured `tickets.system` (Linear, Jira or GitHub Issues; with `none`, print them instead).

   Follow `scan-template.md` → **Creating tickets**, then list the ids.
9. **Clean up** any temp clone.
