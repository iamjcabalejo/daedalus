# Writing an overlay

An overlay adds one team's or organization's specifics to the generic workflow without forking it. It stays private: `overlays/*` is gitignored in this repository, and `scripts/check-generic.sh` fails if any overlay file except the template gets tracked.

The format reference, with the install mapping and the backup steps, is [overlays/_template/README.md](../../overlays/_template/README.md). This guide is the walkthrough.

## 1. Start from the template

```bash
cp -R overlays/_template overlays/<name>
```

Edit `overlays/<name>/overlay.yml`: set `name` (kebab-case; it's also the value of `overlay:` in config) and `description`, and list only the files you'll provide.

## 2. Add what your team needs

| You want | Add | Notes |
|---|---|---|
| Conventions every session should know (secrets manager, time zones, repo map, house style) | `rules/<name>-context.md` | Write rules, not tutorials. Stack idioms belong in the public packs |
| Review checks for your business invariants | `skills/argus-rubric/domains/<name>.md` (copy `.claude/skills/argus-rubric/domains/_template.md`), plus `domain: <name>` in `config.yml` | Each invariant is an outcome that must never happen, with how to spot a violation in a diff; mark the always-critical ones |
| Ticket system and keys, chat, graph | `config.yml` (`tickets`, `chat`, `graph`, `domain`, `house_rules`) | Merged into `~/.workflow/config.yml` at install; keys you already set win |
| Sign-in steps for browser QA | `qa/auth.md` | The exact signal for each probe state (signed-in, expiring, signed-out, re-auth, account changed, access denied, reconnecting), the app's own sign-in button, and the identity-provider hosts the tester must never touch. Never credentials |
| Daily-report sources | `daily-report/sources.md` | Git roots (`DAILY_REPORT_ROOTS`), ticket key prefixes, which chat to search, the report format |
| A line at session start | `hooks/context.txt` | Keep it to one or two lines |

Every file is loaded into context when it applies, so keep each one short.

## 3. Install it

- **Script install:**

  ```bash
  ./install.sh --user --overlay overlays/<name>
  ```

  Rules and skills go into `~/.claude`, `hooks/context.txt` into `~/.claude/hooks/`, the QA and report notes into `~/.claude/overlays/<name>/`, and `config.yml` becomes `~/.workflow/config.yml` if you don't have one yet. If you do, it's left alone and the installer tells you to merge by hand. `--uninstall` removes it all again.
- **Plugin install:** copy the folder to `~/.claude/overlays/<name>/`, put its `config.yml` keys (including `overlay: <name>`) into `~/.workflow/config.yml`, and copy any domain pack or rules into `~/.claude/skills/` and `~/.claude/rules/`. The session-start hook reads `~/.claude/overlays/<name>/hooks/context.txt`.

## 4. Check it

1. Start a session in a repo the overlay is for. The session context should end with your `hooks/context.txt` line.
2. Run `/argus --local`. The review's run notes should name your domain and the config file it came from.
3. In a UI project, run `/manual-test --login`. The tester should recognize your sign-in page from `qa/auth.md`.

## 5. Keep it safe

Back it up encrypted (the template README has the commands), and move it to a private repository once more than one person maintains it. Remember that a personal `domain:` applies to every repo you open, unless a repo sets `domain: none`.
