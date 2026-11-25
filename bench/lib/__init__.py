"""Benchmark harness library (stdlib only, Python 3.8+). See bench/README.md.

Shared pieces: hub paths, schema ids, the error type, UTC time, JSON I/O, schema validation through the hub's
validator (.claude/scripts/validate-profile.py, loaded with importlib like scripts/test-detector.sh loads the
detector), glob matching and output redaction.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Pattern

BENCH = Path(__file__).resolve().parent.parent
HUB = BENCH.parent
SCHEMA_DIR = BENCH / "schema"
VALIDATOR_PATH = HUB / ".claude" / "scripts" / "validate-profile.py"

HARNESS_VERSION = "0.1.0"
TASK_SCHEMA_ID = "daedalus.bench-task/1"
ARM_SCHEMA_ID = "daedalus.bench-arm/1"
RESULT_SCHEMA_ID = "daedalus.bench/1"

KINDS = ("build", "review", "safety", "recovery")
# Scheduling order when the budget is short (§3.8 budget, step 4).
PRIORITY = ("safety", "build", "recovery", "review")
SEVERITIES = ("critical", "important", "consider")
BOUNDARIES = ("docker", "sandbox", "local")
REDACTED = "<REDACTED>"


class BenchError(Exception):
    """A harness error with context. The CLI prints it and exits 1."""


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_date() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as err:
        raise BenchError(f"cannot read {path}: {err}") from err
    except ValueError as err:
        raise BenchError(f"invalid JSON in {path}: {err}") from err


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


_VALIDATE: Optional[Callable[..., None]] = None


def _validator() -> Callable[..., None]:
    global _VALIDATE
    if _VALIDATE is None:
        spec = importlib.util.spec_from_file_location("daedalus_validate_profile", VALIDATOR_PATH)
        if spec is None or spec.loader is None:
            raise BenchError(f"cannot load the schema validator at {VALIDATOR_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _VALIDATE = module.validate
    return _VALIDATE


def schema_errors(doc: Any, schema_name: str) -> List[str]:
    """Validate `doc` against bench/schema/<schema_name>.schema.json with the hub's validator subset."""
    schema = load_json(SCHEMA_DIR / f"{schema_name}.schema.json")
    errors: List[str] = []
    _validator()(doc, schema, schema, "", errors)
    return errors


def _glob_regex(pattern: str) -> Pattern[str]:
    """`**` crosses directories, `**/` matches zero or more directories, `*` and `?` stay within one segment."""
    if pattern.endswith("/"):
        pattern += "**"
    out: List[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def glob_match(path: str, patterns: Iterable[str]) -> bool:
    return any(_glob_regex(p).match(path) for p in patterns)


_KEYED_SECRET = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?)[A-Z0-9_]*)(\s*[=:]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s\"',;]+)")
_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/=]{8,}"),
)
MIN_SECRET_LEN = 6


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Mask known secret values (e.g. from BENCH_ENV_FILE) and token or key shapes in captured output."""
    for value in sorted({s for s in secrets if s and len(s) >= MIN_SECRET_LEN}, key=len, reverse=True):
        text = text.replace(value, REDACTED)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return _KEYED_SECRET.sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)


def tail(text: str, limit: int = 2000, secrets: Iterable[str] = ()) -> str:
    """The last `limit` characters of captured output, redacted before the cut so no key fragment survives."""
    return redact(text, secrets)[-limit:]


def read_env_file(path: Optional[str]) -> Dict[str, str]:
    """Parse a docker-style env file (KEY=VALUE per line, # comments). Values are never printed."""
    if not path:
        return {}
    values: Dict[str, str] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise BenchError(f"cannot read BENCH_ENV_FILE ({path}): {err.strerror}") from err
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise BenchError(f"BENCH_ENV_FILE line {number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        values[key.strip()] = value
    return values
