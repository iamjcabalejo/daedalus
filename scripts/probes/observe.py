"""Evaluate a probe case's observations against one run's capture, and decide its status (AC-2).

Observation kinds (fields per kind are checked by probelib.validate_case):
  event                 records of `event` (optional `tag`, `where`) are present / absent
                        (any kind's `expect` may be given per install as `expect_by_install`)
  field                 `field` on the matching payloads: present | absent | equals (value or value_by_install) |
                        value (records the values; only for SAFE_VALUE_FIELDS); `scope` all (default) or any
  count                 number of matching records compared with `op` and `value`
  keys                  key names of `field` ("" for the payload root) across matching records (recorded)
  marker                a file at `path` (relative to the probe repo) exists (expect true) or not (expect false)
  file                  a seeded file at `path` is "changed" or "unchanged"
  identity-echo         every Bash payload whose command names one of `names` has that agent_type (raw only)
  identity-consistency  each agent_id maps to one agent_type, and each of `names` has an agent_id; this works on
                        redacted fixtures too, because placeholders keep id equality
  stream                facts from the host's JSON stream: result | permission-denials | usage-keys | codex-usage |
                        tool-use (passes when the assistant issued a tool_use whose name is in `names` and whose block
                        matches `where`, for example input.command; proves a call was attempted even when no hook
                        could record it, as in E4; the stream-json shape is verify in T0)
  git                   worktrees | branches in the probe repo (counts)
  transcript-usage      usage key names and totals from SubagentStop's agent_transcript_path
  manual                needs the maintainer; adds a note
Roles: precondition (must pass, else inconclusive), assert (decides confirmed / contradicted), record (facts only).
An asserted absence (no marker, no PostToolUse, fewer than n calls) needs a precondition proving the probed call was
attempted, or a run where nothing happened would pass it.
`actual` values are booleans, counts, key names or values of SAFE_VALUE_FIELDS, never prompt or tool text.

Denials (T0, 2.1.325): every `result` event's `permission_denials` entry is matched to its `tool_result` by tool_use_id
and classified from that text: `hook` (it carries one of the run's recorder markers: a control reason, the recorder's
default or crash text, or the recorder's hook command, which the host quotes when a hook fails under onFailure: block),
`permission` (host wording: "needs approval", "permission", "haven't granted"), else `unknown`. A denial hits the
probed call when it matches one of the case's call selectors (CALL_KINDS on TOOL_EVENTS with `where`, or a stream
`tool-use`); the `where` clauses run on the call's recorded PreToolUse payload, joined on tool_use_id.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PASS, FAIL, UNKNOWN, RECORDED = "pass", "fail", "unknown", "recorded"
SAFE_VALUE_FIELDS = ("agent_type", "command_name", "hook_event_name", "permission_mode", "stop_hook_active",
                     "tool_name", "tool_input.subagent_type", "source")
COUNT_OPS = {"lt": lambda a, b: a < b, "le": lambda a, b: a <= b, "eq": lambda a, b: a == b,
             "ge": lambda a, b: a >= b, "gt": lambda a, b: a > b}
MISSING = object()
HOOK, PERMISSION = "hook", "permission"  # denial sources; the third is UNKNOWN
DENIAL_SOURCES = (HOOK, PERMISSION, UNKNOWN)
# Host wording of a permission-layer denial (T0, 2.1.325): "… needs approval", "Claude requested permissions to use
# …, but you haven't granted it yet", "Permission to use Bash has been denied".
PERMISSION_TEXT_RE = re.compile(r"needs approval|requires approval|permission|haven'?t granted|not (?:been )?granted",
                                re.IGNORECASE)
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest")
CALL_KINDS = ("event", "field", "count", "identity-echo")
DENIAL_FIELDS = ("tool_name", "tool_input")  # the parts of a call a permission_denials entry carries itself


@dataclass
class Context:
    records: list
    repo: Path
    workspace: Path
    install: str
    stream: list = field(default_factory=list)
    seeds: dict = field(default_factory=dict)


def get_field(payload: object, dotted: str) -> object:
    if dotted == "":
        return payload
    node = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


def agent_matches(name: str, agent_type: object) -> bool:
    return isinstance(agent_type, str) and (agent_type == name or agent_type.endswith(":" + name))


def where_ok(payload: dict, clause: dict) -> bool:
    value, op, wanted = get_field(payload, clause["field"]), clause["op"], clause.get("value")
    if op == "present":
        return value is not MISSING
    if op == "absent":
        return value is MISSING
    if value is MISSING:
        return False
    if op == "equals":
        return value == wanted
    if op == "in":
        return isinstance(wanted, list) and value in wanted
    if op == "contains":
        return isinstance(value, str) and str(wanted) in value
    if op == "endswith":
        return isinstance(value, str) and value.endswith(str(wanted))
    if op == "startswith":
        return isinstance(value, str) and value.startswith(str(wanted))
    return False


def select(records: list, obs: dict) -> list:
    picked = []
    for record in records:
        if obs.get("event") and record.get("event") != obs["event"]:
            continue
        if "tag" in obs and record.get("tag") != obs["tag"]:
            continue
        if all(where_ok(record["payload"], clause) for clause in obs.get("where", [])):
            picked.append(record["payload"])
    return picked


def expectation(obs: dict, install: str) -> object:
    """`expect_by_install` (for example C4: script honored, plugin ignored) wins over `expect`."""
    by_install = obs.get("expect_by_install") or {}
    return by_install.get(install, obs.get("expect"))


def expected_value(obs: dict, install: str) -> object:
    by_install = obs.get("value_by_install") or {}
    return by_install.get(install, obs.get("value"))


def eval_event(obs: dict, ctx: Context) -> tuple:
    count = len(select(ctx.records, obs))
    seen = count > 0
    return (PASS if seen == (expectation(obs, ctx.install) == "present") else FAIL), {"count": count}


def eval_field(obs: dict, ctx: Context) -> tuple:
    payloads = select(ctx.records, obs)
    if not payloads:
        return UNKNOWN, {"matched": 0}
    values = [get_field(p, obs["field"]) for p in payloads]
    present = [v for v in values if v is not MISSING]
    expect, scope = expectation(obs, ctx.install), obs.get("scope", "all")
    if expect == "value":
        return RECORDED, sorted({json.dumps(v) for v in present})
    if expect == "equals":
        wanted = expected_value(obs, ctx.install)
        hits = [v == wanted for v in values]
        ok = all(hits) if scope == "all" else any(hits)
        shown = sorted({json.dumps(v) for v in present}) if obs["field"] in SAFE_VALUE_FIELDS else None
        return (PASS if ok else FAIL), {"matched": len(values), "equal": sum(hits), "values": shown}
    hits = [(v is not MISSING) == (expect == "present") for v in values]
    ok = all(hits) if scope == "all" else any(hits)
    return (PASS if ok else FAIL), {"matched": len(values), "with_field": len(present)}


def eval_count(obs: dict, ctx: Context) -> tuple:
    count = len(select(ctx.records, obs))
    return (PASS if COUNT_OPS[obs["op"]](count, obs["value"]) else FAIL), count


def eval_keys(obs: dict, ctx: Context) -> tuple:
    payloads = select(ctx.records, obs)
    if not payloads:
        return UNKNOWN, []
    keys = set()
    for payload in payloads:
        value = get_field(payload, obs.get("field", ""))
        if isinstance(value, dict):
            keys.update(str(k) for k in value)
    return RECORDED, sorted(keys)


def inside(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


def eval_marker(obs: dict, ctx: Context) -> tuple:
    target = ctx.repo / obs["path"]
    if not inside(target, ctx.workspace):
        return UNKNOWN, "path outside the workspace"
    exists = target.exists()
    if obs.get("role") == "record":
        return RECORDED, exists
    return (PASS if exists == bool(expectation(obs, ctx.install)) else FAIL), exists


def eval_file(obs: dict, ctx: Context) -> tuple:
    target = ctx.repo / obs["path"]
    seed = ctx.seeds.get(obs["path"])
    if seed is None or not inside(target, ctx.workspace):
        return UNKNOWN, "not a seeded file"
    if not target.is_file():
        return UNKNOWN, "missing"
    state = "unchanged" if target.read_text(encoding="utf-8", errors="replace") == seed else "changed"
    if obs.get("role") == "record":
        return RECORDED, state
    return (PASS if state == expectation(obs, ctx.install) else FAIL), state


def named_agent(command: object, names: list) -> Optional[str]:
    if not isinstance(command, str):
        return None
    for name in sorted(names, key=len, reverse=True):
        if f"{name}-" in command:
            return name
    return None


def eval_identity_echo(obs: dict, ctx: Context) -> tuple:
    checked = mismatches = 0
    for payload in select(ctx.records, obs):
        name = named_agent(get_field(payload, "tool_input.command"), obs["names"])
        if name is None:
            continue
        checked += 1
        mismatches += 0 if agent_matches(name, payload.get("agent_type")) else 1
    if not checked:
        return UNKNOWN, {"checked": 0, "mismatches": 0}
    return (PASS if mismatches == 0 else FAIL), {"checked": checked, "mismatches": mismatches}


def identity_consistency(payloads: list, names: list) -> tuple:
    """agent_id -> agent_type must be one-to-one for the named agents (works on raw or redacted payloads)."""
    types_by_id: dict = {}
    for payload in payloads:
        agent_id, agent_type = payload.get("agent_id"), payload.get("agent_type")
        if isinstance(agent_id, str) and any(agent_matches(n, agent_type) for n in names):
            types_by_id.setdefault(agent_id, set()).add(agent_type)
    seen = sorted({n for n in names for types in types_by_id.values() for t in types if agent_matches(n, t)})
    conflicts = sum(1 for types in types_by_id.values() if len(types) > 1)
    ids_by_name = {n: {i for i, types in types_by_id.items() if any(agent_matches(n, t) for t in types)}
                   for n in names}
    shared = any(ids_by_name[a] & ids_by_name[b] for a in names for b in names if a < b)
    actual = {"agent_ids": len(types_by_id), "conflicts": conflicts, "names_seen": seen}
    if not types_by_id:
        return UNKNOWN, actual
    return (PASS if not conflicts and not shared and seen == sorted(names) else FAIL), actual


def eval_identity_consistency(obs: dict, ctx: Context) -> tuple:
    return identity_consistency([r["payload"] for r in ctx.records], obs["names"])


def last_result(stream: list) -> Optional[dict]:
    results = [e for e in stream if isinstance(e, dict) and e.get("type") == "result"]
    return results[-1] if results else None


def tool_uses(stream: list) -> list:
    """tool_use blocks from stream-json assistant events: {"type": "assistant", "message": {"content": [...]}}.

    The shape is verify in T0. Subagent turns, when the stream carries them, are included.
    """
    blocks = []
    for event in stream:
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        content = (event.get("message") or {}).get("content")
        if isinstance(content, list):
            blocks += [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
    return blocks


def eval_tool_use(obs: dict, ctx: Context) -> tuple:
    """A tool_use named in `names` (and matching `where`) was issued. `actual` is a count, never the input text."""
    issued = [b for b in tool_uses(ctx.stream) if b.get("name") in obs["names"]
              and all(where_ok(b, clause) for clause in obs.get("where", []))]
    return (PASS if issued else FAIL), {"count": len(issued)}


def eval_stream(obs: dict, ctx: Context) -> tuple:
    if not ctx.stream:
        return UNKNOWN, None
    check, result = obs["check"], last_result(ctx.stream)
    if check == "tool-use":  # doesn't need the result event: a killed or cut-short run may still have issued it
        return eval_tool_use(obs, ctx)
    if check == "codex-usage":  # Codex `turn.completed` events: verify in T0
        keys = sorted({k for e in ctx.stream if isinstance(e, dict) and e.get("type") == "turn.completed"
                       for k in (e.get("usage") or {})})
        return (RECORDED if keys else UNKNOWN), keys
    if result is None:
        return UNKNOWN, None
    if check == "result":
        return RECORDED, {"subtype": result.get("subtype"), "is_error": result.get("is_error"),
                          "num_turns": result.get("num_turns"), "has_cost": "total_cost_usd" in result}
    if check == "permission-denials":  # every result event's permission_denials (T0, 2.1.325: one per turn)
        return RECORDED, len(permission_denials(ctx.stream))
    return RECORDED, sorted((result.get("usage") or {}).keys())


# ---- denials: which layer denied a call, and was it the probed one --------------------------------------------

@dataclass
class Denial:
    tool_use_id: Optional[str]
    tool_name: Optional[str]
    tool_input: dict
    source: str
    block: Optional[dict] = None  # the assistant's tool_use block, when the stream has it


def permission_denials(stream: list) -> list:
    """`permission_denials` from every result event, first entry per tool_use_id.

    T0 (2.1.325): a run with a background agent emits one result per turn, and the last one can be empty while an
    earlier one holds the denial, so reading only the last result undercounts.
    """
    found, seen = [], set()
    for event in stream:
        if not isinstance(event, dict) or event.get("type") != "result":
            continue
        for entry in event.get("permission_denials") or []:
            key = entry.get("tool_use_id") if isinstance(entry, dict) else None
            if isinstance(entry, dict) and (key is None or key not in seen):
                seen.add(key)
                found.append(entry)
    return found


def result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


def tool_results(stream: list) -> dict:
    """tool_use_id -> the text of its tool_result block (from the stream's `user` events)."""
    texts = {}
    for event in stream:
        if not isinstance(event, dict) or event.get("type") != "user":
            continue
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id"):
                texts.setdefault(block["tool_use_id"], result_text(block.get("content")))
    return texts


def classify_denial(text: str, hook_markers: tuple) -> str:
    """`hook` when the text carries one of the run's recorder markers, `permission` for the host's own wording."""
    if any(marker and marker in text for marker in hook_markers):
        return HOOK
    return PERMISSION if PERMISSION_TEXT_RE.search(text) else UNKNOWN


def classify_denials(stream: list, hook_markers: tuple) -> list:
    texts = tool_results(stream)
    blocks = {b.get("id"): b for b in tool_uses(stream) if b.get("id")}
    denials = []
    for entry in permission_denials(stream):
        tool_use_id = entry.get("tool_use_id")
        tool_input = entry.get("tool_input") if isinstance(entry.get("tool_input"), dict) else {}
        source = classify_denial(texts.get(tool_use_id, ""), hook_markers)
        denials.append(Denial(tool_use_id, entry.get("tool_name"), tool_input, source, blocks.get(tool_use_id)))
    return denials


def call_selectors(observations: list) -> list:
    """The precondition and assert observations that name a tool call: the calls a verdict depends on."""
    selectors = []
    for obs in observations:
        if obs.get("role", "assert") == "record":
            continue
        if obs["kind"] in CALL_KINDS and obs.get("event") in TOOL_EVENTS and obs.get("where"):
            selectors.append(obs)
        elif obs["kind"] == "stream" and obs.get("check") == "tool-use":
            selectors.append(obs)
    return selectors


def denied_call_payload(denial: Denial, records: list) -> tuple:
    """(payload, joined): the call's recorded PreToolUse payload, else one built from the denial entry."""
    if denial.tool_use_id:
        for record in records:
            payload = record.get("payload") or {}
            if record.get("event") == "PreToolUse" and payload.get("tool_use_id") == denial.tool_use_id:
                return payload, True
    return {"tool_name": denial.tool_name, "tool_input": denial.tool_input}, False


def selector_hit(denial: Denial, obs: dict, records: list) -> bool:
    if obs["kind"] == "stream":
        block = denial.block or {"name": denial.tool_name, "input": denial.tool_input}
        return block.get("name") in obs["names"] and all(where_ok(block, c) for c in obs.get("where", []))
    payload, joined = denied_call_payload(denial, records)
    # Without the recorded payload, a clause on another field (agent_type) can't be checked: count it as a match,
    # so an unattributable denial errs towards inconclusive.
    return all(where_ok(payload, c) for c in obs["where"]
               if joined or c["field"].split(".", 1)[0] in DENIAL_FIELDS)


def hits_probed_call(denial: Denial, observations: list, records: list) -> bool:
    return any(selector_hit(denial, obs, records) for obs in call_selectors(observations))


def command_head(tool_input: dict) -> Optional[str]:
    """The command's first word (its basename, so no path is ever recorded); None for tools without a command."""
    command = tool_input.get("command")
    words = command.split(None, 1) if isinstance(command, str) else []
    return os.path.basename(words[0]) if words else None


def denial_sources_record(denials: list, probed: list) -> dict:
    """The `denial-sources` record added to every run: counts per source, tool names and command heads only."""
    actual: dict = {source: sum(1 for d in denials if d.source == source) for source in DENIAL_SOURCES}
    listed = []
    for denial, is_probed in zip(denials, probed):
        item = {"tool": denial.tool_name, "source": denial.source, "probed_call": is_probed}
        head = command_head(denial.tool_input)
        listed.append(dict(item, command=head) if head else item)
    actual["denials"] = listed
    return {"check": "denial-sources", "expected": "recorded", "actual": actual, "outcome": RECORDED,
            "role": "record"}


def eval_git(obs: dict, ctx: Context) -> tuple:
    args = {"worktrees": ["worktree", "list", "--porcelain"], "branches": ["for-each-ref", "refs/heads"]}
    try:
        out = subprocess.run(["git", "-C", str(ctx.repo)] + args[obs["check"]], capture_output=True,
                             text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return UNKNOWN, None
    lines = [line for line in out.splitlines() if line.strip()]
    if obs["check"] == "worktrees":
        lines = [line for line in lines if line.startswith("worktree ")]
    return RECORDED, len(lines)


def usage_from_transcript(path: Path) -> list:
    usages = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        usage = (entry.get("message") or {}).get("usage") if isinstance(entry, dict) else None
        if isinstance(usage, dict):
            usages.append(usage)
    return usages


def eval_transcript_usage(obs: dict, ctx: Context) -> tuple:
    paths = {p.get("agent_transcript_path") for p in select(ctx.records, {"event": "SubagentStop"})}
    usages, read = [], 0
    for raw in sorted(p for p in paths if isinstance(p, str)):
        try:
            usages += usage_from_transcript(Path(raw))
            read += 1
        except OSError:
            continue
    if not read:
        return UNKNOWN, {"transcripts": 0}
    totals: dict = {}
    for usage in usages:
        for key, value in usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    keys = sorted({k for u in usages for k in u})
    return RECORDED, {"transcripts": read, "keys": keys, "totals": totals}


EVALUATORS = {"event": eval_event, "field": eval_field, "count": eval_count, "keys": eval_keys,
              "marker": eval_marker, "file": eval_file, "identity-echo": eval_identity_echo,
              "identity-consistency": eval_identity_consistency, "stream": eval_stream, "git": eval_git,
              "transcript-usage": eval_transcript_usage}


def describe_expected(obs: dict, install: str) -> object:
    kind, expect = obs["kind"], expectation(obs, install)
    if kind == "count":
        return f"{obs['op']} {obs['value']}"
    if kind == "field" and expect == "equals":
        return f"equals {expected_value(obs, install)}"
    if kind in ("identity-echo", "identity-consistency"):
        return "consistent for " + ", ".join(obs["names"])
    if kind == "stream" and obs.get("check") == "tool-use":
        return "tool_use issued: " + ", ".join(obs["names"])
    if kind == "manual":
        return obs.get("description", "maintainer review")
    return expect if expect is not None else "recorded"


def evaluate(observations: list, ctx: Context) -> list:
    evaluated = []
    for obs in observations:
        role = obs.get("role", "assert")
        if obs["kind"] == "manual":
            outcome, actual = UNKNOWN, None
        else:
            outcome, actual = EVALUATORS[obs["kind"]](dict(obs, role=role), ctx)
        if role == "record" and outcome in (PASS, FAIL):
            outcome = RECORDED
        evaluated.append({"check": obs["id"], "expected": describe_expected(obs, ctx.install), "actual": actual,
                          "outcome": outcome, "role": role})
    return evaluated


def decide_status(evaluated: list, rules: dict, observations: tuple = ()) -> tuple:
    """Return (status, notes) per §3.10: a contradiction is a finding, missing evidence is inconclusive."""
    notes = [f"manual check {o['id']}: {o.get('description', '')}" for o in observations if o["kind"] == "manual"]
    if rules.get("evaluate") == "manual":
        return "inconclusive", notes + ["needs maintainer review: " + rules.get("confirmed", "")]
    unmet = [e["check"] for e in evaluated if e["role"] == "precondition" and e["outcome"] != PASS]
    if unmet:
        return "inconclusive", notes + ["precondition not met: " + ", ".join(unmet)]
    asserts = [e for e in evaluated if e["role"] == "assert"]
    if not asserts:
        return "inconclusive", notes + ["no assertions"]
    failed = [e["check"] for e in asserts if e["outcome"] == FAIL]
    if failed:
        return "contradicted", notes + ["failed: " + ", ".join(failed)]
    unknown = [e["check"] for e in asserts if e["outcome"] != PASS]
    if unknown:
        return "inconclusive", notes + ["no evidence: " + ", ".join(unknown)]
    return "confirmed", notes
