#!/usr/bin/env bash
# Keep the public hub generic (plug-and-play AC-11). Exit 1 on any violation.
#
#   scripts/check-generic.sh                 run the checks
#   scripts/check-generic.sh --add <tier> "<term>"   add a term (stored only as a hash; tier: org | private)
#
# Checks:
#   1. `git ls-files overlays/` lists only overlays/_template/ (overlays hold org content and stay gitignored).
#   2. "private" terms (partner names, private repo names) appear in no tracked or new (unignored) file.
#   3. "org" terms (the originating org and its product repos) appear in no tracked file outside the
#      records under docs/ (plans, reviews, validation and the migration guide keep history).
# docs/research/ is excluded from both checks (AC-11): it is the calibration corpus. Its hit count is still
# printed as a notice, so it stays visible.
# Terms live in scripts/generic-terms.sha256 as SHA-256 hashes of their compact form (lowercase letters and
# digits only, so "Acme-Corp", "acme corp" and "AcmeCorp" are one term), and the public repo never contains
# the words it guards against. Matching hashes the compact form of every 1- to 5-word window of each file.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HUB
exec python3 - "$@" <<'PY'
from __future__ import annotations  # Python 3.8+
import hashlib, os, re, subprocess, sys
from pathlib import Path

hub = Path(os.environ["HUB"])
terms_file = hub / "scripts" / "generic-terms.sha256"
WORD = re.compile(r"[a-z0-9]+")
MAX_WORDS = 5
RECORD_PREFIXES = ("docs/",)
EXCLUDED_PREFIXES = ("docs/research/",)
WARN_ONLY: set[str] = set()  # paths whose org-term hits only warn (none since the Phase 4 README rewrite)
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tgz", ".woff", ".woff2")

def normalize(text: str) -> str:
    return " ".join(WORD.findall(text.lower()))

def compact(phrase: str) -> str:
    return phrase.replace(" ", "")

def digest(phrase: str) -> str:
    return hashlib.sha256(phrase.encode()).hexdigest()

def load_terms() -> dict[str, str]:
    terms: dict[str, str] = {}
    for line in terms_file.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            tier, value = line.split()
            terms[value] = tier
    return terms

def add_term(tier: str, term: str) -> int:
    if tier not in ("org", "private"):
        print("tier must be org or private"); return 2
    phrase = normalize(term)
    if not phrase or len(phrase.split()) > MAX_WORDS:
        print(f"a term must be 1-{MAX_WORDS} words"); return 2
    value = digest(compact(phrase))
    if value in load_terms():
        print("already listed"); return 0
    with terms_file.open("a") as fh:
        fh.write(f"{tier} {value}\n")
    print(f"added one {tier} term ({len(phrase.split())} word(s))")
    return 0

def windows(text: str):
    words = WORD.findall(text.lower())
    for n in range(1, MAX_WORDS + 1):
        for i in range(len(words) - n + 1):
            yield "".join(words[i:i + n])

def tracked_files() -> list[str]:
    # Tracked files plus new files not yet added (so a leak is caught before it is committed).
    out = subprocess.run(["git", "-C", str(hub), "ls-files", "--cached", "--others", "--exclude-standard"],
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f]

def scan(files: list[str], terms: dict[str, str]) -> tuple[list[str], list[str], int]:
    failures, warnings, excluded = [], [], 0
    for rel in files:
        path = hub / rel
        if rel.endswith(SKIP_SUFFIXES) or not path.is_file() or rel == "scripts/generic-terms.sha256":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for phrase in windows(line):
                tier = terms.get(digest(phrase))
                if not tier:
                    continue
                where = f"{rel}:{lineno} ({tier} term)"
                if rel.startswith(EXCLUDED_PREFIXES):
                    excluded += 1
                elif tier == "private":
                    failures.append(where)
                elif rel.startswith(RECORD_PREFIXES):
                    pass
                elif rel in WARN_ONLY:
                    warnings.append(where)
                else:
                    failures.append(where)
    return failures, warnings, excluded

def main() -> int:
    if sys.argv[1:2] == ["--add"]:
        if len(sys.argv) != 4:
            print('usage: check-generic.sh --add <org|private> "<term>"'); return 2
        return add_term(sys.argv[2], sys.argv[3])
    files = tracked_files()
    problems = 0
    stray = [f for f in files if f.startswith("overlays/") and not f.startswith("overlays/_template/")]
    for f in stray:
        print(f"FAIL tracked overlay file (overlays/* must stay gitignored): {f}"); problems += 1
    failures, warnings, excluded = scan(files, load_terms())
    # Report locations only; never print the matched words.
    for where in sorted(set(failures)):
        print(f"FAIL {where}"); problems += 1
    for where in sorted(set(warnings)):
        print(f"WARN {where}")
    if excluded:
        print(f"NOTE {excluded} term hit(s) under {', '.join(EXCLUDED_PREFIXES)} (excluded by AC-11; this corpus is tracked)")
    print(f"\n{len(files)} tracked files, {problems} problem(s), {len(set(warnings))} warning(s)")
    return 1 if problems else 0

sys.exit(main())
PY
