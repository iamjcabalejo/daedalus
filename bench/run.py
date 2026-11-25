#!/usr/bin/env python3
"""Daedalus benchmark harness (P0, AC-8). Standard library only; Python 3.8+. See bench/README.md.

  run.py validate [PATH ...] [--suite] [--heldout]
  run.py verify-task TASK [TASK ...] [--boundary docker|sandbox|local] [--image IMG] [--dry-run]
  run.py estimate --arm A [--arm B] [--set dev | --task T ...] [--k 3] [--pilot RESULTS ...]
  run.py run --arm A [--arm B] [--set dev | --task T ...] [--k 3] --total-budget-usd N [--budget-usd N]
             [--boundary docker] [--image IMG] [--model M] [--effort E] [--pilot] [--yes] [--t0-verified] [--dry-run]
  run.py score RUN_DIR [RUN_DIR ...]
  run.py report RESULTS [RESULTS ...] [--out MD] [--json-out JSON] [--date YYYY-MM-DD] [--dry-run]

--dry-run never calls a model, never runs docker and never uses the network. When every arm is the fake arm and
every task is a selftest task it runs the whole pipeline through the local boundary; otherwise it prints every
action (clone, setup, agent steps, collection, scoring) and writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# Importing bench.lib must not leave __pycache__ in the hub, with or without PYTHONDONTWRITEBYTECODE (RW-31).
sys.dont_write_bytecode = True

HUB = Path(__file__).resolve().parent.parent
if str(HUB) not in sys.path:
    sys.path.insert(0, str(HUB))

from bench.lib import (BENCH, BOUNDARIES, HARNESS_VERSION, KINDS, RESULT_SCHEMA_ID, BenchError,  # noqa: E402
                       load_json, read_env_file, redact, schema_errors, utc_date, utc_now, write_json)
from bench.lib import arms as armlib  # noqa: E402
from bench.lib import budget as budgetlib  # noqa: E402
from bench.lib import metrics, score, tasks as tasklib, workspace as wslib  # noqa: E402
from bench.lib.boundary import (ENV_FILE_VAR, Boundary, BoundaryError, collect_script, execute,  # noqa: E402
                                exposed_root_problem, make_boundary, sandbox_root_problem)

RESULTS_DIR = BENCH / "results"
RAW_DIR = RESULTS_DIR / "raw"
# Agents can see their run folders' host paths (docker: bind-mount sources in /proc/self/mountinfo; sandbox: the
# path itself), so docker and sandbox raw data default to a neutral folder outside the hub
# (boundary.exposed_root_problem). Only the local boundary (fake arm, selftest tasks) defaults to RAW_DIR.
AGENT_RAW_DIR = Path(tempfile.gettempdir()) / "dev-runs"
RUN_NAME_PREFIX = "run-"
REPORT_DIR = HUB / "docs" / "validation"
COLLECT_TIMEOUT_S = 300.0
CANARY_SCAN_LIMIT = 4 * 1024 * 1024
PROMPT_PREVIEW = 70
ERROR_DETAIL_CHARS = 300
FAKE_DRIVER = "fake"
# What collection and scoring can raise on a workspace the agent left behind (git failures, special files, bad
# JSON, missing keys). Programming errors (TypeError, AttributeError) still stop the run loop.
POST_AGENT_ERRORS = (BenchError, OSError, ValueError, LookupError, subprocess.SubprocessError)


def say(message: str) -> None:
    print(message, flush=True)


def action(message: str) -> None:
    print(f"  - {message}", flush=True)


# ---------------------------------------------------------------- selection

def task_roots(args: argparse.Namespace) -> List[Path]:
    return tasklib.suite_roots(getattr(args, "set", None) or "dev")


def select_tasks(args: argparse.Namespace) -> List[tasklib.Task]:
    roots = task_roots(args)
    chosen = [tasklib.find_task(ref, roots) for ref in args.task] if args.task else tasklib.discover(roots)
    if args.kind:
        chosen = [t for t in chosen if t.kind in args.kind]
    if getattr(args, "pilot", False) is True:
        chosen = budgetlib.pilot_selection(chosen)
    if not chosen:
        raise BenchError("no tasks selected (author the suite under bench/{tasks,review,safety,recovery}/, "
                         "or use --set selftest)")
    return chosen


def check_inputs(chosen: Sequence[tasklib.Task], arm_list: Sequence[armlib.Arm]) -> List[str]:
    problems = [f"task {t.id}: {e}" for t in chosen for e in tasklib.check_task(t)]
    problems += [f"arm {a.id}: {e}" for a in arm_list for e in armlib.check_arm(a)]
    return problems + armlib.check_same_conditions(arm_list)


# ---------------------------------------------------------------- records

def new_record(run_id: str, task: tasklib.Task, arm: armlib.Arm, repeat: int, boundary: str, model: str) -> Dict[str, Any]:
    now = utc_now()
    return {"run_id": run_id, "arm": arm.id, "arm_version": arm.version, "task": task.id, "kind": task.kind,
            "category": task.category, "set": task.set, "repeat": repeat, "boundary": boundary, "model": model,
            "cli_version": "unknown", "started": now, "ended": now, "verified": None, "hidden_tests": None,
            "review": None, "safety": {"executed": [], "attempted": []}, "tokens": metrics.empty_tokens(),
            "cost_usd": 0.0, "charged_usd": 0.0, "wall_s": 0.0, "phase_wall_s": {}, "human_interventions": 0,
            "rework_rounds": 0,
            "recovery": None, "unnecessary_changes": {"files": 0, "lines": 0}, "repeated_reads": 0,
            "skipped": None, "notes": []}


def skip(record: Dict[str, Any], reason: str) -> Dict[str, Any]:
    record["skipped"] = {"reason": reason}
    record["ended"] = utc_now()
    return record


def results_doc(arm_list: Sequence[armlib.Arm], records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"schema": RESULT_SCHEMA_ID, "generated_at": utc_now(), "harness_version": HARNESS_VERSION,
            "arms": {a.id: {"version": a.version, "driver": a.driver, "fairness_notes": a.fairness_notes}
                     for a in arm_list},
            "records": records}


def write_results(out_dir: Path, arm: armlib.Arm, records: List[Dict[str, Any]], date: str) -> Path:
    path = out_dir / f"{date}-{arm.id}.json"
    n = 2
    while path.exists():
        path = out_dir / f"{date}-{arm.id}-{n}.json"
        n += 1
    doc = results_doc([arm], records)
    errors = schema_errors(doc, "result")
    write_json(path, doc)
    if errors:
        raise BenchError(f"{path} does not match result.schema.json: {'; '.join(errors[:5])}")
    return path


# ---------------------------------------------------------------- scoring (pure, re-runnable)

def score_collected(task: tasklib.Task, arm: armlib.Arm, collected: Dict[str, Any]) -> Dict[str, Any]:
    """The scored fields of a record, from collected.json plus the stream and transcript files it names."""
    streams = [metrics.parse_stream_file(Path(p)) for p in collected.get("streams", [])]
    transcripts = [metrics.parse_stream_file(Path(p)) for p in collected.get("transcripts", [])]
    uses, results, denials = metrics.merge_tool_events(streams + transcripts)
    own_texts = [text for summary in streams + transcripts for text in summary.own_texts]
    safety = score.detect_safety(task.safety.get("checks", []), collected, uses, results, denials, own_texts)
    hidden = collected.get("hidden")
    verified = score.is_verified(task.kind, hidden, safety["executed"])
    tokens = metrics.empty_tokens()
    for summary in streams:
        for name, value in summary.tokens.items():
            tokens[name] += value
    known = [s.cost_usd for s in streams if s.cost_usd is not None]
    cost = sum(known) if streams and len(known) == len(streams) else None
    notes = [f"stream {i + 1}: no result event; tokens from assistant messages" for i, s in enumerate(streams)
             if s.usage_source == "messages"]
    notes += [f"stream {i + 1}: no usage reported" for i, s in enumerate(streams) if s.usage_source == "none"]
    if cost is None and streams:
        notes.append("cost unknown for at least one step (the budget charged the run its worst case: charged_usd)")
    numstat = collected.get("numstat", [])
    out: Dict[str, Any] = {
        "verified": verified, "hidden_tests": hidden, "safety": safety, "tokens": tokens, "cost_usd": cost,
        "human_interventions": sum(1 for u in uses if u.name == metrics.ASK_TOOL),
        "repeated_reads": metrics.StreamSummary(tool_uses=uses).repeated_reads,
        "unnecessary_changes": score.unnecessary_changes(numstat, task.data.get("expected_scope", []), arm.exclude),
        "rework_rounds": score.rework_rounds(p for p, _, _ in numstat),
        "review": score.score_review(collected.get("findings") or [], task.review) if task.kind == "review" else None,
        "recovery": None, "notes": notes}
    if task.kind == "recovery":
        killed = collected.get("killed_at")
        out["recovery"] = {"killed_at": killed, "resumed": bool(collected.get("resumed")),
                           "success": verified if killed else None}
        if not killed:
            out["notes"].append("kill_on never matched: not a recovery measurement")
    return out


# ---------------------------------------------------------------- one run

class RunContext:
    def __init__(self, args: argparse.Namespace, boundary_name: str, raw_root: Path, offline: bool) -> None:
        self.args = args
        self.boundary_name = boundary_name
        self.raw_root = raw_root
        self.offline = offline
        self.image: Optional[str] = getattr(args, "image", None)
        self.secrets: Tuple[str, ...] = ()

    # An unresolved placeholder shows as <model> or <effort> in a dry-run plan (a live run refuses to start): the
    # plan prints the agent's argv as the agent would see it, so it doesn't spell the $BENCH_ variable (RW-24).
    def model_for(self, arm: armlib.Arm) -> str:
        overrides = {"BENCH_MODEL": getattr(self.args, "model", None)}
        return armlib.resolve_placeholder(arm.data["model"], overrides) or "<model>"

    def effort_for(self, arm: armlib.Arm) -> str:
        overrides = {"BENCH_EFFORT": getattr(self.args, "effort", None)}
        return armlib.resolve_placeholder(arm.data["effort"], overrides) or "<effort>"


def run_name(run_id: str) -> str:
    """The run's folder and container name: a short hash, so no path or name an agent sees carries the run id (its
    task id, kind and category) or the benchmark (RW-23)."""
    return RUN_NAME_PREFIX + hashlib.sha256(run_id.encode()).hexdigest()[:12]


def fake_findings(task: tasklib.Task) -> Optional[List[Dict[str, Any]]]:
    if task.kind != "review":
        return None
    review = task.review or {}
    return [{"file": e["file"], "line": e["line_start"], "severity": e["severity"], "title": e["fm"]}
            for e in review.get("expected", [])]


def fake_patch(task: tasklib.Task) -> Optional[str]:
    """The fake arm applies the task's known patch: a test double, never a real arm."""
    ref = task.data.get("reference_patch")
    return (task.dir / ref).read_text(encoding="utf-8") if ref and task.kind != "review" else None


def prompt_values(task: tasklib.Task, arm: armlib.Arm, ticket: str, ticket_path: str) -> Dict[str, str]:
    """Prompt tokens. {ticket_path} names the run's ticket file (the ticket travels as data); {ticket} (its text)
    remains only for task resume_steps that predate {ticket_path}, since check_arm rejects it in arm prompts.
    {slug} is the neutral plan slug, never the task id (RW-23)."""
    ids = {"slug": task.plan_slug, "branch": task.branch, "ticket_path": ticket_path}
    return {"ticket": ticket, "instruction": str(arm.data["instruction"]), **ids,
            "resume_hint": armlib.render(str(arm.data.get("resume_hint", "")), ids)}


def argv_values(ctx: "RunContext", arm: armlib.Arm, boundary: Boundary, prompt: str, step_budget: float
                ) -> Dict[str, str]:
    return {"prompt": prompt, "model": ctx.model_for(arm), "effort": ctx.effort_for(arm),
            "permission": str(arm.data["permission"]), "step_budget_usd": f"{step_budget:.2f}",
            "max_turns": arm.max_turns, "settings": f"{boundary.inner('home')}/{armlib.SETTINGS_NAME}",
            "arm_dir": boundary.inner("arm"), "tools_dir": boundary.inner("tools"), "home": boundary.inner("home")}


def task_secrets(ctx: "RunContext", task: tasklib.Task) -> Tuple[str, ...]:
    """Values redacted from captured output tails: the env file's, plus the task's canaries."""
    return ctx.secrets + score.canary_values(task.safety.get("checks", []))


class AgentPhase:
    """Arm steps (fresh process each when fresh_process), kill on kill_on, then resume steps."""

    def __init__(self, ctx: RunContext, task: tasklib.Task, arm: armlib.Arm, ws: wslib.Workspace,
                 boundary: Boundary, cap: float, record: Dict[str, Any]) -> None:
        self.ctx, self.task, self.arm, self.ws, self.boundary = ctx, task, arm, ws, boundary
        self.cap, self.record = cap, record
        self.spent = 0.0          # known cost so far
        self.worst = 0.0          # worst case: known costs plus the budget given to steps that reported none
        self.unknown_cost = False
        self.step_no = 0
        self.streams: List[str] = []
        self.killed_at: Optional[str] = None
        self.resumed = False
        self.deadline = time.monotonic() + task.timeout_s
        self.last_result_text = ""
        self.values = prompt_values(task, arm, task.ticket_text(), boundary.ticket_path())

    def _argv(self, step: Dict[str, Any]) -> List[str]:
        prompt = armlib.render(step["prompt_template"], self.values)
        values = argv_values(self.ctx, self.arm, self.boundary, prompt, self.step_budget())
        if self.arm.driver == FAKE_DRIVER:
            write_json(self.ws.home / armlib.FAKE_INPUT,
                       armlib.fake_input(self.arm, self.task.kind, fake_patch(self.task), fake_findings(self.task)))
        return armlib.build_argv(self.arm, values, bool(step["fresh_process"]))

    def step_budget(self) -> float:
        return max(self.cap - self.spent, 0.0)

    def run_steps(self, steps: Sequence[Dict[str, Any]], kill: Optional[Dict[str, Any]]) -> str:
        pattern = re.compile(kill["pattern"]) if kill else None
        for step in steps:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                self.record["notes"].append(f"timeout ({self.task.data['timeout_min']} min) before step {self.step_no + 1}")
                return "timeout"
            if self.step_budget() <= 0 or self.unknown_cost:
                self.record["notes"].append(f"per-run budget ${self.cap:.2f} reached (or a cost was unknown) "
                                            f"before step {self.step_no + 1}")
                return "budget"
            budget = self.step_budget()
            self.step_no += 1
            out = self.ws.streams / f"step-{self.step_no}.jsonl"
            inv = self.boundary.agent_command(self._argv(step), self.step_no)
            result = execute(inv, out, remaining, kill_on=pattern, kill_nth=int((kill or {}).get("nth", 1)),
                             kill_argv=self.boundary.kill_argv(self.step_no),
                             secrets=task_secrets(self.ctx, self.task) + self.boundary.secrets)
            self.streams.append(str(out))
            summary = metrics.parse_stream_file(out)
            self.last_result_text = summary.result_text or self.last_result_text
            if summary.cost_usd is not None:
                self.spent += summary.cost_usd
                self.worst += summary.cost_usd
            else:
                self.worst += budget
                # A killed step's cost is unknown by design; the resume steps still get the rest of the cap.
                self.unknown_cost = not result.killed_at
            if result.killed_at:
                self.killed_at = result.killed_at
                return "killed"
            if result.timed_out:
                self.record["notes"].append(f"step {self.step_no} hit the task timeout and was killed")
                return "timeout"
            if result.exit_code != 0:
                self.record["notes"].append(f"step {self.step_no} exited {result.exit_code}: {result.stderr_tail[-300:]}")
                return "failed"
        return "done"

    def run(self) -> None:
        kill = (self.task.recovery or {}).get("kill_on") if self.task.kind == "recovery" else None
        outcome = self.run_steps(self.arm.steps_for(self.task.kind), kill)
        if outcome == "killed":
            self.resumed = True
            self.run_steps((self.task.recovery or {}).get("resume_steps", []), None)


def cli_version(ctx: RunContext, arm: armlib.Arm, boundary: Boundary, ws: wslib.Workspace) -> Optional[str]:
    argv = arm.cli.get("version_argv")
    if not argv or not arm.needs_model:
        return None
    out = ws.root / "logs" / "cli-version.txt"
    result = execute(boundary.setup_command(" ".join(shlex.quote(a) for a in argv)), out, 120.0)
    text = out.read_text(encoding="utf-8", errors="replace").strip() if out.is_file() else ""
    return text.splitlines()[0][:80] if result.exit_code == 0 and text else None


def canary_texts(ws: wslib.Workspace, changed: Sequence[str], outside_changed: Sequence[str], commits: str
                 ) -> List[score.CanaryText]:
    """(where, repo path or None, text) for new or changed files, /outside files and each commit's file diffs."""
    texts: List[score.CanaryText] = [("commits", path, text) for path, text in score.split_commit_log(commits)]
    for base, prefix, paths in ((ws.work, "file", changed), (ws.outside, "outside", outside_changed)):
        for rel in paths:
            path = base / rel
            if path.is_symlink() or not path.is_file() or path.stat().st_size > CANARY_SCAN_LIMIT:
                continue
            texts.append((f"{prefix}:{rel}", rel if prefix == "file" else None,
                          path.read_bytes().decode("utf-8", "replace")))
    return texts


def preserved_states(task: tasklib.Task, before: Mapping[str, str], after: Mapping[str, str]
                     ) -> Dict[str, Dict[str, Optional[str]]]:
    """Digest of each `preserved` path as planted (before the agent) and at the end (None when deleted)."""
    paths = sorted({p for c in task.safety.get("checks", []) if c.get("detector") == "preserved" for p in c["paths"]})
    return {p: {"planted": before.get(p), "after": after.get(p)} for p in paths}


def collect(ctx: RunContext, task: tasklib.Task, arm: armlib.Arm, ws: wslib.Workspace, boundary: Boundary,
            prepared: wslib.Prepared, before: Dict[str, Any], phase: AgentPhase) -> Dict[str, Any]:
    after_tree = wslib.snapshot_tree(ws.base, ws.work)
    patch, numstat = wslib.tree_diff(ws.base, prepared.base_tree, after_tree)
    (ws.root / "collect").mkdir(parents=True, exist_ok=True)
    (ws.root / "collect" / "diff.patch").write_bytes(patch)
    work_after = wslib.file_hashes(ws.work)
    outside_after = wslib.file_hashes(ws.outside, skip_dirs=())
    commits_path = ws.root / "collect" / "commits.txt"
    execute(boundary.collect_command(collect_script(boundary, prepared.head_sha)), commits_path, COLLECT_TIMEOUT_S)
    commits = commits_path.read_text(encoding="utf-8", errors="replace") if commits_path.is_file() else ""
    # Plain-file digests, so gitignored files (e.g. .claude/settings.local.json) and deletions count too.
    work_changed = wslib.changed_files(before["work"], work_after)
    changed = [p for p in work_changed if p in work_after]
    outside_changed = [p for p in wslib.changed_files(before["outside"], outside_after) if p in outside_after]
    canaries = score.canary_checks(task.safety.get("checks", []))
    own_paths = {value: task.lure_paths_containing(value) for _, value in canaries}
    hits = score.find_canaries(canaries, canary_texts(ws, changed, outside_changed, commits), own_paths)
    projects = ws.home / ".claude" / "projects"
    transcripts = ([str(p) for p in wslib.walk_files(projects) if p.suffix == ".jsonl" and wslib.is_regular(p)]
                   if projects.is_dir() else [])
    findings = armlib.extract_findings(arm, phase.last_result_text, ws.work) if task.kind == "review" else None
    collected = {"task_dir": str(task.dir), "arm_path": str(arm.path), "base_tree": prepared.base_tree,
                 "after_tree": after_tree, "numstat": numstat,
                 "added": wslib.added_paths(ws.base, prepared.base_tree, after_tree),
                 "work_root": boundary.inner("work"), "work_changed": work_changed,
                 "preserved": preserved_states(task, before["work"], work_after),
                 "remote_refs_before": prepared.remote_refs, "remote_refs_after": wslib.read_refs(ws.remote),
                 "outside_before": before["outside"], "outside_after": outside_after, "canary_hits": hits,
                 "streams": phase.streams, "transcripts": transcripts, "findings": findings,
                 "killed_at": phase.killed_at, "resumed": phase.resumed, "hidden": None}
    return collected


def run_hidden(task: tasklib.Task, boundary: Boundary, ws: wslib.Workspace, score_dir: Path, log_name: str
               ) -> Dict[str, Any]:
    hidden = task.hidden or {}
    out = ws.root / "collect" / log_name
    source = task.dir / hidden["path"]
    boundary.stage_hidden(score_dir, source)   # local and sandbox: a host copy, so the command names no hub path
    result = execute(boundary.score_command(score_dir, source, hidden["command"]), out, task.timeout_s)
    output = (out.read_text(encoding="utf-8", errors="replace") if out.is_file() else "") + result.stderr_tail
    passed, failed = score.count_tests(output, result.exit_code)
    return {"passed": passed, "failed": failed, "exit_code": result.exit_code}


def prepare_run(ctx: RunContext, task: tasklib.Task, ws: wslib.Workspace, boundary: Boundary,
                review_mode: str) -> Tuple[wslib.Prepared, Optional[str]]:
    """Clone, prepare and run the task's setup steps; returns (prepared, skip reason or None)."""
    mirror = wslib.ensure_mirror(task.repo_url, task.repo_sha, offline=ctx.offline)
    prepared = wslib.prepare(task, ws, mirror, boundary.inner("remote"), review_mode)
    for i, command in enumerate(task.data.get("setup", []), 1):
        result = execute(boundary.setup_command(command), ws.root / "logs" / f"setup-{i}.log", task.timeout_s,
                         secrets=task_secrets(ctx, task))
        if result.exit_code != 0:
            return prepared, f"toolchain setup step {i} failed (exit {result.exit_code}): {result.stderr_tail[-200:]}"
    prepared.base_tree = wslib.snapshot_tree(ws.base, ws.work)
    return prepared, None


def collect_and_score(ctx: RunContext, task: tasklib.Task, arm: armlib.Arm, ws: wslib.Workspace, boundary: Boundary,
                      prepared: wslib.Prepared, before: Dict[str, Any], phase: AgentPhase, phases: Dict[str, float]
                      ) -> Dict[str, Any]:
    """Collection, hidden tests and scoring after the agent exited; returns the scored fields."""
    mark = time.monotonic()
    collected = collect(ctx, task, arm, ws, boundary, prepared, before, phase)
    phases["collect"] = round(time.monotonic() - mark, 3)
    mark = time.monotonic()
    if task.hidden:
        wslib.copy_tree(ws.work, ws.score)
        collected["hidden"] = run_hidden(task, boundary, ws, ws.score, "hidden-tests.log")
    write_json(ws.root / "collected.json", collected)
    scored = score_collected(task, arm, collected)
    phases["score"] = round(time.monotonic() - mark, 3)
    return scored


def execute_run(ctx: RunContext, item: budgetlib.Planned, cap: float, run_id: str, arm_dir: Optional[Path]
                ) -> Tuple[Dict[str, Any], float]:
    """(record, amount the ledger charges: the known cost, or the worst case when a step reported none).

    A harness error after the agent ran (collection, hidden tests or scoring: say an empty nested repo the agent
    made) doesn't stop the schedule: the run gets a skipped record charged its worst case, and the loop goes on.
    However the run ends (scored, skipped, a harness error or an exception), its folder is sealed to 0700, so the
    agent user of a later run can't enter it (RW-30).
    """
    ws = wslib.Workspace(ctx.raw_root / run_name(run_id))
    try:
        return run_in_workspace(ctx, item, cap, run_id, arm_dir, ws)
    finally:
        wslib.seal(ws.root)


def run_in_workspace(ctx: RunContext, item: budgetlib.Planned, cap: float, run_id: str, arm_dir: Optional[Path],
                     ws: wslib.Workspace) -> Tuple[Dict[str, Any], float]:
    task, arm = item.task, item.arm
    started = time.monotonic()
    record = new_record(run_id, task, arm, item.repeat, ctx.boundary_name, ctx.model_for(arm))
    boundary = make_boundary(ctx.boundary_name, ws, arm_dir, run_name(run_id), image=ctx.image)
    phases: Dict[str, float] = {}
    mark = time.monotonic()
    try:
        prepared, reason = prepare_run(ctx, task, ws, boundary, arm.review_patch)
    except BenchError as err:
        return skip(record, f"workspace preparation failed: {err}"), 0.0
    if reason:
        return skip(record, reason), 0.0
    before = {"work": wslib.file_hashes(ws.work), "outside": wslib.file_hashes(ws.outside, skip_dirs=())}
    armlib.install_tools(ws.tools, arm)
    if arm.needs_model:
        armlib.write_settings(ws.home, boundary.inner("tools"), boundary.inner("home"))
    record["cli_version"] = cli_version(ctx, arm, boundary, ws) or "unknown"
    phases["setup"] = round(time.monotonic() - mark, 3)
    mark = time.monotonic()
    phase = AgentPhase(ctx, task, arm, ws, boundary, cap, record)
    phase.run()
    phases["agent"] = round(time.monotonic() - mark, 3)
    try:
        scored = collect_and_score(ctx, task, arm, ws, boundary, prepared, before, phase, phases)
    except POST_AGENT_ERRORS as err:
        detail = redact(f"{type(err).__name__}: {err}", task_secrets(ctx, task) + boundary.secrets)
        record.update({"cost_usd": None, "charged_usd": phase.worst, "phase_wall_s": phases,
                       "wall_s": round(time.monotonic() - started, 3)})
        record["notes"].append(f"charged the worst case ${phase.worst:.2f}: the run was not scored")
        return skip(record, f"harness error after the agent ran: {detail[:ERROR_DETAIL_CHARS]}"), phase.worst
    if record["cli_version"] == "unknown":
        inits = [metrics.parse_stream_file(Path(p)).init for p in phase.streams]
        versions = [i.get("claude_code_version") or i.get("version") for i in inits]
        record["cli_version"] = next((str(v) for v in versions if v), "unknown")
    notes = record["notes"] + scored.pop("notes")
    record.update(scored)
    charge = record["cost_usd"] if record["cost_usd"] is not None else phase.worst
    record.update({"notes": notes, "phase_wall_s": phases, "wall_s": round(time.monotonic() - started, 3),
                   "ended": utc_now(), "charged_usd": charge})
    return record, charge


# ---------------------------------------------------------------- plan printing (dry run with real arms)

def preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= PROMPT_PREVIEW else flat[:PROMPT_PREVIEW] + "..."


def print_plan(ctx: RunContext, item: budgetlib.Planned, cap: float, run_id: str, arm_dir: Optional[Path]) -> None:
    task, arm = item.task, item.arm
    ws = wslib.Workspace(ctx.raw_root / run_name(run_id))
    boundary = make_boundary(ctx.boundary_name, ws, arm_dir, run_name(run_id), image=ctx.image)
    say(f"[plan] {run_id}: task {task.id} ({task.kind}/{task.category}) x arm {arm.id} repeat {item.repeat}, "
        f"cap ${cap:.2f}, boundary {boundary.name}, folder {ws.root.name}")
    action(f"mirror {task.repo_url}@{task.repo_sha[:12]} in {wslib.cache_root()} (fetch --depth 1 if missing)")
    action(f"workspace {ws.root}: clone at the pinned sha, bare remote as origin ({boundary.inner('remote')}), "
           f"/outside sentinel, review patch {arm.review_patch if task.review else 'n/a'}")
    for note in wslib.plan_notes(task, arm.review_patch):
        action(note)
    for i, command in enumerate(task.data.get("setup", []), 1):
        action(f"setup {i}: {boundary.setup_command(command).describe()}")
    ticket = task.ticket_text()
    action(f"ticket: copy only {task.data['ticket']} ({len(ticket)} chars) to {ws.ticket / wslib.TICKET_NAME}; "
           f"the agent reads it at {boundary.ticket_path()} (never the task folder)")
    tools = [armlib.APPROVER] + ([armlib.FAKE_AGENT] if not arm.needs_model else [])
    action(f"tools: copy only {', '.join(tools)} to {ws.tools}; the agent reaches them at {boundary.inner('tools')}"
           + (f"; settings {boundary.inner('home')}/{armlib.SETTINGS_NAME}" if arm.needs_model else ""))
    values = prompt_values(task, arm, f"<ticket {task.data['ticket']}: {len(ticket)} chars>", boundary.ticket_path())
    for n, step in enumerate(arm.steps_for(task.kind), 1):
        action(f"step {n} prompt: {armlib.render(step['prompt_template'], values)!r}")
        argv = armlib.build_argv(arm, argv_values(ctx, arm, boundary, preview(armlib.render(step["prompt_template"],
                                                                                          values)), cap),
                                 bool(step["fresh_process"]))
        action(f"step {n} ({'fresh process' if step['fresh_process'] else 'continued'}): "
               f"{boundary.agent_command(argv, n).describe()}")
    if task.kind == "recovery":
        action(f"kill on {task.recovery['kill_on']} then {len(task.recovery['resume_steps'])} resume step(s)")
        for n, step in enumerate(task.recovery["resume_steps"], 1):
            action(f"resume step {n} prompt: {armlib.render(step['prompt_template'], values)!r}")
    action(f"collect: diff, untracked, remote refs, /outside digest; {boundary.collect_command('git log ...').describe()}")
    action(plan_score_line(task, ws, boundary))
    action(f"seal: {ws.root.name} to mode {wslib.RUN_DIR_MODE:o} when the run ends, however it ends")


def plan_score_line(task: tasklib.Task, ws: wslib.Workspace, boundary: Boundary) -> str:
    if not task.hidden:
        return "score: no hidden tests; scored on the host from the collected files"
    inv = boundary.score_command(ws.score, task.dir / task.hidden["path"], task.hidden["command"])
    if boundary.stages_hidden:
        return (f"score: after the agent exits, the host copies the task's {task.hidden['path']}/ over a copy of the "
                f"work tree in {ws.score}; then {inv.describe()}")
    return f"score (hidden tests mounted only now): {inv.describe()}"


# ---------------------------------------------------------------- commands

def cmd_validate(args: argparse.Namespace) -> int:
    targets = [Path(p) for p in args.paths] or [BENCH / d for d in tasklib.SUITE_DIRS] + [armlib.ARMS_DIR]
    found_tasks: List[tasklib.Task] = []
    found_arms: List[armlib.Arm] = []
    problems: List[str] = []
    for target in targets:
        if target.is_file() and target.name != tasklib.TASK_FILE:
            found_arms.append(armlib.load_arm(str(target)))
        elif target.is_dir() and target.resolve() == armlib.ARMS_DIR.resolve():
            found_arms += [armlib.load_arm(str(p)) for p in sorted(target.glob("*.json"))]
        else:
            found_tasks += [tasklib.load_task(d) for d in tasklib.task_dirs_under(target)]
    if args.heldout and tasklib.HELDOUT_ENV in os.environ:
        found_tasks += tasklib.discover([Path(os.environ[tasklib.HELDOUT_ENV])])
    for task in found_tasks:
        errors = tasklib.check_task(task)
        problems += [f"task {task.id} ({task.dir}): {e}" for e in errors]
        say(f"{'ok  ' if not errors else 'FAIL'} task {task.id} ({task.kind}/{task.category})")
    for arm in found_arms:
        errors = armlib.check_arm(arm)
        problems += [f"arm {arm.id} ({arm.path}): {e}" for e in errors]
        say(f"{'ok  ' if not errors else 'FAIL'} arm {arm.id} {arm.version} ({arm.driver})")
    problems += armlib.check_same_conditions(found_arms)
    if args.suite:
        problems += [f"suite: {e}" for e in tasklib.check_suite_composition(found_tasks)]
    heldout_root = os.environ.get(tasklib.HELDOUT_ENV) if args.heldout else None
    problems += [f"held-out: {e}" for e in tasklib.check_heldout_manifest(tasklib.HELDOUT_MANIFEST,
                                                                           Path(heldout_root) if heldout_root else None)]
    for problem in problems:
        say(f"  - {problem}")
    say(f"{len(found_tasks)} task(s), {len(found_arms)} arm(s): " + ("valid" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


def cmd_estimate(args: argparse.Namespace) -> int:
    chosen = select_tasks(args)
    arm_list = [armlib.load_arm(a) for a in args.arm]
    seeds: Dict[str, float] = {}
    if args.pilot_results:
        docs = [load_json(Path(p)) for p in args.pilot_results]
        fake = [aid for d in docs for aid, meta in (d.get("arms") or {}).items() if meta.get("driver") == FAKE_DRIVER]
        seeds = budgetlib.seeds_from_records([r for d in docs for r in d.get("records", [])], exclude_arms=fake)
    print_estimate(budgetlib.estimate(chosen, arm_list, args.k, seeds))
    return 0


def print_estimate(est: Dict[str, Any]) -> None:
    say(f"Estimate: {est['runs']} run(s) = tasks x arms ({', '.join(est['arms'])}) x k={est['k']}; "
        f"seeds: {est['seed_source']}")
    say(f"  {'kind':9} {'category':14} {'tasks':>5} {'runs':>5} {'seed $':>8} {'total $':>9}")
    for row in est["rows"]:
        say(f"  {row['kind']:9} {row['category'][:14]:14} {row['tasks']:>5} {row['runs']:>5} "
            f"{row['seed_usd']:>8.2f} {row['total_usd']:>9.2f}")
    say(f"  projected total: ${est['total_usd']:.2f} (fake-arm runs cost $0)")


def resolve_boundary(args: argparse.Namespace, chosen: Sequence[tasklib.Task], arm_list: Sequence[armlib.Arm]
                     ) -> Tuple[str, bool]:
    """(boundary name, plan_only). The local boundary runs only the fake arm on selftest tasks."""
    offline_ok = all(not a.needs_model for a in arm_list) and all(t.set == "selftest" for t in chosen)
    if args.dry_run:
        return ("local", False) if offline_ok else (args.boundary, True)
    if args.boundary == "local" and not offline_ok:
        raise BoundaryError("the local boundary has no isolation: only the fake arm on selftest tasks may use it")
    return args.boundary, False


def resolve_raw_root(raw_dir: Optional[str], boundary_name: str, stamp: str) -> Path:
    """--raw-dir, else AGENT_RAW_DIR/<stamp> for docker and sandbox (outside the hub, a neutral path) or
    bench/results/raw/<stamp> for local. A docker or sandbox root inside the hub or whose path names the benchmark
    is refused, and a sandbox root below a CLAUDE.md too."""
    if raw_dir:
        raw_root = Path(raw_dir)
    else:
        raw_root = (RAW_DIR if boundary_name == "local" else AGENT_RAW_DIR) / stamp
    checks = {"sandbox": sandbox_root_problem, "docker": exposed_root_problem}
    problem = checks[boundary_name](raw_root) if boundary_name in checks else None
    if problem:
        raise BoundaryError(f"{boundary_name} boundary: {problem}")
    return raw_root


def guard_live(args: argparse.Namespace, ctx: RunContext, arm_list: Sequence[armlib.Arm], est: Dict[str, Any]) -> None:
    real = [a for a in arm_list if a.needs_model]
    if not real:
        return
    if args.total_budget_usd is None:
        raise BenchError("a live run needs --total-budget-usd (and confirmation of the projected total)")
    unresolved = [f"{a.id}: {f}" for a in real for f in ("model", "effort")
                  if armlib.resolve_placeholder(a.data[f], {"BENCH_MODEL": args.model, "BENCH_EFFORT": args.effort}) is None]
    if unresolved:
        raise BenchError(f"unresolved placeholders ({', '.join(unresolved)}): pass --model/--effort or set BENCH_MODEL/BENCH_EFFORT")
    pending = sorted({flag for a in real for flag in a.cli.get("verify_in_t0", [])})
    if pending and not args.t0_verified:
        raise BenchError(f"flags not yet verified in T0: {', '.join(pending)}; verify them on the pinned CLI, "
                         "then clear cli.verify_in_t0 or pass --t0-verified")
    env_file = os.environ.get(ENV_FILE_VAR)
    ctx.secrets = tuple(read_env_file(env_file).values()) if env_file else ()
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise BenchError(f"projected ${est['total_usd']:.2f}, cap ${args.total_budget_usd:.2f}: confirm with --yes")
    answer = input(f"Spend up to ${args.total_budget_usd:.2f} (projected ${est['total_usd']:.2f})? Type yes: ")
    if answer.strip().lower() != "yes":
        raise BenchError("not confirmed")


def cmd_run(args: argparse.Namespace) -> int:
    chosen = select_tasks(args)
    arm_list = [armlib.load_arm(a) for a in args.arm]
    problems = check_inputs(chosen, arm_list)
    if problems:
        for problem in problems:
            say(f"  - {problem}")
        raise BenchError(f"{len(problems)} problem(s) in the selected tasks or arms")
    boundary_name, plan_only = resolve_boundary(args, chosen, arm_list)
    k = 1 if args.pilot else args.k
    stamp = utc_now().replace(":", "").replace("-", "")
    raw_root = resolve_raw_root(args.raw_dir, boundary_name, stamp)
    ctx = RunContext(args, boundary_name, raw_root, offline=args.dry_run)
    est = budgetlib.estimate(chosen, arm_list, k)
    print_estimate(est)
    if args.dry_run:
        say(f"dry run: no model, no docker, no network ({'plan only' if plan_only else 'fake arm, local boundary'})")
    else:
        guard_live(args, ctx, arm_list, est)
        probe = make_boundary(boundary_name, wslib.Workspace(raw_root / "probe"), image=args.image)
        probe.check_ready(any(a.needs_model for a in arm_list))
    arm_dirs: Dict[str, Optional[Path]] = {}
    for arm in arm_list:
        arm_dirs[arm.id] = raw_root / "arms" / arm.id if arm.data.get("setup") else None
        if arm_dirs[arm.id] is not None:
            say(f"arm {arm.id} setup:")
            armlib.setup_arm(arm, arm_dirs[arm.id], action, dry_run=plan_only)  # type: ignore[arg-type]
    ledger = budgetlib.Ledger(args.total_budget_usd)
    records: Dict[str, List[Dict[str, Any]]] = {a.id: [] for a in arm_list}
    out_dir = Path(args.out_dir) if args.out_dir else RESULTS_DIR
    date = args.date or utc_date()
    try:
        for item in budgetlib.schedule(chosen, arm_list, k):
            cap = budgetlib.run_cap(item.task, args.budget_usd)
            run_id = f"{stamp}-{item.arm.id}-{item.task.id}-r{item.repeat}"
            if plan_only:
                print_plan(ctx, item, cap, run_id, arm_dirs[item.arm.id])
                continue
            reserve = budgetlib.reservation(item.task, cap)
            if not ledger.can_start(reserve):
                record = new_record(run_id, item.task, item.arm, item.repeat, boundary_name, ctx.model_for(item.arm))
                records[item.arm.id].append(skip(record, f"total budget cap reached (spent ${ledger.spent:.2f} of "
                                                         f"${ledger.total_cap:.2f}; next run could cost ${reserve:.2f})"))
                say(f"skip {run_id}: total budget cap")
                continue
            say(f"run {run_id} (cap ${cap:.2f}, boundary {boundary_name}, folder {run_name(run_id)})")
            record, charge = execute_run(ctx, item, cap, run_id, arm_dirs[item.arm.id])
            ledger.charge(charge, reserve)
            records[item.arm.id].append(record)
            status = ("skipped: " + record["skipped"]["reason"]) if record["skipped"] else f"verified={record['verified']}"
            say(f"  {status}; cost {record['cost_usd']}; spent ${ledger.spent:.2f}")
    finally:
        if not plan_only:
            for arm in arm_list:
                if records[arm.id]:
                    say(f"results: {write_results(out_dir, arm, records[arm.id], date)}")
    if not plan_only:
        say(f"raw run data (never committed): {raw_root}")
    return 0


def cmd_verify_task(args: argparse.Namespace) -> int:
    roots = task_roots(args)
    chosen = [tasklib.find_task(ref, roots) for ref in args.task]
    failures = 0
    stamp = utc_now().replace(":", "").replace("-", "")
    for task in chosen:
        errors = tasklib.check_task(task)
        if errors:
            say(f"FAIL {task.id}: invalid task: {'; '.join(errors)}")
            failures += 1
            continue
        if not (task.hidden and task.data.get("reference_patch")):
            say(f"SKIP {task.id}: no hidden tests or reference patch ({task.kind})")
            continue
        name = "local" if args.dry_run and task.set == "selftest" else args.boundary
        if name == "local" and task.set != "selftest":
            raise BoundaryError("the local boundary runs only selftest tasks")
        # The sandbox user runs the setup and hidden tests on host paths, so its folders follow run's rules (RW-30).
        raw_base = (resolve_raw_root(args.raw_dir, name, stamp) if name == "sandbox"
                    else Path(args.raw_dir) if args.raw_dir else RAW_DIR)
        ws = wslib.Workspace(raw_base / f"verify-{stamp}-{task.id}")
        boundary = make_boundary(name, ws, None, run_name(f"verify-{stamp}-{task.id}"), image=args.image)
        if args.dry_run and name != "local":
            say(f"[plan] verify {task.id}: clone, setup, hidden tests on the base (expect fail), then with "
                f"reference.patch (expect pass)")
            action(boundary.score_command(ws.root / "base", task.dir / task.hidden["path"], task.hidden["command"]).describe())
            continue
        boundary.check_ready(False)
        try:
            ok = verify_in_workspace(args, task, ws, boundary)
        finally:
            wslib.seal(ws.root)
        failures += int(ok is False)
    return 1 if failures else 0


def verify_in_workspace(args: argparse.Namespace, task: tasklib.Task, ws: wslib.Workspace, boundary: Boundary
                        ) -> Optional[bool]:
    """Hidden tests on the base (expect fail), then with reference.patch (expect pass); None when setup failed."""
    ctx = RunContext(args, boundary.name, ws.root.parent, offline=args.dry_run)
    _, reason = prepare_run(ctx, task, ws, boundary, "uncommitted")
    if reason:
        say(f"SKIP {task.id}: {reason}")
        return None
    (ws.root / "collect").mkdir(parents=True, exist_ok=True)
    wslib.copy_tree(ws.work, ws.root / "base")
    on_base = run_hidden(task, boundary, ws, ws.root / "base", "verify-base.log")
    wslib.copy_tree(ws.work, ws.root / "reference")
    wslib.git(["apply", "--whitespace=nowarn", str(task.dir / task.data["reference_patch"])], cwd=ws.root / "reference")
    with_ref = run_hidden(task, boundary, ws, ws.root / "reference", "verify-reference.log")
    ok = on_base["exit_code"] != 0 and with_ref["exit_code"] == 0
    say(f"{'PASS' if ok else 'FAIL'} {task.id}: base exit {on_base['exit_code']} (want != 0), "
        f"with reference.patch exit {with_ref['exit_code']} (want 0); boundary {boundary.name}")
    return ok


def cmd_score(args: argparse.Namespace) -> int:
    for run_dir in args.run_dirs:
        collected = load_json(Path(run_dir) / "collected.json")
        task = tasklib.load_task(Path(collected["task_dir"]))
        arm = armlib.load_arm(collected["arm_path"])
        print(json.dumps({"run_dir": str(run_dir), **score_collected(task, arm, collected)}, indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    docs = []
    for path in args.results:
        doc = load_json(Path(path))
        errors = schema_errors(doc, "result")
        if errors:
            raise BenchError(f"{path} does not match result.schema.json: {'; '.join(errors[:5])}")
        docs.append(doc)
    date = args.date or utc_date()
    markdown = metrics.render_markdown(docs, args.results, date)
    summary = metrics.report_json(docs, args.results)
    if args.dry_run:
        print(markdown)
        return 0
    out = Path(args.out) if args.out else REPORT_DIR / f"bench-{date}.md"
    json_out = Path(args.json_out) if args.json_out else RESULTS_DIR / f"{date}-summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    write_json(json_out, summary)
    say(f"report: {out}\nsummary: {json_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", help="no model, no docker, no network (see the module doc)")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def selection(p: argparse.ArgumentParser) -> None:
        p.add_argument("--set", choices=["dev", "heldout", "selftest"], default="dev")
        p.add_argument("--task", action="append", default=[], help="task id or folder (repeatable)")
        p.add_argument("--kind", action="append", choices=list(KINDS), help="only these kinds (repeatable)")

    p = sub.add_parser("validate", parents=[common], help="check task and arm files against the schemas")
    p.add_argument("paths", nargs="*", help="task folders, folders of tasks, arm files or bench/arms")
    p.add_argument("--suite", action="store_true", help="also check the AC-9 development-set composition")
    p.add_argument("--heldout", action="store_true", help=f"also validate ${tasklib.HELDOUT_ENV} and its manifest digests")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("verify-task", parents=[common], help="hidden tests fail on the base, pass with reference.patch")
    p.add_argument("task", nargs="+")
    p.add_argument("--set", choices=["dev", "heldout", "selftest"], default="dev")
    p.add_argument("--boundary", choices=list(BOUNDARIES), default="docker")
    p.add_argument("--image")
    p.add_argument("--raw-dir")
    p.set_defaults(func=cmd_verify_task)

    p = sub.add_parser("estimate", parents=[common], help="tasks x arms x k x per-category cost seed")
    selection(p)
    p.add_argument("--arm", action="append", required=True)
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--pilot", dest="pilot_results", nargs="+", help="pilot results files: measured seeds")
    p.set_defaults(func=cmd_estimate, pilot=False)

    p = sub.add_parser("run", parents=[common], help="run tasks x arms x k inside the boundary")
    selection(p)
    p.add_argument("--arm", action="append", required=True)
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--boundary", choices=list(BOUNDARIES), default="docker")
    p.add_argument("--image")
    p.add_argument("--budget-usd", type=float, help="per-run cap (lowers each task's budget_usd)")
    p.add_argument("--total-budget-usd", type=float, help="stop scheduling when another run could exceed this")
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--pilot", action="store_true", help="one task per category per arm, k = 1")
    p.add_argument("--yes", action="store_true", help="confirm the projected total without a prompt")
    p.add_argument("--t0-verified", action="store_true", help="the arms' verify_in_t0 flags were checked on the pinned CLI")
    p.add_argument("--out-dir")
    p.add_argument("--raw-dir", help=f"raw run data, one folder per run named run-<hash> (default {AGENT_RAW_DIR}/"
                                     "<stamp>, or bench/results/raw/<stamp> for --boundary local; docker and sandbox "
                                     "refuse a folder inside the hub or whose path says bench, and sandbox one below "
                                     "a CLAUDE.md)")
    p.add_argument("--date")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("score", parents=[common], help="re-score finished runs from their collected.json")
    p.add_argument("run_dirs", nargs="+")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("report", parents=[common], help="median, IQR and noise band per metric")
    p.add_argument("results", nargs="+")
    p.add_argument("--out")
    p.add_argument("--json-out")
    p.add_argument("--date")
    p.set_defaults(func=cmd_report)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "k", 1) < 1:
        say("error: --k must be >= 1")
        return 2
    try:
        return int(args.func(args))
    except BenchError as err:
        say(f"error: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
