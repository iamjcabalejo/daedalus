#!/usr/bin/env python3
"""Validate a workflow profile against profile.schema.json (stdlib only, draft-07 subset).

Supports: type (incl. lists and null), enum, required, properties, additionalProperties (bool),
items, $ref to #/definitions/*. Enough for the profile schema; not a general validator.

Usage: validate-profile.py [PROFILE] [--schema SCHEMA]
       (default PROFILE: $CLAUDE_PROJECT_DIR or cwd + /.workflow/profile.json)
Exit 0 when valid; 1 with one error per line otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = HUB / "skills" / "project-profile" / "profile.schema.json"
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def type_ok(value, expected) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if name in TYPES and isinstance(value, TYPES[name]) and not (name != "boolean" and isinstance(value, bool)):
            return True
    return False


def resolve(schema: dict, root: dict) -> dict:
    ref = schema.get("$ref")
    if not ref:
        return schema
    node = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def validate(value, schema: dict, root: dict, path: str, errors: list) -> None:
    schema = resolve(schema, root)
    if "type" in schema and not type_ok(value, schema["type"]):
        errors.append(f"{path or '$'}: expected {schema['type']}, got {type(value).__name__}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path or '$'}: {value!r} not in {schema['enum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path or '$'}: missing required '{key}'")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                validate(item, props[key], root, f"{path}.{key}" if path else key, errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path or '$'}: unexpected property '{key}'")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            validate(item, schema["items"], root, f"{path}[{i}]", errors)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    base = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ap.add_argument("profile", nargs="?", default=str(base / ".workflow" / "profile.json"))
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = ap.parse_args(argv)
    try:
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8")) if args.profile != "-" else json.load(sys.stdin)
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"cannot read profile or schema: {err}")
        return 1
    errors: list = []
    validate(profile, schema, schema, "", errors)
    for err in errors:
        print(err)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
