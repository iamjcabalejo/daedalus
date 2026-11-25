"""Post-run isolation check and guarded cleanup for the probe harness (AC-1).

snapshot() records digests, never file contents:
  - the hub's `git status --porcelain` lines. Only status lines are compared, so a file that was already modified
    and changes again (for example the hub's own audit log) is not a difference; a new, deleted or newly modified
    file is;
  - user-scope files: ~/.claude/settings.json, the plugin registries under ~/.claude/plugins/ (file names: verify
    in T0), and the Cursor and Codex user hook files;
  - optionally the text of the host's plugin list (`claude plugin list`, verify in T0), passed in by the caller.
compare() returns one line per difference; any difference is a FAIL.

safe_remove() deletes only inside a `daedalus-probes` root and refuses any path with a `..` part, so a bad path can
never reach the hub, the home dir or $TMPDIR.
Every function takes its paths as arguments, so test-probes.sh runs them on fake hubs and fake home dirs.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional

PROBE_ROOT_NAME = "daedalus-probes"
USER_SCOPE_FILES = (
    ".claude/settings.json",
    ".claude/plugins/installed_plugins.json",
    ".claude/plugins/known_marketplaces.json",
    ".cursor/hooks.json",
    ".codex/hooks.json",
    ".codex/config.toml",
)


class IsolationError(RuntimeError):
    """The isolation state can't be read, or a cleanup target is outside the probe root."""


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return digest_bytes(path.read_bytes())
    except OSError as err:
        raise IsolationError(f"cannot read {path.name} for the isolation snapshot: {err}") from err


def hub_status(hub: Path) -> list:
    try:
        out = subprocess.run(["git", "-C", str(hub), "status", "--porcelain=v1", "--untracked-files=all"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as err:
        raise IsolationError(f"cannot read git status of {hub}: {err}") from err
    return sorted(line for line in out.splitlines() if line.strip())


def snapshot(hub: Path, home: Path, plugin_list: Optional[str] = None) -> dict:
    status = hub_status(hub)
    return {
        "hub_status": status,
        "hub_status_digest": digest_bytes("\n".join(status).encode()),
        "user_files": {rel: file_digest(home / rel) for rel in USER_SCOPE_FILES},
        "plugin_list_digest": digest_bytes(plugin_list.encode()) if plugin_list is not None else None,
    }


def compare(before: dict, after: dict) -> list:
    diffs = []
    if before["hub_status_digest"] != after["hub_status_digest"]:
        added = sorted(set(after["hub_status"]) - set(before["hub_status"]))
        removed = sorted(set(before["hub_status"]) - set(after["hub_status"]))
        diffs += [f"hub git status gained: {line}" for line in added]
        diffs += [f"hub git status lost: {line}" for line in removed]
    for rel in USER_SCOPE_FILES:
        old, new = before["user_files"].get(rel), after["user_files"].get(rel)
        if old != new:
            state = "created" if old is None else "deleted" if new is None else "changed"
            diffs.append(f"user-scope file {state}: ~/{rel}")
    if before.get("plugin_list_digest") != after.get("plugin_list_digest"):
        diffs.append("user-scope plugin list changed")
    return diffs


def is_within(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


def safe_remove(target: Path, probe_root: Path) -> bool:
    """Remove a file or folder that lies strictly inside the probe root; return True when something was removed."""
    if probe_root.name != PROBE_ROOT_NAME:
        raise IsolationError(f"refusing to clean up: {probe_root} is not a {PROBE_ROOT_NAME} folder")
    # Resolving only the parent leaves a trailing `..` in place (root/run/.. would pass and rmtree the root), so any
    # `..` is refused outright; no cleanup target needs one.
    if ".." in target.parts:
        raise IsolationError(f"refusing to remove {target}: the path contains '..'")
    # Resolve the parent only, so a symlink inside the root is unlinked rather than followed.
    location = target.parent.resolve() / target.name
    if not is_within(location.parent, probe_root) or location == probe_root.resolve():
        raise IsolationError(f"refusing to remove {target}: it is not inside {probe_root}")
    if target.is_symlink() or target.is_file():
        target.unlink()
        return True
    if target.is_dir():
        shutil.rmtree(target)
        return True
    return False


def leftovers(paths: Iterable) -> list:
    return [str(path) for path in paths if Path(path).exists() or Path(path).is_symlink()]
