"""Trust levels, the user trust store and effective commands (plan P1a §3.3, §3.7, §3.8).

- `inside_work_tree`, `top_level`: the one work-tree check (TL3, DAEDALUS_HOME, the trust store) and the
  target's top-level folder.
- `repo_identity`: {normalized origin URL, realpath of the top level} → a `sha256:` id. No credentials, ever.
- `TrustStore`: `<user>/.workflow/trust.json` (`daedalus.trust/1`): read safety checks, flock'ed atomic writes.
  It holds command digests and `trusted_at` only, never command text.
- `effective_commands` / `evaluate`: both command channels (the committed profile and `commands` overrides in
  configuration) with their trust state; `commands_digest` over the definitions.
- `add_cli` / `run_cli`: `workflow.py trust list|pending|record|revoke`.

Nothing here runs project code: re-detection runs the detector's `build_profile` in process (read-only), and the
only subprocesses are read-only `git` calls. Python 3.8+, standard library only; POSIX (fcntl, pwd).
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import secrets
import stat
import subprocess
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from . import wfconfig
from .text import escape_hidden, has_hidden, has_line_break
from .unsafe import UNSAFE_RE
from .wfconfig import ConfigError, SourceContext, UsageError

GIT_TIMEOUT_SECONDS = 2
STORE_SCHEMA = "daedalus.trust/1"
STORE_FOLDER = ".workflow"
STORE_NAME = "trust.json"
LOCK_NAME = "trust.lock"
MAX_STORE_BYTES = 8 * 1024 * 1024
CHANNELS = ("profile", "config")
DETECTED_CONFIDENCES = ("script", "derived")
# Config levels whose `commands` overrides are trusted as they are: TL1 managed organization policy and TL2 the
# user's own file. TL3 needs the store like TL4: an extracted folder outside any work tree can sit above a nested
# repository and claim workspace level (rework-1, finding 1ef278f-3).
SELF_TRUSTED_LEVELS = ("TL1", "TL2")
KNOWN_CONFIDENCES = ("script", "derived", "user", "inferred")
DEFAULT_DETECT_TIMEOUT = 5.0
# detect-stack.py arms its own hard limit at its timeout + 3 s (arm_hard_timeout); re-detection waits as long.
DETECT_HARD_GRACE = 3.0
STOPPED_EARLY = "detection stopped early"
COMMANDS_SCHEMA = "daedalus.commands/1"
MALFORMED = "malformed profile entry"
MALFORMED_CONFIG = "malformed config override"

E_TRUST_STORE_UNSAFE = wfconfig.E_TRUST_STORE_UNSAFE
E_TRUST_STORE_INVALID = wfconfig.E_TRUST_STORE_INVALID
E_TRUST_SET_CHANGED = "E_TRUST_SET_CHANGED"
E_REPO_ID = wfconfig.E_REPO_ID

# Variables that point git at another repository; any of them set means "a repository can be anywhere".
_GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE")
_GIT_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
                 "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_DEFAULT_PORTS = {"https": 443, "http": 80, "ssh": 22, "git": 9418}
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)

RedetectFn = Callable[[Path, float], Mapping[str, Any]]


def _git_env() -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_DROP}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(folder: Path, *args: str) -> Optional[str]:
    """Run a read-only git command in `folder`; stdout on success, None on any error or timeout."""
    try:
        result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True,
                                timeout=GIT_TIMEOUT_SECONDS, env=_git_env(), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _find_dot_git(real: Path) -> Tuple[Optional[Path], bool]:
    """(folder holding the nearest `.git` at or above `real`, whether an unreadable component was met)."""
    for folder in (real, *real.parents):
        try:
            os.lstat(os.path.join(str(folder), ".git"))
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            return None, True
        return folder, False
    return None, False


def inside_work_tree(path: Path, *, environ: Optional[Mapping[str, str]] = None) -> bool:
    """True when `path` may be repository content (§3.3; review finding a663546-13).

    1. GIT_DIR or GIT_WORK_TREE set → True (a repository can be anywhere).
    2. Walk realpath(path) and each ancestor up to `/`: an unreadable component → True; no `.git` entry
       (directory, or a `gitdir:` file) anywhere → False, without ever calling git.
    3. A `.git` was found: confirm with `git rev-parse --is-inside-work-tree` (GIT_OPTIONAL_LOCKS=0, 2 s
       timeout). Any answer other than a clean `true` (an error such as dubious ownership, a timeout, or
       `false` inside a `.git` folder) → True: fail closed, because a `.git` exists.

    git is never asked about a folder with no `.git` above it, so "not a repository" (exit 128) can't be
    misread as "inside". `environ` defaults to os.environ.
    """
    env = os.environ if environ is None else environ
    if any(env.get(name) for name in _GIT_LOCATION_VARS):
        return True
    real = Path(os.path.realpath(str(path)))
    holder, unreadable = _find_dot_git(real)
    if unreadable:
        return True
    if holder is None:
        return False
    # Step 3 (§3.3). A clean `true` confirms "inside"; every other answer fails closed because a `.git`
    # exists, so the walk alone decides the result and git only confirms it.
    _git(real if real.is_dir() else holder, "rev-parse", "--is-inside-work-tree")
    return True


def top_level(target: Path) -> Tuple[Path, bool]:
    """(the target's top-level folder, whether git confirmed it) for an existing folder (§3.3, TL4).

    No `.git` at or above the target → the target folder itself (a project folder without git).
    A `.git` that git accepts → `git rev-parse --show-toplevel`, resolved with realpath (C-13).
    A `.git` that git refuses (dubious ownership, a broken `gitdir:`) → the folder holding that `.git`.
    """
    real = Path(os.path.realpath(str(target)))
    holder, _unreadable = _find_dot_git(real)
    if holder is None:
        return real, False
    out = _git(real, "rev-parse", "--show-toplevel")
    if out and out.strip():
        return Path(os.path.realpath(out.strip())), True
    return holder, False


# ---------- repository identity (§3.7, PF-6, PF-8) ----------

class RepoId(NamedTuple):
    """Repository identity (§3.7): `id` is "sha256:<hex>" over {remote, root}; no credentials, ever."""

    id: str
    remote: Optional[str]
    root: str


def normalize_remote(url: Optional[str]) -> Optional[str]:
    """`host/owner/repo` for a remote URL, with no credentials (§3.7, PF-6); None for an empty one.

    Lowercases the host; drops user info, query, fragment, a default port, a trailing `.git` and `/`; maps
    `git@host:o/r` and `ssh://git@host/o/r` to `host/o/r`. A local-path remote keeps its path.
    """
    text = (url or "").strip()
    if not text:
        return None
    if "://" in text:
        return _normalize_url(text)
    return _normalize_scp_or_path(text)


def _clean_path(path: str) -> str:
    path = re.split(r"[?#]", path, 1)[0].rstrip("/")
    if path.endswith(".git"):
        path = path[:-4].rstrip("/")
    return path


def _join(host: str, path: str) -> Optional[str]:
    clean = _clean_path(path).lstrip("/")
    if not host:
        return clean or None
    return f"{host}/{clean}" if clean else host


def _normalize_url(text: str) -> Optional[str]:
    try:
        parts = urlsplit(text)
    except ValueError:  # a malformed bracketed host: keep what follows the last `@` of the authority
        authority, _, path = re.split(r"[?#]", text.split("://", 1)[1], 1)[0].partition("/")
        return _join(authority.rpartition("@")[2].lower(), path)
    try:
        port = parts.port
    except ValueError:  # a non-numeric port: keep the host alone
        port = None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if port is not None and _DEFAULT_PORTS.get(scheme) != port:
        host = f"{host}:{port}"
    if scheme == "file" or not host:
        return _clean_path(parts.path) or None
    return _join(host, parts.path)


def _normalize_scp_or_path(text: str) -> Optional[str]:
    """`[userinfo@]host:path` (git's scp-like form: a colon before the first slash), else a local path."""
    slash = text.find("/")
    head = text if slash < 0 else text[:slash]
    rest = text[head.rfind("@") + 1:]
    colon = rest.find(":")
    rest_slash = rest.find("/")
    if colon > 0 and (rest_slash < 0 or colon < rest_slash):
        return _join(rest[:colon].lower(), rest[colon + 1:])
    # A local path. Anything up to a last `@` goes too, so nothing credential-like can survive; the identity
    # also holds the root's realpath, so a lossy remote never merges two repositories.
    return _clean_path(rest.rpartition("@")[2]) or None


def repo_identity(repo: Path) -> RepoId:
    """Identity of the repository containing `repo` (§3.7).

    remote: the normalized origin URL (host lowercased; user info, query, fragment, a trailing `.git`
    and `/` dropped; `git@host:o/r` and `ssh://git@host/o/r` → `host/o/r`), or None without git.
    root: realpath of the top level (the folder itself for a project without git, PF-8).
    Raises ConfigError(E_REPO_ID) when the folder doesn't exist.
    """
    real = Path(os.path.realpath(str(repo)))
    if not real.is_dir():
        raise ConfigError(E_REPO_ID, f"target folder {repo} doesn't exist or isn't a folder",
                          "run from the project folder, or pass --repo <folder>")
    top, is_git = top_level(real)
    remote = None
    if is_git:
        url = _git(top, "config", "--get", "remote.origin.url")
        remote = normalize_remote(url) if url else None
    ident = wfconfig.sha256_tag(wfconfig.canonical_bytes({"remote": remote, "root": str(top)}))
    return RepoId(ident, remote, str(top))


# ---------- digests (§3.7, §3.8) ----------

def store_key(channel: str, root: str, name: str) -> str:
    """The store key of one command: `<channel>:<root>:<name>` (the digest binds the parts exactly)."""
    return f"{channel}:{root}:{name}"


def command_digest(channel: str, root: str, name: str, cmd: str) -> str:
    """sha256 over {channel, root, name, cmd}: changing the text, the channel or the root invalidates trust."""
    return wfconfig.sha256_tag(wfconfig.canonical_bytes({"channel": channel, "root": root, "name": name,
                                                         "cmd": cmd}))


def set_digest(digests: Iterable[str]) -> str:
    """sha256 over the sorted list of pending command digests (`trust record --pending --digest`)."""
    return wfconfig.sha256_tag(wfconfig.canonical_bytes(sorted(digests)))


def commands_digest(records: Sequence[Mapping[str, Any]]) -> str:
    """sha256 over the canonical sorted [{root, name, channel, cmd}] of the effective set (definitions only)."""
    items = [{"root": r["root"], "name": r["name"], "channel": r["channel"], "cmd": r["cmd"]} for r in records]
    items.sort(key=lambda i: (i["root"], i["name"], i["channel"], i["cmd"] or ""))  # a malformed entry's cmd is None
    return wfconfig.sha256_tag(wfconfig.canonical_bytes(items))


def _valid_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    channel, _, rest = key.partition(":")
    return channel in CHANNELS and ":" in rest


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- the trust store (§3.7) ----------

def _invalid(path: Path, why: str) -> ConfigError:
    return ConfigError(E_TRUST_STORE_INVALID, f"trust store {path} {why}; every committed command is untrusted",
                       f"move it aside (`mv {path} {path}.bak`) and rerun /setup", file=str(path))


def _validate_document(doc: Any, path: Path) -> Dict[str, Any]:
    """The store document with known fields only, or E_TRUST_STORE_INVALID (schema and version, R-AC-57)."""
    if not isinstance(doc, dict):
        raise _invalid(path, "isn't a JSON object")
    schema = doc.get("schema")
    if schema != STORE_SCHEMA:
        if isinstance(schema, str) and schema.startswith("daedalus.trust/"):
            raise ConfigError(E_TRUST_STORE_INVALID,
                              f"trust store {path} has version {schema[:40]!r}; this Daedalus reads {STORE_SCHEMA}",
                              f"upgrade Daedalus, or move the store aside (`mv {path} {path}.bak`) and rerun /setup",
                              file=str(path))
        raise _invalid(path, f"has schema {str(schema)[:40]!r}, not {STORE_SCHEMA!r}")
    repos = doc.get("repos")
    if not isinstance(repos, dict):
        raise _invalid(path, "has no `repos` object")
    clean: Dict[str, Any] = {}
    for repo_id, entry in repos.items():
        label = str(repo_id)[:80]
        if not isinstance(repo_id, str) or not _DIGEST_RE.match(repo_id) or not isinstance(entry, dict):
            raise _invalid(path, f"has a malformed repository entry {label!r}")
        remote, root, commands = entry.get("remote"), entry.get("root"), entry.get("commands")
        if (remote is not None and not isinstance(remote, str)) or not isinstance(root, str) \
                or not isinstance(commands, dict):
            raise _invalid(path, f"has a malformed repository entry {label!r}")
        kept: Dict[str, Dict[str, str]] = {}
        for key, item in commands.items():
            if not _valid_key(key) or not isinstance(item, dict) or not isinstance(item.get("digest"), str) \
                    or not _DIGEST_RE.match(item["digest"]) or not isinstance(item.get("trusted_at"), str) \
                    or not _STAMP_RE.match(item["trusted_at"]):
                raise _invalid(path, f"has a malformed command entry {str(key)[:80]!r} in {label!r}")
            # Known fields only: whatever else a hand edit put there (command text, say) is never kept.
            kept[key] = {"digest": item["digest"], "trusted_at": item["trusted_at"]}
        clean[repo_id] = {"remote": remote, "root": root, "commands": kept}
    return {"schema": STORE_SCHEMA, "repos": clean}


def _remove_quietly(path: Path) -> None:
    try:
        os.unlink(str(path))
    except OSError:  # best-effort cleanup of our own temporary file on an error path that already raises
        pass


def _fsync_folder(folder: Path) -> None:
    fd = os.open(str(folder), os.O_RDONLY | _O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class TrustStore:
    """The user trust store `<user>/.workflow/trust.json` (`daedalus.trust/1`, §3.7).

    Reads refuse (E_TRUST_STORE_UNSAFE) a store that is a symlink, owned by another user, group- or
    world-writable, or inside the target project folder; a store under DAEDALUS_HOME is also refused
    inside a git work tree. Writes take `flock` on `<user>/.workflow/trust.lock`, then write a temporary
    file, fsync, rename and fsync the folder; mode 0600 in a 0700 folder. Entries hold a command digest and
    `trusted_at`, never command text or credentials. Store keys are `<channel>:<root>:<name>`.
    """

    def __init__(self, path: Optional[Path] = None, *, ctx: Optional[SourceContext] = None,
                 repo_top: Optional[Path] = None) -> None:
        """`path` defaults to `<user>/.workflow/trust.json` (DAEDALUS_HOME under the AC-2 conditions).

        Keyword-only additions (P1a batch 2): `ctx` injects the environment, uid, password-database home and
        lstat (the ownership seam tests use; never an environment variable); `repo_top` is the target project
        folder the store must stay out of (default: the current folder's top level).
        """
        self.ctx = ctx if ctx is not None else SourceContext()
        top = Path(os.path.realpath(str(repo_top))) if repo_top is not None else None
        self.home_warning: Optional[str] = None
        if path is None:
            if top is None:
                top = top_level(Path.cwd())[0]
            user, self.home_warning = wfconfig.user_folder(top, self.ctx)
            path = user / STORE_FOLDER / STORE_NAME
        self.repo_top = top
        self.path = Path(os.path.abspath(str(path)))

    # ----- read checks -----

    def _in_passwd_home(self) -> bool:
        """The store is `<password-database home>/.workflow/trust.json` (no work-tree check, finding -16)."""
        home = self.ctx.passwd_home
        if self.path == Path(os.path.abspath(str(home))) / STORE_FOLDER / STORE_NAME:
            return True
        return Path(os.path.realpath(str(self.path.parent))) == Path(os.path.realpath(str(home))) / STORE_FOLDER

    def _unsafe_reason(self, projects: Sequence[Path]) -> Optional[Tuple[str, str]]:
        lstat = self.ctx.lstat
        try:
            info: Any = lstat(str(self.path))
        except (FileNotFoundError, NotADirectoryError):
            info = None
        except OSError as err:
            return f"can't be checked ({err.strerror or err})", f"fix the permissions of {self.path.parent}"
        if info is not None:
            if stat.S_ISLNK(info.st_mode):
                return "is a symlink", f"replace {self.path} with a regular file you own (or remove it), then rerun /setup"
            if not stat.S_ISREG(info.st_mode):
                return "isn't a regular file", f"remove {self.path}, then rerun /setup"
            if info.st_uid != self.ctx.uid:
                return "is owned by another user", f"remove {self.path} (it isn't yours), then rerun /setup"
            if info.st_mode & 0o022:
                return "is group- or world-writable", f"run `chmod 600 {self.path}`, then rerun /setup"
        folder = Path(os.path.realpath(str(self.path.parent)))
        try:
            folder_info: Any = lstat(str(folder))
        except (FileNotFoundError, NotADirectoryError):
            folder_info = None
        except OSError as err:
            return f"can't be checked ({err.strerror or err})", f"fix the permissions of {folder}"
        if folder_info is not None:
            if not stat.S_ISDIR(folder_info.st_mode):
                return f"has a parent {folder} that isn't a folder", f"remove {folder}, then rerun /setup"
            if folder_info.st_uid != self.ctx.uid:
                return f"is in {folder}, owned by another user", "unset DAEDALUS_HOME, or point it at a folder you own"
            if folder_info.st_mode & 0o022:
                return f"is in {folder}, which is group- or world-writable", f"run `chmod 700 {folder}`"
        real = folder / self.path.name
        for project in projects:
            top = Path(os.path.realpath(str(project)))
            if real == top or top in real.parents:
                return ("is inside the target project folder",
                        "unset DAEDALUS_HOME, or point it at a folder outside the project and every git work tree")
        if not self._in_passwd_home() and inside_work_tree(folder, environ=self.ctx.environ):
            return ("is inside a git work tree (only the home folder's own store may be)",
                    "point DAEDALUS_HOME at a folder outside every git work tree, or unset it")
        return None

    def problem(self, repo_root: Optional[str] = None) -> Optional[ConfigError]:
        """The read safety checks (§3.7): None when the store may be used, else E_TRUST_STORE_UNSAFE."""
        projects = [p for p in (self.repo_top, Path(repo_root) if repo_root else None) if p is not None]
        found = self._unsafe_reason(projects)
        if found is None:
            return None
        why, fix = found
        return ConfigError(E_TRUST_STORE_UNSAFE, f"trust store {self.path} {why}; every committed command is untrusted",
                           f"{fix}, then rerun /setup" if "rerun" not in fix else fix, file=str(self.path))

    def check(self, repo_root: Optional[str] = None) -> None:
        """Raise E_TRUST_STORE_UNSAFE when the read checks fail; `trust record` runs this before writing."""
        problem = self.problem(repo_root)
        if problem is not None:
            raise problem

    def _read_document(self) -> Optional[Dict[str, Any]]:
        """The validated document, or None when the store doesn't exist. Raises E_TRUST_STORE_INVALID."""
        try:
            fd = os.open(str(self.path), os.O_RDONLY | _O_NOFOLLOW | _O_CLOEXEC | _O_NONBLOCK)
        except FileNotFoundError:
            return None
        except OSError as err:
            raise ConfigError(E_TRUST_STORE_UNSAFE, f"can't open trust store {self.path}: {err.strerror or err}",
                              f"check {self.path} is a regular file you own, then rerun /setup",
                              file=str(self.path)) from err
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ConfigError(E_TRUST_STORE_UNSAFE, f"trust store {self.path} isn't a regular file",
                                  f"remove {self.path}, then rerun /setup", file=str(self.path))
            data = handle.read(MAX_STORE_BYTES + 1)
        if len(data) > MAX_STORE_BYTES:
            raise _invalid(self.path, "is larger than 8 MiB")
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as err:
            raise _invalid(self.path, f"isn't valid JSON ({err})") from err
        return _validate_document(doc, self.path)

    def snapshot(self, repo_id: str, repo_root: Optional[str] = None) -> Tuple[Dict[str, Dict[str, str]],
                                                                             Dict[str, Any]]:
        """(this repository's entries `key → {digest, trusted_at}`, the store's status). Never raises a store
        error: a refused or invalid store yields no entries and status `refused` / `invalid` with the error."""
        status: Dict[str, Any] = {"path": str(self.path), "status": "ok", "error": None,
                                  "warning": self.home_warning}
        try:
            self.check(repo_root)
            doc = self._read_document()
        except ConfigError as err:
            status["status"] = "refused" if err.code == E_TRUST_STORE_UNSAFE else "invalid"
            status["error"] = {"code": err.code, "message": err.message, "fix": err.fix}
            return {}, status
        if doc is None:
            status["status"] = "missing"
            return {}, status
        entry = doc["repos"].get(repo_id) or {}
        return dict(entry.get("commands", {})), status

    def contains(self, repo_id: str, key: str, digest: str) -> bool:
        """True when the store trusts `digest` for `key` in repository `repo_id` (False for an unusable store)."""
        entries, _status = self.snapshot(repo_id)
        return (entries.get(key) or {}).get("digest") == digest

    # ----- writes -----

    def record(self, repo: RepoId, commands: Mapping[str, str]) -> None:
        """Trust each `key → digest` in `commands` for `repo`, stamped with the current UTC time."""
        items = dict(commands)
        for key, digest in items.items():
            if not _valid_key(key) or not isinstance(digest, str) or not _DIGEST_RE.match(digest):
                raise ValueError(f"not a store key and command digest: {key!r} -> {digest!r}")
        if not items:
            self.check(repo.root)  # nothing to write, but never report success for a store that would be refused
            return
        stamp = _utc_now()

        def change(doc: Dict[str, Any]) -> Tuple[bool, None]:
            entry = doc["repos"].setdefault(repo.id, {"remote": repo.remote, "root": repo.root, "commands": {}})
            entry["remote"], entry["root"] = repo.remote, repo.root
            for key, digest in items.items():
                entry["commands"][key] = {"digest": digest, "trusted_at": stamp}
            return True, None

        self._mutate(change, repo.root)

    def revoke(self, repo: RepoId, keys: Optional[Iterable[str]] = None) -> int:
        """Remove trust for `keys` (all of the repository's entries when None); return how many were removed."""
        self.check(repo.root)
        if not os.path.lexists(str(self.path)):
            return 0
        wanted = None if keys is None else set(keys)

        def change(doc: Dict[str, Any]) -> Tuple[bool, int]:
            entry = doc["repos"].get(repo.id)
            if entry is None:
                return False, 0
            if wanted is None:
                del doc["repos"][repo.id]
                return True, len(entry["commands"])
            removed = [key for key in entry["commands"] if key in wanted]
            for key in removed:
                del entry["commands"][key]
            if not entry["commands"]:
                del doc["repos"][repo.id]
            return bool(removed), len(removed)

        return int(self._mutate(change, repo.root))

    def pending(self, repo: RepoId, records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        """The untrusted committed commands among effective-command `records`, each with its key and digest.

        `records` come from `effective_commands` for `repo`. Pending means untrusted and claiming to run: a TL3 or
        TL4 config override, or a profile entry that is `script`, `derived`, `user` or `confirmed`. An `inferred`
        entry without `confirmed` isn't pending: /setup confirms it on its own (`detect-stack.py --confirm`,
        then `trust record --root R --name N`). A malformed profile entry or config override (any level) is listed
        too, with `recordable: false` and no command text, so /setup names it; it stays out of the set digest and
        can't be recorded.
        """
        _ = repo  # the identity the items will be recorded under; records already belong to it
        items = [_pending_item(record) for record in records
                 if not record.get("trusted") and (_claims_trust(record) or is_malformed(record))]
        items.sort(key=lambda i: (i["root"], i["name"], i["channel"]))
        return items

    def _mutate(self, change: Callable[[Dict[str, Any]], Tuple[bool, Any]], repo_root: str) -> Any:
        self.check(repo_root)  # before creating anything: a refused store gets no folder, lock or file
        folder = self.path.parent
        try:
            folder.mkdir(mode=0o700)
            os.chmod(str(folder), 0o700)  # exact, whatever the umask
        except FileExistsError:
            pass
        except OSError as err:
            raise ConfigError(E_TRUST_STORE_UNSAFE, f"can't create {folder}: {err.strerror or err}",
                              f"create {folder} (mode 700), or fix DAEDALUS_HOME, then rerun /setup",
                              file=str(self.path)) from err
        with self._locked(folder):
            self.check(repo_root)
            doc = self._read_document() or {"schema": STORE_SCHEMA, "repos": {}}
            changed, result = change(doc)
            if changed:
                self._write(doc, folder)
        return result

    @contextmanager
    def _locked(self, folder: Path) -> Iterator[None]:
        import fcntl  # POSIX only, like the rest of the hub

        lock = folder / LOCK_NAME
        try:
            fd = os.open(str(lock), os.O_RDWR | os.O_CREAT | _O_NOFOLLOW | _O_CLOEXEC, 0o600)
        except OSError as err:
            raise ConfigError(E_TRUST_STORE_UNSAFE, f"can't open the trust lock {lock}: {err.strerror or err}",
                              f"remove {lock} if it isn't a regular file you own, then rerun /setup",
                              file=str(self.path)) from err
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)  # closing the descriptor releases the lock

    def _write(self, doc: Dict[str, Any], folder: Path) -> None:
        data = (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        tmp = folder / f".{STORE_NAME}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        try:
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_CLOEXEC, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fchmod(handle.fileno(), 0o600)
                os.fsync(handle.fileno())
            os.replace(str(tmp), str(self.path))
            _fsync_folder(folder)
        except OSError as err:
            _remove_quietly(tmp)
            raise ConfigError(E_TRUST_STORE_UNSAFE, f"can't write trust store {self.path}: {err.strerror or err}",
                              "check the folder's permissions and free space, then rerun /setup",
                              file=str(self.path)) from err


PENDING_FIELDS = ("key", "digest", "root", "name", "channel", "level", "cmd", "source", "declared", "unsafe",
                  "reason", "recordable")


def _claims_trust(record: Mapping[str, Any]) -> bool:
    if record.get("channel") == "config":
        return record.get("level") not in SELF_TRUSTED_LEVELS
    declared = record.get("declared") or {}
    return declared.get("confidence") in ("script", "derived", "user") or declared.get("confirmed") is True


def is_malformed(record: Mapping[str, Any]) -> bool:
    """A record `evaluate` reports with no command, key or digest because its shape is wrong: a profile entry
    (rework-2) or a config override at any level (rework-3). Always untrusted, listed by `trust pending` as not
    recordable until the profile or the config file is fixed."""
    return record.get("channel") in CHANNELS and record.get("digest") is None


def _pending_item(record: Mapping[str, Any]) -> Dict[str, Any]:
    item = {field: record.get(field) for field in PENDING_FIELDS}
    item["recordable"] = not is_malformed(record)
    return item


def pending_digest(items: Sequence[Mapping[str, Any]]) -> str:
    """The set digest `trust record --pending --digest` confirms: the recordable pending items only."""
    return set_digest(item["digest"] for item in items if item["recordable"])


# ---------- effective commands (§3.8) ----------

class _Candidate(NamedTuple):
    channel: str
    level: str
    root: str
    name: str
    cmd: Optional[str]  # None for a malformed entry or override: its raw value is never carried
    source: Optional[str]
    confidence: Optional[str]
    confirmed: Optional[bool]
    committed_unsafe: bool
    problem: Optional[str] = None  # why an entry or override is malformed; such a one has no key or digest

    @property
    def key(self) -> Optional[str]:
        return None if self.problem else store_key(self.channel, self.root, self.name)

    @property
    def digest(self) -> Optional[str]:
        if self.problem or self.cmd is None:
            return None
        return command_digest(self.channel, self.root, self.name, self.cmd)


class CommandSet(NamedTuple):
    """`evaluate`'s result: the identity, the records, the store's status and how re-detection went
    (`ok`, `timed out`, `failed`, `skipped` in fast mode, or `not needed` without profile commands)."""

    repo: RepoId
    records: List[Dict[str, Any]]
    store: Dict[str, Any]
    redetection: str


def _shape_problem(subject: str, *values: str) -> Optional[str]:
    """Why `values` can't be shown faithfully on one line (lib/text.py), or None. Line breaks keep their own reason
    (rework-2); any other hidden character, such as ESC or a bidi override, gets the rework-3 one."""
    if any(has_line_break(value) for value in values):
        return f"{subject} spans more than one line"
    if any(has_hidden(value) for value in values):
        return f"{subject} contains control or format characters"
    return None


def _profile_problem(path: Any, name: str, entry: Any) -> Optional[str]:
    """Why one profile command entry is malformed, or None. Rework-2 (finding 1ef278f-4): a malformed entry is
    reported untrusted with this reason instead of being skipped, so the banner counts it and /setup names it."""
    if not isinstance(path, str):
        return "root path is not a string"
    problem = _shape_problem("root path or name", path, name)
    if problem:
        return problem
    if not isinstance(entry, Mapping):
        return "entry is not an object"
    command = entry.get("cmd")
    if not isinstance(command, str):
        return "cmd is not a string"
    if not command.strip():
        return "cmd is empty"
    return _shape_problem("cmd", command)


def _printable(value: Any) -> str:
    """A malformed record's root or name as one line of visible text: itself when it is a string with no hidden
    character, else its JSON with every non-ASCII character escaped."""
    if isinstance(value, str) and not has_hidden(value):
        return value
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _profile_candidates(profile: Optional[Mapping[str, Any]]) -> Iterator[_Candidate]:
    roots = profile.get("roots") if isinstance(profile, Mapping) else None
    for root in roots if isinstance(roots, list) else ():
        if not isinstance(root, Mapping):
            continue  # no command names: nothing anyone could run by name
        path = root.get("path")
        commands = root.get("commands")
        for name, entry in commands.items() if isinstance(commands, Mapping) else ():
            if not isinstance(name, str):
                continue  # JSON object keys are always strings
            problem = _profile_problem(path, name, entry)
            fields = entry if isinstance(entry, Mapping) else {}
            raw, confidence, source = fields.get("cmd"), fields.get("confidence"), fields.get("source")
            committed_unsafe = bool(fields.get("unsafe")) or (isinstance(raw, str) and bool(UNSAFE_RE.search(raw)))
            yield _Candidate("profile", "TL4", path if problem is None else _printable(path),
                             name if problem is None else _printable(name), raw if problem is None else None,
                             source if isinstance(source, str) else None,
                             confidence if isinstance(confidence, str) else None,
                             fields.get("confirmed") is True, committed_unsafe, problem)


def _config_candidate(override: Mapping[str, Any]) -> Optional[_Candidate]:
    """One `commands` override, or None when it isn't one. Rework-3 (finding 1ef278f-5): a root, name or cmd holding
    a line break or a hidden character makes it malformed at every level, TL1 and TL2 included: no command text,
    key or digest, so it is never trusted or recorded. The rest of the configuration still resolves."""
    root, name, command, level = (override.get(field) for field in ("root", "name", "cmd", "level"))
    if not all(isinstance(value, str) for value in (root, name, command, level)) or level == "TL5":
        return None
    source = override.get("source")
    source = source if isinstance(source, str) else None
    problem = _shape_problem("root path or name", root, name) or _shape_problem("cmd", command)
    if problem is None:
        return _Candidate("config", level, root, name, command, source, None, None, False)
    return _Candidate("config", level, _printable(root), _printable(name), None, source, None, None,
                      bool(UNSAFE_RE.search(command)), problem)


def _candidates(profile: Optional[Mapping[str, Any]], resolved: Any) -> Dict[Tuple[str, str], List[_Candidate]]:
    """(root, name) → candidates, winner first: config overrides nearest level first, then the profile entry."""
    groups: Dict[Tuple[str, str], List[_Candidate]] = {}
    for override in getattr(resolved, "command_overrides", None) or []:
        candidate = _config_candidate(override)
        if candidate is not None:
            groups.setdefault((candidate.root, candidate.name), []).append(candidate)
    for candidate in _profile_candidates(profile):
        groups.setdefault((candidate.root, candidate.name), []).append(candidate)
    return groups


def _detect_timeout(environ: Mapping[str, str]) -> float:
    raw = environ.get("WORKFLOW_DETECT_TIMEOUT", "")
    try:
        value = float(raw) if raw else DEFAULT_DETECT_TIMEOUT
    except ValueError:
        return DEFAULT_DETECT_TIMEOUT
    return value if math.isfinite(value) and value >= 0 else DEFAULT_DETECT_TIMEOUT


_DETECTOR: Any = None


def _build_profile(top: Path, timeout: float) -> Mapping[str, Any]:
    """The detector's own `build_profile`, loaded in process from this hub's `detect-stack.py` (read-only)."""
    global _DETECTOR
    if _DETECTOR is None:
        path = Path(__file__).resolve().parent.parent / "detect-stack.py"
        spec = importlib.util.spec_from_file_location("daedalus_detect_stack", str(path))
        if spec is None or spec.loader is None:
            raise ImportError(f"can't load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _DETECTOR = module
    return _DETECTOR.build_profile(top, timeout)


def _redetect(top: Path, timeout: float, runner: Optional[RedetectFn]
              ) -> Tuple[str, Dict[Tuple[str, str], Mapping[str, Any]]]:
    """("ok" | "timed out" | "failed", (root, name) → re-detected entry). Fails closed on every error."""
    box: Dict[str, Any] = {}
    run = runner or _build_profile

    def target() -> None:
        try:
            box["profile"] = run(top, timeout)
        except Exception as err:  # noqa: BLE001 - fail closed: any detector error leaves the entries untrusted
            box["error"] = err

    thread = threading.Thread(target=target, name="daedalus-redetect", daemon=True)
    thread.start()
    thread.join(timeout + DETECT_HARD_GRACE)
    if thread.is_alive():
        return "timed out", {}
    profile = box.get("profile")
    if "error" in box or not isinstance(profile, Mapping):
        return "failed", {}
    gaps = profile.get("gaps") or []
    if any(isinstance(gap, str) and gap.startswith(STOPPED_EARLY) for gap in gaps):
        return "timed out", {}
    index: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    for root in profile.get("roots") or []:
        if isinstance(root, Mapping) and isinstance(root.get("commands"), Mapping):
            for name, entry in root["commands"].items():
                if isinstance(entry, Mapping):
                    index.setdefault((str(root.get("path")), name), entry)
    return "ok", index


def _reproduced(candidate: _Candidate, redetection: str,
                detected: Mapping[Tuple[str, str], Mapping[str, Any]]) -> Optional[str]:
    """None when re-detection reproduces the entry (same cmd, same confidence, PF-1); else why not."""
    if redetection == "timed out":
        return "re-detection timed out"
    if redetection == "failed":
        return "re-detection failed"
    if redetection != "ok":
        return "not re-detected (fast mode)"
    fresh = detected.get((candidate.root, candidate.name))
    if fresh is None or fresh.get("cmd") != candidate.cmd:
        return "re-detection doesn't reproduce this command"
    if fresh.get("confidence") != candidate.confidence:
        return f"re-detection gives confidence {fresh.get('confidence')!r}, not {candidate.confidence!r}"
    return None


def _malformed_reason(candidate: _Candidate) -> str:
    """The reason a malformed record carries: the shape problem and the file to fix."""
    if candidate.channel == "config":
        return (f"{MALFORMED_CONFIG}: {candidate.problem} (fix {_printable(candidate.source)}; "
                "it can't be trusted as is)")
    return f"{MALFORMED}: {candidate.problem} (fix .workflow/profile.json; it can't be trusted as is)"


def _decide(candidate: _Candidate, held: Mapping[str, Mapping[str, str]], store: Mapping[str, Any],
            redetection: str, detected: Mapping[Tuple[str, str], Mapping[str, Any]]
            ) -> Tuple[bool, Optional[str], Optional[str]]:
    """(trusted, basis, reason) per the §3.8 table."""
    if candidate.problem:  # whatever the store or the level says: there is no command text to trust
        return False, None, _malformed_reason(candidate)
    if candidate.channel == "config" and candidate.level == "TL1":
        return True, "policy", None  # managed organization policy (root-owned, §3.3)
    if candidate.channel == "config" and candidate.level == "TL2":
        return True, "user-config", None  # the user's own ~/.workflow/config.yml
    error = store.get("error")
    if error:  # AC-8: a refused or invalid store leaves every committed command untrusted
        return False, None, f"trust store unusable ({error['code']})"
    in_store = (held.get(candidate.key) or {}).get("digest") == candidate.digest
    if candidate.channel == "config":
        where = "workspace" if candidate.level == "TL3" else "committed"
        return (True, "trust-store", None) if in_store else \
            (False, None, f"{where} config override; not in your trust store")
    if candidate.confidence in DETECTED_CONFIDENCES:
        why = _reproduced(candidate, redetection, detected)
        if why is None:
            return True, "detected", None
        return (True, "trust-store", None) if in_store else (False, None, why)
    if in_store:
        return True, "trust-store", None
    if candidate.confidence == "inferred" and not candidate.confirmed:
        return False, None, "inferred and not confirmed"
    return False, None, "committed profile entry; not in your trust store"


def _record(group: Sequence[_Candidate], held: Mapping[str, Mapping[str, str]], store: Mapping[str, Any],
            redetection: str, detected: Mapping[Tuple[str, str], Mapping[str, Any]]) -> Dict[str, Any]:
    winner = group[0]
    trusted, basis, reason = _decide(winner, held, store, redetection, detected)
    fresh = detected.get((winner.root, winner.name)) or {}
    # Only ever added: a committed `unsafe: false` can't clear what the text or the re-detected body says.
    is_unsafe = winner.committed_unsafe or bool(UNSAFE_RE.search(winner.cmd or "")) \
        or (fresh.get("cmd") == winner.cmd and fresh.get("unsafe") is True)
    if not trusted:
        confidence, confirmed = "inferred", False  # R-AC-61: consumers ask, or send the user to /setup
    elif winner.channel == "config":
        confidence, confirmed = "user", True
    else:
        confidence = winner.confidence if winner.confidence in KNOWN_CONFIDENCES else "user"
        confirmed = basis == "trust-store" or bool(winner.confirmed)
    return {"root": winner.root, "name": winner.name, "cmd": winner.cmd, "channel": winner.channel,
            "level": winner.level, "source": winner.source, "key": winner.key, "digest": winner.digest,
            "declared": {"confidence": winner.confidence, "confirmed": winner.confirmed},
            "confidence": confidence, "confirmed": confirmed,
            "trusted": trusted, "basis": basis, "unsafe": is_unsafe, "reason": reason,
            "shadowed": [{"channel": c.channel, "level": c.level, "source": c.source, "cmd": c.cmd,
                          "key": c.key, "digest": c.digest} for c in group[1:]]}


def evaluate(repo: Path, profile: Optional[Mapping[str, Any]], resolved: Any, rederive: bool = True, *,
             store: Optional[TrustStore] = None, ctx: Optional[SourceContext] = None,
             redetect: Optional[RedetectFn] = None) -> CommandSet:
    """`effective_commands` plus the identity, the store's status and the re-detection outcome (for the CLIs)."""
    ctx = ctx if ctx is not None else SourceContext()
    ident = repo_identity(repo)
    top = Path(ident.root)
    store = store if store is not None else TrustStore(ctx=ctx, repo_top=top)
    held, status = store.snapshot(ident.id, ident.root)
    groups = _candidates(profile, resolved)
    has_profile = any(c.channel == "profile" for group in groups.values() for c in group)
    if not rederive:
        redetection, detected = "skipped", {}
    elif not has_profile:
        redetection, detected = "not needed", {}
    else:
        redetection, detected = _redetect(top, _detect_timeout(ctx.environ), redetect)
    records = [_record(groups[ident_key], held, status, redetection, detected) for ident_key in sorted(groups)]
    return CommandSet(ident, records, status, redetection)


def effective_commands(repo: Path, profile: Optional[Mapping[str, Any]], resolved: Any,
                       rederive: bool = True, *, store: Optional[TrustStore] = None,
                       ctx: Optional[SourceContext] = None,
                       redetect: Optional[RedetectFn] = None) -> List[Dict[str, Any]]:
    """One record per root and command name from both channels (§3.8):

    {"root", "name", "cmd", "channel": "profile"|"config", "level", "declared", "trusted", "basis",
     "unsafe", "reason"}. `resolved` is a wfconfig.Resolved (its `command_overrides` hold the config
    channel). Untrusted entries are reported as unconfirmed `inferred`; `unsafe` is never cleared by a
    committed value. rederive=False (fast mode) skips re-detection, so a `script` or `derived` entry is trusted
    only when the store holds its digest (`trust record --pending` stores the reproduced ones); it never trusts
    more than full mode.

    Each record also carries `source`, `key` and `digest` (the store key and command digest), `confidence` and
    `confirmed` (what consumers read: `inferred` / false when untrusted) and `shadowed` (the entries the
    winning one hides). Keyword-only additions (batch 2): `store` and `ctx` (injection; the default store is
    the user's), `redetect(top, timeout)` (replaces the detector's build_profile, for tests).

    A malformed profile entry (not an object, a `cmd` that isn't a non-empty single-line string, a root `path`
    that isn't one) is a record too (rework-2): `cmd`, `key` and `digest` null, its root or name JSON-encoded when
    it isn't single-line text, never trusted, `reason` "malformed profile entry: …" (`is_malformed`). Rework-3: a
    root, name or `cmd` holding a hidden character (lib/text.py: ESC, a bidi override, a zero-width space, …) is
    malformed too, and so is a config override at any level whose root, name or `cmd` holds a line break or a
    hidden character (`reason` "malformed config override: … (fix <config file>; …)").
    """
    return evaluate(repo, profile, resolved, rederive, store=store, ctx=ctx, redetect=redetect).records


def commands_document(found: CommandSet) -> Dict[str, Any]:
    """The `config commands --json` document (`daedalus.commands/1`): the only output with command text
    besides `trust pending`."""
    return {"schema": COMMANDS_SCHEMA, "repo": found.repo.root, "repo_id": found.repo.id,
            "remote": found.repo.remote, "store": found.store, "redetection": found.redetection,
            "commands": found.records, "commands_digest": commands_digest(found.records),
            "untrusted": sum(1 for record in found.records if not record["trusted"])}


def _shown_cmd(record: Mapping[str, Any]) -> str:
    return "(malformed: not shown)" if record["cmd"] is None else record["cmd"]


def _text(lines: Iterable[str]) -> str:
    """Text output, one item per line. Rework-3 (finding 1ef278f-5): a hidden character any value carries (a line
    break, ESC, a bidi override; repository paths and store messages included) is written as its escape, so every
    line shows all it holds and nothing is hidden from a trust prompt."""
    return "\n".join(escape_hidden(line) for line in lines)


def format_commands(doc: Mapping[str, Any]) -> str:
    store = doc["store"]
    lines = [f"Effective commands for {doc['repo']} (trust store: {store['status']}, {store['path']}; "
             f"re-detection: {doc['redetection']})"]
    if store.get("error"):
        lines += [f"  {store['error']['code']}: {store['error']['message']}", f"  fix: {store['error']['fix']}"]
    if store.get("warning"):
        lines.append(f"  warning: {store['warning']}")
    if not doc["commands"]:
        lines.append("  no commands")
    for record in doc["commands"]:
        if record["trusted"]:
            state = f"trusted: {record['basis']}"
        else:
            state = f"untrusted ({record['reason']}): ask the user, or run /setup"
        flag = ", unsafe: always ask" if record["unsafe"] else ""
        lines.append(f"  {record['root']}:{record['name']} = {_shown_cmd(record)}  "
                     f"[{record['channel']} {record['level']}, {state}{flag}]")
    lines.append(f"commands_digest: {doc['commands_digest']}")
    return _text(lines)


# ---------- CLI: workflow.py trust list | pending | record | revoke (T10) ----------

def add_cli(parser: Any) -> None:
    """Register `trust list|pending|record|revoke`."""
    sub = parser.add_subparsers(dest="action", metavar="ACTION")
    sub.required = True
    for name, help_text in (("list", "list trusted commands for this repository"),
                            ("pending", "list committed commands that need trust"),
                            ("record", "trust the pending set, or one command"),
                            ("revoke", "remove trust for one command, or all of this repository's")):
        action = sub.add_parser(name, help=help_text, description=help_text)
        action.add_argument("--json", action="store_true", help="print JSON")
        action.add_argument("--repo", default=None, help="the target project folder (default: the current folder)")
        action.add_argument("--workspace", default=None, help="the folder the session started from")
        if name == "record":
            action.add_argument("--pending", action="store_true", help="trust the whole pending set")
            action.add_argument("--digest", default=None, help="the pending set's digest, as shown by `pending`")
        if name in ("record", "revoke"):
            action.add_argument("--root", default=None, help="profile root, for one command")
            action.add_argument("--name", default=None, help="command name, for one command")
            action.add_argument("--channel", choices=CHANNELS, default=None)


def _repo_json(ident: RepoId) -> Dict[str, Any]:
    return {"id": ident.id, "remote": ident.remote, "root": ident.root}


def _emit(doc: Mapping[str, Any], as_json: bool, lines: Sequence[str]) -> None:
    """`doc` as JSON, or `lines` as text (`_text`: hidden characters escaped, one item per line)."""
    print(json.dumps(doc, indent=2, ensure_ascii=False) if as_json else _text(lines))


def _evaluate_cli(repo: Path, workspace: Optional[Path], ctx: SourceContext, rederive: bool,
                  store: Optional[TrustStore] = None) -> Tuple[CommandSet, TrustStore]:
    resolved = wfconfig.resolve(repo, workspace, ctx=ctx)
    store = store if store is not None else TrustStore(ctx=ctx, repo_top=resolved.repo)
    found = evaluate(resolved.repo, wfconfig.load_profile(resolved.repo), resolved, rederive, store=store, ctx=ctx)
    return found, store


MALFORMED_HEADINGS = (
    ("profile", "Malformed profile entries (never run, and can't be trusted until .workflow/profile.json is fixed):"),
    ("config", "Malformed config overrides (never run, and can't be trusted until the config file each names is "
               "fixed):"))


def _cli_pending(args: Any, repo: Path, workspace: Optional[Path], ctx: SourceContext) -> int:
    found, store = _evaluate_cli(repo, workspace, ctx, rederive=True)
    items = store.pending(found.repo, found.records)
    doc = {"schema": "daedalus.trust-pending/1", "repo": _repo_json(found.repo), "store": found.store,
           "redetection": found.redetection, "pending": items, "set_digest": pending_digest(items)}
    recordable = [item for item in items if item["recordable"]]
    malformed = [item for item in items if not item["recordable"]]
    lines = [f"No committed command needs trust in {found.repo.root}."] if not recordable else \
        [f"Untrusted committed commands in {found.repo.root}" + (f" ({found.repo.remote})" if found.repo.remote else "")
         + ":"]
    for item in recordable:
        flag = ", unsafe" if item["unsafe"] else ""
        lines.append(f"  {item['root']}:{item['name']} = {item['cmd']}  [{item['channel']} {item['level']}{flag}; "
                     f"{item['reason']}]")
    if recordable:
        lines.append(f"Set digest: {doc['set_digest']}")
        lines.append(f"Trust them all: workflow.py trust record --pending --digest {doc['set_digest']}")
    for channel, heading in MALFORMED_HEADINGS:
        entries = [item for item in malformed if item["channel"] == channel]
        if entries:
            lines.append(heading)
            lines += [f"  {item['root']}:{item['name']}  [{item['reason']}]" for item in entries]
    if found.store.get("error"):
        lines += [f"Trust store: {found.store['error']['message']}", f"fix: {found.store['error']['fix']}"]
    _emit(doc, args.json, lines)
    return 0


def _malformed_refusal(option: Mapping[str, Any], root: str, name: str) -> UsageError:
    """`trust record --root R --name N` on a malformed record: what is wrong and the file to fix."""
    if option["channel"] == "config":
        return UsageError(f"{root}:{name} is a {MALFORMED_CONFIG} (its root, name or command holds a line break or a "
                          "control or format character), so it can't be trusted",
                          f"rewrite it in {_printable(option.get('source'))} as plain one-line text, then trust it")
    return UsageError(f"{root}:{name} is a {MALFORMED}, so it can't be trusted",
                      "fix .workflow/profile.json (or run /setup --refresh), then trust it")


def _one_command(records: Sequence[Mapping[str, Any]], root: str, name: str,
                 channel: Optional[str]) -> Dict[str, Any]:
    for record in records:
        if record["root"] != root or record["name"] != name:
            continue
        options = [dict(record)] + [dict(s, root=root, name=name) for s in record["shadowed"]]
        for option in options:
            if channel not in (None, option["channel"]):
                continue
            if is_malformed(option):
                raise _malformed_refusal(option, root, name)
            return option
        raise UsageError(f"{root}:{name} has no {channel} command",
                         "run `workflow.py config commands` to see where it comes from")
    raise UsageError(f"no command {root}:{name} in this repository",
                     "run `workflow.py config commands` to list them")


def _reproduced_records(records: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """The effective `script` and `derived` entries full-mode re-detection reproduced (`basis: detected`).

    `trust record --pending` stores their digests next to the confirmed set, so fast mode (the session banner),
    which can't re-detect, can tell them from forged ones. They need no confirmation: full mode already trusts
    them, and they never enter the pending set or its digest (rework-1, finding 1ef278f-1).
    """
    return [record for record in records if record.get("basis") == "detected"]


def _record_items(items: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [{field: item.get(field) for field in ("key", "digest", "root", "name", "channel", "level")}
            for item in items]


def _check_record_flags(args: Any) -> None:
    one = args.root is not None or args.name is not None
    if args.pending and one:
        raise UsageError("pass either --pending --digest D, or --root R --name N, not both")
    if args.pending and not args.digest:
        raise UsageError("--pending needs --digest (the set digest `trust pending` printed)",
                         "run `workflow.py trust pending`, review the list, then pass its digest")
    if not args.pending and (args.digest or args.root is None or args.name is None):
        raise UsageError("pass --pending --digest D, or --root R --name N [--channel C]")


def _cli_record(args: Any, repo: Path, workspace: Optional[Path], ctx: SourceContext) -> int:
    _check_record_flags(args)
    ident = repo_identity(repo)
    store = TrustStore(ctx=ctx, repo_top=Path(ident.root))
    store.check(ident.root)  # the read checks first: exit 3 with the fix, and write nothing (AC-8)
    found, _ = _evaluate_cli(repo, workspace, ctx, rederive=True, store=store)
    skipped: List[Dict[str, Any]] = []
    detected: List[Mapping[str, Any]] = []
    if args.pending:
        pending = store.pending(found.repo, found.records)
        current = pending_digest(pending)
        if args.digest != current:
            raise ConfigError(E_TRUST_SET_CHANGED,
                              f"the pending set changed since it was shown (now {current}, not {args.digest})",
                              "run `workflow.py trust pending` again, review the commands, and confirm the new digest")
        detected = _reproduced_records(found.records)
        chosen = [item for item in pending if item["recordable"]]
        skipped += [{"key": None, "root": item["root"], "name": item["name"], "reason": item["reason"]}
                    for item in pending if not item["recordable"]]
    else:
        option = _one_command(found.records, args.root, args.name, args.channel)
        if option["channel"] == "config" and option["level"] in SELF_TRUSTED_LEVELS:
            chosen = []
            skipped.append({"key": option["key"], "root": option["root"], "name": option["name"],
                            "reason": f"a {option['level']} override is trusted as it is"})
        else:
            chosen = [option]
    store.record(found.repo, {item["key"]: item["digest"] for item in [*chosen, *detected]})
    recorded, verified = _record_items(chosen), _record_items(detected)
    doc: Dict[str, Any] = {"schema": "daedalus.trust-record/1", "repo": _repo_json(found.repo),
                           "store": str(store.path), "recorded": recorded, "detected": verified, "skipped": skipped}
    if args.pending:
        doc["set_digest"] = args.digest
    lines = [f"Trusted {len(recorded)} command(s) for {found.repo.root} in {store.path}."]
    lines += [f"  {item['key']}" for item in recorded]
    lines += [f"  skipped {s['key'] or s['root'] + ':' + s['name']}: {s['reason']}" for s in skipped]
    if verified:
        lines.append(f"Stored {len(verified)} detected command(s) re-detection reproduced, for the session banner:")
        lines += [f"  {item['key']}" for item in verified]
    _emit(doc, args.json, lines)
    return 0


def _cli_revoke(args: Any, repo: Path, workspace: Optional[Path], ctx: SourceContext) -> int:
    if (args.root is None) != (args.name is None):
        raise UsageError("pass both --root and --name, or neither (to revoke all of this repository's trust)")
    ident = repo_identity(repo)
    store = TrustStore(ctx=ctx, repo_top=Path(ident.root))
    keys: Optional[List[str]] = None
    if args.root is not None:
        channels = (args.channel,) if args.channel else CHANNELS
        keys = [store_key(channel, args.root, args.name) for channel in channels]
    count = store.revoke(ident, keys)
    doc = {"schema": "daedalus.trust-revoke/1", "repo": _repo_json(ident), "store": str(store.path),
           "revoked": count, "keys": keys}
    _emit(doc, args.json, [f"Revoked {count} trusted command(s) for {ident.root}."])
    return 0


def _cli_list(args: Any, repo: Path, workspace: Optional[Path], ctx: SourceContext) -> int:
    found, store = _evaluate_cli(repo, workspace, ctx, rederive=False)
    held, status = store.snapshot(found.repo.id, found.repo.root)
    current = {r["key"]: r["digest"] for r in found.records}
    for record in found.records:
        for hidden in record["shadowed"]:
            current.setdefault(hidden["key"], hidden["digest"])
    trusted = [{"key": key, "digest": item["digest"], "trusted_at": item["trusted_at"],
                "current": current.get(key) == item["digest"]} for key, item in sorted(held.items())]
    doc = {"schema": "daedalus.trust-list/1", "repo": _repo_json(found.repo), "store": status, "trusted": trusted}
    lines = [f"Trusted commands for {found.repo.root} (trust store: {status['status']}, {status['path']}):"]
    lines += [f"  {t['key']}  trusted {t['trusted_at']}" + ("" if t["current"] else "  (stale: the command changed)")
              for t in trusted] or ["  none"]
    _emit(doc, args.json, lines)
    return 0


def run_cli(args: Any) -> int:
    ctx = SourceContext()
    repo = Path(args.repo) if args.repo else Path.cwd()
    workspace = Path(args.workspace) if args.workspace else None
    handlers = {"list": _cli_list, "pending": _cli_pending, "record": _cli_record, "revoke": _cli_revoke}
    return handlers[args.action](args, repo, workspace, ctx)
