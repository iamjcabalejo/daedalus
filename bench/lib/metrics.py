"""Transcript metrics (stream-json, parsed tolerantly), per-metric statistics and the Markdown/JSON report.

Stream-json shapes read here [verify in T0 against the pinned CLI]: `system`/`init` (model, version),
`assistant` messages with `text` and `tool_use` blocks and `usage`, `user` messages with `tool_result` blocks, and one
`result` per process with `usage`, `total_cost_usd`, `result` and `permission_denials`. Every field is
optional: a missing field yields zero, None or a note, never an exception.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import HARNESS_VERSION, utc_now

TOKEN_KEYS = (("input", "input_tokens"), ("output", "output_tokens"),
              ("cache_creation", "cache_creation_input_tokens"), ("cache_read", "cache_read_input_tokens"))
ASK_TOOL = "AskUserQuestion"
READ_TOOL = "Read"


def empty_tokens() -> Dict[str, int]:
    return {name: 0 for name, _ in TOKEN_KEYS}


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _tokens_from(usage: Any) -> Dict[str, int]:
    usage = usage if isinstance(usage, dict) else {}
    return {name: _int(usage.get(key)) for name, key in TOKEN_KEYS}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c.get("text", c.get("content", ""))) if isinstance(c, dict) else str(c) for c in content)
    return "" if content is None else str(content)


@dataclass
class ToolUse:
    id: str
    name: str
    input: Dict[str, Any]
    parent: Optional[str] = None


@dataclass
class ToolResult:
    is_error: bool
    text: str


@dataclass
class StreamSummary:
    tool_uses: List[ToolUse] = field(default_factory=list)
    results: Dict[str, ToolResult] = field(default_factory=dict)
    tokens: Dict[str, int] = field(default_factory=empty_tokens)
    cost_usd: Optional[float] = None
    result_text: str = ""
    assistant_texts: List[str] = field(default_factory=list)
    init: Dict[str, Any] = field(default_factory=dict)
    denials: List[Dict[str, Any]] = field(default_factory=list)
    bad_lines: int = 0
    has_result: bool = False
    usage_source: str = "none"

    @property
    def own_texts(self) -> List[str]:
        """What the agent itself wrote: assistant text blocks and the final result (never tool results)."""
        return self.assistant_texts + ([self.result_text] if self.result_text else [])

    @property
    def human_interventions(self) -> int:
        return sum(1 for t in self.tool_uses if t.name == ASK_TOOL)

    @property
    def repeated_reads(self) -> int:
        seen: Dict[str, int] = {}
        for tool in self.tool_uses:
            path = tool.input.get("file_path") if tool.name == READ_TOOL else None
            if isinstance(path, str):
                seen[path] = seen.get(path, 0) + 1
        return sum(n - 1 for n in seen.values())


def parse_stream(lines: Iterable[str]) -> StreamSummary:
    """One process's stream-json (or a transcript .jsonl). Unknown or malformed lines are counted, not fatal."""
    summary = StreamSummary()
    message_usage: Dict[str, Dict[str, int]] = {}
    seen_ids = set()
    for number, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            summary.bad_lines += 1
            continue
        if not isinstance(event, dict):
            summary.bad_lines += 1
            continue
        kind = event.get("type")
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        if kind == "system" and event.get("subtype") == "init":
            summary.init = {k: event[k] for k in ("model", "claude_code_version", "version", "session_id") if k in event}
        elif kind == "assistant":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    summary.assistant_texts.append(block["text"])
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_id = str(block.get("id") or f"line{number}")
                    if tool_id in seen_ids:
                        continue
                    seen_ids.add(tool_id)
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    summary.tool_uses.append(ToolUse(tool_id, str(block.get("name", "")), tool_input,
                                                     event.get("parent_tool_use_id")))
            if isinstance(message.get("usage"), dict):
                message_usage[str(message.get("id") or f"line{number}")] = _tokens_from(message["usage"])
        elif kind == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id"):
                    summary.results[str(block["tool_use_id"])] = ToolResult(bool(block.get("is_error")),
                                                                            _text(block.get("content")))
        elif kind == "result":
            summary.has_result = True
            cost = event.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                summary.cost_usd = (summary.cost_usd or 0.0) + float(cost)
            if isinstance(event.get("usage"), dict):
                for name, value in _tokens_from(event["usage"]).items():
                    summary.tokens[name] += value
                summary.usage_source = "result"
            if isinstance(event.get("result"), str):
                summary.result_text = event["result"]
            denials = event.get("permission_denials")
            if isinstance(denials, list):
                summary.denials += [d for d in denials if isinstance(d, dict)]
    if summary.usage_source == "none" and message_usage:
        for usage in message_usage.values():
            for name, value in usage.items():
                summary.tokens[name] += value
        summary.usage_source = "messages"
    return summary


def parse_stream_file(path: Path) -> StreamSummary:
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            return parse_stream(handle)
    except OSError:
        return StreamSummary(bad_lines=1)


def merge_tool_events(summaries: Sequence[StreamSummary]) -> Tuple[List[ToolUse], Dict[str, ToolResult], List[Dict[str, Any]]]:
    """Tool uses from the main streams and subagent transcripts, de-duplicated by tool_use id."""
    uses: Dict[str, ToolUse] = {}
    results: Dict[str, ToolResult] = {}
    denials: List[Dict[str, Any]] = []
    for summary in summaries:
        for tool in summary.tool_uses:
            uses.setdefault(tool.id, tool)
        results.update(summary.results)
        denials += summary.denials
    return list(uses.values()), results, denials


# ---------------------------------------------------------------- statistics

def percentile(values: Sequence[float], q: float) -> float:
    """Linear interpolation between closest ranks (the 'inclusive' method); `values` need not be sorted."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile of an empty list")
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def describe(values: Sequence[Optional[float]]) -> Optional[Dict[str, Any]]:
    """Median, interquartile range and noise band (max − min) across repeats; None values are dropped."""
    present = [float(v) for v in values if v is not None]
    if not present:
        return None
    q1, q3 = percentile(present, 0.25), percentile(present, 0.75)
    return {"n": len(present), "median": percentile(present, 0.5), "q1": q1, "q3": q3, "iqr": q3 - q1,
            "band": max(present) - min(present), "values": present}


def _active(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in records if not r.get("skipped")]


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    return numerator / denominator if denominator else None


def _judged_builds(rs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build records with a verdict. Safety (nothing executed) and recovery (success) have their own rows, so
    they never move the verified rate or the cost per verified task."""
    return [r for r in _active(rs) if r.get("kind") == "build" and r.get("verified") is not None]


def charged_cost(record: Dict[str, Any]) -> Optional[float]:
    """The run's known cost, else the worst case the budget charged it (charged_usd); None when neither is known."""
    if record.get("cost_usd") is not None:
        return float(record["cost_usd"])
    charged = record.get("charged_usd")
    return float(charged) if isinstance(charged, (int, float)) and not isinstance(charged, bool) else None


def _verified_rate(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
    judged = _judged_builds(rs)
    return _ratio(sum(1 for r in judged if r["verified"]), len(judged))


def _cost_per_verified(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
    judged = _judged_builds(rs)
    costs = [charged_cost(r) for r in judged]
    if any(c is None for c in costs):
        return None
    return _ratio(sum(c for c in costs if c is not None), sum(1 for r in judged if r["verified"]))


def _review(rs: Sequence[Dict[str, Any]], clean: bool) -> List[Dict[str, Any]]:
    return [r["review"] for r in _active(rs) if r.get("review") and bool(r["review"].get("clean")) == clean]


def _recall(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
    reviews = _review(rs, clean=False)
    return _ratio(sum(r["tp"] for r in reviews), sum(r["tp"] + r["fn"] for r in reviews))


def _precision(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
    reviews = _review(rs, clean=False)
    return _ratio(sum(r["tp"] for r in reviews), sum(r["tp"] + r["fp"] for r in reviews))


def _severity_accuracy(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
    reviews = _review(rs, clean=False)
    return _ratio(sum(r["severity_correct"] for r in reviews), sum(r["tp"] for r in reviews))


def _clean_fp(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
    reviews = _review(rs, clean=True)
    return _ratio(sum(r["fp"] for r in reviews), len(reviews))


def _mean(field_fn: Callable[[Dict[str, Any]], Optional[float]]) -> Callable[[Sequence[Dict[str, Any]]], Optional[float]]:
    def metric(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
        values = [field_fn(r) for r in _active(rs)]
        present = [v for v in values if v is not None]
        return sum(present) / len(present) if present else None
    return metric


def _sum(field_fn: Callable[[Dict[str, Any]], float]) -> Callable[[Sequence[Dict[str, Any]]], Optional[float]]:
    def metric(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
        active = _active(rs)
        return float(sum(field_fn(r) for r in active)) if active else None
    return metric


def _recovery_rate(rs: Sequence[Dict[str, Any]]) -> Optional[float]:
    judged = [r["recovery"] for r in _active(rs) if r.get("recovery") and r["recovery"].get("success") is not None]
    return _ratio(sum(1 for r in judged if r["success"]), len(judged))


MetricFn = Callable[[Sequence[Dict[str, Any]]], Optional[float]]
METRICS: List[Tuple[str, str, MetricFn]] = [
    ("verified_rate", "Verified rate (build tasks)", _verified_rate),
    ("cost_per_verified_usd", "Cost per verified build task (USD; unknown costs charged their worst case)",
     _cost_per_verified),
    ("human_interventions_per_task", "Human interventions per task", _mean(lambda r: r["human_interventions"])),
    ("review_recall", "Review recall", _recall),
    ("review_precision", "Review precision", _precision),
    ("review_severity_accuracy", "Review severity accuracy", _severity_accuracy),
    ("clean_false_positives_per_diff", "False positives per clean diff", _clean_fp),
    ("safety_executed", "Executed safety violations", _sum(lambda r: len(r["safety"]["executed"]))),
    ("safety_attempted", "Attempted safety violations", _sum(lambda r: len(r["safety"]["attempted"]))),
    ("recovery_success_rate", "Recovery success rate", _recovery_rate),
    ("tokens_input", "Input tokens (total)", _sum(lambda r: r["tokens"]["input"])),
    ("tokens_output", "Output tokens (total)", _sum(lambda r: r["tokens"]["output"])),
    ("tokens_cache_creation", "Cache-creation tokens (total)", _sum(lambda r: r["tokens"]["cache_creation"])),
    ("tokens_cache_read", "Cache-read tokens (total)", _sum(lambda r: r["tokens"]["cache_read"])),
    ("wall_s_per_task", "Wall time per task (s)", _mean(lambda r: r["wall_s"])),
    ("unnecessary_files_per_task", "Unnecessary files changed per task", _mean(lambda r: r["unnecessary_changes"]["files"])),
    ("repeated_reads_per_task", "Repeated reads per task", _mean(lambda r: r["repeated_reads"])),
    ("cost_usd_total", "Cost (USD, total; unknown costs count 0)", _sum(lambda r: r["cost_usd"] or 0.0)),
]


def summarize(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per (set, arm): each metric computed per repeat, then median, IQR and noise band across repeats."""
    groups: Dict[Tuple[str, str], Dict[int, List[Dict[str, Any]]]] = {}
    for record in records:
        key = (record["set"], record["arm"])
        groups.setdefault(key, {}).setdefault(int(record["repeat"]), []).append(record)
    out = []
    for (set_name, arm), repeats in sorted(groups.items()):
        metrics = {name: describe([fn(repeats[r]) for r in sorted(repeats)]) for name, _, fn in METRICS}
        unknown_cost = sum(1 for rs in repeats.values() for r in _active(rs) if r.get("cost_usd") is None)
        worst_case = sum(1 for rs in repeats.values() for r in _judged_builds(rs) if r.get("cost_usd") is None)
        out.append({"set": set_name, "arm": arm, "repeats": sorted(repeats), "metrics": metrics,
                    "runs": sum(len(rs) for rs in repeats.values()),
                    "skipped": sum(1 for rs in repeats.values() for r in rs if r.get("skipped")),
                    "unknown_cost_runs": unknown_cost, "worst_case_cost_build_runs": worst_case})
    return out


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9 and abs(value) >= 1:
        return f"{int(round(value)):,}"
    return f"{value:.3f}"


def _cell(stats: Optional[Dict[str, Any]]) -> str:
    if not stats:
        return "n/a"
    return (f"{_fmt(stats['median'])} (IQR {_fmt(stats['q1'])}–{_fmt(stats['q3'])}; "
            f"band {_fmt(stats['band'])}; n={stats['n']})")


def _md(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _distinct(records: Sequence[Dict[str, Any]], key: str) -> str:
    return ", ".join(sorted({str(r[key]) for r in records}))


def render_markdown(results: Sequence[Dict[str, Any]], sources: Sequence[str], date: str) -> str:
    records = [r for doc in results for r in doc.get("records", [])]
    summary = summarize(records)
    arms_meta: Dict[str, Dict[str, Any]] = {}
    for doc in results:
        arms_meta.update(doc.get("arms") or {})
    lines = [f"# Benchmark results {date}", "",
             f"Generated {utc_now()} by `bench/run.py report` (harness {HARNESS_VERSION}) from "
             + ", ".join(f"`{_md(s)}`" for s in sources) + ".", "",
             "Numbers only: this report makes no comparative claims beyond the values below. Each metric is "
             "computed per repeat, then reported as median (interquartile range; noise band = max − min across "
             "repeats; n = repeats with a value).", "", "## Conditions", "",
             "| Arm | Version | Boundary | Model | CLI version | Runs | Skipped | Runs with unknown cost |",
             "|---|---|---|---|---|---|---|---|"]
    for group in summary:
        rs = [r for r in records if r["arm"] == group["arm"] and r["set"] == group["set"]]
        cells = [_md(_distinct(rs, key)) for key in ("arm_version", "boundary", "model", "cli_version")]
        lines.append(f"| {_md(group['arm'])} ({group['set']}) | " + " | ".join(cells)
                     + f" | {group['runs']} | {group['skipped']} | {group['unknown_cost_runs']} |")
    for set_name in sorted({g["set"] for g in summary}):
        groups = [g for g in summary if g["set"] == set_name]
        lines += ["", f"## {set_name} set", "", "| Metric | " + " | ".join(_md(g["arm"]) for g in groups) + " |",
                  "|---|" + "---|" * len(groups)]
        for name, label, _ in METRICS:
            lines.append(f"| {label} | " + " | ".join(_cell(g["metrics"][name]) for g in groups) + " |")
        charged = [g for g in groups if g["worst_case_cost_build_runs"]]
        if charged:
            lines += [""] + [f"- {_md(g['arm'])}: {g['worst_case_cost_build_runs']} build run(s) reported no cost; "
                             "cost per verified build task charges each its worst case." for g in charged]
    skipped = [r for r in records if r.get("skipped")]
    lines += ["", "## Skipped tasks", ""]
    if skipped:
        lines += ["| Set | Arm | Task | Repeat | Reason |", "|---|---|---|---|---|"]
        lines += [f"| {r['set']} | {_md(r['arm'])} | {_md(r['task'])} | {r['repeat']} | {_md(r['skipped']['reason'])} |"
                  for r in skipped]
    else:
        lines.append("None.")
    lines += ["", "## Fairness notes", ""]
    for arm in sorted(arms_meta):
        lines.append(f"**{_md(arm)}** ({_md(arms_meta[arm].get('version', '?'))}):")
        lines += [f"- {_md(note)}" for note in arms_meta[arm].get("fairness_notes", [])] or ["- none recorded"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def report_json(results: Sequence[Dict[str, Any]], sources: Sequence[str]) -> Dict[str, Any]:
    records = [r for doc in results for r in doc.get("records", [])]
    return {"schema": "daedalus.bench-report/1", "generated_at": utc_now(), "harness_version": HARNESS_VERSION,
            "sources": list(sources), "groups": summarize(records),
            "skipped": [{"set": r["set"], "arm": r["arm"], "task": r["task"], "repeat": r["repeat"],
                         "reason": r["skipped"]["reason"]} for r in records if r.get("skipped")]}
