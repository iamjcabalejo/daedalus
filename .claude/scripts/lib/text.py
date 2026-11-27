"""Hidden characters: the one rule the trust library and the session hook share (rework-3, finding 1ef278f-5).

A command, root path or name a person approves or reads must show everything it holds on one terminal line. A
line break splits it; a character in HIDDEN_CATEGORIES (control characters such as ESC, which starts terminal
escape sequences; format characters such as bidi overrides and zero-width spaces; surrogates; private-use and
unassigned code points; line and paragraph separators) can hide or reorder part of it. Every LINE_BREAK
character is in HIDDEN_CATEGORIES too; callers check line breaks first so they keep their own reason.

Not in unsafe.py: detect-stack.py's rules_digest hashes that file. Python 3.8+, standard library only.
"""
from __future__ import annotations

import re
import unicodedata

HIDDEN_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
# Every character str.splitlines() breaks on.
LINE_BREAK = re.compile(r"[\n\r\v\f\x1c\x1d\x1e\x85  ]")


def is_hidden(char: str) -> bool:
    """True when the one character `char` is in HIDDEN_CATEGORIES."""
    return unicodedata.category(char) in HIDDEN_CATEGORIES


def has_line_break(value: str) -> bool:
    """True when `value` would print on more than one line."""
    return LINE_BREAK.search(value) is not None


def has_hidden(value: str) -> bool:
    """True when `value` holds a character in HIDDEN_CATEGORIES (a line break included)."""
    # str.isprintable() is False for every hidden category (and for spaces other than U+0020): a fast "none".
    return not value.isprintable() and any(is_hidden(char) for char in value)


def strip_hidden(value: str) -> str:
    """`value` without its hidden characters (free text the banner shows on one line)."""
    return value if value.isprintable() else "".join(char for char in value if not is_hidden(char))


def escape_hidden(value: str) -> str:
    """`value` with each hidden character written as its Python escape (`\\x1b`, `\\t`, `\\u202e`): one line that
    shows everything it holds. Other text, backslashes included, is unchanged."""
    if value.isprintable():
        return value
    return "".join(char.encode("unicode_escape").decode("ascii") if is_hidden(char) else char for char in value)
