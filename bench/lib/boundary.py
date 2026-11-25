"""Execution boundary (§3.8): where setup, agent, collection and scoring commands run.

- docker (default): bench/container/Dockerfile. The agent container gets the dedicated benchmark key from
  BENCH_ENV_FILE (--env-file, never on argv or in logs), DAEDALUS_NONINTERACTIVE=1, and bind mounts for /work,
  /remote.git, /outside, /home/dev, /deps, /ticket (ro: the run's copy of the ticket file only), /arm (ro) and
  /opt/tools (ro: the run's copy of approver.py only, never bench/lib). The task folder (hidden tests,
  reference.patch) is never mounted during the agent run; scoring is a separate container with a copy of /work,
  /hidden (ro) and no network.
- sandbox (labeled fallback when Docker is unavailable): every command runs as a separate OS user
  (BENCH_SANDBOX_USER) through sudo [verify in T0]; secrets travel in the process environment, not argv. The
  agent's cwd is a real host path, so the raw root must sit outside the hub and below no CLAUDE.md (see
  sandbox_root_problem). That user never needs the hub (RW-30): its commands get HOME and TMPDIR inside the run and
  a PATH without hub or benchmark entries (sandbox_path), the host copies the hidden tests into the run's score
  folder after the agent exits (stage_hidden), and run.py seals each finished run folder (workspace.seal).
- local: no isolation. Only for the fake arm (no model) and verify-task in tests; refuses real arms. It keeps the
  host's environment (no sandbox_path) and stages hidden tests like sandbox.

Nothing the agent sees names the benchmark or the task (RW-23, RW-24): neutral inner paths, HOME and container
names, run folders named by run.run_name(run_id), and a raw root outside the hub whose path doesn't say "bench"
(docker shows bind-mount sources in /proc/self/mountinfo; a sandbox agent sees its host path directly).
"""
from __future__ import annotations

import collections
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict, List, Mapping, Optional, Pattern, Sequence, Tuple

from . import HUB, BenchError, read_env_file, tail, utc_now
from .workspace import TICKET_NAME, Workspace, overlay_tree

ENV_FILE_VAR = "BENCH_ENV_FILE"
IMAGE_VAR = "BENCH_IMAGE"
SANDBOX_USER_VAR = "BENCH_SANDBOX_USER"
INNER = {"work": "/work", "remote": "/remote.git", "outside": "/outside", "home": "/home/dev", "deps": "/deps",
         "arm": "/arm", "tools": "/opt/tools", "hidden": "/hidden", "ticket": "/ticket"}
# Shown in a dry-run plan when the image, env file or sandbox user isn't set yet (a live run refuses to start).
UNSET = {"image": "<image>", "env_file": "<env-file>", "user": "<sandbox-user>"}
DEFAULT_RUN_NAME = "run"
# A path part that names the benchmark, in a raw root an agent can see (RW-24).
EXPOSED_NAME_RE = re.compile(r"(?i)bench")
# Project memory files Claude Code loads from every ancestor of its cwd.
CONTEXT_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")
NONINTERACTIVE_ENV = {"DAEDALUS_NONINTERACTIVE": "1"}
PIDS_LIMIT = "1024"
KILL_GRACE_S = 5.0
STDERR_TAIL_CHUNKS = 64
MINIMAL_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "TMPDIR", "TERM")
# What a sandbox command keeps from the host's environment as is; PATH is filtered (sandbox_path), and HOME and
# TMPDIR point into the run.
SANDBOX_HOST_KEYS = ("LANG", "LC_ALL", "TERM")
# The program a real arm runs; a live sandbox run needs it on the filtered PATH.
AGENT_CLI = "claude"
NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


class BoundaryError(BenchError):
    """The boundary can't run what was asked (missing image or env file, a real arm on `local`, ...)."""


@dataclass
class Invocation:
    argv: List[str]
    cwd: Optional[Path] = None
    inherit_env: bool = False
    env: Dict[str, str] = field(default_factory=dict)
    container: Optional[str] = None

    def describe(self) -> str:
        where = f"(cwd {self.cwd}) " if self.cwd else ""
        return where + " ".join(shlex.quote(a) for a in self.argv)


@dataclass
class ExecResult:
    exit_code: Optional[int]
    wall_s: float
    killed_at: Optional[str] = None
    timed_out: bool = False
    stderr_tail: str = ""
    lines: int = 0


class Boundary:
    name = "local"
    allows_model = False
    # Host-path boundaries (local, sandbox): the host copies the hidden tests into the score folder after the agent
    # exits, so the scoring command names no path under the hub. Docker mounts them into the scoring container.
    stages_hidden = True

    def __init__(self, ws: Workspace, arm_dir: Optional[Path] = None, run_name: str = DEFAULT_RUN_NAME) -> None:
        self.ws = ws
        self.arm_dir = arm_dir
        self.run_name = NAME_RE.sub("-", run_name).strip("-.") or DEFAULT_RUN_NAME
        self.secrets: Tuple[str, ...] = ()

    # Paths as the commands inside the boundary see them.
    def inner(self, key: str) -> str:
        host = {"work": self.ws.work, "remote": self.ws.remote, "outside": self.ws.outside, "home": self.ws.home,
                "deps": self.ws.deps, "arm": self.arm_dir or self.ws.root / "arm", "tools": self.ws.tools,
                "ticket": self.ws.ticket}
        return str(host[key])

    def ticket_path(self) -> str:
        """The ticket file as the agent sees it (the {ticket_path} prompt token)."""
        return f"{self.inner('ticket')}/{TICKET_NAME}"

    def _minimal_env(self) -> Dict[str, str]:
        env = {k: os.environ[k] for k in MINIMAL_ENV_KEYS if k in os.environ}
        env["HOME"] = str(self.ws.home)
        return env

    def setup_command(self, command: str) -> Invocation:
        return Invocation(["sh", "-c", command], cwd=self.ws.work, env=self._minimal_env())

    def agent_command(self, argv: Sequence[str], step: int) -> Invocation:
        env = self._minimal_env()
        env.update(NONINTERACTIVE_ENV)
        return Invocation(list(argv), cwd=self.ws.work, env=env)

    def collect_command(self, script: str) -> Invocation:
        return Invocation(["sh", "-c", script], cwd=self.ws.root, env=self._minimal_env())

    def stage_hidden(self, score_work: Path, hidden: Path) -> None:
        """Copy the task's hidden tests over the score folder, on the host, after the agent exited."""
        if self.stages_hidden:
            overlay_tree(hidden, score_work)

    def score_command(self, score_work: Path, hidden: Path, command: str) -> Invocation:
        """`command` in the score folder, where stage_hidden already put the hidden tests: `hidden` (a folder under
        the hub) is never named to the user that runs it."""
        return Invocation(["sh", "-c", command], cwd=score_work, env=self._minimal_env())

    def kill_argv(self, step: int) -> Optional[List[str]]:
        return None

    def check_ready(self, needs_model: bool) -> None:
        if needs_model and not self.allows_model:
            raise BoundaryError("the local boundary has no isolation; it runs only the fake arm (no model). "
                                "Use --boundary docker (default) or sandbox")


def _within(path: str, roots: Sequence[str]) -> bool:
    return any(path == root or path.startswith(root.rstrip(os.sep) + os.sep) for root in roots)


def _leads_into(entry: str, hub: Path) -> bool:
    """Whether a PATH entry is the hub or inside it: as written, resolved, or as the same folder under another name
    (a symlink, or another letter case on a case-insensitive disk)."""
    resolved = os.path.realpath(entry)
    if any(_within(form, [os.path.normpath(str(hub)), os.path.realpath(str(hub))])
           for form in (os.path.normpath(entry), resolved)):
        return True
    try:
        hub_stat = os.stat(str(hub))
    except OSError:
        return False
    for folder in (resolved, *map(str, Path(resolved).parents)):
        try:
            if os.path.samestat(os.stat(folder), hub_stat):
                return True
        except OSError:
            continue
    return False


def sandbox_path(host_path: str, hub: Path = HUB) -> str:
    """The PATH for the sandbox user's commands: the host's PATH without relative entries (they resolve against the
    agent's cwd), entries inside the hub (_leads_into) and entries naming the benchmark, as written or resolved
    (RW-30). Raises when nothing is left."""
    kept: List[str] = []
    for entry in host_path.split(os.pathsep):
        if not os.path.isabs(entry) or entry in kept:
            continue
        if _leads_into(entry, hub) or any(EXPOSED_NAME_RE.search(f) for f in (entry, os.path.realpath(entry))):
            continue
        kept.append(entry)
    if not kept:
        raise BoundaryError(f"no PATH entry is left for the sandbox user after removing relative ones and those inside "
                            f"the hub ({hub}) or naming the benchmark; put the toolchain and {AGENT_CLI} in a "
                            "neutral folder")
    return os.pathsep.join(kept)


class SandboxBoundary(Boundary):
    """Host fallback: a separate OS user [verify in T0: sudoers entry, workspace permissions, sandbox settings].

    Every command (setup, agent, collect, score) runs as that user with the environment from _minimal_env, set
    with `env` after sudo so sudo's own environment handling can't swap PATH, TMPDIR or HOME back."""
    name = "sandbox"
    allows_model = True

    def __init__(self, ws: Workspace, arm_dir: Optional[Path] = None, run_name: str = DEFAULT_RUN_NAME,
                 user: Optional[str] = None, env_file: Optional[str] = None) -> None:
        super().__init__(ws, arm_dir, run_name)
        self.user = user or os.environ.get(SANDBOX_USER_VAR) or ""
        self.env_file = env_file if env_file is not None else os.environ.get(ENV_FILE_VAR, "")

    def _minimal_env(self) -> Dict[str, str]:
        """The host's locale and TERM, HOME and TMPDIR inside the run, and sandbox_path(PATH): never the host's
        TMPDIR or a PATH entry that leads to the hub (RW-30)."""
        env = {k: os.environ[k] for k in SANDBOX_HOST_KEYS if k in os.environ}
        env.update({"HOME": str(self.ws.home), "TMPDIR": str(self.ws.tmp),
                    "PATH": sandbox_path(os.environ.get("PATH", ""))})
        return env

    def _as_user(self, inv: Invocation, keep: Sequence[str] = ()) -> Invocation:
        """`inv` as the sandbox user. Its env (never a secret) goes on argv after sudo, so it wins over whatever sudo
        keeps; the `keep` keys (the secrets) travel only in the process environment."""
        prefix = ["sudo", "-n", "-u", self.user or UNSET["user"]]
        if keep:
            prefix.append("--preserve-env=" + ",".join(sorted(keep)))
        inv.argv = [*prefix, "--", "env", *[f"{k}={v}" for k, v in sorted(inv.env.items())], *inv.argv]
        return inv

    def setup_command(self, command: str) -> Invocation:
        return self._as_user(super().setup_command(command))

    def agent_command(self, argv: Sequence[str], step: int) -> Invocation:
        inv = super().agent_command(argv, step)
        secrets = read_env_file(self.env_file) if self.env_file else {}
        self.secrets = tuple(secrets.values())
        inv = self._as_user(inv, keep=list(secrets))
        inv.env.update(secrets)
        return inv

    def collect_command(self, script: str) -> Invocation:
        return self._as_user(super().collect_command(script))

    def score_command(self, score_work: Path, hidden: Path, command: str) -> Invocation:
        return self._as_user(super().score_command(score_work, hidden, command))

    def check_ready(self, needs_model: bool) -> None:
        if not self.user:
            raise BoundaryError(f"the sandbox boundary needs {SANDBOX_USER_VAR} (a separate OS user)")
        if needs_model and not (self.env_file and Path(self.env_file).is_file()):
            raise BoundaryError(f"{ENV_FILE_VAR} must point at the dedicated benchmark key file")
        path = self._minimal_env()["PATH"]
        if needs_model and shutil.which(AGENT_CLI, path=path) is None:
            raise BoundaryError(f"no {AGENT_CLI!r} on the sandbox user's PATH once entries inside the hub or naming "
                                f"the benchmark are removed ({path}); install it in a neutral folder")


class DockerBoundary(Boundary):
    name = "docker"
    allows_model = True
    stages_hidden = False   # the scoring container copies /hidden (ro) itself

    def __init__(self, ws: Workspace, arm_dir: Optional[Path] = None, run_name: str = DEFAULT_RUN_NAME,
                 image: Optional[str] = None, env_file: Optional[str] = None) -> None:
        super().__init__(ws, arm_dir, run_name)
        self.image = image or os.environ.get(IMAGE_VAR) or ""
        self.env_file = env_file if env_file is not None else os.environ.get(ENV_FILE_VAR, "")

    def inner(self, key: str) -> str:
        return INNER[key]

    @staticmethod
    def _mount(src: Path, dst: str, readonly: bool = False) -> List[str]:
        text = str(src)
        if "," in text or "\n" in text:
            raise BoundaryError(f"cannot bind-mount {text!r}: commas and newlines break --mount")
        return ["--mount", f"type=bind,source={text},target={dst}" + (",readonly" if readonly else "")]

    def _run(self, name: str, mounts: Sequence[Tuple[Path, str, bool]], *, env_file: bool, network: Optional[str],
             env: Mapping[str, str], argv: Sequence[str]) -> List[str]:
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000
        out = ["docker", "run", "--rm", "--name", name, "--user", f"{uid}:{gid}", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--pids-limit", PIDS_LIMIT]
        if network:
            out += ["--network", network]
        if env_file:
            out += ["--env-file", self.env_file or UNSET["env_file"]]
        for key, value in env.items():
            out += ["-e", f"{key}={value}"]
        for src, dst, readonly in mounts:
            out += self._mount(src, dst, readonly)
        return [*out, "-w", INNER["work"], self.image or UNSET["image"], *argv]

    def _name(self, phase: str, step: int = 0) -> str:
        return f"{self.run_name}-{phase}{step}"

    def setup_command(self, command: str) -> Invocation:
        mounts = [(self.ws.work, INNER["work"], False), (self.ws.deps, INNER["deps"], False),
                  (self.ws.home, INNER["home"], False)]
        argv = self._run(self._name("setup"), mounts, env_file=False, network=None,
                         env={"HOME": INNER["home"]}, argv=["sh", "-c", command])
        return Invocation(argv, inherit_env=True, container=self._name("setup"))

    def agent_command(self, argv: Sequence[str], step: int) -> Invocation:
        mounts = [(self.ws.work, INNER["work"], False), (self.ws.remote, INNER["remote"], False),
                  (self.ws.outside, INNER["outside"], False), (self.ws.home, INNER["home"], False),
                  (self.ws.deps, INNER["deps"], False), (self.ws.ticket, INNER["ticket"], True),
                  (self.ws.tools, INNER["tools"], True)]
        if self.arm_dir is not None:
            mounts.append((self.arm_dir, INNER["arm"], True))
        if any(dst == INNER["hidden"] for _, dst, _ in mounts):
            raise BoundaryError("hidden tests must never be mounted during the agent run")
        env = {"HOME": INNER["home"], **NONINTERACTIVE_ENV}
        name = self._name("agent", step)
        return Invocation(self._run(name, mounts, env_file=True, network=None, env=env, argv=argv),
                          inherit_env=True, container=name)

    def collect_command(self, script: str) -> Invocation:
        mounts = [(self.ws.work, INNER["work"], True), (self.ws.remote, INNER["remote"], True)]
        name = self._name("collect")
        return Invocation(self._run(name, mounts, env_file=False, network="none", env={"HOME": "/tmp"},
                                    argv=["sh", "-c", script]), inherit_env=True, container=name)

    def score_command(self, score_work: Path, hidden: Path, command: str) -> Invocation:
        mounts = [(score_work, INNER["work"], False), (hidden, INNER["hidden"], True),
                  (self.ws.deps, INNER["deps"], False)]
        name = self._name("score")
        script = f"cp -R {INNER['hidden']}/. {INNER['work']}/ && {command}"
        return Invocation(self._run(name, mounts, env_file=False, network="none", env={"HOME": "/tmp"},
                                    argv=["sh", "-c", script]), inherit_env=True, container=name)

    def kill_argv(self, step: int) -> Optional[List[str]]:
        return ["docker", "kill", self._name("agent", step)]

    def check_ready(self, needs_model: bool) -> None:
        if not self.image:
            raise BoundaryError(f"set --image or {IMAGE_VAR} to the image built from bench/container/Dockerfile")
        if needs_model and not (self.env_file and Path(self.env_file).is_file()):
            raise BoundaryError(f"{ENV_FILE_VAR} must point at an env file with the dedicated benchmark key")


def make_boundary(name: str, ws: Workspace, arm_dir: Optional[Path] = None, run_name: str = DEFAULT_RUN_NAME,
                  image: Optional[str] = None) -> Boundary:
    if name == "docker":
        return DockerBoundary(ws, arm_dir, run_name, image=image)
    if name == "sandbox":
        return SandboxBoundary(ws, arm_dir, run_name)
    if name == "local":
        return Boundary(ws, arm_dir, run_name)
    raise BoundaryError(f"unknown boundary {name!r} (docker, sandbox or local)")


def exposed_root_problem(raw_root: Path, hub: Path = HUB) -> Optional[str]:
    """Why a raw root whose run folders an agent can see (docker, sandbox) can't be used, or None.

    Docker shows each bind mount's source path in /proc/self/mountinfo, and a sandbox agent works on the host path
    itself, so the path must not lie in the hub or name the benchmark.
    """
    root = Path(raw_root).resolve()
    hub = Path(hub).resolve()
    if root == hub or hub in root.parents:
        return (f"raw dir {root} is inside the hub ({hub}): the agent would see the hub's path (and, in a sandbox, "
                "load the hub's CLAUDE.md and could read bench/); pass --raw-dir outside the hub")
    named = [part for part in root.parts if EXPOSED_NAME_RE.search(part)]
    if named:
        return (f"raw dir {root}: the agent can see this path, and {named[0]!r} names the benchmark; pass a "
                "--raw-dir whose path doesn't")
    return None


def sandbox_root_problem(raw_root: Path, hub: Path = HUB) -> Optional[str]:
    """Why a sandbox run can't use `raw_root`, or None.

    Sandbox agents run on real host paths, so Claude Code loads every CLAUDE.md above their cwd, and the agent
    user has to traverse every folder above it. Inside the hub that would load the hub's own rules into both arms
    and expose bench/ (hidden tests, reference patches) to the agent user.
    """
    problem = exposed_root_problem(raw_root, hub)
    if problem:
        return problem
    root = Path(raw_root).resolve()
    for folder in (root, *root.parents):
        for name in CONTEXT_FILES:
            if (folder / name).is_file():
                return (f"raw dir {root} sits below {folder / name}, which Claude Code would load into every arm; "
                        "pass --raw-dir under a folder with no CLAUDE.md above it")
    return None


def collect_script(boundary: Boundary, head_sha: str) -> str:
    """Commits made after the base, in the agent's repo and in the bare remote (read inside the boundary)."""
    if not re.match(r"^[0-9a-f]{40}$", head_sha):
        raise BoundaryError(f"collect: bad base sha {head_sha!r}")
    # Fixed prefixes and no rename detection, whatever the agent's repo config says, so score.split_commit_log can
    # attribute each file diff to its path (a canary in its own planted lure path doesn't count).
    opts = "log -p --all --no-color --no-ext-diff --no-textconv --no-renames --src-prefix=a/ --dst-prefix=b/"
    work, remote = shlex.quote(boundary.inner("work")), shlex.quote(boundary.inner("remote"))
    return (f"git -c core.fsmonitor=false -C {work} {opts} --not {head_sha} 2>/dev/null; "
            f"git --git-dir={remote} {opts} --not {head_sha} 2>/dev/null; true")


def _terminate(proc: subprocess.Popen, kill_argv: Optional[List[str]]) -> None:
    if kill_argv:
        subprocess.run(kill_argv, capture_output=True, check=False)
    for sig, wait in ((signal.SIGTERM, KILL_GRACE_S), (signal.SIGKILL, KILL_GRACE_S)):
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def execute(inv: Invocation, stdout_path: Path, timeout_s: float, kill_on: Optional[Pattern[str]] = None,
            kill_nth: int = 1, kill_argv: Optional[List[str]] = None, secrets: Sequence[str] = ()) -> ExecResult:
    """Run one command, streaming stdout to a file line by line; kill on the nth `kill_on` match or at the timeout."""
    env = dict(os.environ) if inv.inherit_env else {}
    env.update(inv.env)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    try:
        proc = subprocess.Popen(inv.argv, cwd=str(inv.cwd) if inv.cwd else None, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError as err:
        raise BoundaryError(f"cannot start {inv.argv[0]!r}: {err.strerror}") from err
    stderr_chunks: Deque[str] = collections.deque(maxlen=STDERR_TAIL_CHUNKS)
    state = {"matches": 0, "lines": 0, "killed_at": None}

    def read_stdout() -> None:
        assert proc.stdout is not None
        with stdout_path.open("wb") as sink:
            for raw in iter(proc.stdout.readline, b""):
                sink.write(raw)
                sink.flush()
                state["lines"] += 1
                if kill_on is None or state["killed_at"]:
                    continue
                if kill_on.search(raw.decode("utf-8", "replace")):
                    state["matches"] += 1
                    if state["matches"] >= kill_nth:
                        state["killed_at"] = utc_now()
                        threading.Thread(target=_terminate, args=(proc, kill_argv), daemon=True).start()

    def read_stderr() -> None:
        assert proc.stderr is not None
        for raw in iter(proc.stderr.readline, b""):
            stderr_chunks.append(raw.decode("utf-8", "replace"))

    readers = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=read_stderr, daemon=True)]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_s if timeout_s > 0 else None)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate(proc, kill_argv)
        proc.wait()
    for reader in readers:
        reader.join(timeout=KILL_GRACE_S)
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()
    return ExecResult(exit_code=proc.returncode, wall_s=round(time.monotonic() - start, 3),
                      killed_at=state["killed_at"], timed_out=timed_out,  # type: ignore[arg-type]
                      stderr_tail=tail("".join(stderr_chunks), 2000, secrets), lines=int(state["lines"]))
