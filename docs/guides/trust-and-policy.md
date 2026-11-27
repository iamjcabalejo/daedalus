# Trust and policy

Daedalus decides two things deterministically, in code, instead of leaving them to the model:
- **which configuration value applies**, when the organization, the user, the workspace, the repository and the current run all set one (`lib/wfconfig.py`);
- **which committed commands may run without asking** (`lib/trust.py` and your trust store).

Both are read through one command line, `workflow.py`, which every hook, command and role uses. This guide explains the rules, how to inspect them, and how to set organization policy.

**Where `workflow.py` is:** `~/.claude/scripts/` (script install with `--user`), `<project>/.claude/scripts/` (`--project`), or the plugin's `scripts/` folder (`${CLAUDE_PLUGIN_ROOT}/scripts/` inside Claude Code; on disk, under `~/.claude/plugins/cache/`). The examples write it as `<scripts>`. Always run it as `python3 -I <scripts>/workflow.py …`: `-I` keeps the current folder off Python's import path, so a file in the project can't run inside Daedalus.

## 1. Trust levels

Configuration is read from five levels, farthest first:

| Level | Sources, in reading order | Read when |
|---|---|---|
| **TL1 organization** | `$DAEDALUS_POLICY_DIR/policy.yml`, `/etc/daedalus/policy.yml` (Linux and macOS), `/Library/Application Support/Daedalus/policy.yml` (macOS) | Only from a **managed** path: every folder on the file's real path is owned by root and not group- or world-writable, and every symlink met on the way is itself root-owned (so macOS's root-owned `/etc → /private/etc` passes). A file that fails the check is ignored, and `config explain` warns about it. `DAEDALUS_POLICY_DIR` adds a source; it never replaces the default paths. A managed file with a syntax error stops resolution: organization policy that can't be read is never skipped silently |
| **TL2 user** | `~/.claude/argus.yml` (legacy), then `~/.workflow/config.yml` (it also holds an installed overlay's defaults) | Always. `~` is your home folder from the password database; `DAEDALUS_HOME` replaces it only when that folder is outside every git work tree and the project, owned by you, and not group- or world-writable |
| **TL3 workspace** | `<workspace>/.argus.yml`, then `<workspace>/.workflow/config.yml` | Only when the workspace folder (commands pass `--workspace`; hooks use `CLAUDE_PROJECT_DIR`) is a strict ancestor of the repository and isn't inside a git work tree itself. Otherwise its files are read as TL4: a committed or downloaded folder can't claim workspace trust. Even at TL3, a `commands` override needs your trust store (§4), because an extracted archive outside any work tree can hold a repository and sit at TL3; TL3 preferences and tighten-only security values apply as they are |
| **TL4 repository** | `<repo>/.argus.yml`, then `<repo>/.workflow/config.yml`; facts in `<repo>/.workflow/profile.json` | Always. A folder without git is a TL4 project folder |
| **TL5 per run** | `--set KEY=VALUE` arguments | When a command passes them |

Within a level, a later file wins for preferences (so `config.yml` beats the legacy file), and security keys combine strictest across the level's files, so no TL1 file can loosen another.

Files use a strict YAML subset: block mappings and lists, one-line `[…]` and `{…}`, and plain or quoted scalars. Anchors, aliases, tags, block scalars (`|`, `>`), `yes`/`no`/`on`/`off`, `True`/`False` and unquoted floats are errors that name the file, line and column. An optional `version: 1` is the only accepted version.

## 2. Setting classes

Every key has a class (`lib/config_keys.py`; documented per key in [templates/workflow-config.example.yml](../../templates/workflow-config.example.yml), where `P`, `S` and `G` mark them):

| Class | Examples | How levels combine |
|---|---|---|
| **Preference** (`P`) | `tickets.*`, `chat`, `review.*`, `qa.*`, `overlay`, `graph`, `stacks` | The nearest level that sets the key wins (TL5 > TL4 > TL3 > TL2 > TL1). Mappings combine key by key; lists are replaced whole; a missing, empty or `null` value falls through to the next level, while an explicit value (even `none` or `[]`) wins |
| **Security** (`S`) | `guard.mode`, `budgets.*`, `gate.*`, `exec.*`, `tdd.min`, `tiers.*`, `parallel.max_agents`, `telemetry.export` | Monotonic. TL1 (combined with TL2) sets the **anchor**; without TL1, your TL2 value does; without either, the default. TL3, TL4 and TL5 can only tighten the anchor. A value that would loosen it is ignored and recorded with the reason |
| **Governance** (`G`) | `governance.trust_roots`, `governance.risk_components` | TL1 only. A TL2 value applies, labeled advisory, when TL1 doesn't set the key; lower levels are ignored |
| **Project facts** | `commands` overrides; the profile | Trusted per command (§4), not merged |

The anchor rule means you may loosen a default on your own machine (TL2 `guard.mode: warn`), but never an organization's TL1 value, and a repository or a single run can never loosen either.

**Security operators,** one per key:

| Operator | Keys | Result |
|---|---|---|
| `mode-order` | `guard.mode` (`enforce` > `warn` > `off`), `gate.mode` (`enforce` > `advisory`) | The strictest mode |
| `min` | Ceilings: `budgets.*` (`null` means no ceiling), `tiers.trivial_max_files`, `parallel.max_agents`, `exec.timeout_minutes` | The smallest ceiling |
| `max-order` | `tdd.min` (`strict` > `bugfix` > `off`), `gate.approver_role`, `tiers.floors.<dimension>` | The strictest value |
| `union` | `gate.require`, `gate.non_waivable`, `tiers.steps.<tier>` | Every level's entries; a lower level can't remove one |
| `intersect` | Privileged allowlists: `exec.env_passthrough`, `gate.trusted_classes` | Only entries the anchor allows; a lower level can't add one |
| `trusted-add` | `guard.readonly_bash_allow` | TL1, TL2 and the default only; TL3–TL5 values are ignored |
| `tl2-only` | `isolation.share_sensitive` | TL1 and TL2 only |
| `opt-in-trusted` | `telemetry.export` | Anything but `none` only from TL1 or TL2 |

A wrong type or an unknown enum value is an error at TL1 or TL2 (a broken trusted policy stops the commands that read it) and an ignored contribution with a warning at TL3–TL5 (a broken repository value can't weaken anything). An unknown key is a warning that suggests the nearest known key.

## 3. Inspecting the resolved configuration

```bash
python3 -I <scripts>/workflow.py config resolve --json --repo . --workspace <folder the session started from>
python3 -I <scripts>/workflow.py config get tickets.system --repo .
python3 -I <scripts>/workflow.py config explain guard.mode --repo .
```

- `config resolve --json` prints the `daedalus.policy/1` document: `values` (every key, defaults filled in), `sources` (each file read, its level and digest), `provenance` (where each value came from), `ignored` (contributions the resolver dropped, with reasons), `advisory`, `warnings` and `policy_digest` (a digest of the security and governance values; later phases bind evidence to it). It never contains command text.
- `config explain <key>` shows the value, its level, class and operator, and every level's contribution (paths shortened):

  ```
  guard.mode = warn
    class: security · operator: mode-order · levels: TL1, TL2, TL3, TL4, TL5
    from: TL2 (~/.workflow/config.yml)
    contributions:
      TL2 ~/.workflow/config.yml:2: warn → accepted
      TL4 .workflow/config.yml:2: off → ignored (weakens TL2 value (off is weaker than warn))
  ```
- Exit codes: `0` ok, `2` usage, `3` configuration error. An error prints its code, the file and line, and a fix; with `--json` it's also `{"error": {…}}` on stdout.

## 4. Which commands run without asking

The profile stores each command as `{cmd, source, confidence, confirmed?, unsafe?}`. Those fields say how a command was found, not whether it may run: anyone who can commit to the repository can write `confidence: "user"` or `confirmed: true`, or add a `commands` override to `.workflow/config.yml`. So the **effective command set** decides:

```bash
python3 -I <scripts>/workflow.py config commands --json --repo . --workspace <folder the session started from>
```

| Source of the command | Trusted when | `basis` |
|---|---|---|
| `commands` override at TL1 | Always (root-owned organization policy) | `policy` |
| `commands` override at TL2 | Always (your own `~/.workflow/config.yml`) | `user-config` |
| `commands` override at TL3 (workspace) or TL4 (committed) | Your trust store holds its digest | `trust-store` |
| Profile entry, `script` or `derived` | Re-detection from the repository's own manifests reproduces the same command at the same confidence; otherwise as a `user` entry | `detected` |
| Profile entry, `user`, or any `confirmed: true` | Your trust store holds its digest | `trust-store` |
| Profile entry, `inferred` and not confirmed | Never without `/setup` | — |

- Roles and commands run only records with `trusted: true` and `unsafe: false`, and ask about everything else (or send you to `/setup`). An untrusted record is reported as unconfirmed `inferred`.
- `unsafe` is recomputed from the command's text (and, for re-detected entries, what it runs: a `package.json` script body, a Make, Task or just recipe). A committed `unsafe: false` never clears it, and an unsafe command always needs your approval, trusted or not.
- A `commands` override wins over the profile entry for the same root and name; the hidden entry is listed under `shadowed`.
- A command, root path or name that holds a line break or a control, format or bidi character (the escape that starts terminal sequences, a tab, a right-to-left override, a zero-width space) is malformed in both channels and at every level, TL1 and TL2 included: it never runs, `trust pending` lists it as not recordable with the file to fix, and it can't be trusted until it is rewritten as plain one-line text.
- Re-detection uses the detector's own timeout (`WORKFLOW_DETECT_TIMEOUT`, default 5 s). If it times out, the entries that need it stay untrusted.
- The session banner uses a fast check without re-detection. It never trusts more than the full check: it counts every untrusted command that claims to run (committed `user` and confirmed entries, TL3 and TL4 overrides, and detected `script` or `derived` entries whose digest isn't in your store) and shows `(untrusted)` in the profile summary instead of their text. The summary shows a command's text only when that check trusts the exact single-line command that runs (for an override, the override's own text); every other command shows `(untrusted)`, a malformed profile entry (a `cmd` that isn't one line of text, a root `path` that isn't a string) is counted as untrusted and listed by `trust pending` as not recordable, and when the check can't run the summary shows no command text at all. `/setup` stores the digests of the detected commands re-detection reproduces, so after one run the banner shows them; a stored digest trusts exactly that text. The banner refreshes and reads the profile at the repository's top level, also when the session starts in a subfolder.

## 5. The trust store

Your trust decisions live in `~/.workflow/trust.json` (`daedalus.trust/1`), outside every repository.

- **Keyed by repository identity:** the `origin` remote, normalized (host lowercased; user, password or token, query and fragment removed; `.git` dropped; `git@host:owner/repo` and `ssh://` forms mapped to `host/owner/repo`), plus the real path of the repository's top level. A project without git uses its folder's real path and no remote. A fork, or a second clone at another path, is a different repository: share trust across a team through TL1 policy, not by copying stores.
- **One digest per command:** `sha256` over the channel (`profile` or `config`), the root, the name and the exact command text, plus the time you trusted it. The store holds no command text and no credentials. Changing a command's text, root or channel makes it untrusted again.
- **Written safely:** under a lock, through a temporary file, `fsync` and rename; mode `0600` in a `0700` folder.
- **Refused when unsafe:** a store that is a symlink, owned by another user, group- or world-writable, or inside the project is refused (`E_TRUST_STORE_UNSAFE`), and every committed command is then untrusted. A store under `DAEDALUS_HOME` is also refused inside a git work tree; your real home folder isn't, so a dotfiles repository at `~/.git` doesn't disable trust. A store that isn't valid `daedalus.trust/1` is `E_TRUST_STORE_INVALID`: move it aside and rerun `/setup`.

**Recording trust.** `/setup` lists every untrusted committed command from both channels, with its exact text, root, name, level and why it's untrusted, and asks once. The confirmation is bound to that list's digest, so a list that changes between display and confirmation is refused (`E_TRUST_SET_CHANGED`) and shown again. `trust record --pending` also stores the digests of the detected commands re-detection reproduces at that moment (listed as `detected`; they're outside the confirmed list and its digest), and `/setup` runs it even when the list is empty, which needs no confirmation. `/setup --print` writes nothing, including the store. The same operations are available directly:

```bash
python3 -I <scripts>/workflow.py trust pending --json --repo .     # what needs trust, with set_digest
python3 -I <scripts>/workflow.py trust record --pending --digest <set_digest> --repo .
python3 -I <scripts>/workflow.py trust record --root . --name test --channel profile --repo .
python3 -I <scripts>/workflow.py trust list --repo .
python3 -I <scripts>/workflow.py trust revoke --root . --name test --repo .   # or no flags: the whole repository
```

`trust record` runs the store's safety checks first and exits 3 with the fix when they fail, so it never reports trust it can't apply.

## 6. Organization policy (managed TL1)

An organization sets values that no user file, repository or run can loosen by installing a root-owned policy file. It uses the same format as `.workflow/config.yml`.

**macOS:**

```bash
sudo mkdir -p "/Library/Application Support/Daedalus"
sudo install -o root -g wheel -m 0644 policy.yml "/Library/Application Support/Daedalus/policy.yml"
```

**Linux:**

```bash
sudo install -d -o root -g root -m 0755 /etc/daedalus
sudo install -o root -g root -m 0644 policy.yml /etc/daedalus/policy.yml
```

On macOS, `/etc/daedalus/policy.yml` works too: `/etc` is a root-owned symlink to `/private/etc`. To add a policy from another managed folder, set `DAEDALUS_POLICY_DIR` to it (for example `/opt/<org>/daedalus`); that folder and every folder above it must pass the same check.

**Check it:** `python3 -I <scripts>/workflow.py config explain guard.mode --repo .` should say `from: TL1 (…/policy.yml)`. A policy file that exists but isn't managed (owned by a user, or in a writable folder) is ignored, and `explain` warns about it.

Without a managed file, organization defaults delivered through an overlay land in `~/.workflow/config.yml` and are **advisory TL2**: the user can change them. Claude Code's managed settings, with `allowManagedHooksOnly`, are the documented way to stop users and projects from removing hooks; the deterministic guard that would be registered there arrives in P2, and nothing in P1 needs it.

## 7. What Claude Code's workspace trust does and doesn't do

Claude Code asks whether you trust a folder. That decision is separate from Daedalus' trust levels and trust store, and Daedalus never reads it:
- **It does** gate the project's own permission allow rules: in an untrusted folder, `.claude/settings.json` `permissions.allow` is ignored.
- **It doesn't** gate the project's hooks. In headless `claude -p` runs on Claude Code 2.1.325, every untrusted test folder's `.claude/settings.json` hooks ran, and their decisions were enforced, while the same folders' allow rules were ignored (65 of 65 sessions). So a cloned repository's own hook commands can run on the first `claude -p` in it, before anyone accepts a trust dialog. Daedalus can't change this.

For `-p` runs in repositories you haven't reviewed, use a container or Claude Code's sandbox. Trusting a repository's commands in `/setup` is a decision about those commands only; it says nothing about the repository's hooks.

## 8. What's enforced, and when

- **Deterministic now (P1):** the resolved configuration, the effective command set, the recomputed `unsafe` flag and the trust store's safety checks. The same inputs give the same answer, and `config explain` and `config commands` show why.
- **Prompt-followed until P2:** acting on those answers. Every command, role and the session banner tell the model to run only trusted commands that aren't `unsafe`, and `/project-manager` puts only those in briefs, but nothing yet blocks a model that ignores its instructions. From P2, the guard and `exec.py` enforce it. The security keys (`guard.mode`, `budgets.*`, `gate.*`, `exec.*`) resolve today; the components that enforce them arrive in P2 and later.

## 9. Upgrading from 0.4.0

Committed `user` and confirmed profile commands, and `commands` overrides in a committed `.workflow/config.yml`, no longer run without asking. After upgrading, run `/setup` once in each repository to review and trust them. Until you do, the session banner counts them as untrusted, and roles ask before running them. Commands that re-detection reproduces from the repository's own files (`script`, `derived`) need nothing.
