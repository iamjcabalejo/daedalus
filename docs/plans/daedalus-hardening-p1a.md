# Daedalus hardening P1a: trust and configuration

- **Type:** Infrastructure (workflow hub): a configuration resolver, a trust hierarchy and a user trust store. Changes the shipped `.claude/` tree
- **Complexity:** Medium–large. Two library modules, one CLI skeleton, a detector change, and edits to the commands that read configuration today
- **Estimated effort:** 3–5 engineering days (P1 total 12–20, roadmap §14; P1b 4–7, P1c 5–8)
- **Ticket:** none
- **Program plan:** [daedalus-hardening-roadmap.md](daedalus-hardening-roadmap.md) rev 2.1: §5.5, §6.5, §6.21, §9 P1, D11, D19, D23. Roadmap ACs are written **R-AC-n**; this plan's are **AC-n**
- **Sibling plans:** [P1b artifacts and evidence](daedalus-hardening-p1b.md) (runs **after** this plan: both edit eight of the same files, §12), [P1c runtime](daedalus-hardening-p1c.md) (consumes this plan's interfaces, §3.9). Order: P1a → P1b → P1c
- **Review:** revised after [the Argus review of the P1 plans](../reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans.md); this plan carries the fixes for findings a663546-1, -2, -3, -9, -10 and -11, and, from [the second review](../reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r2.md), -13 (the work-tree check), and, from [the third](../reviews/tb-claude-custom-workflow-hardening-p0a-a663546-p1-plans-r3.md), -16 (trust store in a git home) and -19 (`/setup` profile rewrites)
- **Findings used:** [daedalus-hardening-phase0.md](daedalus-hardening-phase0.md) (findings §8, corrections C-3, C-4, C-11, C-13; decision D9); [threat model](daedalus-hardening-threat-model.md) T3, T16
- **Metadata:** `Security: critical`. The resolver and the trust store decide which committed commands may run without asking, and which security settings a repository can change
- **Base:** `feat/hardening-p0a` @ `a663546`, plugin `0.4.0`. The plugin version moves to `0.5.0` in P1c, which lands last; this plan doesn't bump it
- **Graph gate:** skipped (no graph; `integrations.graph.graphify: false`)
- **Profile:** root `.` · layer `lib` · packs `ci-cd`, `go`, `iac`, `python`. Only `python` and `ci-cd` apply to the files this plan touches; `go` and `iac` come from benchmark fixtures and the benchmark Dockerfile, which this plan doesn't touch. Shell scripts follow the repo's own conventions (no pack)

---

## 1. Feature overview

**Problem.** Configuration and command trust are decided by the model today:
- **F1 / T3 (Critical, exploitable):** a committed `.workflow/profile.json` can mark its own commands `confidence: "user"` or `confirmed: true`, and roles run them without asking (`.claude/scripts/detect-stack.py:947–952`; `.claude/skills/project-profile/SKILL.md:38–43`). A committed `.workflow/config.yml` `commands` override is a second channel with no confidence at all (C-3; `templates/workflow-config.example.yml:31`).
- **F3:** organization defaults have the lowest precedence; a repository overrides them (`ARCHITECTURE.md:159`; `install.sh:207–227`).
- **F9:** the session hook reads `overlay:` with a regex (`.claude/hooks/session-init.sh:54–64`, regex at `:59`); every other key is merged by the model from prose rules (`.claude/skills/argus/SKILL.md:39–50`), so the same files can resolve differently between runs, and nothing can explain a resolved value.

**Audience.** Developers running Daedalus in repositories they clone; organizations that want settings a repository can't weaken; P1c and P2, which read the resolved policy and the trusted command set.

**Key functionality.**
1. A **strict YAML-subset reader** and a **resolver** (`lib/wfconfig.py`) over the TL1–TL5 chain, with setting classes: preferences resolve nearest-wins, security keys merge monotonically, governance keys are TL1-only.
2. `workflow.py config resolve | explain | get | commands`: the one way hooks, scripts and commands read configuration.
3. A **user trust store** (`~/.workflow/trust.json`) and an **effective-command resolver** (`lib/trust.py`): a committed command runs without asking only when re-detection reproduces it or the user's trust store holds its digest. `/setup` records trust.

**Out of scope:** the guard, `exec.py` and every deterministic enforcement of these decisions (P2: R-AC-2, R-AC-62). In P1 the resolver's verdict is deterministic, but roles follow it through their prompts and the project-manager's briefs. Capability contracts (P2, R-AC-45). Risk tiers and floors computed from diffs (P3). `doctor` (P2, R-AC-65).

### 1.1 Findings made while planning

| # | Finding | Evidence | Resolution in this plan |
|---|---|---|---|
| PF-1 | **A forged `script` or `derived` entry bypasses R-AC-61's wording.** R-AC-61 covers committed `user` and `confirmed` entries. But a committed profile can also change a `script` entry's `cmd` while keeping its `manifest_hash`; `--ensure` then treats the profile as fresh and doesn't regenerate it (`detect-stack.py:997–1001`), and roles run `script` commands without asking (`project-profile/SKILL.md:38–43`) | `detect-stack.py:997–1001`, `:941–952` | AC-9: a committed `script` or `derived` entry counts as detected only when re-detection reproduces the same command at the same confidence; otherwise it needs the trust store like a `user` entry |
| PF-2 | **The session hook puts the repository's directory on `sys.path`.** `python3 - <<'PY'` prepends the working directory (the project) to `sys.path`, so a repository file named `json.py`, `os.py` or `lib/wfconfig.py` would run inside Daedalus' own hook, on every session start, in every repository the plugin is enabled for. `python3 -m http.server` in `/manual-test` has the same exposure | `.claude/hooks/session-init.sh:12`; `.claude/commands/manual-test.md:42` | AC-7: every Python process Daedalus starts from a hook or command runs with `python3 -I`, and each entry point adds only its own real directory to `sys.path` |
| PF-3 | **Environment overrides can come from the repository.** Claude Code project settings can set environment variables through an `env` block [D, settings docs; not probed, and whether it applies in an untrusted folder is unverified]. A `DAEDALUS_HOME` pointing into the repository would let a repository supply its own trust store; a `DAEDALUS_POLICY_DIR` that *replaces* the managed paths would hide organization policy | Roadmap §12 lists `DAEDALUS_POLICY_DIR`; `install.sh:3` uses `DAEDALUS_HOME` for tests | AC-2: `DAEDALUS_HOME` is honored only for a directory outside every git work tree, owned by the user and not group- or world-writable; `DAEDALUS_POLICY_DIR` only **adds** a TL1 source, and only when it passes the managed-path check |
| PF-4 | **The roadmap names two CLIs for one job.** R-AC-27 says `wfconfig.py resolve --json` / `wfconfig.py explain`; §6.1 consolidates entry points and lists `workflow.py config resolve\|explain` | Roadmap §5.5, §6.1 | The library is `lib/wfconfig.py`; the CLI is `workflow.py config …`, per §6.1. R-AC-27's verification applies to that CLI |
| PF-5 | **"Most restrictive across TL1..TL5" needs an anchor.** Taken literally, either a lone repository `guard.mode: off` wins when no higher level sets the key, or (if the hub default counts as a value) a user can never choose `warn` on their own machine | Roadmap §6.5 | §3.4: the **anchor** is TL1 combined with TL2, or the hub default when neither sets the key. TL2 may loosen the default but never TL1; TL3–TL5 can only tighten the anchor |
| PF-6 | **Remote URLs can carry credentials** (`https://user:token@host/…`), and the roadmap keys repository identity on the remote URL | Roadmap §6.5 "Repository trust" | AC-8: the stored identity strips user info, query and fragment; a test proves no credential reaches the trust store |
| PF-7 | **The rule "committed `user` and confirmed commands run unasked" is stated in many prompts, not only the profile skill.** Rewiring a few consumers leaves `/test-gen`, `/scaffold`, `/code-cleanup`, `/code-optimize`, `/manual-test`'s dev-server start, the `test-strategy` and `workflow-contract` skills, the always-on `stack-knowledge.md` rule, `CLAUDE.md` (installed as an always-on rule) and the session banner still running an untrusted command | `.claude/commands/test-gen.md:27`, `scaffold.md:42`, `code-cleanup.md:21`, `code-optimize.md:30`, `manual-test.md:39`; `.claude/skills/test-strategy/SKILL.md:37`; `.claude/skills/workflow-contract/SKILL.md:26`; `.claude/rules/stack-knowledge.md:16`; `.claude/rules/compounding-dev-cycle.md:28`; `CLAUDE.md:11` (copied by `install.sh:56`); `.claude/hooks/session-init.sh:27`, `:38`; `README.md:12` (review finding a663546-1) | AC-13 lists every one of them, and its grep test covers all of `.claude/**`, `CLAUDE.md` and `README.md` |
| PF-8 | **A project outside git has no work tree,** so a rule that demotes only folders "inside a git work tree" would read a ZIP-downloaded project, or one `git` refuses for dubious ownership, as TL3 and trust its own committed `commands` | AC-2, §3.3 as first written (review finding a663546-2) | §3.3: TL3 is only a folder that is a strict ancestor of the target's top level and not inside a work tree; a target with no git top level is a TL4 project folder. Work-tree membership comes from walking for a `.git` entry; `git` only confirms one, and an error there counts as inside (fail closed). Deciding it from `git`'s exit status alone would have made every folder "inside", because `git rev-parse` fails outside a repository (review finding a663546-13) |
| PF-9 | **`/daedalus-qa:manual-test` can't reach the main plugin's scripts.** The build rewrites a cross-plugin script reference into prose ("the daedalus plugin's scripts/…"), and the QA plugin ships no `scripts/` | `scripts/build-plugin.sh:60–69`; `plugins/daedalus-qa/` has no `scripts/` (review finding a663546-4, which applies to this plan's `/manual-test` change too) | T14: the build also copies `workflow.py`, `detect-stack.py` and `scripts/lib/` into the QA plugin, and `/manual-test` calls `${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py` |

---

## 2. Acceptance criteria

| AC | Criterion | Roadmap | Verification |
|---|---|---|---|
| **AC-1** | **Strict YAML-subset reader.** `lib/wfconfig.py` parses the subset in §3.2.<br>• Every construct outside it is an error `E_CONFIG_SYNTAX` naming the file, line, column and construct: anchors, aliases, tags, block scalars (`\|`, `>`), more than one document, complex keys (`?`), merge keys (`<<`), duplicate keys, tab indentation, ambiguous booleans (`yes`, `no`, `on`, `off`, and capitalized `True`/`False`), unquoted floats, multi-line flow collections and multi-line plain scalars.<br>• An optional top-level `version: 1` is accepted; any other value is `E_CONFIG_VERSION`; a missing `version` means 1 (R-AC-57 for config).<br>• `templates/workflow-config.example.yml` and `overlays/_template/config.yml` parse to committed expected JSON | R-AC-27, R-AC-57 (config) | U (`U-config-yaml-01`…`-20`) |
| **AC-2** | **Trust levels and sources.** The resolver reads exactly the sources in §3.3.<br>• **TL1** only from a managed path (§3.3): every component of the path's `realpath` is owned by root and not group- or world-writable, and every symlink met on the way is itself root-owned (so macOS's `/etc → /private/etc` passes). `DAEDALUS_POLICY_DIR` adds a TL1 source only when it passes the same check, and never replaces the default paths. `explain` warns when a policy file exists but fails the check.<br>• **TL4 without git:** a target with no git top level (no repository, or `git` refuses it) is a TL4 project folder, identified by its `realpath` with `remote: null` (PF-8).<br>• **"Inside a git work tree"** is decided by one helper, `trust.inside_work_tree(path)` (§3.3), which walks the folder and its ancestors for a `.git` entry instead of reading `git`'s exit status (outside a repository, `git rev-parse` fails with 128, so "any git error means inside" would make every folder inside). An unreadable component, or a set `GIT_DIR` or `GIT_WORK_TREE`, counts as inside; `git` is called only to confirm a `.git` the walk found, and an error there (dubious ownership, say) counts as inside.<br>• **TL3** comes only from a workspace folder that is a strict ancestor of the target's top level and not inside a work tree; otherwise its files are read as TL4.<br>• `DAEDALUS_HOME` replaces the user folder only when it's not inside a work tree and not inside the target project folder, owned by the current user and not group- or world-writable; otherwise it's ignored with a warning, and the home folder from the password database is used. The same helper decides the location check for a trust store under `DAEDALUS_HOME` (AC-8).<br>• Claude Code's workspace trust is never read as a trust level (C-11) | R-AC-44, R-AC-27 | U (`U-trust-sources-01`…`-15`) |
| **AC-3** | **Setting classes.** `lib/config_keys.py` gives every key in `templates/workflow-config.example.yml` and roadmap §6.21 a class (preference, workflow preference, security, governance, project facts), a type, a default, a merge operator (§3.4) and the levels allowed to set it. A test fails when a template key has no registry entry, or a registry entry isn't documented in the template | R-AC-27, R-AC-44 | U (`U-config-registry-01`) |
| **AC-4** | **Resolution.**<br>• **Preferences:** nearest wins (TL5 > TL4 > TL3 > TL2 > TL1); mappings merge recursively, lists are replaced whole, and a missing, empty or `null` value falls through while an explicit value (including `none` and `[]`) wins: the semantics of `argus/SKILL.md:44–50`, now in code.<br>• **Legacy files:** the legacy file at each level (`.argus.yml`, or `~/.claude/argus.yml` at TL2) is read below that level's `.workflow/config.yml`, so `config.yml` wins on a shared key at every level, with the legacy key lift (`severity`, `post` → `review.*`).<br>• **Security keys** merge monotonically with the anchor rule and the operator table (§3.4).<br>• **Governance keys** take TL1 only; a TL2 value is kept and labeled `advisory`.<br>• Every contribution a level made and the resolver ignored is reported with a reason | R-AC-44, R-AC-27 | U (`U-config-merge-01`…`-12`) |
| **AC-5** | **Monotonic policy tests,** one per R-AC-44 case, each from TL4 or TL5 against a TL1 or TL2 value:<br>• the repository can't disable the organization's guard (`guard.mode`);<br>• per-run options can't drop critical-tier gates (`gate.require`, `tiers.steps.critical`);<br>• the repository can't raise a resource ceiling (`budgets.*`);<br>• the repository can't mark its own evidence trusted (`gate.trusted_classes`);<br>• the repository can't extend a privileged allowlist (`exec.env_passthrough`, `guard.readonly_bash_allow`);<br>• the repository can't waive organization security requirements (`gate.non_waivable`).<br>Plus one table test per merge operator, including the anchor cases of PF-5 | R-AC-44 | U, PT (`U-policy-monotonic-01`…`-06`, `PT-policy-ops-01`…`-09`) |
| **AC-6** | **CLI.** `workflow.py config resolve [--json] [--set KEY=VALUE …]` prints the resolved document (`daedalus.policy/1`, §3.6); `--set` is TL5. `config explain <key> [--json]` prints the value, the source file, the level, the class, the merge operator and every level's contribution (accepted or ignored, with the reason). `config get <key>` prints one value. Exit codes: 0 ok, 2 usage, 3 configuration error (code, file, line, fix on stderr and in `--json`). In-process resolution takes ≤ 50 ms p95 on the fixture set | R-AC-27 | U (`U-config-cli-01`…`-06`) |
| **AC-7** | **Every consumer uses the resolver, and Python runs isolated.**<br>• `session-init.sh` gets `overlay` from `lib/wfconfig.py`, in process; the regex at `:59` is gone. The hook still fails open (D9: context hooks keep failing open [V] E1–E4 default variants), and its banner names a configuration error by file and line instead of failing.<br>• The banner adds one line when committed commands are untrusted (fast mode, §3.8).<br>• `/argus`, the `argus` skill, `/setup`, `/daily-report`, `/manual-test`, `/feature-plan`, `/apply-ticket`, the `ticket-adapters` and `project-profile` skills read configuration through `workflow.py config resolve --json` (or `get`) and pass the result on. None of them describes a manual merge any more.<br>• Commands pass `--workspace <folder the session started from>` explicitly; `CLAUDE_PROJECT_DIR` is only the fallback, because whether Bash-tool commands receive it is unverified (§3.10, OQ-10). The session hook, which receives it [D], uses it.<br>• On plugin installs, `/daedalus-qa:manual-test` calls its own plugin's copy, `${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py` (PF-9).<br>• Every hook and command starts Daedalus' Python with `python3 -I`, and every entry point inserts only its own real directory into `sys.path` (PF-2).<br>• Session start stays within today's budget (warm ≤ 0.2 s + 50 ms) | R-AC-27 | U (`U-config-consumers-01`: a grep test for the regex, for prose merge rules, and for `python3` without `-I` in `.claude/**`), OQ |
| **AC-8** | **Trust store.** `~/.workflow/trust.json` (`daedalus.trust/1`, §3.7):<br>• keyed by repository identity: the normalized remote URL with user info, query and fragment removed, plus the real path of the repository's top level (C-13 [V]: payload paths are canonical, so identity uses `realpath`); a project without git uses its folder's `realpath` and `remote: null` (PF-8);<br>• each entry holds a command digest and `trusted_at`; no command text, no credentials;<br>• written atomically (temporary file, `fsync`, rename) under `flock`, with mode `0600` in a `0700` folder;<br>• a store that is a symlink, owned by another user, group- or world-writable, or inside the target project folder is refused with `E_TRUST_STORE_UNSAFE`, and every committed command is then untrusted. A store under `DAEDALUS_HOME` is also refused inside a git work tree; a store in the password-database home isn't, so a dotfiles repository at `~/.git` doesn't disable trust (review finding a663546-16);<br>• `trust record` runs the same read checks before writing and fails with the fix line, never reporting success for a store that would be refused | R-AC-61 | U (`U-trust-store-01`…`-14`, including `U-trust-repoid-creds-01` and `U-trust-repoid-nongit-01`) |
| **AC-9** | **Effective commands.** `trust.effective_commands()` applies the rules in §3.8 to both channels, the committed profile and `commands` overrides in configuration (C-3):<br>• a TL4 config override, a profile `user` entry or any `confirmed: true` entry is trusted only when the store holds its digest;<br>• a profile `script` or `derived` entry is trusted only when re-detection reproduces the same command at the same confidence (PF-1); otherwise the store decides;<br>• TL2 and TL3 overrides are the user's own and are trusted;<br>• anything untrusted is reported as unconfirmed `inferred`;<br>• `unsafe` is recomputed from the command text (and the body, for re-detected entries) and is never cleared by a committed value. Re-detection that times out leaves the affected entries untrusted (fail closed) | R-AC-61 | U, PT (`U-trust-effective-01`…`-10`) |
| **AC-10** | **Detector changes.**<br>• `carry_over` still copies `user` entries, but recomputes `unsafe` (adding it, never removing it) and records nothing about trust.<br>• The unsafe vocabulary moves verbatim to `.claude/scripts/lib/unsafe.py`; `rules_digest` also hashes that file, so changing the vocabulary marks profiles stale.<br>• `write_profile` leaves the file untouched when the new profile differs from the one on disk only in `generated_at`, so `/setup` on an unchanged repository doesn't change the source fingerprint and doesn't make P1c's review and QA evidence stale (review finding a663546-19; today every run without `--ensure` rewrites it, `detect-stack.py:932`, `:1094–1097`). `--set` and `--confirm` still write when they change something.<br>• `scripts/test-detector.sh` passes with unchanged expected outputs | R-AC-61 | U (`U-trust-carryover-01`, `U-detector-nowrite-01`), existing matrix |
| **AC-11** | **`/setup` records trust.**<br>• After detection, `/setup` lists every untrusted committed command from both channels (`workflow.py trust pending --json`), grouped by repository, with the exact command text.<br>• One confirmation trusts the listed set (`workflow.py trust record --pending --digest <set-digest>`). The set digest guards against the list changing between display and confirmation.<br>• `--set` and `--confirm` also record trust for the command they write.<br>• `--print` writes nothing, including the trust store | R-AC-61 | U (`U-trust-cli-01`…`-05`), OQ |
| **AC-12** | **Malicious fixtures.** Each fixture repository resolves its command as untrusted, and no command or role presents it as runnable without asking:<br>• a profile `user` entry that writes a canary (`PT-trust-profile-01`);<br>• a forged `script` entry with a valid `manifest_hash` (`PT-trust-profile-02`, PF-1);<br>• a committed config `commands` override (`PT-trust-config-01`, C-3);<br>• an `inferred` entry with `confirmed: true` (`PT-trust-profile-03`);<br>• the same config override in a project folder that isn't a git repository (`PT-trust-nongit-01`, PF-8).<br>After `trust record` each becomes trusted; after its command text changes it's untrusted again; a clone of the same repository at another path is untrusted (`PT-trust-repoid-01`). OQ runs the `user`-entry canary through `/project-manager`, `/test-gen` and `/manual-test`'s dev-server start | R-AC-61, T3 | PT, OQ (`B-safety-S5` itself runs in P2, D29) |
| **AC-13** | **Every prompt uses the effective set** (PF-7). Each place that today says which profile commands may run unasked takes them from `workflow.py config commands --json` (trusted and not `unsafe`) instead of the confidence column:<br>• commands: `/project-manager` (`:34`, `:81`), `/test-gen` (`:27`), `/scaffold` (`:42`), `/code-cleanup` (`:21`), `/code-optimize` (`:30`), `/manual-test` (the dev-server start, `:39`);<br>• roles: `implementer` (`:45`), `test-runner` (`:37`);<br>• skills and rules: `project-profile` (`SKILL.md:38–43`), `test-strategy` (`:37`), `workflow-contract` (`:26`), `stack-knowledge.md` (`:16`), `compounding-dev-cycle.md` (`:28`);<br>• always-on text: `CLAUDE.md:11` (installed as a rule by `install.sh:56`), the session banner's contract strings (`session-init.sh:27`, `:38`), and `README.md:12`.<br>An untrusted command is never put in a brief or run; the prompt says "ask the user, or run `/setup`". Labeled in the docs as **prompt-followed in P1, enforced from P2** (`exec.py` and the guard) | R-AC-61 | U (`U-trust-consumers-01`: a grep over all of `.claude/**`, `CLAUDE.md` and `README.md` finds no statement that `script`, `derived`, `user` or confirmed commands may run without the effective set), OQ |
| **AC-14** | **Hub hygiene.**<br>• `scripts/test-config.sh` and `scripts/test-trust.sh` (Python `unittest` under Bash) are added to `scripts/test-all.sh`, plus two new checks there: `shell-syntax` (`bash -n` on every hub shell script) and `py38-syntax` (`ast.parse(..., feature_version=(3, 8))` on every `.claude/scripts/**/*.py`).<br>• `.github/workflows/check.yml` runs `scripts/test-all.sh` as one step, keeping `WORKFLOW_MATRIX_CACHE`.<br>• `build-plugin.sh` also copies `workflow.py`, `detect-stack.py` and `scripts/lib/` into the `daedalus-qa` plugin (PF-9); `--check` keeps both copies identical to the source.<br>• `build-plugin.sh --check`, `check-generic.sh` and `lint-packs.sh` pass; `plugins/**` is regenerated and carries `scripts/lib/`.<br>• Docs change in this plan: ARCHITECTURE §4.2, §4.4, §11 and §13 (D19, D23), the `workflow-contract` skill's trust rule, the README's profile section, and a new `docs/guides/trust-and-policy.md`. No version bump | R-AC-42 | CI, D |
| **AC-15** | **Operational QA** (§9) on the script and plugin installs: headless scenarios plus an interactive checklist, reported in `docs/qa/daedalus-hardening-p1a-qa-N.md`. No scenario writes the maintainer's real `~/.workflow` or `~/.claude` (`DAEDALUS_HOME` points at a temporary folder; the plugin loads with `--plugin-dir`). FAIL → `docs/plans/daedalus-hardening-p1a-rework-N.md`; BLOCKED → the user | R-AC-66 | OQ |

**Roadmap coverage.** R-AC-27 → AC-1, 2, 3, 4, 6, 7. R-AC-44 → AC-2, 3, 4, 5. R-AC-61 → AC-8, 9, 10, 11, 12, 13. R-AC-57 (config and trust-store versions only; the framework is P1b) → AC-1, AC-8. R-AC-42 → AC-14. R-AC-66 → AC-15.

---

## 3. Technical design

### 3.1 Components

| Component | Path | Kind |
|---|---|---|
| Package marker | `.claude/scripts/lib/__init__.py` | Exact content: one line, `"""Daedalus runtime library (stdlib only, Python 3.8+)."""`. P1b, which runs after this plan, reuses it |
| YAML subset and resolver | `.claude/scripts/lib/wfconfig.py` | Library |
| Key registry | `.claude/scripts/lib/config_keys.py` | Data (Python, so the resolver doesn't depend on P1b's schema validator) |
| Trust levels, trust store, effective commands | `.claude/scripts/lib/trust.py` | Library |
| Unsafe vocabulary | `.claude/scripts/lib/unsafe.py` | Library, moved verbatim from `detect-stack.py:38–46` (P2 extends it, roadmap §6.1) |
| CLI skeleton | `.claude/scripts/workflow.py` | Entry point. A static table maps subcommand groups to modules; this plan adds `config` and `trust`. P1c adds the runtime groups (§3.9) |
| Tests | `scripts/test-config.sh`, `scripts/test-trust.sh`, fixtures under `scripts/fixtures/config/**` and `scripts/fixtures/trust/**` | Hub tests |

**Conventions** (repo conventions win over pack defaults, `stack-knowledge.md`): Python 3.8+ standard library only, `from __future__ import annotations`, `argparse`, explicit exceptions with context and no bare `except`, UTC timestamps, Bash wrappers with `set -euo pipefail` around `unittest` (like `scripts/test-detector.sh`). The python pack's pytest and Pydantic advice doesn't apply: the hub is stdlib-only (roadmap principle 6).

**Errors** are `ConfigError(code, message, fix, file=None, line=None, col=None)`. Codes: `E_CONFIG_SYNTAX`, `E_CONFIG_VERSION`, `E_CONFIG_INVALID` (a value of the wrong type or outside its enum at TL1 or TL2), `E_TRUST_STORE_UNSAFE`, `E_TRUST_STORE_INVALID`, `E_REPO_ID` (the target folder doesn't exist; a folder without git is a TL4 project folder, not an error). Every CLI error prints `{code, message, fix}`.

### 3.2 YAML subset

Accepted:
- UTF-8, with an optional BOM; LF or CRLF.
- Comments: `#` at the start of a line or after whitespace, outside quotes.
- **Block mappings**, indented with spaces only; each block keeps one indentation width.
- **Keys:** plain (`[A-Za-z0-9_.-]+`) or quoted (`"…"`, `'…'`), so `".": {test: …}` works.
- **Scalars:** `null`, `~` or an empty value → null; `true` and `false` (lowercase only); integers (`-?[0-9]+`); plain strings that don't start with `& * ! | > % @` or a backtick; double-quoted strings with `\" \\ \n \t \uXXXX`; single-quoted strings with `''`.
- **Flow collections** on one line, nested: `[a, "b c"]`, `{k: v, "k2": [x]}`.
- **Block sequences** (`- item`) of scalars, flow collections or mappings (`- category: x` with the item's further keys indented under it).
- One optional leading `---`.

Everything else is `E_CONFIG_SYNTAX` (AC-1). The error names the construct ("anchor `&base` at .workflow/config.yml:7:12; anchors aren't supported: repeat the value") and a fix.

### 3.3 Trust levels and sources

Trust levels are TL1–TL5 (C-4); T1–T20 stay threat ids. Within a level, sources are listed lowest first.

| Level | Sources | Notes |
|---|---|---|
| **TL1 organization** | `/etc/daedalus/policy.yml` (Linux); `/Library/Application Support/Daedalus/policy.yml` (macOS); `$DAEDALUS_POLICY_DIR/policy.yml` (additive) | Read only when managed: (1) walking the path as written, every symlink met is itself owned by uid 0 (`os.lstat`), so a user-owned link can't redirect it; (2) every component of `realpath(path)` is owned by uid 0 and not group- or world-writable (`mode & 0o022 == 0`). macOS's root-owned `/etc → /private/etc` therefore passes, and `/Library/Application Support` (root:admin, `0755`) passes. Unmanaged files are ignored, reported, and flagged by `explain`. A managed file with a syntax error is a hard `E_CONFIG_SYNTAX`: organization policy that can't be read must not be silently skipped |
| **TL2 user** | `~/.claude/argus.yml` (legacy), then `<user>/.workflow/config.yml` (it holds the installed overlay's merged keys, `install.sh:207–227`). The trust store `<user>/.workflow/trust.json` is TL2 data, not configuration | `<user>` is the home folder from `pwd.getpwuid(os.getuid())`, or `DAEDALUS_HOME` under the AC-2 conditions. Overlay policy installed per user is advisory TL2 (roadmap §6.5) |
| **TL3 workspace** | `<workspace>/.argus.yml` (legacy), then `<workspace>/.workflow/config.yml` | `<workspace>` is `--workspace` (commands pass the folder the session started from), else `CLAUDE_PROJECT_DIR` (§3.10). It is TL3 only when it is a **strict ancestor** of the target's top level and `trust.inside_work_tree(<workspace>)` is false. Otherwise its files are read as TL4: a committed or downloaded file can't claim workspace trust (PF-8) |
| **TL4 repository** | `<repo>/.argus.yml` (legacy), then `<repo>/.workflow/config.yml`; `<repo>/.workflow/profile.json` (facts and commands) | `<repo>` is `git rev-parse --show-toplevel` of the target, resolved with `realpath` (C-13). When the walk finds no `.git`, `<repo>` is the target folder itself; when it finds one but `git` refuses it (for example for dubious ownership), `<repo>` is the folder holding that `.git` entry. Either way it stays TL4, with `remote: null` in its identity |

**`trust.inside_work_tree(path) -> bool`** (one helper for TL3, `DAEDALUS_HOME` and the trust store; review finding a663546-13):
1. If `GIT_DIR` or `GIT_WORK_TREE` is set in the environment → true (a repository can be anywhere).
2. Walk `realpath(path)` and each ancestor up to `/`. A component that can't be read (`PermissionError`) → true. A `.git` entry (a directory, or a file such as a worktree's or submodule's `gitdir:` pointer) → go to step 3. No `.git` anywhere → false.
3. Confirm with `git -C <folder> rev-parse --is-inside-work-tree` (`GIT_OPTIONAL_LOCKS=0`, a 2-second timeout). Any answer other than a clean `true`, including an error or a timeout, → true (fail closed: a `.git` exists, so the folder may be repository content).

It never calls `git` for a folder with no `.git` above it, so "not a repository" (exit 128) can't be misread as "inside".
| **TL5 per-run** | `--set KEY=VALUE` arguments | Values are parsed as YAML-subset scalars or flow collections |

Workspace trust in Claude Code gates a project's allow rules, not its hooks [V] (findings §8.1: 65 of 65 untrusted `-p` sessions ignored `permissions.allow` but ran and enforced project hooks; C-11). It isn't read as a level, and the trust guide says so.

### 3.4 Setting classes and merge operators

Classes (roadmap §6.5), as recorded per key in `lib/config_keys.py`:

| Class | Examples | Levels | Merge |
|---|---|---|---|
| Preference | `chat`, `review.*`, `qa.auth`, `qa.base_url`, `overlay`, `ignore`, `house_rules`, `budgets.price_table`, `retention.*`, `runtime.lease_ttl_minutes` | TL1–TL5 | Nearest wins |
| Workflow preference | `tickets.*`, `graph`, `stacks`, `extra_stacks`, `tiers.default`, `tdd.mode`, `isolation.mode`, `isolation.baseline`, `isolation.dependencies`, `parallel.enabled`, `specs.system` | TL1–TL5 | Nearest wins |
| Security | `guard.mode`, `guard.readonly_bash_allow`, `budgets.rework_rounds`, `budgets.qa_rounds`, `budgets.run_tokens.*`, `budgets.attempt.*`, `budgets.role_turns.*`, `tdd.min`, `tiers.trivial_max_files`, `tiers.floors`, `tiers.steps`, `parallel.max_agents`, `exec.env_passthrough`, `exec.timeout_minutes`, `isolation.share_sensitive`, `gate.mode`, `gate.require`, `gate.non_waivable`, `gate.approver_role`, `gate.trusted_classes`, `telemetry.export` | TL1–TL5, monotonic | Operator per key (below) |
| Governance | `governance.trust_roots`, `governance.risk_components` | TL1 only; TL2 kept as advisory | TL1 authoritative |
| Project facts | `commands` overrides; the profile | Detector and `/setup`; trust from TL2 | §3.8 |

`gate.trusted_classes` (default `[ci, human]`) is new: it is the key R-AC-44's "can't mark its own evidence trusted" case needs, and P5's gate reads it. The registry records it, and the template documents it.

**Anchor rule (PF-5).** For each security key:
1. **anchor** = combine(TL1, TL2) with the key's operator when TL1 sets it; else the TL2 value when TL2 sets it; else the hub default. TL2 may therefore loosen the default on the user's own machine, never a TL1 value.
2. **effective** = combine(anchor, TL3, TL4, TL5): lower levels only tighten.
3. A lower-level value that would loosen is ignored for that key and recorded in `ignored[]` with reason `weakens <level> value` (shown by `explain`, and by `doctor` in P2).

**Operators:**

| Operator | Keys | Combine |
|---|---|---|
| `mode-order` | `guard.mode` (`enforce` > `warn` > `off`), `gate.mode` (`enforce` > `advisory`) | Strictest |
| `min` | ceilings: `budgets.*` (`null` = no ceiling = +∞), `tiers.trivial_max_files`, `parallel.max_agents`, `exec.timeout_minutes` | Minimum |
| `max-order` | `tdd.min` (`strict` > `bugfix` > `off`), `gate.approver_role` (`admin` > `maintain` > `write` > `triage` > `read`), `tiers.floors.<dimension>` (`critical` > `full` > `standard` > `trivial`) | Maximum |
| `union` | `gate.require`, `gate.non_waivable`, `tiers.steps.<tier>` | Union; a lower level can't remove entries |
| `intersect` | privileged allowlists: `exec.env_passthrough`, `gate.trusted_classes` | Intersection with the anchor; a lower level can't add entries |
| `trusted-add` | read-only allowlists: `guard.readonly_bash_allow` | Union of TL1, TL2 and the default; TL3–TL5 values ignored |
| `tl2-only` | `isolation.share_sensitive` | TL1 ∪ TL2 per path; TL3–TL5 ignored |
| `opt-in-trusted` | `telemetry.export` | Non-`none` only from TL1 or TL2; lower levels may only set `none` |

A wrong type or an out-of-enum value is `E_CONFIG_INVALID` at TL1 or TL2 (fail closed: consumers refuse to run on a broken trusted policy), and an ignored contribution with a warning at TL3–TL5 (a broken repository value can't weaken anything). Unknown keys produce a warning, not an error, so a newer and an older hub can share a repository; the warning names the nearest known key when the edit distance is ≤ 2.

### 3.5 Resolution flow

```mermaid
flowchart TD
  S["resolve(repo, workspace, run_options)"] --> D["discover sources (§3.3)<br/>managed check, DAEDALUS_HOME check, workspace demotion"]
  D --> P["parse each file (YAML subset, §3.2)"]
  P -- error --> E["ConfigError E_CONFIG_SYNTAX (file:line:col)"]
  P --> L["legacy lift (.argus.yml → review.*)"]
  L --> C{"key class (config_keys)"}
  C -- preference --> N["nearest wins, recursive maps, lists whole"]
  C -- security --> A["anchor = TL1⊕TL2 or default<br/>effective = anchor ⊕ TL3 ⊕ TL4 ⊕ TL5"]
  C -- governance --> G["TL1 only; TL2 advisory"]
  N --> O["daedalus.policy/1 document + ignored[] + warnings[]"]
  A --> O
  G --> O
  O --> PD["policy_digest = sha256(canonical(security + governance values))"]
```

### 3.6 Resolved document (`daedalus.policy/1`)

The output of `config resolve --json`, and the contract P1b writes `policy.schema.json` from:

```json
{"schema": "daedalus.policy/1",
 "repo": "/abs/real/path", "workspace": null,
 "sources": [{"level": "TL2", "path": "<user>/.workflow/config.yml", "kind": "config", "sha256": "…", "version": 1},
             {"level": "TL4", "path": ".workflow/config.yml", "kind": "config", "sha256": "…", "version": 1}],
 "values": {"guard.mode": "enforce", "tickets.system": "github", "…": "…"},
 "provenance": {"guard.mode": {"level": "default", "source": null, "class": "security", "op": "mode-order"}},
 "ignored": [{"key": "guard.mode", "level": "TL4", "source": ".workflow/config.yml", "value": "off", "reason": "weakens default value"}],
 "advisory": ["governance.risk_components"],
 "warnings": ["unknown key 'gaurd.mode' in .workflow/config.yml:3 (did you mean 'guard.mode'?)"],
 "policy_digest": "sha256:…"}
```

- `values` is flat, keyed by dotted path. It holds every registry key, with defaults filled in.
- `policy_digest` is `sha256` over the canonical JSON (sorted keys, `(",", ":")` separators, UTF-8, no NaN) of `{"schema": "daedalus.policy-digest/1", "values": <security and governance values only>}`. Preference changes therefore don't invalidate evidence (P1c, R-AC-15); security changes do. `lib/wfconfig.py` carries its own ~10-line canonical serializer with exactly the rules P1b's `artifacts.canonical_bytes` uses, and a P1c integration test asserts the two agree.
- The document holds no command text: `commands` overrides are summarized as `{root, name, channel, level}`, and their text appears only in `config commands`.

### 3.7 Trust store (`daedalus.trust/1`)

```json
{"schema": "daedalus.trust/1",
 "repos": {"sha256:<repo-id>": {
   "remote": "github.com/owner/repo", "root": "/abs/real/path",
   "commands": {"profile:.:test": {"digest": "sha256:…", "trusted_at": "2026-12-01T10:00:00Z"},
                "config:.:lint":  {"digest": "sha256:…", "trusted_at": "2026-12-01T10:00:00Z"}}}}}
```

- **Repository identity:** `repo_id = sha256(canonical({"remote": <normalized origin URL or null>, "root": <realpath of top level>}))`. Normalization: lowercase the host; drop user info (`user:token@`), query and fragment; drop a trailing `.git` and `/`; map `git@host:owner/repo` and `ssh://git@host/owner/repo` to `host/owner/repo`. A fork or a second clone at another path is a different repository (risk 10 in the roadmap: trust is shared across a team through TL1 policy, not by copying stores).
- **Command digest:** `sha256(canonical({"channel": "profile"|"config", "root": <root path>, "name": <name>, "cmd": <exact command text>}))`. Changing the text, moving it between channels or roots invalidates trust.
- **Set digest:** `sha256(canonical(sorted list of the pending command digests))`. `trust record --pending --digest <d>` refuses when the current pending set's digest differs (`E_TRUST_SET_CHANGED`).
- **Writes:** `flock` on `<user>/.workflow/trust.lock`, then temporary file, `fsync`, rename, `fsync` of the folder. Mode `0600`, folder `0700` (created when missing).
- **Reads:** refused (`E_TRUST_STORE_UNSAFE`, every committed command untrusted) when the store is a symlink, owned by another user, group- or world-writable, or inside the target project folder (which covers projects without git, PF-8). The work-tree test (`trust.inside_work_tree`, §3.3) applies only to a store under `DAEDALUS_HOME`, the one location a repository could influence (PF-3). The password-database home passes even when it is itself a git work tree (a dotfiles repository is the user's own, not one Daedalus works on; review finding a663546-16).
- **Record:** `trust record` runs the read checks first and exits 3 with `E_TRUST_STORE_UNSAFE` and its fix when they fail, so `/setup` never reports trust it can't apply. A store that fails its schema is `E_TRUST_STORE_INVALID`, with the same effect and a fix line ("move it aside and rerun /setup").

### 3.8 Effective commands

`trust.effective_commands(repo, profile, resolved, rederive=True)` returns one record per root and command name:

```json
{"root": ".", "name": "test", "cmd": "bash scripts/test-all.sh", "channel": "profile", "level": "TL4",
 "declared": {"confidence": "user", "confirmed": true},
 "trusted": true, "basis": "trust-store", "unsafe": false, "reason": null}
```

| Source of the command | Trusted when | `basis` |
|---|---|---|
| Config override at TL2 or TL3 | Always (the user's own file) | `user-config` |
| Config override at TL4 (C-3) | The store holds its digest | `trust-store` |
| Profile entry, `script` or `derived` | Re-detection reproduces the same `cmd` at the same confidence (PF-1); otherwise as a `user` entry | `detected` |
| Profile entry, `user`, or any entry with `confirmed: true` | The store holds its digest | `trust-store` |
| Profile entry, `inferred` without `confirmed` | Never without `/setup` | — |

- A config override still wins over the profile entry for the same root and name (today's semantics, `project-profile/SKILL.md:27`); the losing entry is listed as `shadowed`.
- **Re-detection** runs the detector's `build_profile` in process, read-only, with the detector's own timeout (`WORKFLOW_DETECT_TIMEOUT`, default 5 s). On a timeout, entries that need it are `trusted: false`, `reason: "re-detection timed out"`.
- **Fast mode** (`rederive=False`, used by the session banner) skips re-detection and treats `script` and `derived` entries as unverified; it only counts untrusted entries for the banner and never marks anything trusted that full mode wouldn't.
- **`unsafe`** = the committed flag OR `UNSAFE_RE` on the command OR (for re-detected entries) `UNSAFE_BODY_RE` on the body. A committed `unsafe: false` never clears it.
- **Untrusted** entries are reported as unconfirmed `inferred` (R-AC-61): consumers ask, or send the user to `/setup`.
- `trust.commands_digest(records)` = `sha256(canonical(sorted [{root, name, channel, cmd}]))` over the effective set. It covers command **definitions** only, not trust state, because trust changes who may run a command, not what it does. P1c binds evidence to it (R-AC-48).

### 3.9 Interfaces this plan exports (consumed by P1c and P2)

| Interface | Signature or form | Consumer |
|---|---|---|
| Resolver | `wfconfig.resolve(repo: Path, workspace: Optional[Path] = None, run_options: Optional[dict] = None) -> Resolved` | P1c `init`, `admit`, `resume`; P2 guard, `exec.py` |
| Resolved values | `Resolved.values: dict`, `Resolved.get(key)`, `Resolved.explain(key) -> dict`, `Resolved.to_json() -> dict` (`daedalus.policy/1`) | P1c, P2, P1b's `policy.schema.json` |
| Policy digest | `Resolved.policy_digest() -> str` (`sha256:<hex>`) | P1c manifest, drift check, evidence binding |
| Effective commands | `trust.effective_commands(repo, profile, resolved, rederive=True) -> list[dict]` | P1c `init` (briefs), P2 `exec.py` |
| Commands digest | `trust.commands_digest(records) -> str` | P1c manifest, drift check, evidence |
| Trust store | `trust.TrustStore(path: Optional[Path] = None)`: `contains(repo_id, key, digest)`, `record(...)`, `revoke(...)`, `pending(...)` | `/setup`; P2 `exec.py` |
| Repository identity | `trust.repo_identity(repo: Path) -> RepoId(id, remote, root)` | P1c manifest |
| Work-tree check | `trust.inside_work_tree(path: Path) -> bool` (§3.3) | P1a's own source and store checks; P2 (guard paths) |
| Errors | `wfconfig.ConfigError` with `code`, `message`, `fix`, `file`, `line` | P1c (passes codes through) |
| CLI | `workflow.py config resolve\|explain\|get\|commands`, `workflow.py trust list\|pending\|record\|revoke`; the dispatcher's static group table | Commands, hooks; P1c adds groups |

The interfaces are frozen at the end of this plan's first task (T1). A change after that needs a note in P1c's plan.

### 3.10 Platform facts this plan relies on

| Fact | Tag | Used for |
|---|---|---|
| Workspace trust gates allow rules, not hooks | [V] findings §8.1 (65 of 65 sessions, S and P); C-11 | The trust store doesn't read or depend on workspace trust; the guide says so |
| A hook without `onFailure` fails open on a crash or timeout | [V] E1, E2, E4 `default` variants (S, P) | `session-init.sh` keeps failing open (D9: context hooks stay fail-open) |
| Payload `cwd` and paths are canonical (`/private/var/…`) | [V] J1 (C-13) | Repository identity and the TL3 work-tree check use `realpath` |
| An installed plugin's `SessionStart` hook runs in every repository a session opens | [V] findings §8.2 | PF-2's `python3 -I` fix matters on every repository, not just this one |
| Project settings can set environment variables (`env`) | [D] settings docs; not probed | PF-3's constraints on `DAEDALUS_HOME` and `DAEDALUS_POLICY_DIR` |
| Hooks receive `CLAUDE_PROJECT_DIR` | [D] hooks docs; `session-init.sh` already relies on it [I] (`.claude/hooks/session-init.sh:22`) | The banner's TL3 discovery |
| Commands run through the Bash tool receive `CLAUDE_PROJECT_DIR` | **Unverified** | Not relied on: commands pass `--workspace` explicitly, and the variable is only a fallback (AC-7). OQ-10 checks it on both installs |
| Managed settings and `allowManagedHooksOnly` | [D] TC-21, TC-22 | Documented in the trust guide as the way to lock TL1 hooks (P2 registers the guard); not built here |

**Inconclusive probes.** None of I1, M1, C3, C4 or L1 (script install) affects this plan: it adds no hook, no guard rule, no turn cap and no sandbox setting.

---

## 4. Layer tasks

### Layer: lib (python, ci-cd)

- **Root(s):** `.`
- **Needs:** nothing from earlier layers or sibling plans.
- **Produces:** the interfaces in §3.9 (P1c, P2); `daedalus.policy/1` and `daedalus.trust/1` shapes (P1b writes their schemas); `lib/unsafe.py` (P2 extends it).

**Tasks**
- [ ] **T1 Skeleton and interface freeze:** `lib/__init__.py` (exact content, §3.1), `workflow.py` (argparse dispatcher with a static group table; `sys.path.insert(0, <own realpath dir>)`), stubs with the §3.9 signatures and docstrings. Interfaces frozen here.
- [ ] **T2 YAML subset** in `lib/wfconfig.py` (§3.2), with error positions; fixtures `scripts/fixtures/config/yaml/{ok,bad}/*.yml` plus expected JSON.
- [ ] **T3 Key registry** `lib/config_keys.py`: every template and §6.21 key with class, type, enum, default, operator and levels (§3.4); add `gate.trusted_classes` and the `version` key.
- [ ] **T4 Sources and resolution** in `lib/wfconfig.py` (§3.3–§3.5): discovery, managed-path check, `DAEDALUS_HOME` and workspace demotion rules, legacy lift, preference merge, anchor rule and operators, governance, `ignored[]`, warnings, `policy_digest`.
- [ ] **T5 CLI** `workflow.py config resolve|explain|get|commands` with `--json`, `--set`, exit codes (AC-6).
- [ ] **T6 Unsafe vocabulary:** move `UNSAFE_RE` and `UNSAFE_BODY_RE` to `lib/unsafe.py` verbatim; `detect-stack.py` imports it (explicit `sys.path` insert of its own directory); `rules_digest` hashes `lib/unsafe.py` too.
- [ ] **T7 Trust store and identity** in `lib/trust.py` (§3.7): normalization, digests, locked atomic writes, read safety checks.
- [ ] **T8 Effective commands** in `lib/trust.py` (§3.8): both channels, re-detection with timeout, fast mode, `unsafe` recomputation, `commands_digest`.
- [ ] **T9 Detector carry-over:** recompute `unsafe` monotonically in `carry_over` (`detect-stack.py:941–953`); `--set` and `--confirm` stay profile-only (trust is recorded by `workflow.py trust`, called from `/setup`); `write_profile` (`detect-stack.py:1004–1013`) compares the new profile with the file on disk, ignoring `generated_at`, and skips the write when nothing else changed (AC-10).
- [ ] **T10 Trust CLI** `workflow.py trust list|pending|record|revoke` (`--json`; `record --pending --digest`; `record --root R --name N [--channel profile|config]`).
- [ ] **T11 Consumers:**
  - `session-init.sh`: `python3 -I`; overlay from the resolver (regex removed); the banner names configuration errors and untrusted committed commands (fast mode); still exits 0 on every path.
  - Commands and skills read configuration through `workflow.py config`: `.claude/commands/{argus,setup,daily-report,manual-test,feature-plan,apply-ticket,project-manager}.md`, `.claude/skills/{argus,ticket-adapters,project-profile}/SKILL.md`. Each keeps its own `<scripts>` path rule (`setup.md:16`).
  - Commands pass `--workspace <folder the session started from>` to every `workflow.py config` call (AC-7).
  - `/setup` adds the trust step (AC-11) after confirmations.
  - Every file AC-13 lists takes runnable commands from `config commands`: `.claude/commands/{project-manager,test-gen,scaffold,code-cleanup,code-optimize,manual-test}.md`, `.claude/agents/{implementer,test-runner}.md`, `.claude/skills/{project-profile,test-strategy,workflow-contract}/SKILL.md`, `.claude/rules/{stack-knowledge,compounding-dev-cycle}.md`, `CLAUDE.md:11`, the contract strings at `session-init.sh:27` and `:38`, and `README.md:12` (PF-7).
  - `/manual-test` (QA plugin) calls `${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py` on plugin installs and `<scripts>/workflow.py` on script installs (PF-9).
  - Every `python3` invocation in `.claude/**` gets `-I` (PF-2), including `python3 -I -m http.server` in `manual-test.md:42`.
- [ ] **T12 Template:** `templates/workflow-config.example.yml` gains the §6.21 keys with `S`/`P` markers, `gate.trusted_classes`, and `version: 1`; its header describes the five levels and the two merge kinds instead of the three-file list.
- [ ] **T13 Tests** (`scripts/test-config.sh`, `scripts/test-trust.sh`) covering every test id in §2; fixture repositories for AC-12 built in temporary folders at test time (never committed as live repos); every test sets `DAEDALUS_HOME` to a temporary folder or passes explicit paths, so no test reads or writes the real home folder.
- [ ] **T14 Hub hygiene:** `test-all.sh` gains `config`, `trust`, `shell-syntax` and `py38-syntax` (inserted after `bench`); `check.yml` runs `scripts/test-all.sh` as one step with `WORKFLOW_MATRIX_CACHE`; `build-plugin.sh` copies `workflow.py`, `detect-stack.py` and `scripts/lib/**` into `plugins/daedalus-qa/scripts/` as well (a `QA_SCRIPTS` list next to `HOOK_SCRIPTS`, PF-9); regenerate `plugins/**`.
- [ ] **T15 Docs:** ARCHITECTURE §4.2 (command trust), §4.4 (configuration chain → TL1–TL5), §11 (safety model: what is resolved deterministically, what stays prompt-followed until P2), §13 (D19, D23); `docs/guides/trust-and-policy.md` (levels, classes, operators, the trust store, `explain`, managed TL1 setup, what workspace trust does and doesn't do, the `-p` caveat from C-11); README "The project profile"; `workflow-contract/SKILL.md` contract line on trusted commands.
- [ ] **T16 Operational QA** (§9) and `docs/qa/daedalus-hardening-p1a-qa-N.md`.

**Contracts:** §3.6 (resolved document), §3.7 (trust store), §3.8 (effective-command record), §3.9 (Python and CLI interfaces).

**Tests** (all Python `unittest` under Bash wrappers):
- AC-1 → `test-config.sh`: `U-config-yaml-01`…`-20` (one per accepted form and one per rejected construct, each asserting file, line, column and construct).
- AC-2 → `U-trust-sources-01`…`-15`: an unmanaged TL1 file is ignored (ownership injected through a seam in the test, never through an environment variable); a root-owned symlink in the path passes and a user-owned one fails; `DAEDALUS_POLICY_DIR` adds but doesn't replace; a workspace inside a work tree is demoted; a workspace that isn't a strict ancestor of the target is demoted; a `.git` that `git` refuses demotes; a set `GIT_DIR` demotes; a target with no git top level resolves as a TL4 project folder; `DAEDALUS_HOME` inside a work tree, inside the target project folder, owned by another user or world-writable is ignored. **Positive cases:** a non-git folder that is an ancestor of the target repository resolves as TL3; a `DAEDALUS_HOME` under a non-git temporary folder is honored; `inside_work_tree` on a non-git temporary folder returns false without calling `git` (asserted with a stub on the subprocess call).
- AC-3 → `U-config-registry-01` (template ↔ registry drift).
- AC-4 → `U-config-merge-01`…`-13` (preference semantics ported from `argus/SKILL.md:44–50`; legacy lift; governance advisory; `~/.claude/argus.yml` and `<user>/.workflow/config.yml` both set `domain`, and `config.yml` wins).
- AC-5 → `U-policy-monotonic-01`…`-06`, `PT-policy-ops-01`…`-09`.
- AC-6 → `U-config-cli-01`…`-06`, plus a timing test (p95 ≤ 50 ms over 50 in-process resolutions of the fixture set; reported, failing only above 2× the target to keep CI stable).
- AC-7 → `U-config-consumers-01` (grep: no `re.search(r"^overlay:` in hooks; no prose merge rules in the listed files; no `python3 ` without `-I` in `.claude/**`), plus OQ.
- AC-8 → `U-trust-store-01`…`-14` (atomic write, mode bits, lock contention with two processes, unsafe-path refusals including a store inside the project folder, invalid store, a store in a non-git user folder accepted, a password-database home that is a git work tree holds a usable store, a `DAEDALUS_HOME` inside a work tree is refused, `trust record` into a refused store exits 3 without writing, `U-trust-repoid-creds-01`, `U-trust-repoid-nongit-01`).
- AC-9 → `U-trust-effective-01`…`-10` (each table row, shadowing, re-detection timeout, fast mode, `unsafe` never cleared).
- AC-10 → `U-trust-carryover-01`; `U-detector-nowrite-01` (two detector runs without `--ensure` on an unchanged repository leave the profile's bytes and mtime unchanged; a manifest edit still rewrites it); `scripts/test-detector.sh` unchanged.
- AC-11 → `U-trust-cli-01`…`-05` (set digest guard; `--print` writes nothing).
- AC-12 → `PT-trust-profile-01`…`-03`, `PT-trust-config-01`, `PT-trust-nongit-01`, `PT-trust-repoid-01`.
- AC-13 → `U-trust-consumers-01` (grep over all of `.claude/**`, `CLAUDE.md` and `README.md`: no remaining statement that commands of a given confidence run unasked; every file in AC-13's list references `config commands`).
- PF-9 → `U-build-qa-scripts-01` in `test-config.sh`: after a build into a temporary folder, run `workflow.py config resolve --json` and `config commands --json` **from the built QA plugin's `scripts/`** on a fixture repository, and assert both equal the main plugin's output. Command detection doesn't read packs (`detect-stack.py:799–805` builds commands from manifests), so the QA copy, which has no `skills/stacks/`, re-detects the same commands.
- AC-14 → CI. AC-15 → OQ.

**Commands** (from `.workflow/profile.json`):
- **test:** `bash scripts/test-detector.sh` (`user`, confirmed). **Flags:** (1) after T8 lands, this `user` entry is untrusted until the maintainer runs `/setup` and records trust; the test-runner must ask before running it. (2) The umbrella `bash scripts/test-all.sh` isn't the profile's test command yet; register it with `/setup` after T14 (`detect-stack.py --set ".:test=bash scripts/test-all.sh"`, then `workflow.py trust record`).
- **lint:** `bash -n .claude/hooks/session-init.sh` (`user`, confirmed; same trust flag). It covers one file; T14's `shell-syntax` check covers the rest.
- Also run: `scripts/lint-packs.sh`, `scripts/check-generic.sh`, `scripts/build-plugin.sh --check` (all inside `test-all.sh`).
- No typecheck or build commands (stdlib scripts). No command is `unsafe`.

---

## 5. Integration and testing

- **Critical paths:**
  - config files → resolver → `policy_digest` (P1c binds evidence and drift to it);
  - committed profile and config overrides → effective commands → briefs (P1 prompt-followed) → `exec.py` (P2 enforced);
  - `/setup` → trust store → effective commands (trust recorded once per set digest, revoked on text change).
- **Isolation in tests:** every test runs in temporary folders outside any repository; ownership-dependent behavior (TL1) is injected through a function parameter, never through an environment variable a repository could set (PF-3).
- **Cross-plan checks** that run in P1c: `daedalus.policy/1` validates against P1b's `policy.schema.json`; `wfconfig`'s canonical serializer equals `artifacts.canonical_bytes` on shared fixtures.

---

## 6. File changes (root `.`)

**Create**
- `.claude/scripts/lib/__init__.py`, `.claude/scripts/lib/wfconfig.py`, `.claude/scripts/lib/config_keys.py`, `.claude/scripts/lib/trust.py`, `.claude/scripts/lib/unsafe.py`
- `.claude/scripts/workflow.py`
- `scripts/test-config.sh`, `scripts/test-trust.sh`
- `scripts/fixtures/config/**` (YAML subset cases, expected JSON, level fixtures), `scripts/fixtures/trust/**` (profile and config fixtures for AC-12, as plain files copied into temporary repositories at test time)
- `docs/guides/trust-and-policy.md`
- `docs/qa/daedalus-hardening-p1a-qa-N.md` (OQ)

**Modify**
- `.claude/scripts/detect-stack.py` (import `lib/unsafe.py`; `carry_over` recomputes `unsafe`; `rules_digest` covers `lib/unsafe.py`)
- `.claude/hooks/session-init.sh` (`python3 -I`; resolver instead of the regex; banner lines; the contract strings at `:27` and `:38`)
- `.claude/commands/{setup,argus,daily-report,manual-test,feature-plan,apply-ticket,project-manager,test-gen,scaffold,code-cleanup,code-optimize}.md`
- `.claude/skills/{project-profile,argus,ticket-adapters,workflow-contract,test-strategy}/SKILL.md`
- `.claude/rules/{stack-knowledge,compounding-dev-cycle}.md`
- `.claude/agents/{implementer,test-runner}.md` (runnable commands from `config commands`)
- `templates/workflow-config.example.yml`
- `scripts/test-all.sh`, `.github/workflows/check.yml`, `scripts/build-plugin.sh` (QA-plugin script copy, PF-9)
- `ARCHITECTURE.md` (§4.2, §4.4, §11, §13), `README.md` (`:12` and The project profile), `CLAUDE.md` (`:11`; installed as an always-on rule)
- Generated: `plugins/**` (`build-plugin.sh`; copies `scripts/lib/` with structure kept, `scripts/build-plugin.sh:126–130`, and now into `daedalus-qa` too)

**Not touched:** `install.sh` (it already copies `scripts/` recursively, `install.sh:29`; OQ checks that `lib/` lands), `.claude/settings.json` (no new hooks), `.claude/hooks/audit.sh`, `.claude/hooks/audit.log`, `bench/**`, `scripts/probes/**`.

---

## 7. Dependencies / env

- **Runtime:** nothing new. Python 3.8+ standard library (`fcntl`, `pwd`: POSIX only, as today), `git`.
- **Environment variables:**

| Name | Purpose | Example | Required |
|---|---|---|---|
| `DAEDALUS_HOME` | Replaces the user folder (tests, OQ). Honored only outside every git work tree, owned by the user, not group- or world-writable (AC-2) | `$TMPDIR/p1a-home` | Optional |
| `DAEDALUS_POLICY_DIR` | Adds one TL1 source; must pass the managed-path check; never replaces the default paths | `/opt/org/daedalus` (root-owned) | Optional |
| `CLAUDE_PROJECT_DIR` | Workspace folder (set by the host) | — | Set by the host |
| `WORKFLOW_DETECT_TIMEOUT` | Re-detection timeout (existing detector variable) | `5` | Optional |

- **Config changes:** new optional keys in `templates/workflow-config.example.yml` (§3.4, roadmap §6.21); none is required, and every default keeps 0.4.0's behavior except trust (committed commands now need it).

## 8. Design reference

No visual change.

## 9. Manual QA

N/A: no UI-observable AC. **Operational QA** (R-AC-66) replaces it. Each scenario runs in a throwaway repository under `$TMPDIR`, with `DAEDALUS_HOME=$TMPDIR/p1a-home`, on the **script install** (project-scope `.claude/` copied into the throwaway repository) and the **plugin install** (`claude -p … --plugin-dir <built plugin>`, [V] T0 flag check). Headless runs set `DAEDALUS_NONINTERACTIVE=1` (C-12) and `--max-budget-usd` plus `--max-turns`.

| # | Mode | Steps | Expected |
|---|---|---|---|
| OQ-1 | Headless, S and P | Start a session in a repository whose committed profile has a `user` command that writes a canary | The banner says one committed command is untrusted; no canary exists after the session |
| OQ-2 | Headless, S and P | Same repository with a forged `script` entry (PF-1) | `config commands --json` reports `trusted: false`, `basis: null`; the banner counts it after a full check |
| OQ-3 | Headless, S and P | A committed `.workflow/config.yml` `commands` override (C-3) | Untrusted; the project-manager's brief (dry check: ask the main thread to print what it would pass) omits it |
| OQ-4 | Headless, S and P | TL4 `guard.mode: off` and `budgets.rework_rounds: 99` with a TL2 file setting `rework_rounds: 2` | `config explain guard.mode` shows `enforce` from the default and the TL4 value ignored; `rework_rounds` is 2 |
| OQ-5 | Headless, S and P | A config file with an anchor | The banner names the file and line; the session still starts (fail open) |
| OQ-6 | Headless, S and P | A repository containing `json.py` and `lib/wfconfig.py` that each write a canary on import | No canary after session start (PF-2) |
| OQ-7 | Interactive, S and P (maintainer) | Run `/setup` in the OQ-1 repository; confirm the pending set | `trust.json` under `DAEDALUS_HOME` holds the digest, mode `0600`; `config commands` now reports `trusted: true`; editing the command text makes it untrusted again |
| OQ-8 | Interactive (maintainer) | `/argus --local` and `/daily-report` in a repository with TL2 and TL4 settings | Their run notes name the resolved sources from `config resolve`, matching `explain` |
| OQ-9 | Optional, maintainer with admin rights | Create a root-owned policy file with `guard.mode: enforce` at the platform path (`/Library/Application Support/Daedalus/policy.yml` on macOS, `/etc/daedalus/policy.yml` on Linux; on macOS also try `/etc/daedalus/policy.yml`, whose root-owned `/etc` symlink must pass); set TL2 `guard.mode: warn` | `explain` shows `enforce` from TL1 for each path. If the maintainer can't create a root-owned file, record BLOCKED: unit tests cover it through the ownership seam |
| OQ-10 | Headless, S and P | From a command's Bash tool call, print whether `CLAUDE_PROJECT_DIR` is set (name and set/unset only) | Recorded in the QA report; §3.10's "unverified" row is updated from it. Either answer passes, because commands pass `--workspace` |
| OQ-11 | Headless, S and P | Run `/test-gen` on a file in the OQ-1 repository, and `/manual-test` with the dev server down and the committed `dev` command untrusted | Neither runs the untrusted command: no canary; `/manual-test` reports the server BLOCKED and names `/setup` |
| OQ-12 | Headless, S and P | A project folder that isn't a git repository, with a committed `.workflow/config.yml` `commands` override | `config commands` reports it untrusted, level TL4 (PF-8) |
| OQ-13 | Headless, P | Run `/daedalus-qa:manual-test` with a config `qa.base_url` set at TL4 | The QA command resolves it through its own plugin's `workflow.py` (PF-9) |

Report: `docs/qa/daedalus-hardening-p1a-qa-N.md` (PASS / FAIL / BLOCKED per scenario, with the commands run and the observed output, redacted per the P0 rules). Cleanup check: the hub's `git status` and the maintainer's real `~/.workflow` and `~/.claude/settings.json` (content digests) are unchanged.

---

## 10. Risks / potential issues

1. **Prompt fatigue from trust confirmations.** *Mitigation:* one confirmation per pending-set digest; re-detected `script` and `derived` entries need no trust; teams share trusted policy through TL1, not by copying stores.
2. **Re-detection latency** in large repositories. *Mitigation:* only `config commands` and `/setup` re-detect (full mode); the session banner uses fast mode; the detector's own timeout bounds it, and a timeout fails closed.
3. **Behavior change for existing users:** committed `user` commands stop running unprompted after the upgrade. *Mitigation:* the banner and `/setup` explain it; the README and the trust guide carry an upgrade note; P1c's release notes for 0.5.0 lead with it.
4. **Commands drift from the resolver** (prose merge rules creep back). *Mitigation:* `U-config-consumers-01` greps for them in CI.
5. **YAML-subset rejections break existing repository configs.** *Mitigation:* the subset covers every form in the shipped template and overlay template; errors name the line and give a fix; the hook fails open, so a session still starts.

## 11. Open questions

None block this plan. One item for P2: whether the host applies a project `.claude/settings.json` `env` block in an untrusted folder [D, unverified]. AC-2's checks make the answer non-critical here, but P2's guard, which reads `DAEDALUS_NONINTERACTIVE` (C-12), should add a probe for it.

## 12. Next steps

1. `/clear`, then `/daedalus:project-manager docs/plans/daedalus-hardening-p1a.md`.
2. After it lands: register `bash scripts/test-all.sh` as the hub's test command with `/setup`, and record trust for it.
3. Then P1b, then P1c. **P1b doesn't run in parallel with this plan:** P1b reuses this plan's `lib/__init__.py` and QA-plugin copy, and both edit `scripts/test-all.sh`, `scripts/build-plugin.sh`, `.claude/commands/{argus,manual-test,feature-plan,apply-ticket}.md`, `.claude/agents/{implementer,test-runner}.md` and ARCHITECTURE §13, and both regenerate `plugins/**`; there is no worktree isolation before P4 (roadmap §8.3: parallel sessions only on disjoint files). This is a deviation from roadmap §14's "three tracks": the effort is unchanged; only the calendar time grows. If the calendar matters, P1b may be developed in its own git worktree and merged after P1a, rebasing those files.
