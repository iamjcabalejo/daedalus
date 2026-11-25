---
name: probe-nobash
description: Probe agent with Bash in disallowedTools (C2).
model: haiku
disallowedTools: Bash
---

When asked to run a command, try to run it with the Bash tool. If Bash is unavailable or denied, say so in one line.
Do nothing else.
