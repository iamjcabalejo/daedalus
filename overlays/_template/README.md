# Writing an overlay

An overlay adds one team's or organization's specifics to the generic workflow without forking it: business invariants for reviews, ticket keys, sign-in steps for browser QA, daily-report sources, and stack conventions. The hub stays generic; the overlay stays private.

## Layout

```
overlays/<name>/
  overlay.yml                      # name, description, what it provides (see the template)
  rules/<name>-context.md          # always-on context: stack conventions, secrets, time zones, repo map
  skills/argus-rubric/domains/<name>.md   # Argus domain pack (copy .claude/skills/argus-rubric/domains/_template.md)
  config.yml                       # defaults: overlay, tickets, chat, graph, domain, house_rules, qa
  hooks/context.txt                # extra session-start lines (keep it to a few)
  qa/auth.md                       # sign-in notes for qa-tester
  daily-report/sources.md          # git roots, ticket/chat conventions, report format
```

Every file is optional. Keep each one short: these files are loaded into context.

## Where the files go when installed

| Overlay file | Installed to | Read by |
|---|---|---|
| `rules/*.md` | `<.claude>/rules/` | every session (always-on rules) |
| `skills/**` | `<.claude>/skills/**` | the skill or pack that names them (for example Argus loads `domains/<domain>.md`) |
| `hooks/context.txt` | `<.claude>/hooks/context.txt` | the session-start hook, which appends it |
| `config.yml` | merged into `~/.workflow/config.yml` (keys you already set win) | every command, through the config chain |
| `overlay.yml`, `qa/auth.md`, `daily-report/sources.md` | `<.claude>/overlays/<name>/` | `qa-tester` / `manual-qa`, `/daily-report` |

`<.claude>` is `~/.claude` for a user-level install, or `<project>/.claude` for a project install. Plugin installs read the overlay from `~/.claude/overlays/<name>/`. `./install.sh --user --overlay overlays/<name>` (or `--project <path>`) does the copying and merging, and `--uninstall` removes it; for plugin installs, copy the files by hand using the table. Walkthrough: `docs/guides/writing-an-overlay.md`.

## Keep it private

`overlays/*` is gitignored in the hub; only `overlays/_template/` is tracked, and `scripts/check-generic.sh` fails if anything else under `overlays/` is tracked or if org terms leak into tracked files.

Because the overlay isn't in git, **back it up yourself**:

1. **Back up:** `tar czf <name>-overlay.tgz -C overlays <name>`, then encrypt it (for example `gpg -c <name>-overlay.tgz`) and store it in your team's private storage. Delete the unencrypted archive.
2. **Restore:** download it, `gpg -d <name>-overlay.tgz.gpg > <name>-overlay.tgz`, then `tar xzf <name>-overlay.tgz -C overlays`.
3. **Share with teammates** the same way, or move the overlay into a private repository once more than one person maintains it.

## Writing tips

- **Context rule:** state conventions as rules ("all timestamps are UTC", "secrets come from <manager>"), not as stack tutorials; stack idioms belong in the public packs.
- **Domain pack:** list invariants as outcomes that must never happen, each with how to spot a violation in a diff. Mark which ones are always critical.
- **QA auth notes:** for each probe state (signed-in, expiring, signed-out, re-auth needed, account changed, access denied, reconnecting), give the exact on-screen signal and the app's own button. List the identity-provider hosts the tester must never touch. Never include credentials.
- **Daily report sources:** the git roots (`DAILY_REPORT_ROOTS`), ticket key prefixes, which chat to search, and the report's target format.
