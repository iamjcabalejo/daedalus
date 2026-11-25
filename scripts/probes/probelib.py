"""Probe harness library: cases, templates, workspace actions, host commands, budget guard and results (AC-1, AC-2).

scripts/probes/run-probes.sh is the CLI (argparse and the top-level flow live in its heredoc). This module holds the
logic, so scripts/test-probes.sh can exercise everything except the model call: the only action that starts a
host CLI is `host`, and the live preflight (`host_version`, `cli_flags`, `plugin_list_text`) runs only from run_live.

Layout of one run (never inside the hub):
  $TMPDIR/daedalus-probes/<UTC-ts>/<case>[.<variant>]/<install>/
    repo/          fresh `git init` with SEED_FILES; the host's working directory
    probe-plugin/  plugin installs only (loaded with --plugin-dir; verify in T0)
    bin/recorder.py, ctrl.json, out/raw/*.jsonl (raw payloads, never committed), out/stream.jsonl
  $TMPDIR/daedalus-probes/<UTC-ts>/staged/{fixtures,results}/   redacted output, copied into the hub only after the
                                                               isolation check and the leak scan pass
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import isolation
import observe
import redact

PROBES_DIR = Path(__file__).resolve().parent
HUB = PROBES_DIR.parent.parent
CASES_DIR = PROBES_DIR / "cases"
TEMPLATES_DIR = PROBES_DIR / "templates"
FIXTURES_DIR = PROBES_DIR / "fixtures"
RESULTS_DIR = PROBES_DIR / "results"
SCHEMA_DIR = HUB / "bench" / "schema"
VALIDATOR = HUB / ".claude" / "scripts" / "validate-profile.py"

CASE_SCHEMA = "daedalus.probe-case/1"
RESULT_SCHEMA = "daedalus.probe-result/1"
HOSTS = ("claude", "cursor", "codex")
INSTALLS = ("script", "plugin")
HOST_BINARIES = {"claude": "claude", "cursor": "agent", "codex": "codex"}
MODEL = "haiku"  # [D] the probes test the platform, not the model
DEFAULT_TIMEOUT_S = 300
PREFLIGHT_TIMEOUT_S = 30
PLUGIN_NAME = "probe"
DEFAULT_VARS = {"interpreter": None, "hook_timeout": 10, "on_failure": None, "fail_closed": None, "dialect": None}
# Flags the claude preflight looks for in `claude --help` (verify in T0). A missing required flag blocks the run;
# a missing optional one is dropped and its fallback is noted on every affected result.
REQUIRED_FLAGS = {"claude": ("--max-turns", "--model", "--output-format")}
OPTIONAL_FLAGS = {"claude": {
    "--max-budget-usd": "fallback: --max-turns plus the run total (--budget-usd)",
    "--plugin-dir": "fallback: project-scope local marketplace install, removed after (manual; verify in T0)",
    "--permission-mode": "fallback: none; the case is inconclusive",
}}
SEED_FILES = {
    "seed.txt": "seed\n",
    "README.md": "# probe workspace\n\nThrowaway repository created by daedalus run-probes.sh.\n",
    **{f"steps/step{n}.txt": f"step {n}\n" for n in range(1, 7)},
}
INSTALLED_PATHS = ("repo/.claude", "repo/.cursor", "repo/.codex", "repo/.mcp.json", "probe-plugin", "bin",
                   "ctrl.json")
# Where the probe-mcp server template is rendered, per install (M2).
MCP_SERVER_DEST = {"script": "repo/.claude/probe-mcp/probe_mcp.py", "plugin": "probe-plugin/mcp/probe_mcp.py"}
GIT_ISOLATION = ["-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "-c", "init.defaultBranch=main",
                 "-c", "user.name=daedalus-probe", "-c", "user.email=probe@localhost"]
RECORDER_ERRORS = "_errors.jsonl"  # recorder.ERRORS_FILE
DECIDED_STATUSES = ("confirmed", "contradicted")  # the statuses a `requires` gate can take away
TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
VERSION_RE = re.compile(r"\d+(?:\.\d+)+")
PLUGIN_ID_RE = re.compile(r"([A-Za-z0-9_.-]+)@[A-Za-z0-9_.-]+")
# Variant ids become a workspace path segment (<case>.<variant>), which mkdir and render write to before any
# containment check, so they may not carry `/`, `\` or `..`.
VARIANT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
DROP = object()

KIND_FIELDS = {
    "event": ("event", "expect"), "field": ("event", "field", "expect"), "count": ("event", "op", "value"),
    "keys": ("event",), "marker": ("path",), "file": ("path",), "identity-echo": ("event", "names"),
    "identity-consistency": ("names",), "stream": ("check",), "git": ("check",), "transcript-usage": (),
    "manual": ("description",),
}
EXPECT_VALUES = {"event": ("present", "absent"), "field": ("present", "absent", "equals", "value"),
                 "marker": (True, False), "file": ("changed", "unchanged")}
CHECKS = {"stream": ("result", "permission-denials", "usage-keys", "codex-usage", "tool-use"),
          "git": ("worktrees", "branches")}


class CaseError(ValueError):
    """A case definition or template is invalid."""


class GuardError(RuntimeError):
    """A live run was refused (budget, missing CLI or flag)."""


class HarnessError(RuntimeError):
    """The harness itself failed during a run (a FAIL per §3.10, not a finding)."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def probe_root() -> Path:
    return Path(tempfile.gettempdir()) / isolation.PROBE_ROOT_NAME


def os_label() -> str:
    return f"{platform.system().lower()}-{platform.release()}"


def safe_version(version: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", version) or "unknown"


# ---- schemas and cases ----------------------------------------------------------------------------------------

def load_validator() -> Callable:
    spec = importlib.util.spec_from_file_location("validate_profile", VALIDATOR)
    if spec is None or spec.loader is None:
        raise CaseError(f"cannot load the schema validator at {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise CaseError(f"{path.name}: cannot read JSON: {err}") from err


def schema_errors(value: object, schema_file: str) -> list:
    schema = read_json(SCHEMA_DIR / schema_file)
    errors: list = []
    load_validator()(value, schema, schema, "", errors)
    return errors


def case_paths() -> list:
    return sorted(CASES_DIR.glob("*.json"))


def check_files(case: dict) -> list:
    errors = []
    for install, entries in case["files"].items():
        if install not in case["applies_to"]["installs"]:
            errors.append(f"files.{install}: install not in applies_to.installs")
        for entry in entries:
            if not (TEMPLATES_DIR / entry["template"]).is_file():
                errors.append(f"files.{install}: template not found: {entry['template']}")
            dest = Path(entry["dest"])
            if dest.parts[:1] not in (("repo",), ("probe-plugin",)) or ".." in dest.parts or ".git" in dest.parts:
                errors.append(f"files.{install}: dest must stay under repo/ or probe-plugin/: {entry['dest']}")
    for install in case["applies_to"]["installs"]:
        if install not in case["files"]:
            errors.append(f"applies_to.installs has {install} but files.{install} is missing")
    return errors


def check_requires(case: dict) -> list:
    known = {path.stem for path in case_paths()}
    required = case.get("requires", [])
    return ([f"requires {r!r}: no such case" for r in required if r not in known]
            + [f"requires {r!r}: a case can't require itself" for r in required if r == case["id"]])


def check_ctrl(rules: list, where: str) -> list:
    keys = [rule["key"] for rule in rules]
    return [f"{where}: duplicate control key {key}" for key in sorted(set(keys)) if keys.count(key) > 1]


def check_observations(observations: list, where: str) -> list:
    errors, ids = [], [o["id"] for o in observations]
    errors += [f"{where}: duplicate observation id {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    for obs in observations:
        kind, role = obs["kind"], obs.get("role", "assert")
        has_expect = "expect" in obs or "expect_by_install" in obs
        missing = [name for name in KIND_FIELDS[kind] if name not in obs and not (name == "expect" and has_expect)]
        if kind in ("marker", "file") and role != "record" and not has_expect:
            missing.append("expect")
        if missing:
            errors.append(f"{where}.{obs['id']}: {kind} needs {', '.join(missing)}")
        expects = ([obs["expect"]] if "expect" in obs else []) + list((obs.get("expect_by_install") or {}).values())
        if kind in EXPECT_VALUES and any(e not in EXPECT_VALUES[kind] for e in expects):
            errors.append(f"{where}.{obs['id']}: expect must be one of {EXPECT_VALUES[kind]}")
        if kind in CHECKS and obs.get("check") not in CHECKS[kind]:
            errors.append(f"{where}.{obs['id']}: {kind} check must be one of {CHECKS[kind]}")
        if kind == "stream" and obs.get("check") == "tool-use" and not obs.get("names"):
            errors.append(f"{where}.{obs['id']}: stream tool-use needs names (the tool names to look for)")
        if kind == "field" and obs.get("expect") == "equals" and "value" not in obs and "value_by_install" not in obs:
            errors.append(f"{where}.{obs['id']}: equals needs value or value_by_install")
        if kind == "field" and obs.get("expect") == "value" and obs.get("field") not in observe.SAFE_VALUE_FIELDS:
            errors.append(f"{where}.{obs['id']}: only {observe.SAFE_VALUE_FIELDS} may be recorded by value")
    return errors


def validate_case(case: object, path: Path) -> list:
    """Schema errors plus the rules the validator subset can't express."""
    errors = schema_errors(case, "probe-case.schema.json")
    if errors or not isinstance(case, dict):
        return [f"{path.name}: {e}" for e in errors] or [f"{path.name}: not an object"]
    if case["id"] != path.stem:
        errors.append(f"id {case['id']!r} does not match the file name")
    errors += check_files(case)
    errors += check_requires(case)
    errors += check_ctrl(case["ctrl"], "ctrl") + check_observations(case["observations"], "observations")
    variant_ids = [v["id"] for v in case.get("variants", [])]
    errors += [f"duplicate variant id {v}" for v in sorted(set(variant_ids)) if variant_ids.count(v) > 1]
    errors += [f"variant id {v!r} must match {VARIANT_ID_RE.pattern} (no '/' or '..')"
               for v in variant_ids if not VARIANT_ID_RE.fullmatch(v)]
    for variant in case.get("variants", []):
        errors += check_ctrl(variant.get("ctrl", []), f"variants.{variant['id']}.ctrl")
        errors += check_observations(variant.get("observations", []), f"variants.{variant['id']}.observations")
    return [f"{path.name}: {e}" for e in errors]


def load_cases(selection: str = "all") -> list:
    paths = case_paths()
    if selection.lower() != "all":
        paths = [p for p in paths if p.stem.lower() == selection.lower()]
        if not paths:
            known = ", ".join(p.stem for p in case_paths())
            raise CaseError(f"unknown case {selection!r}; known: {known}")
    cases, errors = [], []
    for path in paths:
        case = read_json(path)
        problems = validate_case(case, path)
        errors += problems
        if not problems:
            cases.append(case)
    if errors:
        raise CaseError("\n".join(errors))
    return cases


# ---- runs -----------------------------------------------------------------------------------------------------

@dataclass
class Run:
    case: dict
    install: str
    host: str
    workspace: Path
    variant: Optional[dict] = None

    @property
    def case_id(self) -> str:
        return self.case["id"]

    @property
    def variant_id(self) -> Optional[str]:
        return self.variant["id"] if self.variant else None

    @property
    def segment(self) -> str:
        return f"{self.case_id}.{self.variant_id}" if self.variant else self.case_id

    @property
    def label(self) -> str:
        return f"{self.segment}/{self.install}"

    @property
    def repo(self) -> Path:
        return self.workspace / "repo"

    @property
    def vars(self) -> dict:
        return {**DEFAULT_VARS, **self.case.get("vars", {}), **(self.variant or {}).get("vars", {})}

    @property
    def ctrl_rules(self) -> list:
        return (self.variant or {}).get("ctrl", self.case["ctrl"])

    @property
    def observations(self) -> list:
        return (self.variant or {}).get("observations", self.case["observations"])

    @property
    def flags(self) -> dict:
        return {"timeout_s": DEFAULT_TIMEOUT_S, "permission_mode": None, **self.case["flags"]}

    @property
    def files(self) -> list:
        return self.case["files"].get(self.install, [])


def installs_for(choice: str) -> tuple:
    return INSTALLS if choice == "both" else (choice,)


def plan_runs(cases: list, installs: tuple, host: str, run_root: Path) -> tuple:
    """Return (runs, skipped); skipped is [(case id, install or "-", reason)]."""
    runs, skipped, current_os = [], [], platform.system().lower()
    for case in cases:
        applies = case["applies_to"]
        if host not in applies["hosts"]:
            skipped.append((case["id"], "-", f"host {host} not in {'/'.join(applies['hosts'])}"))
            continue
        if applies.get("os") and current_os not in applies["os"]:
            skipped.append((case["id"], "-", f"os {current_os} not in {'/'.join(applies['os'])}"))
            continue
        for install in installs:
            if install not in applies["installs"]:
                skipped.append((case["id"], install, "install type does not apply"))
                continue
            for variant in case.get("variants") or [None]:
                segment = f"{case['id']}.{variant['id']}" if variant else case["id"]
                runs.append(Run(case, install, host, run_root / segment / install, variant))
    return runs, skipped


def estimate_ceiling(runs: list) -> float:
    return round(sum(float(run.flags["max_budget_usd"]) for run in runs), 2)


def check_budget(dry_run: bool, budget: Optional[float], ceiling: float) -> None:
    if dry_run:
        return
    if budget is None:
        raise GuardError(f"a live run needs --budget-usd (estimated ceiling ${ceiling:.2f}); preview with --dry-run")
    if budget <= 0:
        raise GuardError("--budget-usd must be greater than 0")
    if ceiling > budget:
        raise GuardError(f"estimated ceiling ${ceiling:.2f} exceeds --budget-usd {budget:.2f}; "
                         "narrow --case or --install, or raise the budget")


def ctrl_document(rules: list) -> dict:
    """Case ctrl rules -> the recorder's control file: {"<event>[:<tool>]": {...}}."""
    return {rule["key"]: {k: v for k, v in rule.items() if k != "key"} for rule in rules}


# ---- templates ------------------------------------------------------------------------------------------------

def template_vars(run: Run) -> dict:
    values = run.vars
    base = [str(run.workspace / "bin" / "recorder.py"), "--ctrl", str(run.workspace / "ctrl.json"),
            "--out", str(run.workspace / "out" / "raw")]
    dialect = ["--dialect", values["dialect"]] if values["dialect"] else []
    hook = shlex.join([values["interpreter"] or sys.executable] + base + dialect)
    record = shlex.join([sys.executable] + base)
    return {"HOOK_COMMAND": hook, "RECORD_COMMAND": record,
            "FRONTMATTER_COMMAND_JSON": json.dumps(record + " --event PreToolUse --tag frontmatter"),
            "HOOK_TIMEOUT": values["hook_timeout"], "ON_FAILURE": values["on_failure"],
            "FAIL_CLOSED": values["fail_closed"], "REPO": str(run.repo), "WORKSPACE": str(run.workspace),
            "AGENT_PREFIX": f"{PLUGIN_NAME}:" if run.install == "plugin" else "", "PLUGIN_NAME": PLUGIN_NAME,
            "CASE": run.case_id, "PYTHON": sys.executable,
            "MCP_SERVER": str(run.workspace / MCP_SERVER_DEST.get(run.install, MCP_SERVER_DEST["script"]))}


def substitute(text: str, values: dict, where: str) -> str:
    def replace(match: "re.Match") -> str:
        name = match.group(1)
        if name not in values:
            raise CaseError(f"{where}: unknown template variable {name}")
        return "" if values[name] is None else str(values[name])
    return TOKEN_RE.sub(replace, text)


def render_value(node: object, values: dict, where: str) -> object:
    """A string that is exactly one token takes the variable's JSON type; None drops the key or item."""
    if isinstance(node, str):
        whole = TOKEN_RE.fullmatch(node)
        if whole:
            if whole.group(1) not in values:
                raise CaseError(f"{where}: unknown template variable {whole.group(1)}")
            value = values[whole.group(1)]
            return DROP if value is None else value
        return substitute(node, values, where)
    if isinstance(node, dict):
        rendered = {k: render_value(v, values, where) for k, v in node.items()}
        return {k: v for k, v in rendered.items() if v is not DROP}
    if isinstance(node, list):
        return [v for v in (render_value(item, values, where) for item in node) if v is not DROP]
    return node


def render_template(template: str, values: dict) -> str:
    path = TEMPLATES_DIR / template
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise CaseError(f"cannot read template {template}: {err}") from err
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError as err:
            raise CaseError(f"template {template} is not JSON: {err}") from err
        return json.dumps(render_value(data, values, template), indent=2) + "\n"
    return substitute(text, values, template)


# ---- host commands --------------------------------------------------------------------------------------------

def stimulus(run: Run) -> str:
    return substitute(run.case["stimulus"]["prompt"], template_vars(run), f"{run.case_id}.stimulus")


def host_command(run: Run, dropped: frozenset = frozenset()) -> list:
    """The host CLI call for one run. Flags marked in the README as "verify in T0" are confirmed in P0b's T0."""
    prompt, flags = stimulus(run), run.flags
    if run.host == "cursor":
        return [HOST_BINARIES["cursor"], "-p", prompt]  # Cursor CLI; output-format flag: verify in T0
    if run.host == "codex":
        return [HOST_BINARIES["codex"], "exec", "--json", prompt]
    argv = [HOST_BINARIES["claude"], "-p", prompt, "--model", MODEL, "--max-turns", str(flags["max_turns"])]
    if "--max-budget-usd" not in dropped:
        argv += ["--max-budget-usd", f"{float(flags['max_budget_usd']):.2f}"]
    # --verbose: required with stream-json in print mode on current CLIs (verify in T0)
    argv += ["--output-format", "stream-json", "--verbose"]
    if run.install == "plugin" and "--plugin-dir" not in dropped:
        argv += ["--plugin-dir", str(run.workspace / "probe-plugin")]
    if flags["permission_mode"]:
        argv += ["--permission-mode", flags["permission_mode"]]
    return argv


# ---- actions --------------------------------------------------------------------------------------------------

@dataclass
class Action:
    kind: str
    detail: str
    params: dict = field(default_factory=dict)


def build_actions(run: Run, host_version: str, staging: Path, dropped: frozenset = frozenset()) -> list:
    """Every step of one run, in order. --dry-run prints these; a live run executes them."""
    ws, values = run.workspace, template_vars(run)
    fixture_dest = staging / "fixtures" / f"{run.host}-{safe_version(host_version)}" / run.segment / run.install
    actions = [
        Action("mkdir", f"create {ws}/{{repo,bin,out/raw,out/state}}"),
        Action("git-init", f"git init {run.repo}; commit seed files: {', '.join(SEED_FILES)}"),
        Action("copy", f"copy scripts/probes/recorder.py -> {ws / 'bin' / 'recorder.py'}"),
    ]
    for entry in run.files:
        content = render_template(entry["template"], values)
        actions.append(Action("render", f"render templates/{entry['template']} -> {ws / entry['dest']}",
                              {"dest": entry["dest"], "content": content}))
    ctrl = ctrl_document(run.ctrl_rules)
    actions.append(Action("ctrl", f"write {ws / 'ctrl.json'}: {json.dumps(ctrl, sort_keys=True)}", {"ctrl": ctrl}))
    argv, timeout = host_command(run, dropped), int(run.flags["timeout_s"])
    actions.append(Action("host", f"run in {run.repo} (timeout {timeout}s): {shlex.join(argv)}",
                          {"argv": argv, "timeout": timeout}))
    ids = ", ".join(o["id"] for o in run.observations)
    actions.append(Action("observe", f"evaluate {len(run.observations)} observation(s): {ids}"))
    actions.append(Action("redact", f"redact {ws / 'out' / 'raw'} -> {fixture_dest}/<event>-<n>.json",
                          {"dest": fixture_dest}))
    actions.append(Action("cleanup", f"remove {', '.join(INSTALLED_PATHS)} under {ws}; verify none remain"))
    return actions


@dataclass
class RunState:
    host_version: str
    exit_code: Optional[int] = None
    host_ran: bool = False
    timed_out: bool = False
    evaluated: list = field(default_factory=list)
    status: str = "inconclusive"
    notes: list = field(default_factory=list)
    fixture_ids: list = field(default_factory=list)
    cost_usd: Optional[float] = None
    failures: list = field(default_factory=list)
    cleaned: bool = False


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *GIT_ISOLATION, "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def init_repo(run: Run) -> None:
    run.repo.mkdir(parents=True, exist_ok=True)
    git(run.repo, "init", "-q")
    for rel, content in SEED_FILES.items():
        target = run.repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(run.repo, "add", "-A")
    git(run.repo, "commit", "-q", "-m", "probe seed")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_host(run: Run, action: Action, state: RunState) -> None:
    out_dir = run.workspace / "out"
    env = dict(os.environ, PROBE_CTRL=str(run.workspace / "ctrl.json"), PROBE_OUT=str(out_dir / "raw"))
    with (out_dir / "stream.jsonl").open("w", encoding="utf-8") as stdout, \
            (out_dir / "stderr.txt").open("w", encoding="utf-8") as stderr:
        try:
            done = subprocess.run(action.params["argv"], cwd=str(run.repo), stdout=stdout, stderr=stderr,
                                  stdin=subprocess.DEVNULL, env=env, timeout=action.params["timeout"])
            state.exit_code = done.returncode
        except subprocess.TimeoutExpired:
            state.timed_out = True
            state.notes.append(f"host timed out after {action.params['timeout']}s")
    state.host_ran = True


def read_stream(path: Path) -> list:
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def host_gap(state: RunState) -> Optional[str]:
    """Why this run's capture can't confirm or contradict anything, or None when the host ran to the end."""
    if not state.host_ran:
        return "host not run; inconclusive"
    if state.timed_out:
        return "host timed out; inconclusive"
    return None


def observe_run(run: Run, state: RunState) -> None:
    raw = run.workspace / "out" / "raw"
    records = redact.load_raw_records(raw) if raw.is_dir() else []
    stream = read_stream(run.workspace / "out" / "stream.jsonl")
    ctx = observe.Context(records=records, repo=run.repo, workspace=run.workspace, install=run.install,
                          stream=stream, seeds=SEED_FILES)
    state.evaluated = observe.evaluate(run.observations, ctx)
    state.status, notes = observe.decide_status(state.evaluated, run.case["status_rules"], tuple(run.observations))
    state.notes += notes
    gap = host_gap(state)
    if gap:  # the capture can't speak for the host, whatever the checks say (§3.10)
        state.status = "inconclusive"
        state.notes.append(gap)
    result = observe.last_result(stream)
    cost = (result or {}).get("total_cost_usd")
    state.cost_usd = float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None
    errors = raw / RECORDER_ERRORS
    if errors.is_file():
        state.failures.append(f"{run.label}: recorder errors logged in {errors}")


def redact_run(run: Run, action: Action, state: RunState) -> None:
    raw = run.workspace / "out" / "raw"
    records = redact.load_raw_records(raw) if raw.is_dir() else []
    meta = {"host": run.host, "host_version": state.host_version, "install": run.install, "case": run.case_id,
            "variant": run.variant_id}
    written = redact.write_fixtures(redact.build_fixtures(records, meta, str(run.workspace)), action.params["dest"])
    prefix = f"{run.host}-{safe_version(state.host_version)}/{run.segment}/{run.install}"
    state.fixture_ids = [f"{prefix}/{path.stem}" for path in written]


def worktrees_outside(run: Run) -> list:
    if not (run.repo / ".git").exists():
        return []
    try:
        out = git(run.repo, "worktree", "list", "--porcelain")
    except (OSError, subprocess.CalledProcessError):
        return []
    paths = [Path(line[len("worktree "):]) for line in out.splitlines() if line.startswith("worktree ")]
    return [p for p in paths if not isolation.is_within(p, run.workspace)]


def cleanup_run(run: Run, root: Path, state: RunState) -> None:
    """Remove everything this run installed, then prove it is gone (AC-1)."""
    for rel in INSTALLED_PATHS:
        isolation.safe_remove(run.workspace / rel, root)
    left = isolation.leftovers(run.workspace / rel for rel in INSTALLED_PATHS)
    state.failures += [f"{run.label}: cleanup left {path}" for path in left]
    outside = worktrees_outside(run)
    state.failures += [f"{run.label}: a worktree was created outside the workspace (not removed)" for _ in outside]
    state.cleaned = True


def execute_action(action: Action, run: Run, root: Path, state: RunState) -> None:
    ws = run.workspace
    if action.kind == "mkdir":
        for rel in ("repo", "bin", "out/raw", "out/state"):
            (ws / rel).mkdir(parents=True, exist_ok=True)
    elif action.kind == "git-init":
        init_repo(run)
    elif action.kind == "copy":
        shutil.copy2(str(PROBES_DIR / "recorder.py"), str(ws / "bin" / "recorder.py"))
    elif action.kind == "render":
        write_file(ws / action.params["dest"], action.params["content"])
    elif action.kind == "ctrl":
        write_file(ws / "ctrl.json", json.dumps(action.params["ctrl"], indent=2) + "\n")
    elif action.kind == "host":
        run_host(run, action, state)
    elif action.kind == "observe":
        observe_run(run, state)
    elif action.kind == "redact":
        redact_run(run, action, state)
    elif action.kind == "cleanup":
        cleanup_run(run, root, state)
    else:
        raise HarnessError(f"unknown action kind {action.kind}")


def execute_run(run: Run, actions: list, root: Path, state: RunState, skip: tuple = ()) -> RunState:
    """Run the actions in order; always clean up, and turn harness errors into FAIL lines, not crashes."""
    try:
        for action in actions:
            if action.kind not in skip:
                execute_action(action, run, root, state)
    except (OSError, subprocess.SubprocessError, redact.RedactionError, isolation.IsolationError,
            HarnessError, CaseError) as err:
        state.failures.append(f"{run.label}: {type(err).__name__}: {err}")
        state.status = "inconclusive"
        state.notes.append("harness error; see the run output")
    finally:
        if not state.cleaned and "cleanup" not in skip:
            try:
                cleanup_run(run, root, state)
            except (OSError, isolation.IsolationError) as err:
                state.failures.append(f"{run.label}: cleanup failed: {err}")
    return state


# ---- results --------------------------------------------------------------------------------------------------

def result_entry(run: Run, state: RunState, plugins: Optional[list]) -> dict:
    return {"case": run.case_id, "variant": run.variant_id, "install": run.install, "host": run.host,
            "host_version": state.host_version, "os": os_label(), "status": state.status,
            "observations": state.evaluated, "fixture_ids": state.fixture_ids, "cost_usd": state.cost_usd,
            "plugins_enabled": plugins, "notes": state.notes, "run_at": utc_now()}


def docs_only_entry(run: Run, reason: str) -> dict:
    state = RunState(host_version="not-installed", status="docs-only", notes=[reason + "; docs-only [D]"])
    return result_entry(run, state, None)


def not_run_entry(run: Run, host_version: str, reason: str) -> dict:
    state = RunState(host_version=host_version, notes=[f"not run: {reason}"])
    return result_entry(run, state, None)


def case_requirements() -> dict:
    """{case id: [required case ids]} from the case files' optional `requires` key."""
    found = {}
    for path in case_paths():
        case = read_json(path)
        if isinstance(case, dict) and case.get("requires"):
            found[path.stem] = list(case["requires"])
    return found


def required_status(entries: list, entry: dict, required: str) -> str:
    """The required case's status for the entry's host, host version and install ("not run" when it has none)."""
    same = {e["status"] for e in entries if e["case"] == required and e["install"] == entry["install"]
            and e.get("host") == entry.get("host") and e.get("host_version") == entry.get("host_version")}
    if not same:
        return "not run"
    return same.pop() if len(same) == 1 else "mixed " + "/".join(sorted(same))


def gate_requirements(entries: list, requires: dict) -> list:
    """A confirmed or contradicted entry whose required case isn't confirmed becomes inconclusive (RW-26).

    For example C1-C3 attribute calls with agent_type, which only A1 proves the host sends. Downgrade-only, so it
    repeats until nothing changes and a chain of requirements settles. The input entries aren't modified.
    """
    gated = [dict(entry) for entry in entries]
    changed = True
    while changed:
        changed = False
        for entry in gated:
            if entry["status"] not in DECIDED_STATUSES:
                continue
            statuses = {r: required_status(gated, entry, r) for r in requires.get(entry["case"], ())}
            unmet = {r: s for r, s in statuses.items() if s != "confirmed"}
            if unmet:
                entry["status"] = "inconclusive"
                entry["notes"] = list(entry.get("notes") or []) + [f"requires {r} confirmed ({r} {s})"
                                                                   for r, s in unmet.items()]
                changed = True
    return gated


def result_document(host: str, version: str, entries: list, existing: Optional[dict] = None,
                    requires: Optional[dict] = None) -> dict:
    """Merge entries into a results file; a re-run replaces the same (case, variant, install).

    Then gate `requires` over the result: staging gates one run's entries alone (a required case missing from the
    run leaves its dependents inconclusive), and publishing gates the merged file again, so a later re-run of the
    required case that isn't confirmed also downgrades older dependents.
    """
    key = lambda e: (e["case"], e.get("variant") or "", e["install"])  # noqa: E731
    merged = {key(e): e for e in (existing or {}).get("entries", [])}
    merged.update({key(e): e for e in entries})
    gated = gate_requirements([merged[k] for k in sorted(merged)],
                              case_requirements() if requires is None else requires)
    return {"schema": RESULT_SCHEMA, "host": host, "host_version": version, "generated_at": utc_now(),
            "entries": gated}


def enabled_plugins(plugin_list: Optional[str]) -> Optional[list]:
    """Daedalus plugin names plus a count of others, so private plugin names never reach a committed result."""
    if plugin_list is None:
        return None
    names = sorted(set(PLUGIN_ID_RE.findall(plugin_list)))
    ours = [n for n in names if n.startswith("daedalus")]
    others = len(names) - len(ours)
    return ours + ([f"other:{others}"] if others else [])


# ---- live preflight and loop (never called by --dry-run or by the tests) --------------------------------------

def preflight_output(argv: list) -> Optional[str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=PREFLIGHT_TIMEOUT_S,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout + done.stderr if done.returncode == 0 else None


def host_version(binary: str) -> str:
    match = VERSION_RE.search(preflight_output([binary, "--version"]) or "")
    return match.group(0) if match else "unknown"


def dropped_flags(host: str, help_text: str) -> frozenset:
    missing = [flag for flag in REQUIRED_FLAGS.get(host, ()) if flag not in help_text]
    if missing:
        raise GuardError(f"BLOCKED (env): `{HOST_BINARIES[host]} --help` lacks {', '.join(missing)}")
    return frozenset(flag for flag in OPTIONAL_FLAGS.get(host, {}) if flag not in help_text)


def plugin_list_text(host: str) -> Optional[str]:
    if host != "claude":
        return None
    return preflight_output([HOST_BINARIES["claude"], "plugin", "list"])  # verify in T0


def publish(staging: Path, host: str, version: str) -> list:
    """Copy staged fixtures and results into the hub (only after the isolation check and the leak scan)."""
    written = []
    prefix = f"{host}-{safe_version(version)}"
    src_root = staging / "fixtures" / prefix
    for src in sorted(p for p in src_root.glob("*/*") if p.is_dir()):
        dest = FIXTURES_DIR / prefix / src.relative_to(src_root)
        if not isolation.is_within(dest, FIXTURES_DIR):
            raise HarnessError(f"refusing to publish outside fixtures/: {dest}")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(str(src), str(dest))
        written.append(str(dest))
    staged_results = staging / "results" / f"{prefix}.json"
    if staged_results.is_file():
        target = RESULTS_DIR / f"{prefix}.json"
        existing = read_json(target) if target.is_file() else None
        doc = result_document(host, version, read_json(staged_results)["entries"], existing)
        write_file(target, json.dumps(doc, indent=2) + "\n")
        written.append(str(target))
    return written


def stage_results(staging: Path, host: str, version: str, entries: list) -> Path:
    target = staging / "results" / f"{host}-{safe_version(version)}.json"
    write_file(target, json.dumps(result_document(host, version, entries), indent=2) + "\n")
    return target


def finish(staging: Path, host: str, version: str, entries: list, before: Optional[dict],
           failures: list, say: Callable) -> int:
    """Isolation check, leak scan, then publish. Any problem is a FAIL and nothing reaches the hub."""
    stage_results(staging, host, version, entries)
    diffs = isolation.compare(before, isolation.snapshot(HUB, Path.home(), plugin_list_text(host))) if before else []
    leaks = redact.scan_paths([staging])
    for line in failures + diffs:
        say(f"FAIL {line}")
    for where, kind in leaks:
        say(f"FAIL redaction leak ({kind}) in {Path(where.split(':', 1)[0]).name}")
    if failures or diffs or leaks:
        say(f"nothing published; raw and staged output kept under {staging.parent}")
        return 1
    for path in publish(staging, host, version):
        say(f"published {Path(path).relative_to(HUB)}")
    return 0


def run_live(runs: list, host: str, budget: float, run_root: Path, say: Callable = print) -> int:
    binary, staging = HOST_BINARIES[host], run_root / "staged"
    if shutil.which(binary) is None:
        if host == "claude":
            say("BLOCKED (env): the claude CLI is not on PATH")
            return 2
        entries = [docs_only_entry(run, f"{binary} CLI not installed") for run in runs]
        return finish(staging, host, "not-installed", entries, None, [], say)
    version = host_version(binary)
    try:
        dropped = dropped_flags(host, preflight_output([binary, "--help"]) or "") if host == "claude" else frozenset()
    except GuardError as err:
        say(str(err))
        return 2
    plugin_list = plugin_list_text(host)
    before = isolation.snapshot(HUB, Path.home(), plugin_list)
    entries: list = []
    failures: list = []
    finished = False
    try:
        run_all(runs, version, dropped, budget, staging, enabled_plugins(plugin_list), entries, failures, say)
        finished = True
    except KeyboardInterrupt:
        failures.append("interrupted by the user; the remaining runs were skipped")
        finished = True
    finally:
        if not finished:  # an unexpected error is propagating: still check isolation, publish nothing
            failures.append("the harness crashed; see the traceback")
            finish(staging, host, version, entries, before, failures, say)
    return finish(staging, host, version, entries, before, failures, say)


def run_all(runs: list, version: str, dropped: frozenset, budget: float, staging: Path, plugins: Optional[list],
            entries: list, failures: list, say: Callable) -> None:
    """The live loop; appends to entries and failures so the caller keeps them even if a run raises."""
    spent = 0.0
    for run in runs:
        cap = float(run.flags["max_budget_usd"])
        if spent + cap > budget:
            entries.append(not_run_entry(run, version, "budget exhausted"))
            continue
        state = RunState(host_version=version, notes=[f"{flag} missing: {OPTIONAL_FLAGS[run.host][flag]}"
                                                      for flag in sorted(dropped)])
        skip = ("host",) if run.install == "plugin" and "--plugin-dir" in dropped else ()
        say(f"run {run.label}")
        try:
            actions = build_actions(run, version, staging, dropped)
        except CaseError as err:
            failures.append(f"{run.label}: {err}")
            continue
        execute_run(run, actions, probe_root(), state, skip)
        spent += state.cost_usd if state.cost_usd is not None else cap
        failures += state.failures
        entries.append(result_entry(run, state, plugins))
        cost = f"${state.cost_usd:.2f}" if state.cost_usd is not None else "unknown"
        say(f"  {state.status}  cost {cost}  total ${spent:.2f} of ${budget:.2f}")
