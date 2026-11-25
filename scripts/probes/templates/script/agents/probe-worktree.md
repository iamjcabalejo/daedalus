---
name: probe-worktree
description: Probe agent with native worktree isolation (J1).
model: haiku
isolation: worktree
---

Do these steps in order and report each result in one line:
1. Use the Edit tool to replace "seed" with "J1-worktree" in seed.txt in your own working copy.
2. Use the Edit tool on the absolute path {{REPO}}/seed.txt to replace "seed" with "J1-main".
3. Run `git branch --show-current` and then `pwd`, each as its own Bash call.
