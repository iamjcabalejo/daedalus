---
name: agent-selection
description: Select and load the right role (subagent) definitions before a task. Use when a command or workflow needs a specialized role (implementer, test-runner, argus, qa-tester, tech-stack-researcher, technical-writer) without duplicating the role list in every command.
---

# Role selection

Use this skill whenever a command says "apply the agent-selection skill": pick the roles that fit, load their definitions, and brief them with what the profile says about the project.

## 1. Roles

Role files live in `.claude/agents/`. In a plugin install, spawn them as `<plugin>:<name>`; in a script install, by `name`.

| Role | Mode | When to use |
|---|---|---|
| `implementer` | AGENT (Code) | One layer's plan tasks (data, api, worker, ui, infra, lib, cli) in the detected stack. Spawn once per affected layer, in plan order |
| `test-runner` | AGENT (Code), test step | After the implementers: run the profile's safe checks for the touched roots, fill test gaps (test files only), report pass/fail |
| `argus` | AGENT (Review), read-only | Review the diff (`/argus --local`) or a PR; critical/important → Critical, consider → Suggestion |
| `qa-tester` | AGENT (QA), read-only | Browser QA of UI-observable AC, only when a root has `ui.present: true` |
| `tech-stack-researcher` | PLAN | Technology choices and options, against the detected stack |
| `technical-writer` | AGENT | Docs, guides, API references |

A command may narrow this list with its own "Relevant roles" line; use that when given.

## 2. Brief each role from the profile

- Read `.workflow/profile.json` (the `project-profile` skill) once, in the parent.
- Pass each role only what it needs: the plan path and its section, the layer and root paths, the packs, the trusted commands from `workflow.py config commands`, and the AC verbatim. Don't paste whole files.
- **Graph line:** include one only when the project has a graph (`integrations.graph.graphify: true` or `graph: graphify`): "plan-first; query only for gaps or blast radius" for Code, "diff-first" for Review. Otherwise say "no graph; use plain search".

## 3. Apply the role's perspective

Load the role file, then follow its mindset, inputs, steps and boundaries. Read-only roles (`argus`, `qa-tester`) never edit files.

## 4. Several layers

When a task spans layers, spawn one `implementer` per layer in plan order (**data → api / worker → ui → infra**), passing each the contracts the earlier layers produced. Run `test-runner` once after all of them, then `argus`, then `qa-tester` when there's a UI.
