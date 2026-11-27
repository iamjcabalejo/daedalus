"""Daedalus configuration: a strict YAML-subset reader and the TL1-TL5 resolver (plan P1a §3.2-§3.6).

    resolve(repo, workspace=None, run_options=None) -> Resolved

reads the sources of §3.3 (organization policy, user, workspace, repository, per-run options), merges
preferences nearest-wins, security keys monotonically (anchor rule and operators, §3.4), governance keys
from TL1 only, and returns the `daedalus.policy/1` document. Nothing here runs project code; the only
subprocess is a read-only `git rev-parse` (through lib/trust.py).

Python 3.8+, standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from . import config_keys as keys

SCHEMA = "daedalus.policy/1"
DIGEST_SCHEMA = "daedalus.policy-digest/1"
MAX_FILE_BYTES = 1024 * 1024
MAX_DEPTH = 32

E_CONFIG_SYNTAX = "E_CONFIG_SYNTAX"
E_CONFIG_VERSION = "E_CONFIG_VERSION"
E_CONFIG_INVALID = "E_CONFIG_INVALID"
E_TRUST_STORE_UNSAFE = "E_TRUST_STORE_UNSAFE"
E_TRUST_STORE_INVALID = "E_TRUST_STORE_INVALID"
E_REPO_ID = "E_REPO_ID"

LINUX_POLICY = Path("/etc/daedalus/policy.yml")
MACOS_POLICY = Path("/Library/Application Support/Daedalus/policy.yml")


class ConfigError(Exception):
    """A configuration error with a code, a message, a fix line and (for files) a position."""

    def __init__(self, code: str, message: str, fix: str, file: Optional[str] = None, line: Optional[int] = None,
                 col: Optional[int] = None, construct: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix
        self.file = file
        self.line = line
        self.col = col
        self.construct = construct

    def to_json(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "fix": self.fix, "file": self.file,
                "line": self.line, "col": self.col, "construct": self.construct}

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# ---------- canonical JSON (the same rules as P1b's artifacts.canonical_bytes) ----------

def canonical_bytes(value: Any) -> bytes:
    """Sorted keys, (",", ":") separators, UTF-8, no NaN or infinity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_tag(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ---------- YAML subset (§3.2) ----------

_PLAIN_KEY = re.compile(r"[A-Za-z0-9_.-]+\Z")
_INT = re.compile(r"-?[0-9]+\Z")
_LEADING_ZERO = re.compile(r"-?0[0-9]+\Z")
_FLOAT = re.compile(r"[-+]?(\.[0-9]+|[0-9][0-9_]*\.[0-9_]*|[0-9][0-9_]*[eE][-+]?[0-9]+)([eE][-+]?[0-9]+)?\Z"
                    r"|[-+]?\.(inf|Inf|INF)\Z|\.(nan|NaN|NAN)\Z")
_OTHER_NUMBER = re.compile(r"\+[0-9]+\Z|0[xX][0-9a-fA-F_]+\Z|0[oO][0-7_]+\Z|0[bB][01_]+\Z"
                           r"|[-+]?[0-9][0-9_]*_[0-9_]*\Z|[-+]?[0-9]+(:[0-5]?[0-9])+(\.[0-9]*)?\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}([Tt ].*)?\Z")
_YAML11_BOOLS = {"yes", "no", "on", "off"}
_INDICATORS = {"&": "anchor", "*": "alias", "!": "tag", "|": "block scalar", ">": "block scalar",
               "%": "reserved indicator", "@": "reserved indicator", "`": "reserved indicator"}
_FLOW_END = ",[]{}"

# construct -> (why, fix)
_EXPLAIN: Dict[str, Tuple[str, str]] = {
    "anchor": ("anchors aren't supported", "repeat the value instead of anchoring it"),
    "alias": ("aliases aren't supported", "repeat the value instead of referring to an anchor"),
    "tag": ("tags aren't supported", "remove the tag; values are typed by their spelling"),
    "block scalar": ("block scalars (| and >) aren't supported", "write the value on one line, quoted"),
    "multiple documents": ("only one document is allowed", "keep one document; remove the extra '---'"),
    "document end marker": ("'...' isn't supported", "remove the '...' line"),
    "directive": ("directives aren't supported", "remove the directive line"),
    "content after document marker": ("nothing may follow '---' on its line", "move the content to the next line"),
    "complex key": ("complex keys aren't supported", "use a plain or quoted key"),
    "merge key": ("merge keys (<<) aren't supported", "repeat the keys instead of merging"),
    "duplicate key": ("a key appears twice in one mapping", "keep one of the two entries"),
    "tab indentation": ("tabs can't indent", "indent with spaces"),
    "tab character": ("tabs are only allowed inside quoted strings", "use spaces"),
    "ambiguous boolean": ("only lowercase true and false are booleans", "write true or false, or quote the text"),
    "ambiguous null": ("only null and ~ are null", "write null, or quote the text"),
    "unquoted float": ("floats aren't supported", "quote the value, or use an integer"),
    "ambiguous number": ("only plain decimal integers are numbers", "quote the value, or write a decimal integer"),
    "unquoted date": ("dates aren't a supported type", "quote the date"),
    "multi-line flow collection": ("a flow collection must close on its line", "keep [..] or {..} on one line, "
                                   "or use a block list or mapping"),
    "multi-line plain scalar": ("a value must fit on the key's line", "put the value on one line, quoted if needed"),
    "multi-line quoted scalar": ("a quoted string must close on its line", "close the quote on the same line"),
    "unsupported escape": ("only \\\" \\\\ \\n \\t and \\uXXXX escapes are supported", "use a supported escape"),
    "unsupported plain key": ("plain keys may hold only letters, digits, '_', '.' and '-'", "quote the key"),
    "colon in plain scalar": ("': ' inside an unquoted value is ambiguous", "quote the value"),
    "reserved indicator": ("this character can't start an unquoted value", "quote the value"),
    "flow indicator": ("',', ']' and '}' can't start an unquoted value", "quote the value"),
    "inconsistent indentation": ("entries of one block must share one indentation", "align the entry with its "
                                 "siblings"),
    "sequence entry in a mapping": ("a list entry can't sit between mapping keys", "indent the list under its key"),
    "block sequence on the key's line": ("a block list must start on the next line", "move '- item' to its own "
                                         "line, or use [a, b]"),
    "text after value": ("unexpected text after the value", "remove it, or quote the whole value"),
    "flow syntax": ("malformed flow collection", "write [a, b] or {k: v, k2: v2}"),
    "empty flow entry": ("empty entries and trailing commas aren't supported", "remove the extra comma"),
    "flow mapping entry without a value": ("each flow mapping entry needs 'key: value'", "add ': value'"),
    "implicit mapping in flow sequence": ("'k: v' inside [..] is ambiguous", "quote it, or use {k: v}"),
    "nesting too deep": (f"nesting is limited to {MAX_DEPTH} levels", "flatten the structure"),
    "top level is not a mapping": ("a configuration file must be a mapping", "write key: value pairs"),
    "not UTF-8": ("the file isn't valid UTF-8", "save it as UTF-8"),
    "file too large": (f"the file is over {MAX_FILE_BYTES} bytes", "shorten it"),
}


class _Line(NamedTuple):
    no: int
    indent: int
    text: str


def _syntax(construct: str, file: str, line: int, col: int, snippet: str = "") -> ConfigError:
    why, fix = _EXPLAIN[construct]
    shown = f" `{snippet}`" if snippet else ""
    return ConfigError(E_CONFIG_SYNTAX, f"{construct}{shown} at {file}:{line}:{col}; {why}", fix,
                       file=file, line=line, col=col, construct=construct)


def _snippet(text: str, col0: int) -> str:
    token = re.match(r"\S{1,40}", text[col0:])
    return token.group(0) if token else ""


class _Parser:
    def __init__(self, text: str, file: str) -> None:
        self.file = file
        self.positions: Dict[Tuple[Any, ...], Tuple[int, int]] = {}
        self.lines = self._content_lines(text)

    # -- lines --

    def _err(self, construct: str, line: int, col0: int, text: str = "") -> ConfigError:
        return _syntax(construct, self.file, line, col0 + 1, _snippet(text, col0) if text else "")

    def _content_lines(self, text: str) -> List[_Line]:
        if text.startswith("﻿"):
            text = text[1:]
        out: List[_Line] = []
        seen_marker = False
        for no, raw in enumerate(text.split("\n"), 1):
            line = raw[:-1] if raw.endswith("\r") else raw
            stripped = line.lstrip(" \t")
            if not stripped:
                continue
            lead = line[: len(line) - len(stripped)]
            if "\t" in lead:
                raise self._err("tab indentation", no, lead.index("\t"))
            indent = len(lead)
            if stripped.startswith("#"):
                continue
            tab = self._tab_outside_quotes(line, indent)
            if tab is not None:
                raise self._err("tab character", no, tab)
            if indent == 0 and self._is_marker(line, "---"):
                if seen_marker or out:
                    raise self._err("multiple documents", no, 0, line)
                rest = line[3:].strip()
                if rest and not rest.startswith("#"):
                    raise self._err("content after document marker", no, line.index(rest), line)
                seen_marker = True
                continue
            if indent == 0 and self._is_marker(line, "..."):
                raise self._err("document end marker", no, 0, line)
            if indent == 0 and line.startswith("%"):
                raise self._err("directive", no, 0, line)
            out.append(_Line(no, indent, line))
        return out

    @staticmethod
    def _is_marker(line: str, marker: str) -> bool:
        return line.startswith(marker) and (len(line) == 3 or line[3] in " #")

    @staticmethod
    def _tab_outside_quotes(line: str, start: int) -> Optional[int]:
        quote = ""
        i = start
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == "\\" and quote == '"':
                    i += 2
                    continue
                if ch == quote:
                    quote = ""
            elif ch in "\"'" and (i == start or line[i - 1] in " [{,:-"):
                quote = ch
            elif ch == "#" and i > start and line[i - 1] == " ":
                return None
            elif ch == "\t":
                return i
            i += 1
        return None

    # -- document --

    def parse(self) -> Any:
        if not self.lines:
            return None
        first = self.lines[0]
        if first.indent != 0:
            raise self._err("inconsistent indentation", first.no, 0, first.text)
        value, idx = self._block(0, 0, ())
        if idx < len(self.lines):
            line = self.lines[idx]
            raise self._err("inconsistent indentation", line.no, line.indent, line.text)
        return value

    def _is_entry(self, line: _Line) -> bool:
        rest = line.text[line.indent:]
        return rest == "-" or rest.startswith("- ")

    def _block(self, idx: int, indent: int, path: Tuple[Any, ...]) -> Tuple[Any, int]:
        if len(path) >= MAX_DEPTH:
            line = self.lines[idx]
            raise self._err("nesting too deep", line.no, line.indent, line.text)
        line = self.lines[idx]
        if self._is_entry(line):
            return self._sequence(idx, indent, path, stop_at_key=False)
        if self._key_at(line, indent) is None:
            if not path:
                raise self._err("top level is not a mapping", line.no, indent, line.text)
            raise self._err("multi-line plain scalar", line.no, indent, line.text)
        return self._mapping(idx, indent, path)

    # -- mappings --

    def _mapping(self, idx: int, indent: int, path: Tuple[Any, ...]) -> Tuple[Dict[str, Any], int]:
        result: Dict[str, Any] = {}
        lines = self.lines
        while idx < len(lines):
            line = lines[idx]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise self._err("inconsistent indentation", line.no, line.indent, line.text)
            if self._is_entry(line):
                raise self._err("sequence entry in a mapping", line.no, line.indent, line.text)
            found = self._key_at(line, indent)
            if found is None:
                raise self._err("multi-line plain scalar", line.no, indent, line.text)
            key, value_col = found
            if key in result:
                raise self._err("duplicate key", line.no, indent, line.text)
            key_path = path + (key,)
            self.positions[key_path] = (line.no, indent + 1)
            value, idx = self._value_after_key(idx, indent, value_col, key_path)
            result[key] = value
        return result, idx

    def _value_after_key(self, idx: int, indent: int, value_col: int, path: Tuple[Any, ...]) -> Tuple[Any, int]:
        line = self.lines[idx]
        rest = line.text[value_col:]
        if not rest.strip() or rest.strip().startswith("#"):
            nxt = idx + 1
            if nxt < len(self.lines) and self.lines[nxt].indent > indent:
                return self._block(nxt, self.lines[nxt].indent, path)
            if nxt < len(self.lines) and self.lines[nxt].indent == indent and self._is_entry(self.lines[nxt]):
                return self._sequence(nxt, indent, path, stop_at_key=True)
            return None, nxt
        value, plain = self._inline(line, value_col, path)
        nxt = idx + 1
        if nxt < len(self.lines) and self.lines[nxt].indent > indent:
            bad = self.lines[nxt]
            raise self._err("multi-line plain scalar" if plain else "inconsistent indentation",
                            bad.no, bad.indent, bad.text)
        return value, nxt

    def _key_at(self, line: _Line, col: int) -> Optional[Tuple[str, int]]:
        """(key, column after ': ') when the content at `col` is `key:`, else None. Raises on bad keys."""
        text = line.text
        ch = text[col]
        if ch == "?" and (col + 1 == len(text) or text[col + 1] == " "):
            raise self._err("complex key", line.no, col, text)
        if ch in _INDICATORS:
            raise self._err(_INDICATORS[ch], line.no, col, text)
        if ch in "\"'":
            key, end = self._quoted(text, col, line.no)
            while end < len(text) and text[end] == " ":
                end += 1
            if end < len(text) and text[end] == ":" and (end + 1 == len(text) or text[end + 1] == " "):
                return key, end + 1
            return None
        if ch in "[{":
            _value, end = self._flow(text, col, line.no, 1, None)
            if end < len(text) and text[end] == ":" and (end + 1 == len(text) or text[end + 1] == " "):
                raise self._err("complex key", line.no, col, text)
            return None
        colon = self._plain_colon(text, col)
        if colon is None:
            return None
        key = text[col:colon].rstrip(" ")
        if key == "<<":
            raise self._err("merge key", line.no, col, text)
        if not _PLAIN_KEY.match(key):
            raise self._err("unsupported plain key", line.no, col, text)
        return key, colon + 1

    @staticmethod
    def _plain_colon(text: str, start: int) -> Optional[int]:
        """Index of the first ':' followed by a space or the end of line, before any comment."""
        i = start
        while i < len(text):
            ch = text[i]
            if ch == "#" and i > start and text[i - 1] == " ":
                return None
            if ch == ":" and (i + 1 == len(text) or text[i + 1] == " "):
                return i
            i += 1
        return None

    # -- sequences --

    def _sequence(self, idx: int, indent: int, path: Tuple[Any, ...], stop_at_key: bool) -> Tuple[List[Any], int]:
        items: List[Any] = []
        lines = self.lines
        while idx < len(lines):
            line = lines[idx]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise self._err("inconsistent indentation", line.no, line.indent, line.text)
            if not self._is_entry(line):
                if stop_at_key:
                    break
                raise self._err("inconsistent indentation", line.no, line.indent, line.text)
            item_path = path + (len(items),)
            text = line.text
            content = indent + 1
            while content < len(text) and text[content] == " ":
                content += 1
            if content >= len(text) or text[content] == "#":
                nxt = idx + 1
                if nxt < len(lines) and lines[nxt].indent > indent:
                    value, idx = self._block(nxt, lines[nxt].indent, item_path)
                else:
                    value, idx = None, nxt
                items.append(value)
                continue
            virtual = _Line(line.no, content, text[:indent] + " " + text[indent + 1:])
            if self._is_entry(virtual) or self._key_at(virtual, content) is not None:
                if len(item_path) >= MAX_DEPTH:
                    raise self._err("nesting too deep", line.no, content, text)
                lines[idx] = virtual
                value, idx = self._block(idx, content, item_path)
                items.append(value)
                continue
            value, plain = self._inline(line, content, item_path)
            nxt = idx + 1
            if nxt < len(lines) and lines[nxt].indent > indent:
                bad = lines[nxt]
                raise self._err("multi-line plain scalar" if plain else "inconsistent indentation",
                                bad.no, bad.indent, bad.text)
            items.append(value)
            idx = nxt
        return items, idx

    # -- inline values --

    def _inline(self, line: _Line, col: int, path: Tuple[Any, ...]) -> Tuple[Any, bool]:
        """Parse the value that starts at or after `col`; return (value, is_plain)."""
        text = line.text
        while col < len(text) and text[col] == " ":
            col += 1
        if col >= len(text) or text[col] == "#":
            return None, False
        ch = text[col]
        if ch in "\"'":
            value, end = self._quoted(text, col, line.no)
            self._expect_end(text, end, line.no)
            return value, False
        if ch in "[{":
            value, end = self._flow(text, col, line.no, len(path) + 1, path)
            self._expect_end(text, end, line.no)
            return value, False
        if ch == "-" and (col + 1 == len(text) or text[col + 1] == " "):
            raise self._err("block sequence on the key's line", line.no, col, text)
        if ch == "?" and (col + 1 == len(text) or text[col + 1] == " "):
            raise self._err("complex key", line.no, col, text)
        if ch in _INDICATORS:
            raise self._err(_INDICATORS[ch], line.no, col, text)
        if ch in ",]}":
            raise self._err("flow indicator", line.no, col, text)
        end = len(text)
        comment = text.find(" #", col)
        if comment != -1:
            end = comment
        raw = text[col:end].rstrip(" ")
        colon = self._plain_colon(raw, 0)
        if colon is not None:
            raise self._err("colon in plain scalar", line.no, col + colon, text)
        return self._plain_value(raw, line.no, col), True

    def _expect_end(self, text: str, end: int, line_no: int) -> None:
        rest = text[end:]
        stripped = rest.lstrip(" ")
        if not stripped:
            return
        if stripped.startswith("#") and stripped != rest:
            return
        raise self._err("text after value", line_no, end + (len(rest) - len(stripped)), text)

    def _plain_value(self, raw: str, line_no: int, col: int) -> Any:
        if raw in ("~", "null"):
            return None
        if raw in ("true", "false"):
            return raw == "true"
        if raw.lower() in _YAML11_BOOLS or raw.lower() in ("true", "false"):
            raise _syntax("ambiguous boolean", self.file, line_no, col + 1, raw)
        if raw.lower() == "null":
            raise _syntax("ambiguous null", self.file, line_no, col + 1, raw)
        if _INT.match(raw) and not _LEADING_ZERO.match(raw):
            return int(raw)
        if _FLOAT.match(raw):
            raise _syntax("unquoted float", self.file, line_no, col + 1, raw)
        if _LEADING_ZERO.match(raw) or _OTHER_NUMBER.match(raw):
            raise _syntax("ambiguous number", self.file, line_no, col + 1, raw)
        if _DATE.match(raw):
            raise _syntax("unquoted date", self.file, line_no, col + 1, raw)
        return raw

    def _quoted(self, text: str, col: int, line_no: int) -> Tuple[str, int]:
        quote = text[col]
        out: List[str] = []
        i = col + 1
        while i < len(text):
            ch = text[i]
            if quote == "'":
                if ch == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        out.append("'")
                        i += 2
                        continue
                    return "".join(out), i + 1
                out.append(ch)
                i += 1
                continue
            if ch == '"':
                return "".join(out), i + 1
            if ch == "\\":
                i = self._escape(text, i, line_no, out)
                continue
            out.append(ch)
            i += 1
        raise self._err("multi-line quoted scalar", line_no, col, text)

    def _escape(self, text: str, i: int, line_no: int, out: List[str]) -> int:
        nxt = text[i + 1] if i + 1 < len(text) else ""
        simple = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}
        if nxt in simple:
            out.append(simple[nxt])
            return i + 2
        if nxt == "u":
            digits = text[i + 2:i + 6]
            if len(digits) == 4 and all(c in "0123456789abcdefABCDEF" for c in digits):
                code = int(digits, 16)
                if not 0xD800 <= code <= 0xDFFF:
                    out.append(chr(code))
                    return i + 6
        raise self._err("unsupported escape", line_no, i, text)

    # -- flow collections (one line) --

    def _flow(self, text: str, col: int, line_no: int, depth: int,
              path: Optional[Tuple[Any, ...]]) -> Tuple[Any, int]:
        """Parse a one-line flow collection at `col`; record key positions under `path` (None: don't)."""
        if depth > MAX_DEPTH:
            raise self._err("nesting too deep", line_no, col, text)
        opener = text[col]
        closer = "]" if opener == "[" else "}"
        is_map = opener == "{"
        seq: List[Any] = []
        mapping: Dict[str, Any] = {}
        i = self._skip(text, col + 1, line_no, col)
        if text[i] == closer:
            return (mapping if is_map else seq), i + 1
        while True:
            i = self._skip(text, i, line_no, col)
            if text[i] in ",]}":
                raise self._err("empty flow entry" if text[i] in ("," + closer) else "flow syntax", line_no, i, text)
            if is_map:
                key_col = i
                key, i = self._flow_key(text, i, line_no)
                if key in mapping:
                    raise self._err("duplicate key", line_no, key_col, text)
                child = None if path is None else path + (key,)
                if child is not None:
                    self.positions[child] = (line_no, key_col + 1)
                i = self._skip(text, i, line_no, col)
                if text[i] in ",}":
                    mapping[key] = None
                else:
                    mapping[key], i = self._flow_node(text, i, line_no, depth, False, child)
            else:
                child = None if path is None else path + (len(seq),)
                value, i = self._flow_node(text, i, line_no, depth, True, child)
                seq.append(value)
            i = self._skip(text, i, line_no, col)
            if text[i] == ",":
                i = self._skip(text, i + 1, line_no, col)
                if text[i] in ",]}":
                    raise self._err("empty flow entry", line_no, i, text)
                continue
            if text[i] == closer:
                return (mapping if is_map else seq), i + 1
            raise self._err("flow syntax", line_no, i, text)

    def _skip(self, text: str, i: int, line_no: int, opener: int) -> int:
        while i < len(text) and text[i] == " ":
            i += 1
        if i >= len(text) or (text[i] == "#" and text[i - 1] == " "):
            raise self._err("multi-line flow collection", line_no, opener, text)
        return i

    def _flow_key(self, text: str, i: int, line_no: int) -> Tuple[str, int]:
        ch = text[i]
        if ch == "?" and i + 1 < len(text) and text[i + 1] == " ":
            raise self._err("complex key", line_no, i, text)
        if ch in _INDICATORS:
            raise self._err(_INDICATORS[ch], line_no, i, text)
        if ch in "[{":
            raise self._err("complex key", line_no, i, text)
        if ch in "\"'":
            key, end = self._quoted(text, i, line_no)
        else:
            end = i
            while end < len(text) and text[end] not in _FLOW_END and not (
                    text[end] == ":" and (end + 1 == len(text) or text[end + 1] in " ,}")):
                end += 1
            key = text[i:end].rstrip(" ")
            if key == "<<":
                raise self._err("merge key", line_no, i, text)
            if not _PLAIN_KEY.match(key):
                if end >= len(text) or text[end] != ":":
                    raise self._err("flow mapping entry without a value", line_no, i, text)
                raise self._err("unsupported plain key", line_no, i, text)
        if end >= len(text) or text[end] != ":":
            if end >= len(text):
                raise self._err("multi-line flow collection", line_no, i, text)
            raise self._err("flow mapping entry without a value", line_no, i, text)
        if end + 1 < len(text) and text[end + 1] not in " ,}":
            raise self._err("flow syntax", line_no, end, text)
        return key, end + 1

    def _flow_node(self, text: str, i: int, line_no: int, depth: int, in_seq: bool,
                   path: Optional[Tuple[Any, ...]]) -> Tuple[Any, int]:
        ch = text[i]
        if ch in "[{":
            value, end = self._flow(text, i, line_no, depth + 1, path)
            return value, end
        if ch in "\"'":
            value, end = self._quoted(text, i, line_no)
            if in_seq:
                probe = end
                while probe < len(text) and text[probe] == " ":
                    probe += 1
                if probe < len(text) and text[probe] == ":":
                    raise self._err("implicit mapping in flow sequence", line_no, i, text)
            return value, end
        if ch == "?" and i + 1 < len(text) and text[i + 1] == " ":
            raise self._err("complex key", line_no, i, text)
        if ch in _INDICATORS:
            raise self._err(_INDICATORS[ch], line_no, i, text)
        end = i
        while end < len(text) and text[end] not in _FLOW_END and not (text[end] == "#" and text[end - 1] == " "):
            end += 1
        raw = text[i:end].rstrip(" ")
        colon = self._plain_colon(raw, 0)
        if colon is not None or raw.endswith(":"):
            construct = "implicit mapping in flow sequence" if in_seq else "colon in plain scalar"
            raise self._err(construct, line_no, i, text)
        return self._plain_value(raw, line_no, i), end


def parse_yaml(text: str, file: str = "<string>") -> Any:
    """Parse the YAML subset of §3.2; raise ConfigError(E_CONFIG_SYNTAX) naming file, line, column, construct."""
    return _Parser(text, file).parse()


def parse_yaml_positions(text: str, file: str = "<string>") -> Tuple[Any, Dict[Tuple[Any, ...], Tuple[int, int]]]:
    """Like parse_yaml, plus each mapping key's (line, col), keyed by its path tuple."""
    parser = _Parser(text, file)
    return parser.parse(), parser.positions


def parse_value(text: str, file: str = "--set") -> Any:
    """Parse one scalar or one-line flow collection (a TL5 `--set` value)."""
    parser = _Parser("", file)
    line = _Line(1, 0, text)
    if not text.strip():
        return None
    value, _plain = parser._inline(line, 0, ())
    return value


def decode_config(data: bytes, file: str) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise _syntax("file too large", file, 1, 1)
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as err:
        line = data[: err.start].count(b"\n") + 1
        col = err.start - (data.rfind(b"\n", 0, err.start) + 1) + 1
        raise _syntax("not UTF-8", file, line, col) from err


# ---------- sources (§3.3) ----------

LstatFn = Callable[[str], os.stat_result]


class SourceContext:
    """Process facts the resolver reads. Tests inject them; production uses the defaults.

    `lstat` is the ownership seam for the managed-path and DAEDALUS_HOME checks: it is a function
    parameter, never an environment variable, so a repository can't influence it (PF-3).
    """

    def __init__(self, environ: Optional[Mapping[str, str]] = None, passwd_home: Optional[Path] = None,
                 uid: Optional[int] = None, tl1_paths: Optional[Sequence[Path]] = None,
                 lstat: Optional[LstatFn] = None) -> None:
        self.environ: Mapping[str, str] = os.environ if environ is None else environ
        self.uid = os.getuid() if uid is None else uid
        self._passwd_home = passwd_home
        self.tl1_paths: Sequence[Path] = default_policy_paths() if tl1_paths is None else list(tl1_paths)
        self.lstat: LstatFn = os.lstat if lstat is None else lstat

    @property
    def passwd_home(self) -> Path:
        if self._passwd_home is None:
            import pwd

            self._passwd_home = Path(pwd.getpwuid(self.uid).pw_dir)
        return self._passwd_home


def default_policy_paths() -> List[Path]:
    """Platform TL1 paths, lowest first. macOS also reads /etc (its root-owned /etc symlink passes)."""
    if sys.platform == "darwin":
        return [LINUX_POLICY, MACOS_POLICY]
    return [LINUX_POLICY]


def managed_path_problem(path: Path, lstat: LstatFn = os.lstat) -> Optional[str]:
    """Why `path` isn't a managed (root-owned) policy file, or None when it is (§3.3, TL1).

    1. Walking the path as written, every symlink met is owned by uid 0.
    2. Every component of realpath(path) is owned by uid 0 and not group- or world-writable.
    """
    written = os.path.abspath(str(path))
    parts = Path(written).parts
    current = parts[0]
    for part in parts[1:]:
        current = os.path.join(current, part)
        try:
            info = lstat(current)
        except OSError as err:
            return f"can't stat {current}: {err.strerror or err}"
        if stat.S_ISLNK(info.st_mode) and info.st_uid != 0:
            return f"symlink {current} isn't owned by root"
    real = os.path.realpath(written)
    real_parts = Path(real).parts
    current = real_parts[0]
    checks = [current]
    for part in real_parts[1:]:
        current = os.path.join(current, part)
        checks.append(current)
    for component in checks:
        try:
            info = lstat(component)
        except OSError as err:
            return f"can't stat {component}: {err.strerror or err}"
        if info.st_uid != 0:
            return f"{component} isn't owned by root"
        if info.st_mode & 0o022:
            return f"{component} is group- or world-writable"
    try:
        final = lstat(real)
    except OSError as err:
        return f"can't stat {real}: {err.strerror or err}"
    if not stat.S_ISREG(final.st_mode):
        return f"{real} isn't a regular file"
    return None


def daedalus_home_problem(raw: str, repo_top: Path, ctx: SourceContext) -> Optional[str]:
    """Why DAEDALUS_HOME can't replace the user folder, or None when it can (AC-2, PF-3)."""
    from . import trust

    if not os.path.isabs(raw):
        return "not an absolute path"
    real = Path(os.path.realpath(raw))
    if not real.is_dir():
        return "not a directory"
    if real == repo_top or repo_top in real.parents:
        return "inside the target project folder"
    try:
        info = ctx.lstat(str(real))
    except OSError as err:
        return f"can't stat it: {err.strerror or err}"
    if info.st_uid != ctx.uid:
        return "owned by another user"
    if info.st_mode & 0o022:
        return "group- or world-writable"
    if trust.inside_work_tree(real, environ=ctx.environ):
        return "inside a git work tree"
    return None


def user_folder(repo_top: Path, ctx: SourceContext) -> Tuple[Path, Optional[str]]:
    """The TL2 user folder and, when DAEDALUS_HOME was refused, the warning to report."""
    raw = ctx.environ.get("DAEDALUS_HOME", "")
    if not raw:
        return ctx.passwd_home, None
    problem = daedalus_home_problem(raw, repo_top, ctx)
    if problem is None:
        return Path(os.path.realpath(raw)), None
    return ctx.passwd_home, f"DAEDALUS_HOME={raw} ignored ({problem}); using the home folder {ctx.passwd_home}"


class Source:
    """One configuration source that was read."""

    def __init__(self, level: str, kind: str, path: Optional[Path], display: str, data: Dict[str, Any],
                 positions: Dict[Tuple[Any, ...], Tuple[int, int]], sha256: Optional[str],
                 demoted_from: Optional[str] = None) -> None:
        self.level = level
        self.kind = kind
        self.path = path
        self.display = display
        self.data = data
        self.positions = positions
        self.sha256 = sha256
        self.demoted_from = demoted_from

    def to_json(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"level": self.level, "path": self.display, "kind": self.kind,
                               "sha256": self.sha256, "version": 1}
        if self.demoted_from:
            out["demoted_from"] = self.demoted_from
        return out

    def line_of(self, path: Tuple[Any, ...]) -> Optional[int]:
        pos = self.positions.get(path)
        return pos[0] if pos else None


def _display(path: Path, repo_top: Path) -> str:
    try:
        return str(path.relative_to(repo_top))
    except ValueError:
        return str(path)


def _lift_legacy(data: Dict[str, Any], positions: Dict[Tuple[Any, ...], Tuple[int, int]]) -> None:
    """Move a legacy .argus.yml top-level `severity` / `post` under `review:` (argus/SKILL.md)."""
    for name in ("severity", "post"):
        if name not in data:
            continue
        value = data.pop(name)
        if data.get("review") is None:
            data["review"] = {}
        review = data["review"]
        if not isinstance(review, dict):
            continue  # the collector reports `review` itself as invalid
        current = review.get(name)
        if isinstance(current, dict) and isinstance(value, dict):
            review[name] = _deep_merge(value, current)
        elif current is None:
            review[name] = value
        for old_path in [p for p in positions if p[:1] == (name,)]:
            positions[("review",) + old_path] = positions.pop(old_path)


def _deep_merge(base: Dict[str, Any], top: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in top.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config_file(path: Path, level: str, kind: str, display: str,
                     demoted_from: Optional[str] = None) -> Optional[Source]:
    """Read and parse one file; None when it doesn't exist. Raises ConfigError on syntax or version errors."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    except OSError as err:
        raise ConfigError(E_CONFIG_INVALID, f"can't read {display}: {err.strerror or err}",
                          "fix the file's permissions, or remove it", file=display) from err
    text = decode_config(data, display)
    parsed, positions = parse_yaml_positions(text, display)
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise _syntax("top level is not a mapping", display, 1, 1)
    _check_version(parsed, positions, display)
    if kind == "legacy":
        _lift_legacy(parsed, positions)
    return Source(level, kind, path, display, parsed, positions, sha256_tag(data), demoted_from)


def _check_version(data: Dict[str, Any], positions: Dict[Tuple[Any, ...], Tuple[int, int]], display: str) -> None:
    if "version" not in data:
        return
    value = data.pop("version")
    if value is None or (isinstance(value, int) and not isinstance(value, bool) and value == 1):
        return
    line, col = positions.get(("version",), (None, None))
    raise ConfigError(E_CONFIG_VERSION, f"unsupported config version {value!r} in {display}"
                      + (f":{line}" if line else "") + "; this Daedalus reads version 1",
                      "set `version: 1`, or upgrade Daedalus", file=display, line=line, col=col,
                      construct="version")


class Discovery(NamedTuple):
    repo_top: Path
    is_git: bool
    workspace: Optional[Path]
    workspace_level: Optional[str]
    user: Path
    sources: List[Source]
    warnings: List[str]
    unmanaged: List[str]


def _workspace_level(workspace: Optional[Path], repo_top: Path, ctx: SourceContext) -> Tuple[Optional[str], str]:
    """("TL3" | "TL4" | None, reason). None means the workspace is the repository itself (nothing to add)."""
    from . import trust

    if workspace is None:
        return None, ""
    if workspace == repo_top:
        return None, ""
    if repo_top not in workspace.parents and workspace not in repo_top.parents:
        return "TL4", "isn't an ancestor of the repository"
    if workspace not in repo_top.parents:
        return "TL4", "is inside the repository"
    if trust.inside_work_tree(workspace, environ=ctx.environ):
        return "TL4", "is inside a git work tree"
    return "TL3", ""


def discover(repo: Path, workspace: Optional[Path], ctx: SourceContext) -> Discovery:
    """Find and parse every source of §3.3, lowest first (TL1 → TL4; TL5 is added by resolve)."""
    from . import trust

    target = Path(os.path.realpath(str(repo)))
    if not target.is_dir():
        raise ConfigError(E_REPO_ID, f"target folder {repo} doesn't exist or isn't a folder",
                          "run from the project folder, or pass --repo <folder>")
    repo_top, is_git = trust.top_level(target)
    warnings: List[str] = []
    unmanaged: List[str] = []
    sources: List[Source] = []

    dpd = ctx.environ.get("DAEDALUS_POLICY_DIR", "")
    tl1: List[Tuple[Path, str]] = []
    if dpd:
        if os.path.isabs(dpd):
            tl1.append((Path(dpd) / "policy.yml", "DAEDALUS_POLICY_DIR"))
        else:
            warnings.append(f"DAEDALUS_POLICY_DIR={dpd} ignored (not an absolute path)")
    tl1.extend((p, "platform") for p in ctx.tl1_paths)
    for path, _origin in tl1:
        if not os.path.lexists(str(path)):
            continue
        problem = managed_path_problem(path, ctx.lstat)
        if problem:
            note = f"policy file {path} exists but isn't managed ({problem}); ignored"
            warnings.append(note)
            unmanaged.append(note)
            continue
        source = load_config_file(path, "TL1", "policy", str(path))
        if source is not None:
            sources.append(source)

    user, home_warning = user_folder(repo_top, ctx)
    if home_warning:
        warnings.append(home_warning)
    for path, kind in ((user / ".claude" / "argus.yml", "legacy"), (user / ".workflow" / "config.yml", "config")):
        source = load_config_file(path, "TL2", kind, str(path))
        if source is not None:
            sources.append(source)

    ws_real = Path(os.path.realpath(str(workspace))) if workspace is not None else None
    if ws_real is not None and not ws_real.is_dir():
        warnings.append(f"workspace {workspace} isn't a folder; ignored")
        ws_real = None
    ws_level, ws_reason = _workspace_level(ws_real, repo_top, ctx)
    if ws_real is not None and ws_level is not None:
        if ws_level == "TL4":
            warnings.append(f"workspace {ws_real} {ws_reason}; its files are read as TL4")
        demoted = "TL3" if ws_level == "TL4" else None
        for path, kind in ((ws_real / ".argus.yml", "legacy"), (ws_real / ".workflow" / "config.yml", "config")):
            source = _load_contained(path, ws_real, ws_level, kind, _display(path, repo_top), warnings, demoted)
            if source is not None:
                sources.append(source)

    for path, kind in ((repo_top / ".argus.yml", "legacy"), (repo_top / ".workflow" / "config.yml", "config")):
        source = _load_contained(path, repo_top, "TL4", kind, _display(path, repo_top), warnings)
        if source is not None:
            sources.append(source)
    return Discovery(repo_top, is_git, ws_real, ws_level, user, sources, warnings, unmanaged)


def _load_contained(path: Path, folder: Path, level: str, kind: str, display: str, warnings: List[str],
                    demoted_from: Optional[str] = None) -> Optional[Source]:
    """Load a workspace or repository file only when its real path stays inside `folder`."""
    if not os.path.lexists(str(path)):
        return None
    real = Path(os.path.realpath(str(path)))
    if folder not in real.parents:
        warnings.append(f"{display} resolves outside {folder}; ignored")
        return None
    return load_config_file(path, level, kind, display, demoted_from)


def _run_source(run_options: Mapping[str, Any]) -> Source:
    data: Dict[str, Any] = {}
    for dotted, value in run_options.items():
        parts = str(dotted).split(".")
        node = data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
    digest = sha256_tag(canonical_bytes(data))
    return Source("TL5", "run", None, "--set", data, {}, digest)


# ---------- resolution (§3.4, §3.5) ----------

class Contribution:
    """A value one source gave one key, and what the resolver did with it."""

    def __init__(self, level: str, source: Source, value: Any, line: Optional[int]) -> None:
        self.level = level
        self.source = source
        self.value = value
        self.line = line
        self.status = "accepted"
        self.reason: Optional[str] = None

    def ignore(self, reason: str, partly: bool = False) -> None:
        self.status = "partly ignored" if partly else "ignored"
        self.reason = reason

    def to_json(self) -> Dict[str, Any]:
        return {"level": self.level, "source": self.source.display, "line": self.line, "value": self.value,
                "status": self.status, "reason": self.reason}


def _unset(value: Any) -> bool:
    return value is None or value == ""


class _Collector:
    def __init__(self) -> None:
        self.by_key: Dict[str, List[Contribution]] = {}
        self.warnings: List[str] = []

    def add(self, key: str, contribution: Contribution) -> None:
        self.by_key.setdefault(key, []).append(contribution)

    def walk(self, source: Source) -> None:
        self._walk(source, source.data, ())

    def _walk(self, source: Source, node: Dict[str, Any], path: Tuple[str, ...]) -> None:
        for name, value in node.items():
            here = path + (name,)
            dotted = ".".join(here)
            dotted_ok = all("." not in part for part in here)
            key = keys.lookup(dotted) if dotted_ok else None
            if key is not None:
                if key.cls == keys.META:
                    continue
                self.add(dotted, Contribution(source.level, source, value, source.line_of(here)))
            elif dotted_ok and keys.is_prefix(dotted):
                if isinstance(value, dict):
                    self._walk(source, value, here)
                elif not _unset(value):
                    contribution = Contribution(source.level, source, value, source.line_of(here))
                    self.add(dotted, contribution)
            elif isinstance(value, dict) and value:
                self._walk(source, value, here)
            else:
                line = source.line_of(here)
                where = f"{source.display}:{line}" if line else source.display
                hint = keys.nearest(dotted)
                self.warnings.append(f"unknown key '{dotted}' in {where}"
                                     + (f" (did you mean '{hint}'?)" if hint else ""))


class _Outcome:
    def __init__(self, value: Any, level: str, source: Optional[str]) -> None:
        self.value = value
        self.level = level
        self.source = source


def _reject_invalid(key: keys.Key, contribution: Contribution, problem: str, warnings: List[str]) -> None:
    where = contribution.source.display + (f":{contribution.line}" if contribution.line else "")
    if contribution.level in keys.TRUSTED_LEVELS:
        raise ConfigError(E_CONFIG_INVALID, f"invalid value for '{key.name}' in {where}: {problem}",
                          f"fix '{key.name}' in {contribution.source.display} (see `workflow.py config explain "
                          f"{key.name}`)", file=contribution.source.display, line=contribution.line)
    contribution.ignore(f"invalid value: {problem}")
    warnings.append(f"invalid value for '{key.name}' in {where} ignored: {problem}")


def _valid(key: keys.Key, contributions: List[Contribution], warnings: List[str]) -> List[Contribution]:
    out = []
    for contribution in contributions:
        if _unset(contribution.value):
            contribution.status = "unset"
            continue
        problem = keys.check_value(key, contribution.value)
        if problem:
            _reject_invalid(key, contribution, problem, warnings)
            continue
        out.append(contribution)
    return out


def _resolve_preference(key: keys.Key, contributions: List[Contribution], warnings: List[str]) -> _Outcome:
    valid = _valid(key, contributions, warnings)
    if not valid:
        return _Outcome(key.default, "default", None)
    winner = valid[-1]
    if keys.MAPPING in key.types and all(isinstance(c.value, dict) for c in valid):
        merged: Dict[str, Any] = {}
        for contribution in valid:
            merged = _deep_merge(merged, contribution.value)
        return _Outcome(merged, winner.level, winner.source.display)
    for contribution in valid[:-1]:
        contribution.status = "overridden"
        contribution.reason = f"a nearer value from {winner.level} ({winner.source.display}) wins"
    return _Outcome(winner.value, winner.level, winner.source.display)


def _resolve_governance(key: keys.Key, contributions: List[Contribution], warnings: List[str],
                        advisory: List[str]) -> _Outcome:
    allowed = []
    for contribution in contributions:
        if contribution.level in ("TL1", "TL2"):
            allowed.append(contribution)
        elif not _unset(contribution.value):
            contribution.ignore("governance keys come from TL1 only")
    valid = _valid(key, allowed, warnings)
    tl1 = [c for c in valid if c.level == "TL1"]
    tl2 = [c for c in valid if c.level == "TL2"]
    if tl1:
        for contribution in tl2:
            contribution.ignore("governance keys come from TL1; a TL2 value is advisory only when TL1 doesn't "
                                "set the key")
        outcome = _resolve_preference(key, tl1, warnings)
        return outcome
    if tl2:
        advisory.append(key.name)
        return _resolve_preference(key, tl2, warnings)
    return _Outcome(key.default, "default", None)


# -- security operators --

def _rank(key: keys.Key, value: Any) -> int:
    assert key.order is not None
    return key.order.index(value)


def _combine(key: keys.Key, current: Any, new: Any) -> Tuple[Any, Optional[str]]:
    """Combine a lower level's `new` into `current`; return (result, what was refused or None)."""
    op = key.op
    if op in (keys.MODE_ORDER, keys.MAX_ORDER):
        if current is None:
            return new, None
        if _rank(key, new) < _rank(key, current):
            return current, f"{new} is weaker than {current}"
        return new, None
    if op == keys.MIN:
        if current is None:
            return new, None
        if new > current:
            return current, f"{new} is above the ceiling {current}"
        return new, None
    if op == keys.UNION:
        base = list(current or [])
        dropped = [item for item in base if item not in new]
        result = base + [item for item in new if item not in base]
        return result, (f"can't remove {', '.join(map(str, dropped))}" if dropped else None)
    if op == keys.INTERSECT:
        base = list(current or [])
        added = [item for item in new if item not in base]
        result = [item for item in base if item in new]
        return result, (f"can't add {', '.join(map(str, added))}" if added else None)
    if op == keys.OPT_IN_TRUSTED:
        if new == "none":
            return "none", None
        if current == new:
            return current, None
        return current, f"'{new}' would turn on export; only TL1 or TL2 may opt in"
    raise ValueError(f"no combine rule for operator {op}")


def _within_level(key: keys.Key, contributions: List[Contribution]) -> Optional[Tuple[Any, Contribution]]:
    """Combine one trusted level's sources with the key's operator (strictest within the level)."""
    result: Optional[Tuple[Any, Contribution]] = None
    for contribution in contributions:
        if result is None:
            result = (contribution.value, contribution)
            continue
        value, refused = _combine(key, result[0], contribution.value)
        if refused:
            contribution.ignore(f"weakens {result[1].level} value ({refused})", partly=value != result[0])
        if value != result[0]:
            result = (value, contribution)
    return result


def _resolve_security_value(key: keys.Key, contributions: List[Contribution], default: Any) -> _Outcome:
    """The anchor rule (PF-5) for one value of a security key; `contributions` are already valid."""
    by_level: Dict[str, List[Contribution]] = {}
    for contribution in contributions:
        by_level.setdefault(contribution.level, []).append(contribution)
    if key.op in (keys.TRUSTED_ADD, keys.TL2_ONLY):
        return _resolve_trusted_add(key, by_level, default)
    tl1 = _within_level(key, by_level.get("TL1", []))
    tl2 = _within_level(key, by_level.get("TL2", []))
    if tl1 is not None:
        value, level, source = tl1[0], "TL1", tl1[1].source.display
        if tl2 is not None:
            combined, refused = _combine(key, value, tl2[0])
            if refused:
                for contribution in by_level["TL2"]:
                    if contribution.status == "accepted":
                        contribution.ignore(f"weakens TL1 value ({refused})", partly=combined != value)
            if combined != value:
                level, source = "TL2", tl2[1].source.display
            value = combined
    elif tl2 is not None:
        value, level, source = tl2[0], "TL2", tl2[1].source.display
    else:
        value, level, source = default, "default", None
    for name in ("TL3", "TL4", "TL5"):
        for contribution in by_level.get(name, []):
            combined, refused = _combine(key, value, contribution.value)
            if refused:
                contribution.ignore(f"weakens {level} value ({refused})", partly=combined != value)
            if combined != value:
                level, source = name, contribution.source.display
            value = combined
    return _Outcome(value, level, source)


def _resolve_trusted_add(key: keys.Key, by_level: Dict[str, List[Contribution]], default: Any) -> _Outcome:
    """trusted-add and tl2-only: the union of the default, TL1 and TL2; TL3-TL5 can't set the key."""
    value = list(default or [])
    level, source = "default", None
    for name in ("TL1", "TL2"):
        for contribution in by_level.get(name, []):
            added = [item for item in contribution.value if item not in value]
            if added:
                value = value + added
                level, source = name, contribution.source.display
    for name in ("TL3", "TL4", "TL5"):
        for contribution in by_level.get(name, []):
            contribution.ignore("only TL1 and TL2 may set it")
    return _Outcome(value, level, source)


def _resolve_security(key: keys.Key, contributions: List[Contribution], warnings: List[str],
                      entries: Dict[str, Dict[str, Any]]) -> _Outcome:
    valid = _valid(key, contributions, warnings)
    if key.entry_types is None:
        return _resolve_security_value(key, valid, key.default)
    names: List[str] = list((key.default or {}).keys())
    for contribution in valid:
        names.extend(n for n in contribution.value if n not in names)
    result: Dict[str, Any] = {}
    best_level, best_source = "default", None
    for name in names:
        entry_contributions = []
        for contribution in valid:
            entry_value = contribution.value.get(name)
            if _unset(entry_value):
                continue
            entry_contributions.append(Contribution(contribution.level, contribution.source, entry_value,
                                                    contribution.source.line_of(_key_path(key.name) + (name,))))
        outcome = _resolve_security_value(key, entry_contributions, (key.default or {}).get(name))
        for entry_contribution in entry_contributions:
            if entry_contribution.status in ("ignored", "partly ignored"):
                for parent in valid:
                    if parent.source is entry_contribution.source and parent.status in ("accepted",
                                                                                         "entries ignored"):
                        parent.status = "entries ignored"
                        parent.reason = (parent.reason + ", " if parent.reason else "entries ignored: ") + name
        entries[f"{key.name}.{name}"] = {"outcome": outcome, "contributions": entry_contributions}
        if outcome.value is not None:
            result[name] = outcome.value
        if outcome.level != "default" and keys.LEVELS.index(outcome.level) >= (
                keys.LEVELS.index(best_level) if best_level != "default" else -1):
            best_level, best_source = outcome.level, outcome.source
    return _Outcome(result, best_level, best_source)


def _key_path(name: str) -> Tuple[str, ...]:
    return tuple(name.split("."))


def _resolve_commands(contributions: List[Contribution], warnings: List[str]) -> Tuple[List[Dict[str, Any]],
                                                                                       List[Dict[str, Any]]]:
    """(summaries of the winning overrides, every override with its text, nearest first)."""
    key = keys.KEYS["commands"]
    overrides: List[Dict[str, Any]] = []
    for contribution in contributions:
        if _unset(contribution.value):
            contribution.status = "unset"
            continue
        if contribution.level == "TL5":
            contribution.ignore("commands can't be set per run")
            contribution.value = "<redacted>"
            continue
        problem = _commands_problem(contribution.value)
        if problem:
            _reject_invalid(key, contribution, problem, warnings)
            contribution.value = "<redacted>"
            continue
        for root, names in contribution.value.items():
            for name, command in names.items():
                overrides.append({"root": root, "name": name, "cmd": command, "channel": "config",
                                  "level": contribution.level, "source": contribution.source.display})
        contribution.value = {root: sorted(names) for root, names in contribution.value.items()}
    overrides.reverse()
    seen = set()
    summaries = []
    for override in overrides:
        ident = (override["root"], override["name"])
        if ident in seen:
            continue
        seen.add(ident)
        summaries.append({"root": override["root"], "name": override["name"], "channel": "config",
                          "level": override["level"]})
    summaries.sort(key=lambda s: (s["root"], s["name"]))
    return summaries, overrides


def _commands_problem(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return "expected a mapping of root -> {name: command}"
    for root, names in value.items():
        if not isinstance(names, dict):
            return f"{root}: expected a mapping of name -> command"
        for name, command in names.items():
            if not isinstance(command, str) or not command.strip():
                return f"{root}.{name}: expected a non-empty command string"
    return None


class Resolved:
    """The resolved configuration (`daedalus.policy/1`, §3.6)."""

    def __init__(self, repo: Path, workspace: Optional[Path], sources: List[Source], values: Dict[str, Any],
                 provenance: Dict[str, Dict[str, Any]], ignored: List[Dict[str, Any]], advisory: List[str],
                 warnings: List[str], details: Dict[str, Dict[str, Any]],
                 command_overrides: List[Dict[str, Any]], unmanaged: List[str]) -> None:
        self.repo = repo
        self.workspace = workspace
        self.sources = sources
        self.values = values
        self.provenance = provenance
        self.ignored = ignored
        self.advisory = advisory
        self.warnings = warnings
        self._details = details
        # Every `commands` override with its text, nearest level first. Only `config commands` and
        # trust.effective_commands read it; to_json() never includes command text.
        self.command_overrides = command_overrides
        self._unmanaged = unmanaged

    def get(self, key: str) -> Any:
        """One value by dotted key; a prefix (`tickets`) returns the nested mapping. KeyError when unknown."""
        if key in self.values:
            return self.values[key]
        head, _, entry = key.rpartition(".")
        if head in keys.MAPPING_KEYS and isinstance(self.values.get(head), dict) and entry in self.values[head]:
            return self.values[head][entry]
        if keys.is_prefix(key):
            nested: Dict[str, Any] = {}
            for name in sorted(self.values):
                if name.startswith(key + "."):
                    node = nested
                    parts = name[len(key) + 1:].split(".")
                    for part in parts[:-1]:
                        node = node.setdefault(part, {})
                    node[parts[-1]] = self.values[name]
            return nested
        raise KeyError(key)

    def explain(self, key: str) -> Dict[str, Any]:
        """Value, source, level, class, operator and every level's contribution for one key."""
        detail = self._details.get(key)
        if detail is None:
            raise KeyError(key)
        registry = detail["key"]
        outcome: _Outcome = detail["outcome"]
        contributions = [c.to_json() for c in detail["contributions"] if c.status != "unset"]
        if registry.name == "commands":
            value: Any = self.values["commands"]
        else:
            value = outcome.value
        return {"key": key, "value": value, "class": registry.cls, "op": registry.op,
                "level": outcome.level, "source": outcome.source, "levels": list(registry.levels),
                "default": registry.default if key == registry.name else (registry.default or {}).get(
                    key[len(registry.name) + 1:]),
                "advisory": key in self.advisory, "contributions": contributions,
                "warnings": list(self._unmanaged) + [w for w in self.warnings if f"'{key}'" in w
                                                      and w not in self._unmanaged]}

    def policy_digest(self) -> str:
        """sha256 over the canonical security and governance values (preferences never change it)."""
        subset = {name: self.values[name] for name in keys.digest_keys()}
        return sha256_tag(canonical_bytes({"schema": DIGEST_SCHEMA, "values": subset}))

    def to_json(self) -> Dict[str, Any]:
        return {"schema": SCHEMA, "repo": str(self.repo),
                "workspace": str(self.workspace) if self.workspace else None,
                "sources": [s.to_json() for s in self.sources], "values": dict(self.values),
                "provenance": self.provenance, "ignored": list(self.ignored), "advisory": list(self.advisory),
                "warnings": list(self.warnings), "policy_digest": self.policy_digest()}


def resolve(repo: Path, workspace: Optional[Path] = None, run_options: Optional[dict] = None, *,
            ctx: Optional[SourceContext] = None) -> Resolved:
    """Resolve the configuration for `repo` (a folder inside the target project).

    workspace: the folder the session started from (TL3 when it strictly contains the repository's top
    level and isn't inside a git work tree; otherwise its files are read as TL4). Falls back to
    CLAUDE_PROJECT_DIR. run_options: TL5 values by dotted key (`--set`). ctx: injected process facts (tests).
    Raises ConfigError (E_CONFIG_SYNTAX, E_CONFIG_VERSION, E_CONFIG_INVALID, E_REPO_ID).
    """
    ctx = ctx or SourceContext()
    if workspace is None and ctx.environ.get("CLAUDE_PROJECT_DIR"):
        workspace = Path(ctx.environ["CLAUDE_PROJECT_DIR"])
    found = discover(repo, workspace, ctx)
    sources = list(found.sources)
    if run_options:
        sources.append(_run_source(run_options))
    collector = _Collector()
    for source in sources:
        collector.walk(source)
    warnings = found.warnings + collector.warnings
    values: Dict[str, Any] = {}
    provenance: Dict[str, Dict[str, Any]] = {}
    details: Dict[str, Dict[str, Any]] = {}
    advisory: List[str] = []
    entries: Dict[str, Dict[str, Any]] = {}
    command_overrides: List[Dict[str, Any]] = []
    _invalid_prefixes(collector, warnings)
    for name, key in keys.KEYS.items():
        contributions = collector.by_key.get(name, [])
        if key.cls == keys.META:
            outcome = _Outcome(key.default, "default", None)
        elif key.cls == keys.SECURITY:
            outcome = _resolve_security(key, contributions, warnings, entries)
        elif key.cls == keys.GOVERNANCE:
            outcome = _resolve_governance(key, contributions, warnings, advisory)
        elif key.cls == keys.PROJECT_FACTS:
            summaries, command_overrides = _resolve_commands(contributions, warnings)
            levels = [s["level"] for s in summaries]
            nearest_level = max(levels, key=keys.LEVELS.index) if levels else "default"
            outcome = _Outcome(summaries, nearest_level, None)
        else:
            outcome = _resolve_preference(key, contributions, warnings)
        values[name] = outcome.value
        provenance[name] = {"level": outcome.level, "source": outcome.source, "class": key.cls, "op": key.op}
        details[name] = {"key": key, "outcome": outcome, "contributions": contributions}
    for entry_name, entry in entries.items():
        parent = keys.KEYS[entry_name.rsplit(".", 1)[0]] if entry_name.rsplit(".", 1)[0] in keys.KEYS else None
        if parent is None:
            continue
        details[entry_name] = {"key": parent, "outcome": entry["outcome"], "contributions": entry["contributions"]}
    ignored = _ignored_records(details)
    return Resolved(found.repo_top, found.workspace, sources, values, provenance, ignored, advisory, warnings,
                    details, command_overrides, found.unmanaged)


def _invalid_prefixes(collector: _Collector, warnings: List[str]) -> None:
    """A prefix such as `tickets` set to a scalar is a type error (it must be a mapping)."""
    for name in list(collector.by_key):
        if name in keys.KEYS:
            continue
        for contribution in collector.by_key.pop(name):
            where = contribution.source.display + (f":{contribution.line}" if contribution.line else "")
            if contribution.level in keys.TRUSTED_LEVELS:
                raise ConfigError(E_CONFIG_INVALID, f"'{name}' in {where} must be a mapping",
                                  f"write '{name}:' with its keys indented below it",
                                  file=contribution.source.display, line=contribution.line)
            warnings.append(f"invalid value for '{name}' in {where} ignored: expected a mapping")


def _ignored_records(details: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name, detail in details.items():
        for contribution in detail["contributions"]:
            if contribution.status in ("ignored", "partly ignored"):
                out.append({"key": name, "level": contribution.level, "source": contribution.source.display,
                            "value": contribution.value, "reason": contribution.reason})
    return out


# ---------- CLI: workflow.py config resolve | explain | get | commands ----------

class UsageError(Exception):
    """A bad command line (exit 2)."""

    def __init__(self, message: str, fix: str = "run `workflow.py <group> <action> --help`") -> None:
        super().__init__(message)
        self.fix = fix


def parse_set_options(items: Sequence[str]) -> Dict[str, Any]:
    """`KEY=VALUE` arguments to TL5 run options; VALUE is a YAML-subset scalar or one-line flow collection."""
    options: Dict[str, Any] = {}
    for item in items:
        name, sep, raw = item.partition("=")
        if not sep or not _PLAIN_KEY.match(name) or name.startswith(".") or name.endswith(".") or ".." in name:
            raise UsageError(f"bad --set {item!r}: expected KEY=VALUE with a dotted key",
                             "write --set KEY=VALUE, for example --set budgets.qa_rounds=1")
        try:
            options[name] = parse_value(raw)
        except ConfigError as err:
            raise UsageError(f"bad --set {item!r}: {err.message}",
                             f"{err.fix} (for example --set 'guard.mode=\"off\"')") from err
    return options


def add_cli(parser: Any) -> None:
    """Register `config resolve|explain|get|commands` on the group's argparse parser."""
    sub = parser.add_subparsers(dest="action", metavar="ACTION")
    sub.required = True
    common = {"--repo": dict(default=None, help="the target project folder (default: the current folder)"),
              "--workspace": dict(default=None, help="the folder the session started from "
                                  "(default: CLAUDE_PROJECT_DIR)")}

    def add(name: str, help_text: str, with_key: bool, with_set: bool) -> None:
        action = sub.add_parser(name, help=help_text, description=help_text)
        if with_key:
            action.add_argument("key", help="dotted key, for example guard.mode")
        action.add_argument("--json", action="store_true", help="print JSON")
        if with_set:
            action.add_argument("--set", dest="sets", action="append", default=[], metavar="KEY=VALUE",
                                help="a per-run (TL5) value; repeatable")
        for flag, options in common.items():
            action.add_argument(flag, **options)

    add("resolve", "print the resolved configuration (daedalus.policy/1)", False, True)
    add("explain", "show where one key's value came from, and every level's contribution", True, True)
    add("get", "print one value", True, True)
    add("commands", "print the effective commands (trusted and untrusted)", False, False)


def run_cli(args: Any) -> int:
    options = parse_set_options(getattr(args, "sets", []))
    repo = Path(args.repo) if args.repo else Path.cwd()
    workspace = Path(args.workspace) if args.workspace else None
    ctx = SourceContext()
    resolved = resolve(repo, workspace, options or None, ctx=ctx)
    if args.action == "resolve":
        return _print_resolve(resolved, args.json)
    if args.action == "explain":
        try:
            detail = resolved.explain(args.key)
        except KeyError:
            raise UsageError(_unknown_key(args.key)) from None
        _emit(detail, args.json, _format_explain)
        return 0
    if args.action == "get":
        try:
            value = resolved.get(args.key)
        except KeyError:
            raise UsageError(_unknown_key(args.key)) from None
        if args.json:
            print(json.dumps(value, ensure_ascii=False))
        else:
            print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        return 0
    return _print_commands(resolved, args.json, ctx)


def _unknown_key(name: str) -> str:
    hint = keys.nearest(name)
    return f"unknown key '{name}'" + (f" (did you mean '{hint}'?)" if hint else "")


def _emit(document: Dict[str, Any], as_json: bool, formatter: Callable[[Dict[str, Any]], str]) -> None:
    print(json.dumps(document, indent=2, ensure_ascii=False) if as_json else formatter(document))


def _print_resolve(resolved: Resolved, as_json: bool) -> int:
    _emit(resolved.to_json(), as_json, _format_resolve)
    return 0


def _short(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _format_resolve(doc: Dict[str, Any]) -> str:
    lines = [f"Resolved configuration for {doc['repo']}" + (f" (workspace {doc['workspace']})"
                                                             if doc["workspace"] else "")]
    lines.append("Sources:" if doc["sources"] else "Sources: none (defaults only)")
    for source in doc["sources"]:
        lines.append(f"  {source['level']} {source['kind']:7} {source['path']}"
                     + (f" (demoted from {source['demoted_from']})" if source.get("demoted_from") else ""))
    lines.append("Values:")
    for name, value in doc["values"].items():
        prov = doc["provenance"][name]
        origin = prov["level"] + (f" {prov['source']}" if prov["source"] else "")
        lines.append(f"  {name} = {_short(value)}  ({origin})")
    for record in doc["ignored"]:
        lines.append(f"Ignored: {record['key']} from {record['level']} {record['source']}: "
                     f"{_short(record['value'])} ({record['reason']})")
    for name in doc["advisory"]:
        lines.append(f"Advisory (TL2, not organization-enforced): {name}")
    for warning in doc["warnings"]:
        lines.append(f"Warning: {warning}")
    lines.append(f"policy_digest: {doc['policy_digest']}")
    return "\n".join(lines)


def _format_explain(detail: Dict[str, Any]) -> str:
    lines = [f"{detail['key']} = {_short(detail['value'])}",
             f"  class: {detail['class']} · operator: {detail['op']} · levels: {', '.join(detail['levels'])}",
             f"  from: {detail['level']}" + (f" ({detail['source']})" if detail["source"] else "")
             + ("  [advisory]" if detail["advisory"] else "")]
    if detail["contributions"]:
        lines.append("  contributions:")
    for contribution in detail["contributions"]:
        where = contribution["source"] + (f":{contribution['line']}" if contribution["line"] else "")
        reason = f" ({contribution['reason']})" if contribution["reason"] else ""
        lines.append(f"    {contribution['level']} {where}: {_short(contribution['value'])} → "
                     f"{contribution['status']}{reason}")
    for warning in detail["warnings"]:
        lines.append(f"  warning: {warning}")
    return "\n".join(lines)


def load_profile(repo_top: Path) -> Optional[Dict[str, Any]]:
    """The committed `.workflow/profile.json`, or None when it's missing or unreadable."""
    path = repo_top / ".workflow" / "profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as err:
        raise ConfigError(E_CONFIG_INVALID, f"can't read .workflow/profile.json: {err}",
                          "run /setup --refresh to regenerate it", file=".workflow/profile.json") from err
    return data if isinstance(data, dict) else None


def _print_commands(resolved: Resolved, as_json: bool, ctx: Optional[SourceContext] = None) -> int:
    """`config commands`: the effective set with its trust state (full mode, §3.8); the one config output
    that carries command text."""
    from . import trust

    found = trust.evaluate(resolved.repo, load_profile(resolved.repo), resolved, rederive=True, ctx=ctx)
    _emit(trust.commands_document(found), as_json, trust.format_commands)
    return 0
