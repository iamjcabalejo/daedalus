#!/usr/bin/env bash
# Render the Claude Code plugins from the tracked .claude/ tree (plug-and-play Phase 4, C1-C5).
#
#   scripts/build-plugin.sh           regenerate plugins/ and .claude-plugin/marketplace.json
#   scripts/build-plugin.sh --check   exit 1 if the committed output differs from a fresh build (CI)
#
# Output (generated, committed; never edit by hand):
#   plugins/daedalus/      the workflow: commands, roles, skills (plus workflow-contract/rules/), scripts, hooks/hooks.json
#   plugins/daedalus-qa/   companion for browser QA: qa-tester, manual-qa, /manual-test and .mcp.json (Playwright),
#                          so the Playwright server only starts for people who install it (decision D8)
#   .claude-plugin/marketplace.json   makes this repo a marketplace for both
# Only tracked or new unignored files under .claude/ are used, so gitignored overlays and local files never reach a plugin.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HUB
exec python3 - "$@" <<'PY'
from __future__ import annotations  # Python 3.8+
import filecmp, json, os, re, shutil, stat, subprocess, sys, tempfile
from pathlib import Path

hub = Path(os.environ["HUB"])
MAIN, QA = "daedalus", "daedalus-qa"
VERSION = "0.4.0"
REPO_URL = "https://github.com/tb-jcabalejo/tb-claude-custom-workflow"
OWNER = "tb-jcabalejo"
QA_COMMANDS = {"manual-test"}
QA_AGENTS = {"qa-tester"}
QA_SKILLS = {"manual-qa"}
HOOK_SCRIPTS = ("session-init.sh", "audit.sh")
PLAYWRIGHT = {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]}
# A `.claude/<kind>/` path written as a project-relative reference (not ~/.claude/, $HOME/.claude/ or <root>/.claude/).
REF = re.compile(r"(`?)(?<![\w/~}$])\.claude/(rules|skills|commands|agents|scripts)/([A-Za-z0-9_.-]+)?((?:/[A-Za-z0-9_.<>-]+)*)/?(`?)")

def tracked() -> list[str]:
    # Tracked plus new, unignored files (so a build before the first commit includes them); never ignored ones.
    out = subprocess.run(["git", "-C", str(hub), "ls-files", "--cached", "--others", "--exclude-standard", ".claude"],
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f and (hub / f).is_file()]

def owner_of(kind: str, name: str) -> str:
    stem = name[:-3] if name.endswith(".md") else name
    if (kind == "commands" and stem in QA_COMMANDS) or (kind == "agents" and stem in QA_AGENTS) or (kind == "skills" and stem in QA_SKILLS):
        return QA
    return MAIN

def rewrite(text: str, plugin: str) -> str:
    """Point project-relative .claude/ paths at this plugin's files, or name the other plugin's component."""
    def target_for(kind: str, name: str, rest: str) -> tuple[str, bool]:
        """(replacement, is_path). Paths keep code formatting; cross-plugin names are prose."""
        if kind == "rules":
            if not name:
                return ("${CLAUDE_PLUGIN_ROOT}/skills/workflow-contract/rules/" if plugin == MAIN
                        else f"the {MAIN}:workflow-contract skill's rules/"), plugin == MAIN
            if plugin == MAIN:
                return f"${{CLAUDE_PLUGIN_ROOT}}/skills/workflow-contract/rules/{name}{rest}", True
            return f"the {MAIN}:workflow-contract skill's rules/{name}", False
        if not name:
            return f"${{CLAUDE_PLUGIN_ROOT}}/{kind}/", True
        owner = owner_of(kind, name)
        if owner == plugin:
            return f"${{CLAUDE_PLUGIN_ROOT}}/{kind}/{name}{rest}", True
        stem = name[:-3] if name.endswith(".md") else name
        if kind == "commands":
            return f"the /{owner}:{stem} command (plugin {owner})", False
        if kind == "agents":
            return f"the {owner}:{stem} role (plugin {owner})", False
        if kind == "skills":
            return f"the {owner}:{name} skill (plugin {owner})", False
        return f"the {owner} plugin's scripts/{name}{rest}", False

    def sub(m: re.Match) -> str:
        tick_open, kind, name, rest, tick_close = m.group(1), m.group(2), m.group(3) or "", m.group(4) or "", m.group(5)
        replacement, is_path = target_for(kind, name, rest)
        if tick_open and tick_close:
            return f"`{replacement}`" if is_path else replacement
        return (tick_open or "") + replacement + (tick_close or "")
    return REF.sub(sub, text)

def strip_mcp_servers(text: str) -> str:
    """Plugin agents ignore `mcpServers` (Playwright comes from the plugin's .mcp.json instead)."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return text
    fm = re.sub(r"^mcpServers:\n(?:[ \t]+.*\n?)*", "", m.group(1) + "\n", flags=re.M).rstrip("\n")
    return f"---\n{fm}\n---\n" + text[m.end():]

def put(dest: Path, data: str | bytes, executable: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        dest.write_text(data, encoding="utf-8")
    else:
        dest.write_bytes(data)
    mode = 0o755 if executable else 0o644
    os.chmod(dest, mode)

def hooks_json() -> dict:
    settings = json.loads((hub / ".claude/settings.json").read_text())
    out: dict = {}
    for event, groups in settings.get("hooks", {}).items():
        new_groups = []
        for group in groups:
            hooks = []
            for h in group.get("hooks", []):
                script = Path(h["command"]).name
                hooks.append({**h, "command": f"\"${{CLAUDE_PLUGIN_ROOT}}/scripts/{script}\""})
            new_groups.append({**{k: v for k, v in group.items() if k != "hooks"}, "hooks": hooks})
        out[event] = new_groups
    return {"hooks": out}

def build(out: Path) -> None:
    roots = {MAIN: out / "plugins" / MAIN, QA: out / "plugins" / QA}
    for rel in tracked():
        src = hub / rel
        parts = Path(rel).parts[1:]  # drop ".claude"
        kind = parts[0]
        executable = bool(src.stat().st_mode & stat.S_IXUSR)
        if kind == "settings.json" or rel.endswith(("audit.log", ".DS_Store")):
            continue
        if kind == "hooks":
            if parts[-1] in HOOK_SCRIPTS:
                put(roots[MAIN] / "scripts" / parts[-1], src.read_bytes(), True)
            continue
        if kind == "rules":
            put(roots[MAIN] / "skills" / "workflow-contract" / "rules" / parts[-1], rewrite(src.read_text(), MAIN))
            continue
        if kind not in ("commands", "agents", "skills", "scripts"):
            continue
        plugin = owner_of(kind, parts[1]) if kind != "scripts" else MAIN
        dest = roots[plugin].joinpath(*parts)
        if src.suffix == ".md":
            text = rewrite(src.read_text(), plugin)
            if kind == "agents":
                text = strip_mcp_servers(text)
            put(dest, text, executable)
        else:
            put(dest, src.read_bytes(), executable)
    meta = {
        MAIN: "Plug-and-play Plan → Code → Review → QA workflow: detects each project's stacks and commands into "
              ".workflow/profile.json, plans per layer, implements with stack packs, tests with safe commands, and "
              "reviews with Argus. Browser QA is the daedalus-qa companion.",
        QA: "Browser QA companion for daedalus: the qa-tester role, the manual-qa skill and /manual-test, with the "
            "Playwright MCP server. Install only for projects with a UI.",
    }
    for name, root in roots.items():
        manifest = {"name": name, "version": VERSION, "description": meta[name], "author": {"name": OWNER}, "repository": REPO_URL,
                    "keywords": ["workflow", "planning", "code-review", "testing", "stack-detection"] if name == MAIN
                    else ["qa", "playwright", "browser-testing"]}
        put(root / ".claude-plugin" / "plugin.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    put(roots[MAIN] / "hooks" / "hooks.json", json.dumps(hooks_json(), indent=2) + "\n")
    put(roots[QA] / ".mcp.json", json.dumps({"mcpServers": {"playwright": PLAYWRIGHT}}, indent=2) + "\n")
    repo_slug = REPO_URL.split("github.com/", 1)[1]
    readmes = {
        MAIN: f"""# {MAIN}

A plug-and-play Plan → Code → Review → QA workflow for Claude Code. At session start it detects the project's stacks,
commands and integrations into `.workflow/profile.json`; `/{MAIN}:setup` confirms them. `/{MAIN}:feature-plan` writes a
plan with one task block per layer, and `/{MAIN}:project-manager` runs `{MAIN}:implementer` per layer, then
`{MAIN}:test-runner`, then an Argus review. Load the `{MAIN}:workflow-contract` skill for the rules.

## Install

```
/plugin install {MAIN} --marketplace {repo_slug}
```

Projects with a UI also install the browser-QA companion: `/plugin install {QA} --marketplace {repo_slug}`.

Generated by `scripts/build-plugin.sh` from the repository's `.claude/` tree; don't edit it here.
""",
        QA: f"""# {QA}

Browser QA companion for the `{MAIN}` workflow. It adds the `{QA}:qa-tester` role, the `manual-qa` skill and
`/{QA}:manual-test`, which open the pages a change touched in Chrome through the Playwright MCP server and check every
acceptance criterion with screenshot evidence. It needs Node.js 18+ and Chrome. Install it only for projects with a UI,
since the Playwright server starts whenever the plugin is enabled.

## Install

```
/plugin install {QA} --marketplace {repo_slug}
```

Generated by `scripts/build-plugin.sh` from the repository's `.claude/` tree; don't edit it here.
""",
    }
    for name, root in roots.items():
        put(root / "README.md", readmes[name])
    marketplace = {"name": MAIN, "owner": {"name": OWNER},
                   "description": "The daedalus plug-and-play dev workflow and its browser-QA companion.",
                   "plugins": [{"name": n, "source": f"./plugins/{n}", "description": meta[n]} for n in (MAIN, QA)]}
    put(out / ".claude-plugin" / "marketplace.json", json.dumps(marketplace, indent=2, ensure_ascii=False) + "\n")

def snapshot(base: Path) -> dict[str, tuple[bytes, bool]]:
    files = {}
    for top in ("plugins", ".claude-plugin"):
        for p in sorted((base / top).rglob("*")) if (base / top).exists() else []:
            if p.is_file():
                files[str(p.relative_to(base))] = (p.read_bytes(), bool(p.stat().st_mode & stat.S_IXUSR))
    return files

def main() -> int:
    if "--check" in sys.argv[1:]:
        with tempfile.TemporaryDirectory() as tmp:
            build(Path(tmp))
            fresh, committed = snapshot(Path(tmp)), snapshot(hub)
        problems = sorted(set(fresh) ^ set(committed)) + sorted(k for k in set(fresh) & set(committed) if fresh[k] != committed[k])
        for p in problems:
            state = "missing" if p not in committed else ("stale" if p in fresh else "extra")
            print(f"{state}: {p}")
        print(f"{len(fresh)} generated files, {len(problems)} out of date" + ("" if not problems else " — run scripts/build-plugin.sh"))
        return 1 if problems else 0
    for top in ("plugins", ".claude-plugin"):
        shutil.rmtree(hub / top, ignore_errors=True)
    build(hub)
    print(f"built {len(snapshot(hub))} files into plugins/ and .claude-plugin/")
    return 0

sys.exit(main())
PY
