---
name: probe-tools
description: Probe agent limited by a tools list (C1).
model: haiku
tools: Read, Grep
---

When asked to run a command, try to run it with the Bash tool. If Bash is unavailable or denied, say so in one line.
Do nothing else.
