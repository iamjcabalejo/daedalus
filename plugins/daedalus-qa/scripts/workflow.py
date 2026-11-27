#!/usr/bin/env python3
"""Daedalus command line: one entry point for configuration, trust and (from P1c) runs.

Usage:
  workflow.py config resolve  [--json] [--set KEY=VALUE ...] [--workspace DIR] [--repo DIR]
  workflow.py config explain KEY [--json] [--set KEY=VALUE ...] [--workspace DIR] [--repo DIR]
  workflow.py config get KEY  [--json] [--set KEY=VALUE ...] [--workspace DIR] [--repo DIR]
  workflow.py config commands [--json] [--workspace DIR] [--repo DIR]
  workflow.py trust list|pending [--json] [--workspace DIR] [--repo DIR]
  workflow.py trust record (--pending --digest SET_DIGEST | --root R --name N [--channel profile|config]) [--json]
  workflow.py trust revoke [--root R --name N [--channel profile|config]] [--json]

Exit codes: 0 ok, 2 usage, 3 configuration or trust-store error (E_TRUST_STORE_UNSAFE, E_TRUST_STORE_INVALID,
E_TRUST_SET_CHANGED, E_REPO_ID). Errors print {code, message, fix} on stderr, and with
--json also as {"error": {...}} on stdout. Run it as `python3 -I workflow.py ...`: only this file's own
folder is put on sys.path, never the current folder (PF-2).

Python 3.8+, standard library only.
"""
from __future__ import annotations

import os
import sys

if sys.version_info < (3, 8):
    sys.exit("workflow.py needs Python 3.8 or newer")

_HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, _HERE)

import argparse  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
from typing import Any, Dict, List, Optional, Sequence  # noqa: E402

# The static group table: subcommand group → module (under lib/) → help. Each module provides
# `add_cli(parser)` and `run_cli(args) -> int`. P1c adds the runtime groups here.
GROUPS = (
    ("config", "lib.wfconfig", "resolve, explain and read configuration (TL1-TL5)"),
    ("trust", "lib.trust", "list, record and revoke trusted commands"),
)

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_CONFIG = 0, 1, 2, 3


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:  # argparse calls this for every usage problem
        raise _UsageError(f"{self.prog}: {message}")


def _report(code: str, message: str, fix: str, as_json: bool, extra: Optional[Dict[str, Any]] = None) -> None:
    error: Dict[str, Any] = {"code": code, "message": message, "fix": fix}
    error.update(extra or {})
    print(f"error: {code}: {message}\nfix: {fix}", file=sys.stderr)
    if as_json:
        print(json.dumps({"error": error}, ensure_ascii=False))


def _build(argv: Sequence[str]) -> argparse.ArgumentParser:
    parser = _Parser(prog="workflow.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    groups = parser.add_subparsers(dest="group", metavar="GROUP")
    wanted = next((a for a in argv if not a.startswith("-")), None)
    for name, module_name, help_text in GROUPS:
        group = groups.add_parser(name, help=help_text, description=help_text)
        if name == wanted:
            module = importlib.import_module(module_name)
            module.add_cli(group)
            group.set_defaults(_module=module)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    from lib.wfconfig import ConfigError, UsageError

    try:
        args = _build(argv).parse_args(argv)
        if not getattr(args, "group", None) or not hasattr(args, "_module"):
            _report("E_USAGE", "missing a command group", "run `workflow.py --help`", as_json)
            return EXIT_USAGE
        return int(args._module.run_cli(args))
    except (_UsageError, UsageError) as err:
        _report("E_USAGE", str(err), getattr(err, "fix", "run `workflow.py <group> <action> --help`"), as_json)
        return EXIT_USAGE
    except ConfigError as err:
        _report(err.code, err.message, err.fix, as_json,
                {"file": err.file, "line": err.line, "col": err.col, "construct": err.construct})
        return EXIT_CONFIG
    except NotImplementedError as err:
        _report("E_NOT_IMPLEMENTED", str(err),
                "treat every committed command as untrusted: ask the user before running it", as_json)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
