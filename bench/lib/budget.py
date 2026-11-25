"""Budget (§3.8): estimate, pilot seeds, per-run and total caps, and the priority schedule.

1. `estimate` multiplies tasks × arms × k × a per-category cost seed.
2. A pilot (one task per category per arm, k = 1) replaces the seeds with measured costs (`--pilot RESULTS`).
3. A live run prints the projected total and needs the user's confirmation.
4. When the total cap can't cover another run, scheduling stops; finished records are kept and the rest are
   recorded as skipped. Priority when the budget is short: safety, then build, then recovery, then review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, TYPE_CHECKING

from . import PRIORITY

if TYPE_CHECKING:  # pragma: no cover
    from .arms import Arm
    from .tasks import Task

# Placeholder USD per run, used only until a pilot measures real costs. Not measurements.
DEFAULT_SEEDS_USD: Dict[str, float] = {"build": 3.0, "review": 1.0, "safety": 1.0, "recovery": 4.0}
EPSILON = 1e-9


@dataclass(frozen=True)
class Planned:
    task: "Task"
    arm: "Arm"
    repeat: int


def schedule(tasks: Sequence["Task"], arms: Sequence["Arm"], k: int) -> List[Planned]:
    """Priority order by kind, then task id, then repeat, then arm (so both arms see a task before the next)."""
    rank = {kind: i for i, kind in enumerate(PRIORITY)}
    ordered = sorted(tasks, key=lambda t: (rank.get(t.kind, len(PRIORITY)), t.id))
    return [Planned(task, arm, repeat) for task in ordered for repeat in range(1, k + 1) for arm in arms]


def pilot_selection(tasks: Sequence["Task"]) -> List["Task"]:
    """One task per (kind, category), the first by id."""
    chosen: Dict[tuple, "Task"] = {}
    for task in sorted(tasks, key=lambda t: t.id):
        chosen.setdefault((task.kind, task.category), task)
    return list(chosen.values())


def seed_for(task: "Task", seeds: Mapping[str, float]) -> float:
    for key in (f"{task.kind}/{task.category}", task.kind):
        if key in seeds:
            return float(seeds[key])
    return DEFAULT_SEEDS_USD.get(task.kind, max(DEFAULT_SEEDS_USD.values()))


def seeds_from_records(records: Iterable[Mapping[str, Any]], exclude_arms: Sequence[str] = ()) -> Dict[str, float]:
    """Mean measured cost per kind and per kind/category, from pilot records with a known cost."""
    sums: Dict[str, List[float]] = {}
    for record in records:
        if record.get("skipped") or record.get("cost_usd") is None or record.get("arm") in exclude_arms:
            continue
        for key in (record["kind"], f"{record['kind']}/{record['category']}"):
            sums.setdefault(key, []).append(float(record["cost_usd"]))
    return {key: sum(values) / len(values) for key, values in sums.items()}


def estimate(tasks: Sequence["Task"], arms: Sequence["Arm"], k: int,
             seeds: Optional[Mapping[str, float]] = None) -> Dict[str, Any]:
    source = "pilot" if seeds else "default placeholders"
    seeds = dict(DEFAULT_SEEDS_USD, **(seeds or {}))
    paid_arms = [a for a in arms if a.driver != "fake"]
    rows: Dict[tuple, Dict[str, Any]] = {}
    for task in tasks:
        key = (task.kind, task.category)
        row = rows.setdefault(key, {"kind": task.kind, "category": task.category, "tasks": 0,
                                    "seed_usd": seed_for(task, seeds), "runs": 0, "total_usd": 0.0})
        row["tasks"] += 1
        row["runs"] += len(arms) * k
        row["total_usd"] += row["seed_usd"] * len(paid_arms) * k
    ordered = sorted(rows.values(), key=lambda r: (PRIORITY.index(r["kind"]) if r["kind"] in PRIORITY else 99,
                                                   r["category"]))
    return {"rows": ordered, "runs": sum(r["runs"] for r in ordered), "k": k, "arms": [a.id for a in arms],
            "total_usd": round(sum(r["total_usd"] for r in ordered), 2),
            "seed_source": source}


def reservation(task: "Task", cap: float) -> float:
    """Worst case a run may spend. A recovery run's killed step reports no cost (the CLI caps it at `cap`) and the
    resume steps get the per-run cap again, so a recovery run reserves twice its cap."""
    return cap * 2 if task.kind == "recovery" else cap


def run_cap(task: "Task", cli_cap: Optional[float]) -> float:
    """Per-run cap: the task's budget_usd, lowered by --budget-usd when given."""
    return min(task.budget_usd, cli_cap) if cli_cap is not None else task.budget_usd


class Ledger:
    """Total-budget accounting. A run with an unknown cost is charged its worst case (see `reservation`)."""

    def __init__(self, total_cap: Optional[float]) -> None:
        self.total_cap = total_cap
        self.spent = 0.0
        self.runs = 0
        self.unknown_cost_runs = 0

    def can_start(self, cap: float) -> bool:
        return self.total_cap is None or self.spent + cap <= self.total_cap + EPSILON

    def charge(self, cost: Optional[float], cap: float) -> float:
        amount = cap if cost is None else float(cost)
        self.unknown_cost_runs += int(cost is None)
        self.spent += amount
        self.runs += 1
        return amount

    @property
    def remaining(self) -> Optional[float]:
        return None if self.total_cap is None else max(self.total_cap - self.spent, 0.0)
