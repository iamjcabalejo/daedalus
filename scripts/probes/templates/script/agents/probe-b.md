---
name: probe-b
description: Probe agent B for the identity-under-concurrency probe (A2).
model: haiku
tools: Bash
---

Run these three commands, each as its own Bash call and in this order: `echo probe-b-1`, `echo probe-b-2`,
`echo probe-b-3`. Then reply "probe-b done". Do nothing else.
