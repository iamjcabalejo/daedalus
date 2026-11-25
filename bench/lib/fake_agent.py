#!/usr/bin/env python3
"""Fake arm agent (bench/arms/fake.json): applies a known patch or prints known findings. Never calls a model.

Runs inside the boundary with the workspace as its cwd, like a real arm step, and prints stream-json events
shaped like the CLI's (init, assistant tool_use, user tool_result, result with usage and total_cost_usd), so the
whole pipeline (capture, parsing, budget, scoring) runs end to end in tests and dry runs.

Usage: fake_agent.py --input <fake-input.json> [--prompt TEXT]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

VERSION = "fake-agent/1"


def emit(event: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def first_patched_file(patch: str) -> str:
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            return line[len("+++ b/"):]
    return ""


def apply_patch(patch: str) -> Optional[str]:
    """None on success, else the error text."""
    proc = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "apply", "--whitespace=nowarn", "-"],
                          input=patch.encode("utf-8"), capture_output=True)
    return None if proc.returncode == 0 else proc.stderr.decode("utf-8", "replace").strip() or "git apply failed"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True)
    parser.add_argument("--prompt", default="")
    args = parser.parse_args(argv)
    try:
        with open(args.input, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as err:
        print(f"fake_agent: cannot read {args.input}: {err}", file=sys.stderr)
        return 2
    usage = {"input_tokens": int(data.get("input_tokens", 0)), "output_tokens": int(data.get("output_tokens", 0)),
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    emit({"type": "system", "subtype": "init", "model": "none", "claude_code_version": VERSION,
          "session_id": "fake-session"})
    error = None
    patch = data.get("patch")
    if patch:
        emit({"type": "assistant", "message": {"id": "fake-msg-1", "usage": usage, "content": [
            {"type": "tool_use", "id": "fake-tool-1", "name": "Edit",
             "input": {"file_path": first_patched_file(patch)}}]}})
        time.sleep(float(data.get("pause_s", 0)))  # lets tests kill the step between the tool_use and the edit
        error = apply_patch(patch)
        emit({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "fake-tool-1", "is_error": error is not None,
             "content": error or "patch applied"}]}})
    findings = data.get("findings")
    result_text = json.dumps(findings) if findings is not None else "Applied the known patch. Assumptions: none."
    emit({"type": "result", "subtype": "error" if error else "success", "is_error": error is not None,
          "result": result_text, "total_cost_usd": float(data.get("cost_usd", 0.0)), "usage": usage, "num_turns": 1})
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
