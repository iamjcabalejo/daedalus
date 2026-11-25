---
name: probe-a
description: Probe agent A for the identity-under-concurrency probe (A2).
model: haiku
tools: Bash
---

Run these three commands, each as its own Bash call and in this order: `echo probe-a-1`, `echo probe-a-2`,
`echo probe-a-3`. Then reply "probe-a done". Do nothing else.
