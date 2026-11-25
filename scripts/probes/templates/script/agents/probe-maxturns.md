---
name: probe-maxturns
description: Probe agent with a two-turn limit (C3).
model: haiku
maxTurns: 2
---

Read steps/step1.txt, steps/step2.txt, steps/step3.txt, steps/step4.txt and steps/step5.txt, one Read call per file
and one file per turn, in order. Then reply with the five lines you read.
