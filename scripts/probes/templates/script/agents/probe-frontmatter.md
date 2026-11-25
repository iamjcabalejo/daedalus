---
name: probe-frontmatter
description: Probe agent with its own hooks and permissionMode (C4).
model: haiku
permissionMode: plan
hooks:
  PreToolUse:
    - matcher: "*"
      hooks:
        - type: command
          command: {{FRONTMATTER_COMMAND_JSON}}
---

Use the Edit tool to replace the word "seed" with "C4" in seed.txt. If the edit is blocked, say so in one line.
Do nothing else.
