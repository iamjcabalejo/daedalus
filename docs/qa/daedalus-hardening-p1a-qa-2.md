# Operational QA: Daedalus hardening P1a (run 2)

- **Plan:** [daedalus-hardening-p1a.md](../plans/daedalus-hardening-p1a.md), AC-15, §9 · **Previous:** [run 1](daedalus-hardening-p1a-qa-1.md) (headless OQ-1–6 and OQ-10–13 PASS; OQ-7 and OQ-8 BLOCKED on the maintainer) · since then [rework-4](../plans/daedalus-hardening-p1a-rework-4.md), reviewed in [r5](../reviews/tb-claude-custom-workflow-hardening-p1a-1ef278f-r5.md) (no findings)
- **Date:** 2026-11-27 · **Host:** Claude Code 2.1.325, macOS · **Tree:** uncommitted working tree on `feat/hardening-p1a` over `1ef278f`
- **Verdict:** **OQ-7 PASS on both installs; OQ-8 PASS when the `argus` command runs, with a pre-existing defect: typing `/argus` loads the `argus` skill instead of the command.** OQ-9 not run (optional). With run 1, every required scenario of AC-15 has a PASS. Two deviations are recorded below.

| # | Inst | Verdict | How it ran | Evidence |
|---|---|---|---|---|
| OQ-7 | S | **PASS** (deviation 1) | Maintainer, interactive `/setup` in `<RUN>/OQ-1/S/repo`; project-manager ran the checks | `/setup` flagged the committed `test` (`touch …/CANARY-test`, labelled `user`) as not the maintainer's confirmation and offered `npm test` from `package.json:5`; the maintainer chose it. The store is `-rw-------`; `config commands`: `.:test = npm test [profile TL4, trusted: trust-store]`, `.:install = npm install [trusted: detected]`. After editing `test` to `npm test -- --edited`: `untrusted (committed profile entry; not in your trust store): ask the user, or run /setup`. Profile restored after the check |
| OQ-7 | P | **PASS** (deviation 1) | Maintainer, interactive `/daedalus:setup` in `<RUN>/OQ-1/P/repo` with the rework-4 plugin copy | Same `/setup` question and choice; same store mode, `trusted: trust-store`, and untrusted again after the edit |
| OQ-8 | S | **PASS** for the command; **pre-existing defect** for the typed name (deviation 2) | Headless, `DAEDALUS_HOME` absolute, Haiku/Sonnet, $0.50 cap per run | See below |
| OQ-9 | — | **not run** (optional) | — | Needs a root-owned policy file; unit tests cover TL1 through the ownership seam |

## OQ-8 details

Repository: `<RUN>/OQ-4/S/repo` (TL4 `.workflow/config.yml`: `guard: {mode: "off"}`, `budgets: {rework_rounds: 99}`; TL2 `<RUN>/OQ-4/S/home/.workflow/config.yml`: `budgets: {rework_rounds: 2}`), one extra commit, base `HEAD~1`.

**Reference (`config explain`, absolute `DAEDALUS_HOME`):** `guard.mode = enforce`, from default, `TL4 .workflow/config.yml:1: off → ignored (weakens default value …)`; `budgets.rework_rounds = 2`, from TL2 (`<RUN>/OQ-4/S/home/.workflow/config.yml`), `TL4 …:2: 99 → ignored (… above the ceiling 2)`.

| Run | Model · turns · cost | Result |
|---|---|---|
| `/daily-report` | haiku · 5 · $0.011 | **PASS.** First call: `workflow.py config resolve --json --workspace "$PWD"`. The footer matches the resolved values: "tickets 0 (none configured) … chat 0 messages / 0 meetings (none configured)". No invented items |
| `/argus --local HEAD~1` (typed) | haiku · 5 · $0.009; sonnet · 3 · $0.132 | **Did not run the command.** Neither run called `config resolve`, `argus-bundle.sh` or the `argus` role; the Haiku run read `.claude/skills/argus/review-template.md` and the Sonnet run used the host's own findings tool. Both wrote a short review with no configuration notes. Cause: deviation 2 |
| `argus` command, invoked by its file (`.claude/commands/argus.md` with `--local HEAD~1`) | sonnet · 9 · $0.350 | **PASS.** Phase A in order: `workflow.py config resolve --json --repo . --workspace .`, then `argus-bundle.sh --local HEAD~1`, then the `argus` role, then the body check and save (`docs/reviews/repo-main-00492bc.md` in the test repository). Run notes: "Config: domain `none` from default; `tickets.system` `auto` from default" and "The repo's `.workflow/config.yml` tried to set `guard.mode: off` and `budgets.rework_rounds: 99`. Config resolution ignored both". Matches `explain` for the keys Argus uses (`domain`, `tickets.system`) and for the two ignored TL4 values. The notes don't name the TL2 file as the source of `rework_rounds = 2`; that's a project-manager budget Argus doesn't use |

OQ-8 spend: $0.50 of the $1 the maintainer approved. Raw streams: `<RUN>/OQ-8/S/raw/`.

## Deviations and findings

1. **The trust stores of OQ-7 went to the maintainer's real `~/.workflow/trust.json`.** The instructions gave `DAEDALUS_HOME=../home`, a relative path. `wfconfig.user_folder` refuses it (`not an absolute path`) and falls back to the real home folder, reporting it only as `store.warning`. The store holds only the two test repositories (`OQ-1/S/repo`, `OQ-1/P/repo`; `install` and `test` digests each); `~/.workflow` didn't exist before. The checks above read that store. **Suggestion (P1b):** when `DAEDALUS_HOME` is set but refused, fail closed for writes (refuse `trust record`) instead of writing to the real home: the variable exists to keep runs away from the real store.
2. **`/argus` loads the `argus` skill, not the `argus` command (pre-existing, outside P1a).** `.claude/commands/argus.md` and `.claude/skills/argus/SKILL.md` share the name `argus` (both already at `1ef278f`); the plugin has the same pair (`daedalus:argus`). On 2.1.325 the typed `/argus --local HEAD~1` behaved like the skill in both runs: no Phase A, so no `config resolve`, no bundle, no reviewer role. The `/project-manager` cycle isn't affected (it follows the command file), but a maintainer typing `/argus` gets a rubric-only review. **Fix:** give the skill and the command different names (for example a `argus-rubric` skill), and update every reference. These files belong to the concurrent token-diet work, so the fix should land with or after it.
3. **`/setup` caught the forged command (positive).** On both installs it said the committed profile "marks the test command as user-confirmed when it only runs touch on a canary file", that "its 'user' label doesn't count as your confirmation", and offered the real `npm test`.
4. **Plugin-install wording (minor):** the untrusted reason from `trust.py` still ends "or run /setup" on the plugin install (noted in r5's weighed items).

## Isolation and cleanup

- `~/.workflow/` held `trust.json` (two test-repository entries) and `trust.lock`, from deviation 1. With the maintainer's approval both were moved to `<RUN>/OQ-7/stray-home-workflow/` and the empty `~/.workflow` was removed, so the home folder is back to its pre-QA state. Nothing else in the maintainer's home changed in this run; the OQ-8 runs used `--no-session-persistence` and an absolute `DAEDALUS_HOME`.
- The hub's `.workflow/profile.json` is unchanged (two `sed` commands meant for a test repository ran in the hub and matched nothing).
- Test repositories and raw output stay under `<RUN>` (the session scratchpad).

## Remaining maintainer steps

- Plan §12: register `bash scripts/test-all.sh` as the hub's `test` command with `/setup` and record trust.
