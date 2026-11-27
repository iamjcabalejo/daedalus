"""The configuration key registry: class, type, default, merge operator and allowed levels per key.

Every key documented in templates/workflow-config.example.yml has an entry here, and every entry is
documented there (scripts/test-config.sh U-config-registry-01 fails on drift). Plan P1a §3.4.

Classes:
  preference           nearest wins (TL5 > TL4 > TL3 > TL2 > TL1)
  workflow-preference  nearest wins
  security             monotonic: the anchor is TL1 combined with TL2, else TL2, else the default;
                       TL3-TL5 can only tighten it, with the key's operator
  governance           TL1 only; a TL2 value is kept as advisory when TL1 doesn't set the key
  project-facts        `commands` overrides (trust is decided by trust.effective_commands, §3.8)
  meta                 the per-file `version` marker (validated per file, never merged)
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Tuple

LEVELS: Tuple[str, ...] = ("TL1", "TL2", "TL3", "TL4", "TL5")
TRUSTED_LEVELS: Tuple[str, ...] = ("TL1", "TL2")

PREFERENCE = "preference"
WORKFLOW_PREFERENCE = "workflow-preference"
SECURITY = "security"
GOVERNANCE = "governance"
PROJECT_FACTS = "project-facts"
META = "meta"
CLASSES: Tuple[str, ...] = (PREFERENCE, WORKFLOW_PREFERENCE, SECURITY, GOVERNANCE, PROJECT_FACTS, META)

# Merge operators. `nearest` is the preference merge; the rest are the security operators of §3.4.
NEAREST = "nearest"
MODE_ORDER = "mode-order"
MIN = "min"
MAX_ORDER = "max-order"
UNION = "union"
INTERSECT = "intersect"
TRUSTED_ADD = "trusted-add"
TL2_ONLY = "tl2-only"
OPT_IN_TRUSTED = "opt-in-trusted"
TL1_ONLY = "tl1-authoritative"
PER_COMMAND = "per-command"
PER_FILE = "per-file"
OPERATORS: Tuple[str, ...] = (NEAREST, MODE_ORDER, MIN, MAX_ORDER, UNION, INTERSECT, TRUSTED_ADD, TL2_ONLY,
                              OPT_IN_TRUSTED, TL1_ONLY, PER_COMMAND, PER_FILE)
SECURITY_OPERATORS: Tuple[str, ...] = (MODE_ORDER, MIN, MAX_ORDER, UNION, INTERSECT, TRUSTED_ADD, TL2_ONLY,
                                       OPT_IN_TRUSTED)

# Value types. A key lists the types it accepts; `null` always means "unset" and is never validated.
STRING, INTEGER, BOOLEAN, LIST, MAPPING = "string", "integer", "boolean", "list", "mapping"

# Strictness orders, weakest first.
GUARD_MODES = ("off", "warn", "enforce")
GATE_MODES = ("advisory", "enforce")
TDD_LEVELS = ("off", "bugfix", "strict")
APPROVER_ROLES = ("read", "triage", "write", "maintain", "admin")
TIERS = ("trivial", "standard", "full", "critical")


class Key(NamedTuple):
    """One registry entry. `entry_*` fields describe the values of a mapping-typed key's entries."""

    name: str
    cls: str
    types: Tuple[str, ...]
    default: Any
    op: str
    levels: Tuple[str, ...] = LEVELS
    enum: Optional[Tuple[Any, ...]] = None
    order: Optional[Tuple[str, ...]] = None  # strictness order for mode-order / max-order, weakest first
    items: Optional[str] = None  # element type of a list
    minimum: Optional[int] = None
    entry_types: Optional[Tuple[str, ...]] = None  # mapping-typed keys: the type of each entry's value
    entry_items: Optional[str] = None
    doc: str = ""


def _pref(name: str, types: Tuple[str, ...], default: Any, doc: str, **kw: Any) -> Key:
    return Key(name, PREFERENCE, types, default, NEAREST, doc=doc, **kw)


def _wf(name: str, types: Tuple[str, ...], default: Any, doc: str, **kw: Any) -> Key:
    return Key(name, WORKFLOW_PREFERENCE, types, default, NEAREST, doc=doc, **kw)


def _sec(name: str, types: Tuple[str, ...], default: Any, op: str, doc: str, **kw: Any) -> Key:
    levels = TRUSTED_LEVELS if op in (TRUSTED_ADD, TL2_ONLY) else LEVELS
    return Key(name, SECURITY, types, default, op, levels=levels, doc=doc, **kw)


def _ceiling(name: str, default: Optional[int], doc: str) -> Key:
    return _sec(name, (INTEGER,), default, MIN, doc, minimum=0)


_ENTRIES: List[Key] = [
    Key("version", META, (INTEGER,), 1, PER_FILE, enum=(1,), doc="file format version; only 1 is accepted"),
    # Preferences (template keys).
    _pref("overlay", (STRING,), "none", "name of an installed overlay"),
    _pref("domain", (STRING,), "none", "Argus domain pack (skills/argus-rubric/domains/<name>.md)"),
    _pref("chat", (STRING,), "none", "chat system for /daily-report", enum=("teams", "slack", "none")),
    _pref("ignore", (LIST,), [], "globs never reviewed", items=STRING),
    _pref("house_rules", (LIST,), [], "repo-relative docs with team rules", items=STRING),
    _pref("qa.auth", (STRING,), None, "sign-in notes for qa-tester, or none"),
    _pref("qa.base_url", (STRING,), None, "overrides the UI root's dev URL"),
    _pref("review.header", (STRING,), "Argus review", "first line of an Argus review"),
    _pref("review.max_findings", (INTEGER,), 0, "0 = no cap", minimum=0),
    _pref("review.compare_with", (STRING,), None, "GitHub login whose PR review /argus --compare grades against"),
    _pref("review.severity.overrides", (LIST,), [], "per-category severity caps", items=MAPPING),
    _pref("review.severity.critical_triggers", (LIST,), [], "outcomes that are always critical", items=STRING),
    _pref("review.post.inline", (BOOLEAN,), True, "with --post, add inline comments"),
    _pref("budgets.price_table", (MAPPING,), None, "optional token prices; no built-in prices"),
    _pref("retention.runs_days", (INTEGER,), 30, "days a finished run is kept", minimum=0),
    _pref("retention.failed_runs_days", (INTEGER,), 90, "days a failed run is kept", minimum=0),
    _pref("retention.audit_days", (INTEGER,), 30, "days audit records are kept", minimum=0),
    _pref("runtime.lease_ttl_minutes", (INTEGER,), 30, "run lease time-to-live", minimum=1),
    # Workflow preferences.
    _wf("stacks", (STRING, LIST), "auto", "auto, or an explicit list of packs", items=STRING),
    _wf("extra_stacks", (LIST,), [], "packs always added", items=STRING),
    _wf("tickets.system", (STRING,), "auto", "ticket system", enum=("auto", "linear", "jira", "github", "none")),
    _wf("tickets.key", (STRING,), None, "regex for ticket keys"),
    _wf("tickets.team", (STRING,), None, "default team or project for new tickets"),
    _wf("graph", (STRING,), "auto", "code graph", enum=("auto", "graphify", "none")),
    _wf("tiers.default", (STRING,), "auto", "default risk tier", enum=("auto",) + TIERS),
    _wf("tdd.mode", (STRING,), "off", "TDD mode", enum=TDD_LEVELS),
    _wf("isolation.mode", (STRING,), "none", "run isolation", enum=("none", "run", "layer")),
    _wf("isolation.baseline", (STRING,), "snapshot", "isolation baseline", enum=("snapshot", "head")),
    _wf("isolation.dependencies", (STRING,), "none", "dependency handling in isolation",
        enum=("clone", "install", "link", "none")),
    _wf("isolation.root", (STRING,), None, "folder for isolated copies"),
    _wf("isolation.ttl_days", (INTEGER,), 7, "days an isolated copy is kept", minimum=0),
    _wf("parallel.enabled", (BOOLEAN,), False, "parallel layers (benchmark-driven)"),
    _wf("specs.system", (STRING,), "auto", "spec system", enum=("auto", "openspec", "none")),
    # Security (monotonic).
    _sec("guard.mode", (STRING,), "enforce", MODE_ORDER, "guard mode", enum=GUARD_MODES, order=GUARD_MODES),
    _sec("guard.readonly_bash_allow", (LIST,), [], TRUSTED_ADD, "extra read-only command prefixes", items=STRING),
    _ceiling("budgets.rework_rounds", 3, "rework rounds ceiling"),
    _ceiling("budgets.qa_rounds", 2, "QA rounds ceiling"),
    _ceiling("budgets.run_tokens.soft", None, "soft token ceiling per run (null = none)"),
    _ceiling("budgets.run_tokens.hard", None, "hard token ceiling per run (null = none)"),
    _ceiling("budgets.attempt.tool_calls", 200, "tool calls per agent attempt"),
    _ceiling("budgets.attempt.wall_minutes", 45, "minutes per agent attempt"),
    _sec("budgets.role_turns", (MAPPING,), {"implementer": 60, "test-runner": 40, "argus": 40, "qa-tester": 60},
         MIN, "turns per role invocation (each entry: min wins)", entry_types=(INTEGER,), minimum=0),
    _sec("tdd.min", (STRING,), "off", MAX_ORDER, "TDD floor", enum=TDD_LEVELS, order=TDD_LEVELS),
    _ceiling("tiers.trivial_max_files", 3, "most files a trivial change may touch"),
    _sec("tiers.floors", (MAPPING,), {}, MAX_ORDER, "dimension -> minimum tier (each entry: max wins)",
         entry_types=(STRING,), enum=TIERS, order=TIERS),
    _sec("tiers.steps", (MAPPING,), {}, UNION, "tier -> required steps (each entry: union)",
         entry_types=(LIST,), entry_items=STRING),
    _sec("isolation.share_sensitive", (LIST,), [], TL2_ONLY, "paths shared into isolated copies", items=STRING),
    _ceiling("parallel.max_agents", 2, "most agents at once"),
    _sec("exec.env_passthrough", (LIST,), [], INTERSECT, "environment variables passed to commands", items=STRING),
    _ceiling("exec.timeout_minutes", 20, "command timeout"),
    _sec("gate.mode", (STRING,), "advisory", MODE_ORDER, "merge gate mode", enum=GATE_MODES, order=GATE_MODES),
    _sec("gate.require", (LIST,), ["checks", "review", "qa"], UNION, "evidence the gate requires", items=STRING),
    _sec("gate.non_waivable", (LIST,), [], UNION, "findings that can't be waived", items=STRING),
    _sec("gate.approver_role", (STRING,), "maintain", MAX_ORDER, "role that may approve",
         enum=APPROVER_ROLES, order=APPROVER_ROLES),
    _sec("gate.trusted_classes", (LIST,), ["ci", "human"], INTERSECT, "evidence classes the gate trusts",
         items=STRING),
    _sec("telemetry.export", (STRING,), "none", OPT_IN_TRUSTED, "telemetry export; non-none only from TL1/TL2"),
    # Governance (TL1 only).
    Key("governance.trust_roots", GOVERNANCE, (LIST,), [], TL1_ONLY, levels=("TL1",), items=STRING,
        doc="trust roots (TL1 only)"),
    Key("governance.risk_components", GOVERNANCE, (LIST,), [], TL1_ONLY, levels=("TL1",), items=STRING,
        doc="business-critical components (TL1 only)"),
    # Project facts.
    Key("commands", PROJECT_FACTS, (MAPPING,), {}, PER_COMMAND, levels=("TL1", "TL2", "TL3", "TL4"),
        doc="per-root command overrides; committed ones need trust (§3.8)"),
]

KEYS: Dict[str, Key] = {k.name: k for k in _ENTRIES}
# Mapping-typed keys whose entries are free-form (never flattened further, never "unknown").
MAPPING_KEYS = frozenset(k.name for k in _ENTRIES if MAPPING in k.types)
_PREFIXES = frozenset(".".join(name.split(".")[:i]) for name in KEYS for i in range(1, name.count(".") + 1))


def lookup(name: str) -> Optional[Key]:
    """The registry entry for a dotted key, or None."""
    return KEYS.get(name)


def is_prefix(name: str) -> bool:
    """True when `name` is a proper prefix of a registry key (for example `tickets` or `budgets.attempt`)."""
    return name in _PREFIXES


def security_keys() -> List[str]:
    return [k.name for k in _ENTRIES if k.cls == SECURITY]


def digest_keys() -> List[str]:
    """Keys whose values the policy digest covers: security and governance (§3.6)."""
    return [k.name for k in _ENTRIES if k.cls in (SECURITY, GOVERNANCE)]


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def nearest(name: str, max_distance: int = 2) -> Optional[str]:
    """The registry key closest to `name` when its edit distance is at most `max_distance`."""
    best: Optional[Tuple[int, str]] = None
    for candidate in sorted(KEYS):
        if abs(len(candidate) - len(name)) > max_distance:
            continue
        distance = _edit_distance(name, candidate)
        if distance <= max_distance and (best is None or distance < best[0]):
            best = (distance, candidate)
    return best[1] if best else None


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return BOOLEAN
    if isinstance(value, int):
        return INTEGER
    if isinstance(value, str):
        return STRING
    if isinstance(value, list):
        return LIST
    if isinstance(value, dict):
        return MAPPING
    return type(value).__name__


def _check_scalar(value: Any, types: Tuple[str, ...], enum: Optional[Tuple[Any, ...]], items: Optional[str],
                  minimum: Optional[int]) -> Optional[str]:
    kind = _type_name(value)
    if kind not in types:
        return f"expected {' or '.join(types)}, got {kind}"
    if enum is not None and kind in (STRING, INTEGER) and value not in enum:
        return f"expected one of {', '.join(str(e) for e in enum)}, got {value!r}"
    if minimum is not None and kind == INTEGER and value < minimum:
        return f"expected an integer >= {minimum}, got {value}"
    if kind == LIST and items is not None:
        for element in value:
            if _type_name(element) != items:
                return f"expected a list of {items} values, got a {_type_name(element)} entry"
    return None


def check_value(key: Key, value: Any) -> Optional[str]:
    """Why `value` isn't valid for `key`, or None when it is. `None` (unset) is never checked."""
    if value is None:
        return None
    if key.entry_types is not None:
        if not isinstance(value, dict):
            return f"expected a mapping, got {_type_name(value)}"
        for entry, entry_value in value.items():
            if entry_value is None:
                continue
            problem = _check_scalar(entry_value, key.entry_types, key.enum, key.entry_items, key.minimum)
            if problem:
                return f"{entry}: {problem}"
        return None
    return _check_scalar(value, key.types, key.enum, key.items, key.minimum)
