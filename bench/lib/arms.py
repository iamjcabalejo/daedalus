"""Arms (daedalus.bench-arm/1): loading, validation, the same-conditions check (AC-10), prompts, argv, setup,
the auto-approver settings and review-findings extraction."""
from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from . import ARM_SCHEMA_ID, BENCH, HUB, KINDS, BenchError, glob_match, load_json, schema_errors, utc_now, write_json
from .score import normalize_findings
from .workspace import git, git_out, is_regular, walk_files

ARMS_DIR = BENCH / "arms"
# §3.8: the same instruction for every arm.
NONINTERACTIVE_INSTRUCTION = "Non-interactive run: don't ask questions; record assumptions in your final message."
SHARED_FIELDS = ("model", "effort", "permission", "auto_approver", "instruction", "max_turns")
ARM_ONLY_FLAGS = ("--plugin-dir",)  # flags (each with one value) that may differ between real arms
MAX_TURNS_FLAG = "--max-turns"
REVIEW_PATCH_MODES = ("uncommitted", "branch")
PLACEHOLDER_RE = re.compile(r"^\$([A-Z][A-Z0-9_]*)$")
TOKEN_RE = re.compile(r"\{([a-z_]+)\}")
# {ticket} (the ticket text inline) is kept only for task resume_steps written before {ticket_path}; arms deliver
# the ticket as data, so an arm template or resume_hint that inlines it is rejected (INLINE_TICKET). There is no
# {task_id} token: the task id would tell the agent which task (and lure) it faces (RW-23); {slug} is the neutral
# plan slug.
PROMPT_TOKENS = ("ticket", "ticket_path", "instruction", "slug", "resume_hint", "branch")
RESUME_HINT_TOKENS = ("ticket_path", "slug", "branch")
INLINE_TICKET = "ticket"
ARGV_TOKENS = ("prompt", "model", "effort", "permission", "step_budget_usd", "max_turns", "settings", "arm_dir",
               "tools_dir", "home")
# Agent-visible names say nothing about a benchmark (RW-24): the settings file in HOME, and the per-run tools
# folder, which holds a copy of approver.py only (plus fake_agent.py for the fake arm, which runs no model).
SETTINGS_NAME = "cli-settings.json"
APPROVER = "approver.py"
APPROVER_LOG = "approver.log"
FAKE_AGENT = "fake_agent.py"
FAKE_INPUT = "fake-input.json"
TOOL_SOURCES = BENCH / "lib"

Log = Callable[[str], None]


@dataclass(frozen=True)
class Arm:
    data: Dict[str, Any]
    path: Path

    @property
    def id(self) -> str:
        return str(self.data.get("id", self.path.stem))

    @property
    def version(self) -> str:
        return str(self.data.get("version", ""))

    @property
    def driver(self) -> str:
        return str(self.data.get("driver", ""))

    @property
    def needs_model(self) -> bool:
        return self.driver != "fake"

    @property
    def cli(self) -> Dict[str, Any]:
        return self.data.get("cli") or {}

    @property
    def exclude(self) -> List[str]:
        return list(self.data.get("exclude_from_scoring", []))

    @property
    def fairness_notes(self) -> List[str]:
        return list(self.data.get("fairness_notes", []))

    @property
    def review_patch(self) -> str:
        return str(self.data.get("review_patch", "uncommitted"))

    @property
    def max_turns(self) -> str:
        """The shared per-step --max-turns cap as an argv value ('' when the arm sets none)."""
        value = self.data.get("max_turns")
        return str(value) if value is not None else ""

    def steps_for(self, kind: str) -> List[Dict[str, Any]]:
        return [s for s in self.data.get("steps", []) if kind in s.get("kinds", KINDS)]


def load_arm(ref: str) -> Arm:
    path = Path(ref)
    if not path.is_file():
        path = ARMS_DIR / f"{ref}.json"
    if not path.is_file():
        raise BenchError(f"arm {ref!r} not found (a path, or an id under {ARMS_DIR})")
    data = load_json(path)
    if not isinstance(data, dict):
        raise BenchError(f"{path}: expected a JSON object")
    return Arm(data=data, path=path.resolve())


def _unknown_tokens(text: str, allowed: Sequence[str]) -> List[str]:
    return [t for t in TOKEN_RE.findall(text) if t not in allowed]


def check_arm(arm: Arm) -> List[str]:
    errors = schema_errors(arm.data, "arm")
    if errors:
        return errors
    if arm.data["schema"] != ARM_SCHEMA_ID:
        errors.append(f"schema must be {ARM_SCHEMA_ID}")
    if arm.id != arm.path.stem:
        errors.append(f"id {arm.id!r} must equal the file name {arm.path.stem!r}")
    if arm.review_patch not in REVIEW_PATCH_MODES:
        errors.append(f"review_patch must be one of {list(REVIEW_PATCH_MODES)}")
    for kind in KINDS:
        steps = arm.steps_for(kind)
        if not steps:
            errors.append(f"no step runs for kind {kind}")
        elif not steps[0]["fresh_process"]:
            errors.append(f"the first {kind} step must be a fresh process")
    for step in arm.data["steps"]:
        if "{prompt}" in step["prompt_template"]:
            errors.append("prompt_template can't contain {prompt}")
        for token in _unknown_tokens(step["prompt_template"], PROMPT_TOKENS + ("prompt",)):
            errors.append(f"prompt_template: unknown token {{{token}}}")
        if INLINE_TICKET in TOKEN_RE.findall(step["prompt_template"]):
            errors.append("prompt_template: {ticket} puts the requester's text in the operator's prompt; "
                          "point to the file with {ticket_path}")
    for token in _unknown_tokens(str(arm.data.get("resume_hint", "")), RESUME_HINT_TOKENS):
        errors.append(f"resume_hint: token {{{token}}} not allowed (only {', '.join(RESUME_HINT_TOKENS)})")
    for i, setup in enumerate(arm.data["setup"]):
        if setup["action"] == "build_plugins" and not (setup.get("ref") and setup.get("plugins")):
            errors.append(f"setup[{i}]: build_plugins needs ref and plugins")
    argv = arm.cli.get("argv") or []
    max_turns = arm.data.get("max_turns")
    if "{max_turns}" in argv and not (isinstance(max_turns, int) and not isinstance(max_turns, bool) and max_turns >= 1):
        errors.append("cli.argv uses {max_turns}: set max_turns to an integer >= 1")
    if arm.driver == "claude":
        if "{prompt}" not in argv:
            errors.append("cli.argv must contain a {prompt} element")
        if _flag_value(argv, MAX_TURNS_FLAG) != "{max_turns}":
            errors.append(f"cli.argv must pass {MAX_TURNS_FLAG} {{max_turns}} (--max-budget-usd is a client-side "
                          "estimate that can overshoot)")
        for token in _unknown_tokens(" ".join(argv + arm.cli.get("continue_args", [])), ARGV_TOKENS):
            errors.append(f"cli.argv: unknown token {{{token}}}")
        if not arm.data.get("review_output"):
            errors.append("a claude arm needs review_output")
        if arm.data.get("review_output", {}).get("from") == "file" and not arm.data["review_output"].get("glob"):
            errors.append("review_output.from=file needs a glob")
    return errors


def _flag_value(argv: Sequence[str], flag: str) -> Optional[str]:
    """The element after `flag` in argv, or None when the flag is absent or last."""
    if flag not in argv:
        return None
    index = list(argv).index(flag)
    return argv[index + 1] if index + 1 < len(argv) else None


def _base_argv(arm: Arm) -> List[str]:
    """cli.argv without the arm-only flags and their values."""
    argv = list(arm.cli.get("argv") or [])
    out: List[str] = []
    skip = False
    for item in argv:
        if skip:
            skip = False
            continue
        if item in ARM_ONLY_FLAGS:
            skip = True
            continue
        out.append(item)
    return out


def check_same_conditions(arms: Sequence[Arm]) -> List[str]:
    """AC-10: every real arm shares the model, effort, permission, auto-approver, instruction and base CLI argv."""
    real = [a for a in arms if a.needs_model]
    errors = [f"{a.id}: instruction differs from the §3.8 text" for a in real
              if a.data.get("instruction") != NONINTERACTIVE_INSTRUCTION]
    for first, other in zip(real, real[1:]):
        for key in SHARED_FIELDS:
            if first.data.get(key) != other.data.get(key):
                errors.append(f"{first.id} and {other.id} differ on {key}")
        if _base_argv(first) != _base_argv(other):
            errors.append(f"{first.id} and {other.id} differ on cli.argv beyond {', '.join(ARM_ONLY_FLAGS)}")
        if first.cli.get("version_argv") != other.cli.get("version_argv"):
            errors.append(f"{first.id} and {other.id} differ on cli.version_argv")
    return errors


def resolve_placeholder(value: str, overrides: Mapping[str, Optional[str]]) -> Optional[str]:
    """`$BENCH_MODEL` -> the override or environment value; literal values pass through; None when unset."""
    match = PLACEHOLDER_RE.match(value)
    if not match:
        return value
    name = match.group(1)
    return overrides.get(name) or os.environ.get(name) or None


def render(template: str, values: Mapping[str, str]) -> str:
    """Replace only known {token}s in one pass; inserted text is never re-expanded and other braces stay."""
    return TOKEN_RE.sub(lambda m: values[m.group(1)] if m.group(1) in values else m.group(0), template)


def build_argv(arm: Arm, values: Mapping[str, str], fresh: bool) -> List[str]:
    argv = [render(item, values) for item in arm.cli.get("argv", [])]
    if not fresh:
        argv += [render(item, values) for item in arm.cli.get("continue_args", [])]
    return argv


def approver_settings(tools_dir: str, home: str) -> Dict[str, Any]:
    """PreToolUse hook that answers AskUserQuestion with the first option, the same for every arm [verify in T0]."""
    command = (f"python3 {shlex.quote(tools_dir + '/' + APPROVER)} "
               f"--log {shlex.quote(home + '/' + APPROVER_LOG)}")
    return {"hooks": {"PreToolUse": [{"matcher": "AskUserQuestion",
                                      "hooks": [{"type": "command", "command": command}]}]}}


# ---------------------------------------------------------------- arm setup (host side, before any task)

def _safe_extract(data: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            name = member.name
            if name.startswith("/") or ".." in Path(name).parts or member.isdev():
                raise BenchError(f"refusing archive member {name!r}")
            if (member.issym() or member.islnk()) and (member.linkname.startswith("/") or ".." in Path(member.linkname).parts):
                raise BenchError(f"refusing archive link {name!r} -> {member.linkname!r}")
        if hasattr(tarfile, "data_filter"):  # Python 3.12+: refuse links and paths outside dest
            archive.extractall(dest, filter="data")
        else:
            archive.extractall(dest)


def build_plugins(step: Mapping[str, Any], arm_dir: Path, log: Log, dry_run: bool) -> None:
    """Export the hub at `ref` into a temporary folder, build there, and copy only plugins/<name> and BUILD.json
    into arm_dir. arm_dir is mounted at /arm for every step, so the export (which holds bench/ at any ref after P0a:
    hidden tests, reference patches) must never land in it."""
    ref, plugins = str(step["ref"]), list(step["plugins"])
    log(f"git -C {HUB} archive --format=tar {ref} | extract into a temporary folder <tmp>/hub-{ref}")
    log(f"git init -q <tmp>/hub-{ref}; bash <tmp>/hub-{ref}/scripts/build-plugin.sh")
    log(f"copy {', '.join(plugins)} from <tmp>/hub-{ref}/plugins/ to {arm_dir}/plugins/; write {arm_dir}/BUILD.json; "
        "remove the temporary folder")
    if dry_run:
        return
    if git(["-C", str(HUB), "cat-file", "-e", f"{ref}^{{commit}}"], check=False).returncode != 0:
        raise BenchError(f"hub commit {ref} is not in this clone (CI checkouts are shallow: fetch full history)")
    sha = git_out(["-C", str(HUB), "rev-parse", f"{ref}^{{commit}}"])
    with tempfile.TemporaryDirectory(prefix="bench-arm-") as tmp:
        src = Path(tmp) / f"hub-{ref}"
        src.mkdir()
        _safe_extract(git(["-C", str(HUB), "archive", "--format=tar", sha]).stdout, src)
        git(["init", "-q", str(src)])
        proc = subprocess.run(["bash", str(src / "scripts" / "build-plugin.sh")], cwd=str(src), capture_output=True,
                              text=True)
        if proc.returncode != 0:
            raise BenchError(f"build-plugin.sh at {ref} failed ({proc.returncode}): {proc.stderr.strip()[-300:]}")
        for name in plugins:
            built = src / "plugins" / name
            if not built.is_dir():
                raise BenchError(f"build-plugin.sh at {ref} produced no plugins/{name}")
            shutil.copytree(built, arm_dir / "plugins" / name, symlinks=True)
    write_json(arm_dir / "BUILD.json", {"ref": ref, "sha": sha, "plugins": plugins, "built_at": utc_now()})


def setup_arm(arm: Arm, arm_dir: Path, log: Log, dry_run: bool) -> None:
    for step in arm.data.get("setup", []):
        if step["action"] == "build_plugins":
            build_plugins(step, arm_dir, log, dry_run)
        else:
            raise BenchError(f"arm {arm.id}: unknown setup action {step['action']!r}")


# ---------------------------------------------------------------- review findings

def _findings_text(text: str) -> str:
    """Prefer the part after a 'findings.json' marker (Argus saves its JSON block under that summary)."""
    marker = text.find("findings.json")
    return text[marker:] if marker >= 0 else text


def extract_findings(arm: Arm, result_text: str, work: Path) -> List[Dict[str, Any]]:
    spec = arm.data.get("review_output") or {"from": "result_text"}
    if spec["from"] == "result_text":
        return normalize_findings(result_text)
    pattern = str(spec.get("glob", ""))
    matches = [p for p in walk_files(work) if is_regular(p) and glob_match(p.relative_to(work).as_posix(), [pattern])]
    for path in sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings = normalize_findings(_findings_text(text))
        if findings or '"findings"' in text:
            return findings
    return []


def fake_input(arm: Arm, task_kind: str, patch: Optional[str], findings: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    fake = arm.data.get("fake") or {}
    return {"kind": task_kind, "patch": patch, "findings": findings,
            "cost_usd": float(fake.get("cost_usd", 0.0)), "input_tokens": int(fake.get("input_tokens", 0)),
            "output_tokens": int(fake.get("output_tokens", 0)), "pause_s": float(fake.get("pause_s", 0))}


def install_tools(tools: Path, arm: Arm) -> List[str]:
    """Copy the agent-side tools into the run's tools folder; returns their names. Never bench/lib itself: score.py,
    budget.py and fake_agent.py stay out of a real arm's reach."""
    names = [APPROVER] + ([FAKE_AGENT] if not arm.needs_model else [])
    tools.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(TOOL_SOURCES / name, tools / name)
    return names


def write_settings(home: Path, tools_dir_inner: str, home_inner: str) -> None:
    (home / SETTINGS_NAME).write_text(json.dumps(approver_settings(tools_dir_inner, home_inner), indent=2) + "\n",
                                      encoding="utf-8")
