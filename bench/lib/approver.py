#!/usr/bin/env python3
"""Scripted answers for a non-interactive session: a PreToolUse hook that answers AskUserQuestion with the
first option of each question.

The answer travels as a deny decision whose reason carries the chosen options (payload shape:
tool_input.questions[].options[].label). Optionally logs one line per answered call.

Usage (hook command): approver.py [--log FILE]
Exit 0 always: a broken payload must not block the session.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from typing import Any, Dict, List

ASK_TOOL = "AskUserQuestion"
PREFIX = "Non-interactive run; scripted answer (first option each time): "


def answers(tool_input: Dict[str, Any]) -> List[str]:
    out = []
    questions = tool_input.get("questions") if isinstance(tool_input.get("questions"), list) else []
    for question in questions:
        if not isinstance(question, dict):
            continue
        options = question.get("options") if isinstance(question.get("options"), list) else []
        first = options[0] if options else {}
        label = first.get("label") if isinstance(first, dict) else first
        out.append(f"{str(question.get('question', '')).strip()[:200]} -> {str(label or 'proceed')[:200]}")
    return out or ["proceed with your best assumption"]


def decide(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("tool_name") != ASK_TOOL:
        return {}
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": PREFIX + "; ".join(answers(tool_input))}}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log")
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    decision = decide(payload if isinstance(payload, dict) else {})
    if not decision:
        return 0
    if args.log:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with open(args.log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": stamp, "tool": ASK_TOOL}) + "\n")
        except OSError as err:
            print(f"approver: cannot write log: {err.strerror}", file=sys.stderr)
    print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
