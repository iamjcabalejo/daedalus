#!/usr/bin/env bash
# Lint the shared stack packs in .claude/skills/stacks/ (plug-and-play Phase 2, AC-7).
#
#   scripts/lint-packs.sh          lint every pack; exit 1 on any problem
#   scripts/lint-packs.sh go iac   lint only these packs
#
# A pack is any *.md in the folder except SKILL.md, failure-modes.md, _generic.md and _template.md.
# Each pack must have:
#   - frontmatter whose `name` equals the file name, a `detect:` block with a non-empty `files` list,
#     and an `evidence` line;
#   - the sections ## Build, ## Review, ## Test, ## Commands and ## Entry points (scan mode), in that order,
#     each with at least one non-blank line;
#   - ### How the failure modes show up under ## Review, citing only FM-01..FM-19;
#   - fewer than 500 lines.
# The folder must also hold _generic.md (with ## Build, ## Review, ## Test, ## Commands) and failure-modes.md.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HUB
exec python3 - "$@" <<'PY'
from __future__ import annotations  # Python 3.8+
import os, re, sys
from pathlib import Path

folder = Path(os.environ["HUB"]) / ".claude/skills/stacks"
NOT_PACKS = {"SKILL.md", "failure-modes.md", "_generic.md", "_template.md"}
PACK_SECTIONS = ["Build", "Review", "Test", "Commands", "Entry points (scan mode)"]
GENERIC_SECTIONS = ["Build", "Review", "Test", "Commands"]
MAX_LINES = 500
FM_MAX = 19

def sections(text: str) -> dict[str, str]:
    """Map each ## heading to its body (up to the next ## heading or a --- rule)."""
    out: dict[str, str] = {}
    parts = re.split(r"^## +(.+?)\s*$", text, flags=re.M)
    for title, body in zip(parts[1::2], parts[2::2]):
        out[title] = re.split(r"^---\s*$", body, maxsplit=1, flags=re.M)[0]
    return out

def check_sections(text: str, required: list[str]) -> list[str]:
    found = sections(text)
    errors = [f"missing section: ## {s}" for s in required if s not in found]
    errors += [f"empty section: ## {s}" for s in required if s in found and not found[s].strip()]
    order = [s for s in found if s in required]
    if not errors and order != required:
        errors.append(f"sections out of order: {order} (want {required})")
    return errors

def frontmatter(text: str) -> str | None:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return match.group(1) if match else None

def lint_pack(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    fm = frontmatter(text)
    if fm is None:
        return ["no frontmatter"]
    errors: list[str] = []
    name = re.search(r"^name:\s*(\S+)", fm, re.M)
    if not name or name.group(1) != path.stem:
        errors.append(f"frontmatter name {name.group(1) if name else None!r} != file name {path.stem!r}")
    if not re.search(r"^detect:\s*$", fm, re.M):
        errors.append("no detect: block")
    elif not re.search(r"^\s+files:\s*\[\s*\S", fm, re.M):
        errors.append("detect.files is missing or empty")
    if not re.search(r"^evidence:\s*\S", fm, re.M):
        errors.append("no evidence line")
    errors += check_sections(text, PACK_SECTIONS)
    review = sections(text).get("Review", "")
    if "### How the failure modes show up" not in review:
        errors.append("## Review has no '### How the failure modes show up'")
    bad = sorted({fm_id for fm_id in re.findall(r"FM-(\d+)", review) if not 1 <= int(fm_id) <= FM_MAX})
    if bad:
        errors.append(f"unknown failure modes: {', '.join('FM-' + b for b in bad)}")
    lines = text.count("\n")
    if lines >= MAX_LINES:
        errors.append(f"{lines} lines (limit {MAX_LINES})")
    return errors

def main() -> int:
    wanted = set(sys.argv[1:])
    packs = sorted(p for p in folder.glob("*.md") if p.name not in NOT_PACKS and (not wanted or p.stem in wanted))
    problems = 0
    if not wanted:
        for required in ("failure-modes.md", "_generic.md"):
            if not (folder / required).is_file():
                print(f"FAIL {required}: missing"); problems += 1
        if (folder / "_generic.md").is_file():
            for err in check_sections((folder / "_generic.md").read_text(encoding="utf-8"), GENERIC_SECTIONS):
                print(f"FAIL _generic: {err}"); problems += 1
    if wanted - {p.stem for p in packs}:
        print(f"FAIL unknown pack(s): {', '.join(sorted(wanted - {p.stem for p in packs}))}"); problems += 1
    for pack in packs:
        errors = lint_pack(pack)
        problems += len(errors)
        print(f"{'FAIL' if errors else 'ok  '} {pack.stem}" + "".join(f"\n     - {e}" for e in errors))
    print(f"\n{len(packs)} pack(s), {problems} problem(s)")
    return 1 if problems else 0

sys.exit(main())
PY
