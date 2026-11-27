#!/usr/bin/env bash
# Script install of the daedalus workflow (plug-and-play Phase 4, AC-12b). Claude Code plugin users don't need this:
#   /plugin install daedalus --marketplace iamjcabalejo/daedalus
#
#   ./install.sh --user                     install into ~/.claude (every project)
#   ./install.sh --project <path>           install into <path>/.claude (one project or workspace)
#   ./install.sh ... --overlay <dir>        also install a private overlay (see overlays/_template/README.md)
#   ./install.sh ... --addon graphify       also install the optional /graphify build skill
#   ./install.sh ... --cursor               also install the generated Cursor layer (after Phase C builds it)
#   ./install.sh ... --prune-legacy         back up and remove files retired from the original install (restored on uninstall)
#   ./install.sh ... --dry-run              show what would change and stop (the default when not run in a terminal)
#   ./install.sh ... --yes                  don't ask for confirmation
#   ./install.sh --uninstall --user | --project <path>   remove exactly what the manifest says was installed
#
# Safety: files it would overwrite are backed up first (and restored on uninstall); hooks are merged into
# settings.json without touching other entries; a manifest (<.claude>/.daedalus-install-manifest.json) records
# every change. Only tracked or new unignored hub files are copied, so gitignored local files never spread.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HUB
exec python3 - "$@" <<'PY'
from __future__ import annotations  # Python 3.8+
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

hub = Path(os.environ["HUB"])
HOME = Path(os.environ.get("DAEDALUS_HOME") or Path.home())  # DAEDALUS_HOME exists for tests
MANIFEST = ".daedalus-install-manifest.json"
COPY_DIRS = ("commands", "agents", "skills", "scripts", "hooks", "rules")
SKIP = ("settings.json", "audit.log", ".DS_Store")
CONTRACT_RULE = "rules/daedalus-workflow.md"  # CLAUDE.md's contract, installed as a rule so no CLAUDE.md is overwritten
# Retired by plug-and-play Phase 2-3 (content moved to packs, implementer, argus, /scaffold, /test-gen).
LEGACY = ["agents/backend-architect.md", "agents/frontend-architect.md", "agents/backend-reviewer.md",
          "agents/frontend-reviewer.md", "rules/python-backend.md", "rules/api-routes-python.md", "rules/csharp-backend.md",
          "rules/api-routes-csharp.md", "rules/react-frontend.md", "rules/typescript.md", "skills/backend-architect",
          "skills/frontend-architect", "skills/backend-reviewer", "skills/frontend-reviewer", "skills/api-design-patterns",
          "skills/api-testing", "commands/api-new.md", "commands/api-test.md", "skills/argus/stacks",
          "skills/argus/failure-modes.md",
          # Skills renamed so /argus and /trace-flow run their commands; the argus domains/ folder (user packs) stays.
          "skills/argus/SKILL.md", "skills/argus/review-template.md", "skills/argus/scan-template.md",
          "skills/argus/config-template.yml", "skills/trace-flow"]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def hub_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(hub), "ls-files", "--cached", "--others", "--exclude-standard", ".claude"],
                         capture_output=True, text=True, check=True).stdout
    files = []
    for rel in out.splitlines():
        parts = Path(rel).parts
        if len(parts) > 1 and parts[1] in COPY_DIRS and parts[-1] not in SKIP and (hub / rel).is_file():
            files.append(str(Path(*parts[1:])))
    return sorted(files)

def plan_copies(target: Path, args) -> list[tuple[Path, Path]]:
    """(source, destination) pairs."""
    pairs = [(hub / ".claude" / rel, target / rel) for rel in hub_files()]
    pairs.append((hub / "CLAUDE.md", target / CONTRACT_RULE))
    if args.addon == "graphify":
        src = hub / "addons" / "graphify" / "skills" / "graphify"
        pairs += [(p, target / "skills" / "graphify" / p.relative_to(src)) for p in sorted(src.rglob("*")) if p.is_file()]
    if args.overlay:
        pairs += overlay_copies(Path(args.overlay).resolve(), target)
    if args.cursor:
        cursor = hub / "cursor" / ".cursor"
        if not cursor.is_dir():
            sys.exit("--cursor: the Cursor layer isn't built yet (plug-and-play Phase C).")
        dest = (HOME / ".cursor") if args.user else (target.parent / ".cursor")
        pairs += [(p, dest / p.relative_to(cursor)) for p in sorted(cursor.rglob("*")) if p.is_file()]
    return pairs

def overlay_copies(overlay: Path, target: Path) -> list[tuple[Path, Path]]:
    meta = overlay / "overlay.yml"
    if not meta.is_file():
        sys.exit(f"--overlay: {overlay} has no overlay.yml")
    name = next((l.split(":", 1)[1].strip() for l in meta.read_text().splitlines() if l.startswith("name:")), overlay.name)
    pairs = []
    for p in sorted(overlay.rglob("*")):
        if not p.is_file() or p.name == ".DS_Store":
            continue
        rel = p.relative_to(overlay)
        top = rel.parts[0]
        if top in ("rules", "skills"):
            pairs.append((p, target / rel))
        elif rel == Path("hooks/context.txt"):
            pairs.append((p, target / "hooks" / "context.txt"))
        elif rel.name != "config.yml":
            pairs.append((p, target / "overlays" / name / rel))
    return pairs

def hook_entries(target: Path, user: bool) -> dict[str, list[dict]]:
    settings = json.loads((hub / ".claude" / "settings.json").read_text())
    out: dict[str, list[dict]] = {}
    for event, groups in settings.get("hooks", {}).items():
        for group in groups:
            for h in group.get("hooks", []):
                script = Path(h["command"]).name
                command = f"\"{target / 'hooks' / script}\"" if user else f"${{CLAUDE_PROJECT_DIR}}/.claude/hooks/{script}"
                entry = {k: v for k, v in group.items() if k != "hooks"}
                entry["hooks"] = [{**h, "command": command}]
                out.setdefault(event, []).append(entry)
    return out

def is_ours(command: str) -> bool:
    """Our hook, from this or an older install (any path ending in /.claude/hooks/<our script>)."""
    c = command.strip().strip('"')
    return any(c.endswith(f"/.claude/hooks/{s}") for s in ("session-init.sh", "audit.sh"))

def merge_hooks(settings_path: Path, wanted: dict[str, list[dict]], apply: bool) -> tuple[list, list]:
    settings = json.loads(settings_path.read_text()) if settings_path.is_file() else {}
    hooks = settings.setdefault("hooks", {})
    added, replaced = [], []
    for event, entries in wanted.items():
        groups = hooks.setdefault(event, [])
        kept = []
        for g in groups:
            ours = [h for h in g.get("hooks", []) if is_ours(h.get("command", ""))]
            if ours and len(ours) == len(g.get("hooks", [])):
                replaced += [(event, h["command"]) for h in ours]
                continue
            kept.append(g)
        for entry in entries:
            kept.append(entry)
            added.append((event, entry["hooks"][0]["command"]))
        hooks[event] = kept
    replaced = [r for r in replaced if r not in added]
    if apply:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return added, replaced

def confirm(args) -> bool:
    if args.dry_run:
        return False
    if args.yes:
        return True
    if not sys.stdin.isatty():
        print("\nNot a terminal: this was a dry run. Re-run with --yes to apply.")
        return False
    return input("\nProceed? [y/N] ").strip().lower() in ("y", "yes")

def install(target: Path, args) -> int:
    manifest_path = target / MANIFEST
    if manifest_path.is_file():
        sys.exit(f"Already installed in {target} (manifest found). Run --uninstall first, then install again.")
    pairs = plan_copies(target, args)
    new = [d for s, d in pairs if not d.exists()]
    overwrite = [d for s, d in pairs if d.exists() and sha(d) != sha(s)]
    same = [d for s, d in pairs if d.exists() and sha(d) == sha(s)]
    settings_path = target / "settings.json"
    added, replaced = merge_hooks(settings_path, hook_entries(target, args.user), apply=False)
    config_note = overlay_config_plan(args)
    legacy = [target / rel for rel in LEGACY if (target / rel).exists()] if args.prune_legacy else []
    print(f"Install daedalus into {target}")
    print(f"  {len(new)} new files, {len(overwrite)} to overwrite (backed up first), {len(same)} already identical")
    for d in overwrite:
        print(f"    overwrite: {d}")
    print(f"  settings.json: add {len(added)} hook entries; replace {len(replaced)} older daedalus/workflow hook entries")
    for event, command in replaced:
        print(f"    replace: {event} {command}")
    if config_note:
        print(f"  {config_note}")
    if legacy:
        print(f"  prune {len(legacy)} retired files or folders (backed up, restored on uninstall):")
        for p in legacy:
            print(f"    prune: {p}")
    elif not args.prune_legacy and any((target / rel).exists() for rel in LEGACY):
        print("  note: files retired from the original install are present; add --prune-legacy to back them up and remove them")
    if not confirm(args):
        return 0
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    backup_root = target / ".daedalus-backup" / stamp
    record = {"version": 1, "installed_at": stamp, "target": str(target), "user": args.user, "files": {},
              "backups": {}, "dirs_created": [], "hooks_added": [], "hooks_replaced": replaced,
              "settings_created": not settings_path.is_file(), "config_created": None, "pruned": {}}
    for path in legacy:
        backup = backup_root / "pruned" / path.relative_to(target)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(backup))
        record["pruned"][str(path)] = str(backup)
    for src, dest in pairs:
        if dest.exists() and sha(dest) != sha(src):
            try:
                backup = backup_root / dest.relative_to(target)
            except ValueError:  # outside the target (for example ~/.cursor)
                backup = backup_root / "external" / dest.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup)
            record["backups"][str(dest)] = str(backup)
        for parent in reversed(dest.parents):
            if not parent.exists():
                parent.mkdir()
                record["dirs_created"].append(str(parent))
        shutil.copy2(src, dest)
        record["files"][str(dest)] = sha(dest)
    if settings_path.is_file():
        settings_backup = backup_root / "settings.json"
        settings_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings_path, settings_backup)
        record["settings_backup"] = str(settings_backup)
    added, _ = merge_hooks(settings_path, hook_entries(target, args.user), apply=True)
    record["hooks_added"] = added
    record["config_created"] = apply_overlay_config(args)
    manifest_path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"\nInstalled {len(record['files'])} files, {len(added)} hook entries. Manifest: {manifest_path}")
    print("Next: start a new Claude Code session in a project and run /setup.")
    return 0

def overlay_config_plan(args) -> str:
    if not args.overlay:
        return ""
    cfg = Path(args.overlay) / "config.yml"
    if not cfg.is_file():
        return ""
    home_cfg = HOME / ".workflow" / "config.yml"
    if home_cfg.exists():
        return f"overlay config: {home_cfg} exists, so it is left alone; merge {cfg} into it by hand (keys you set win)"
    return f"overlay config: create {home_cfg} from {cfg}"

def apply_overlay_config(args) -> str | None:
    if not args.overlay:
        return None
    cfg = Path(args.overlay) / "config.yml"
    home_cfg = HOME / ".workflow" / "config.yml"
    if not cfg.is_file() or home_cfg.exists():
        return None
    home_cfg.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cfg, home_cfg)
    return json.dumps({"path": str(home_cfg), "sha": sha(home_cfg)})

def uninstall(target: Path, args) -> int:
    manifest_path = target / MANIFEST
    if not manifest_path.is_file():
        sys.exit(f"No daedalus install manifest in {target}.")
    record = json.loads(manifest_path.read_text())
    changed = [f for f, h in record["files"].items() if Path(f).exists() and sha(Path(f)) != h]
    print(f"Uninstall daedalus from {target}")
    print(f"  remove {len(record['files']) - len(changed)} files, keep {len(changed)} you changed; restore {len(record['backups']) + len(record.get('pruned', {}))} backups;"
          f" remove {len(record['hooks_added'])} hook entries")
    for f in changed:
        print(f"    keep (modified since install): {f}")
    if not confirm(args):
        return 0
    for f, h in record["files"].items():
        p = Path(f)
        if p.exists() and sha(p) == h:
            p.unlink()
    for dest, backup in list(record["backups"].items()) + list(record.get("pruned", {}).items()):
        if Path(backup).exists() and not Path(dest).exists():
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(backup, dest)
    settings_path = target / "settings.json"
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text())
        wanted = {(e, c) for e, c in record["hooks_added"]}
        for event in list(settings.get("hooks", {})):
            groups = [g for g in settings["hooks"][event]
                      if not all((event, h.get("command")) in wanted for h in g.get("hooks", [])) or not g.get("hooks")]
            if groups:
                settings["hooks"][event] = groups
            else:
                del settings["hooks"][event]
        if not settings.get("hooks"):
            settings.pop("hooks", None)
        backup = Path(record["settings_backup"]) if record.get("settings_backup") else None
        if record.get("settings_created") and not settings:
            settings_path.unlink()
        elif backup and backup.is_file() and json.loads(backup.read_text()) == settings:
            shutil.copy2(backup, settings_path)  # nothing else changed: restore the original bytes
        else:
            settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        if backup and backup.is_file():
            backup.unlink()
    if record.get("config_created"):
        info = json.loads(record["config_created"])
        p = Path(info["path"])
        if p.exists() and sha(p) == info["sha"]:
            p.unlink()
    for d in sorted(record["dirs_created"], key=len, reverse=True):
        try:
            Path(d).rmdir()
        except OSError:
            pass
    backup_root = target / ".daedalus-backup"
    for d in sorted(backup_root.rglob("*"), key=lambda p: len(str(p)), reverse=True) if backup_root.exists() else []:
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass
    try:
        backup_root.rmdir()
    except OSError:
        pass
    manifest_path.unlink()
    print("Uninstalled.")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(prog="install.sh", description="Install the daedalus workflow by copying it into .claude/.")
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--user", action="store_true", help="install into ~/.claude")
    where.add_argument("--project", metavar="PATH", help="install into PATH/.claude")
    ap.add_argument("--overlay", metavar="DIR", help="also install this overlay folder")
    ap.add_argument("--addon", choices=["graphify"], help="also install an optional add-on")
    ap.add_argument("--cursor", action="store_true", help="also install the generated Cursor layer")
    ap.add_argument("--prune-legacy", action="store_true", help="back up and remove files retired from the original install")
    ap.add_argument("--uninstall", action="store_true", help="remove what the manifest says was installed")
    ap.add_argument("--dry-run", action="store_true", help="show the changes and stop")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    args = ap.parse_args()
    target = (HOME / ".claude") if args.user else (Path(args.project).expanduser().resolve() / ".claude")
    if not args.user and not target.parent.is_dir():
        sys.exit(f"--project: {target.parent} is not a directory")
    if target.resolve() == (hub / ".claude").resolve():
        sys.exit("Refusing to install the hub into itself.")
    return uninstall(target, args) if args.uninstall else install(target, args)

sys.exit(main())
PY
