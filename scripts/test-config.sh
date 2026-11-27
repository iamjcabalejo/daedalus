#!/usr/bin/env bash
# Tests for the configuration resolver and its CLI (plan P1a batch 1: AC-1..AC-6, AC-10, and the work-tree
# check of AC-2 that AC-8 reuses). Python unittest, standard library only; no network, no model.
#
#   scripts/test-config.sh          run every test; exit 1 on any failure
#   scripts/test-config.sh -v       verbose unittest output
#
# Test ids (grep for them): U-config-yaml-01..20 (AC-1), U-trust-sources-01..15 (AC-2), U-config-registry-01
# (AC-3), U-config-merge-01..13 (AC-4), U-policy-monotonic-01..06 and PT-policy-ops-01..09 (AC-5),
# U-config-cli-01..06 plus the p95 timing check (AC-6), U-trust-carryover-01 and U-detector-nowrite-01 (AC-10),
# U-config-consumers-01 (AC-7: hooks and prompts read configuration through the resolver; Python runs with -I),
# U-build-qa-scripts-01 (PF-9: the QA plugin's own workflow.py resolves exactly like the main plugin's),
# U-build-companion-names-01 (rework-4 RW4-AC-2: the QA plugin's Markdown names main-plugin commands with their prefix).
#
# Isolation: every test works in temporary folders outside any repository. DAEDALUS_HOME points at a temporary
# folder for the whole run, in-process resolutions inject the password-database home, and TL1 ownership is
# injected through SourceContext.lstat (a function parameter, never an environment variable), so no test reads
# or writes the real ~/.workflow or ~/.claude.
set -euo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HUB
exec python3 -I -B - "$@" <<'PY'
from __future__ import annotations  # Python 3.8+

import hashlib, importlib.util, io, json, math, os, random, re, shutil, stat, subprocess, sys, tempfile, time, types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

sys.dont_write_bytecode = True
HUB = Path(os.environ["HUB"])
SCRIPTS = HUB / ".claude" / "scripts"
FIX = HUB / "scripts" / "fixtures" / "config"
WORKFLOW = SCRIPTS / "workflow.py"
sys.path.insert(0, str(SCRIPTS))
from lib import config_keys as keys, trust, unsafe, wfconfig  # noqa: E402

for name in ("CLAUDE_PROJECT_DIR", "DAEDALUS_POLICY_DIR", "GIT_DIR", "GIT_WORK_TREE"):
    os.environ.pop(name, None)
SAFE_ROOT = Path(os.path.realpath(tempfile.mkdtemp(prefix="daedalus-config-tests-")))
SAFE_HOME = SAFE_ROOT / "home"
SAFE_HOME.mkdir(mode=0o700)
os.environ["DAEDALUS_HOME"] = str(SAFE_HOME)  # anything that falls back to os.environ uses a temp home
GIT_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")


def to_yaml(flat: Dict[str, Any]) -> str:
    """Dotted keys → a block mapping of one-line flow values (JSON is valid flow YAML in the subset)."""
    nested: Dict[str, Any] = {}
    for dotted, value in flat.items():
        node = nested
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return "".join(f"{json.dumps(k)}: {json.dumps(v)}\n" for k, v in nested.items())


def ownership(test_root: Path, root_owned=(), overrides: Optional[Dict[Path, int]] = None):
    """The TL1 ownership seam: `test_root` and its ancestors and everything under `root_owned` look root-owned
    (ancestors also lose group/other write bits); `overrides` set a path's owner; the rest is real."""
    overrides = {str(k): v for k, v in (overrides or {}).items()}
    owned = [str(p) for p in root_owned]
    root = str(test_root)

    def lstat(path: str) -> Any:
        info = os.lstat(path)
        path = str(path)
        if path in overrides:
            return types.SimpleNamespace(st_mode=info.st_mode, st_uid=overrides[path])
        if path == root or root.startswith(path.rstrip(os.sep) + os.sep) or path == os.sep:
            return types.SimpleNamespace(st_mode=info.st_mode & ~0o022, st_uid=0)
        if any(path == p or path.startswith(p + os.sep) for p in owned):
            return types.SimpleNamespace(st_mode=info.st_mode, st_uid=0)
        return info
    return lstat


class TempCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="case-", dir=SAFE_ROOT)))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.assertFalse(trust.inside_work_tree(self.tmp), "tests need a temp folder outside any git work tree")
        self.home = self.mkdir("home")
        self.pw = self.mkdir("passwd-home")

    def mkdir(self, rel: str, mode: int = 0o700) -> Path:
        path = self.tmp / rel
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
        return path

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def git_init(self, rel: str) -> Path:
        path = self.mkdir(rel)
        subprocess.run(["git", "init", "-q", str(path)], check=True, env=GIT_ENV, capture_output=True)
        return path

    def ctx(self, environ: Optional[Dict[str, str]] = None, **kw: Any) -> wfconfig.SourceContext:
        env = {"DAEDALUS_HOME": str(self.home)} if environ is None else environ
        kw.setdefault("passwd_home", self.pw)
        kw.setdefault("tl1_paths", [])
        return wfconfig.SourceContext(environ=env, **kw)

    def resolve(self, repo: Path, workspace: Optional[Path] = None, run: Optional[dict] = None,
                **kw: Any) -> wfconfig.Resolved:
        return wfconfig.resolve(repo, workspace, run, ctx=self.ctx(**kw))

    # level helpers: dicts of dotted keys
    def tl1(self, flat: Dict[str, Any]) -> Dict[str, Any]:
        path = self.write("org/policy.yml", to_yaml(flat))
        return {"tl1_paths": [path], "lstat": ownership(self.tmp, [self.tmp / "org"])}

    def tl2(self, flat: Dict[str, Any], legacy: bool = False) -> Path:
        rel = ".claude/argus.yml" if legacy else ".workflow/config.yml"
        return self.write(f"home/{rel}", to_yaml(flat))

    def project(self, tl4: Optional[Dict[str, Any]] = None, legacy: Optional[Dict[str, Any]] = None) -> Path:
        repo = self.mkdir("ws/proj")
        if tl4 is not None:
            self.write("ws/proj/.workflow/config.yml", to_yaml(tl4))
        if legacy is not None:
            self.write("ws/proj/.argus.yml", to_yaml(legacy))
        return repo

    def tl3(self, flat: Dict[str, Any]) -> Path:
        self.write("ws/.workflow/config.yml", to_yaml(flat))
        return self.tmp / "ws"


# ---------------------------------------------------------------- AC-1: YAML subset

class YamlSubset(unittest.TestCase):
    def expect_ok(self, name: str) -> None:
        path = FIX / "yaml" / "ok" / f"{name}.yml"
        expected = json.loads(path.with_suffix(".json").read_text())
        self.assertEqual(wfconfig.parse_yaml(path.read_text(), path.name), expected)

    def expect_bad(self, name: str, construct: str, line: int, col: int, code: str = "E_CONFIG_SYNTAX") -> None:
        path = FIX / "yaml" / "bad" / f"{name}.yml"
        with self.assertRaises(wfconfig.ConfigError) as caught:
            wfconfig.load_config_file(path, "TL4", "config", f"bad/{name}.yml")
        err = caught.exception
        self.assertEqual((err.code, err.construct, err.file, err.line, err.col),
                         (code, construct, f"bad/{name}.yml", line, col), name)
        if code == "E_CONFIG_SYNTAX":
            self.assertIn(f"bad/{name}.yml:{line}:{col}", err.message)
        self.assertTrue(err.fix)

    def test_U_config_yaml_01_scalars_bom_crlf_and_comments(self) -> None:
        self.expect_ok("scalars")
        text = (FIX / "yaml" / "ok" / "scalars.yml").read_text()
        expected = json.loads((FIX / "yaml" / "ok" / "scalars.json").read_text())
        self.assertEqual(wfconfig.parse_yaml("\ufeff" + text.replace("\n", "\r\n"), "crlf.yml"), expected)
        decoded = wfconfig.decode_config(b"\xef\xbb\xbf" + text.encode("utf-8"), "bom.yml")
        self.assertEqual(wfconfig.parse_yaml(decoded, "bom.yml"), expected)
        self.assertIsNone(wfconfig.parse_yaml("# only a comment\n\n", "c.yml"))
        self.assertIsNone(wfconfig.parse_yaml("", "empty.yml"))

    def test_U_config_yaml_02_mappings_flow_sequences_and_marker(self) -> None:
        for name in ("mappings", "flow", "sequences", "document-marker"):
            with self.subTest(name):
                self.expect_ok(name)
        mappings = json.loads((FIX / "yaml" / "ok" / "mappings.json").read_text())
        self.assertEqual(mappings["commands"]["."], {"test": "make test"})

    def test_U_config_yaml_03_anchor(self) -> None:
        self.expect_bad("anchor", "anchor", 1, 7)
        path = FIX / "yaml" / "bad" / "anchor.yml"
        with self.assertRaises(wfconfig.ConfigError) as caught:
            wfconfig.load_config_file(path, "TL4", "config", ".workflow/config.yml")
        self.assertIn("anchor `&defaults` at .workflow/config.yml:1:7", caught.exception.message)

    def test_U_config_yaml_04_alias(self) -> None:
        self.expect_bad("alias", "alias", 2, 4)

    def test_U_config_yaml_05_tag(self) -> None:
        self.expect_bad("tag", "tag", 1, 4)

    def test_U_config_yaml_06_block_scalars(self) -> None:
        self.expect_bad("block-scalar-literal", "block scalar", 1, 8)
        self.expect_bad("block-scalar-folded", "block scalar", 1, 8)

    def test_U_config_yaml_07_more_than_one_document(self) -> None:
        self.expect_bad("two-documents", "multiple documents", 2, 1)
        self.expect_bad("document-end", "document end marker", 2, 1)

    def test_U_config_yaml_08_complex_key(self) -> None:
        self.expect_bad("complex-key", "complex key", 1, 1)

    def test_U_config_yaml_09_merge_key(self) -> None:
        self.expect_bad("merge-key", "merge key", 3, 3)

    def test_U_config_yaml_10_duplicate_keys(self) -> None:
        self.expect_bad("duplicate-key", "duplicate key", 3, 3)
        self.expect_bad("duplicate-key-flow", "duplicate key", 1, 27)

    def test_U_config_yaml_11_tab_indentation(self) -> None:
        self.expect_bad("tab-indentation", "tab indentation", 2, 1)

    def test_U_config_yaml_12_ambiguous_booleans(self) -> None:
        cases = {"bool-yes": (1, 21), "bool-no": (1, 4), "bool-on": (1, 4), "bool-off": (2, 9),
                 "bool-True": (1, 4), "bool-False": (1, 4)}
        for name, (line, col) in cases.items():
            with self.subTest(name):
                self.expect_bad(name, "ambiguous boolean", line, col)

    def test_U_config_yaml_13_unquoted_floats(self) -> None:
        self.expect_bad("float", "unquoted float", 2, 18)
        self.expect_bad("float-exponent", "unquoted float", 1, 4)

    def test_U_config_yaml_14_multi_line_flow_collection(self) -> None:
        self.expect_bad("multi-line-flow", "multi-line flow collection", 2, 12)

    def test_U_config_yaml_15_multi_line_scalars(self) -> None:
        self.expect_bad("multi-line-plain", "multi-line plain scalar", 3, 5)
        self.expect_bad("multi-line-quoted", "multi-line quoted scalar", 2, 11)

    def test_U_config_yaml_16_version(self) -> None:
        self.expect_bad("version-2", "version", 1, 1, code="E_CONFIG_VERSION")
        self.expect_bad("version-string", "version", 1, 1, code="E_CONFIG_VERSION")
        root = Path(os.path.realpath(tempfile.mkdtemp(dir=SAFE_ROOT)))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "with.yml").write_text("version: 1\nchat: slack\n")
        (root / "without.yml").write_text("chat: slack\n")
        for name in ("with.yml", "without.yml"):
            source = wfconfig.load_config_file(root / name, "TL4", "config", name)
            self.assertEqual(source.data, {"chat": "slack"})
            self.assertEqual(source.to_json()["version"], 1)

    def test_U_config_yaml_17_workflow_template_parses_to_expected_json(self) -> None:
        path = HUB / "templates" / "workflow-config.example.yml"
        expected = json.loads((FIX / "templates" / "workflow-config.example.json").read_text())
        self.assertEqual(wfconfig.parse_yaml(path.read_text(), str(path)), expected)
        self.assertIsNotNone(wfconfig.load_config_file(path, "TL4", "config", "template"))

    def test_U_config_yaml_18_overlay_template_parses_to_expected_json(self) -> None:
        path = HUB / "overlays" / "_template" / "config.yml"
        expected = json.loads((FIX / "templates" / "overlay-template-config.json").read_text())
        self.assertEqual(wfconfig.parse_yaml(path.read_text(), str(path)), expected)

    def test_U_config_yaml_19_other_constructs_outside_the_subset(self) -> None:
        cases = [("inconsistent-indentation", "inconsistent indentation", 3, 3),
                 ("unsupported-plain-key", "unsupported plain key", 1, 1),
                 ("colon-in-plain", "colon in plain scalar", 1, 5), ("directive", "directive", 1, 1),
                 ("reserved-indicator", "reserved indicator", 1, 4),
                 ("top-level-list", "top level is not a mapping", 1, 1),
                 ("unsupported-escape", "unsupported escape", 1, 5)]
        for name, construct, line, col in cases:
            with self.subTest(name):
                self.expect_bad(name, construct, line, col)
        inline = {"a: 012\n": "ambiguous number", "a: 0x1F\n": "ambiguous number", "a: 2026-01-01\n": "unquoted date",
                  "a: NULL\n": "ambiguous null", "a: [x: 1]\n": "implicit mapping in flow sequence",
                  "a: [1, ]\n": "empty flow entry", "a: {x}\n": "flow mapping entry without a value",
                  "a: - b\n": "block sequence on the key's line", "a: 'x' y\n": "text after value",
                  "a: \"\\ud800\"\n": "unsupported escape", "a: x\tb\n": "tab character",
                  "a: .inf\n": "unquoted float"}
        for text, construct in inline.items():
            with self.subTest(text=text), self.assertRaises(wfconfig.ConfigError) as caught:
                wfconfig.parse_yaml(text, "inline.yml")
            self.assertEqual(caught.exception.construct, construct, text)
        with self.assertRaises(wfconfig.ConfigError) as caught:
            wfconfig.decode_config(b"a: \xff\n", "latin.yml")
        self.assertEqual((caught.exception.construct, caught.exception.line, caught.exception.col), ("not UTF-8", 1, 4))
        with self.assertRaises(wfconfig.ConfigError) as caught:
            wfconfig.decode_config(b"#" * (wfconfig.MAX_FILE_BYTES + 1), "big.yml")
        self.assertEqual(caught.exception.construct, "file too large")
        deep = "a: " + "[" * 40 + "]" * 40 + "\n"
        with self.assertRaises(wfconfig.ConfigError) as caught:
            wfconfig.parse_yaml(deep, "deep.yml")
        self.assertEqual(caught.exception.construct, "nesting too deep")

    def test_U_config_yaml_20_every_fixture_matches_its_expected_json(self) -> None:
        ok = sorted((FIX / "yaml" / "ok").glob("*.yml"))
        bad = sorted((FIX / "yaml" / "bad").glob("*.yml"))
        self.assertGreaterEqual(len(ok), 5)
        self.assertGreaterEqual(len(bad), 30)
        for path in ok:
            with self.subTest(path.name):
                self.assertEqual(wfconfig.parse_yaml(path.read_text(), path.name),
                                 json.loads(path.with_suffix(".json").read_text()))
        for path in bad:
            expected = json.loads(path.with_suffix(".json").read_text())
            with self.subTest(path.name), self.assertRaises(wfconfig.ConfigError) as caught:
                wfconfig.load_config_file(path, "TL4", "config", path.name)
            err = caught.exception
            self.assertEqual({"code": err.code, "line": err.line, "col": err.col, "construct": err.construct},
                             expected, path.name)
            self.assertTrue(err.fix and err.message)


# ---------------------------------------------------------------- AC-3: registry

def flatten_template(node: Dict[str, Any], prefix=()) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, value in node.items():
        path = prefix + (name,)
        dotted = ".".join(path)
        if dotted in keys.KEYS:
            out[dotted] = value
        elif isinstance(value, dict) and value:
            out.update(flatten_template(value, path))
        else:
            out[dotted] = value
    return out


class Registry(unittest.TestCase):
    def test_U_config_registry_01_template_and_registry_agree(self) -> None:
        path = HUB / "templates" / "workflow-config.example.yml"
        text = path.read_text()
        flat = flatten_template(wfconfig.parse_yaml(text, str(path)))
        self.assertEqual(sorted(set(flat) - set(keys.KEYS)), [], "template keys without a registry entry")
        self.assertEqual(sorted(set(keys.KEYS) - set(flat)), [], "registry entries the template doesn't document")
        for name, value in flat.items():
            self.assertEqual(value, keys.KEYS[name].default, f"template default for {name}")
        for key in keys.KEYS.values():
            with self.subTest(key.name):
                self.assertIn(key.cls, keys.CLASSES)
                self.assertIn(key.op, keys.OPERATORS)
                self.assertTrue(set(key.levels) <= set(keys.LEVELS) and key.levels)
                self.assertTrue(key.types and key.doc)
                self.assertIsNone(keys.check_value(key, key.default), "the default is valid")
                if key.cls == keys.SECURITY:
                    self.assertIn(key.op, keys.SECURITY_OPERATORS)
                if key.cls == keys.GOVERNANCE:
                    self.assertEqual(key.levels, ("TL1",))
                if key.op in (keys.MODE_ORDER, keys.MAX_ORDER):
                    self.assertTrue(key.order)
        self.assertEqual((keys.KEYS["gate.trusted_classes"].default, keys.KEYS["gate.trusted_classes"].op),
                         (["ci", "human"], keys.INTERSECT))
        self.assertEqual(keys.KEYS["version"].default, 1)
        # Each S / P / G marker in the template matches the class of every key on that line.
        markers = {"S": {keys.SECURITY}, "P": {keys.PREFERENCE, keys.WORKFLOW_PREFERENCE}, "G": {keys.GOVERNANCE}}
        stack: List[tuple] = []
        checked = 0
        for line in text.splitlines():
            match = re.match(r"^( *)([A-Za-z_][A-Za-z0-9_.-]*):(.*)$", line)
            if not match:
                continue
            indent, name, rest = len(match.group(1)), match.group(2), match.group(3)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, name))
            dotted = ".".join(n for _, n in stack)
            marker = re.search(r"#\s+([SPG])\b", rest)
            if not marker:
                continue
            covered = [k for k in keys.KEYS if k == dotted or k.startswith(dotted + ".")]
            self.assertTrue(covered, f"marker on unknown key {dotted}")
            for name in covered:
                self.assertIn(keys.KEYS[name].cls, markers[marker.group(1)], f"{name} marked {marker.group(1)}")
                checked += 1
        self.assertGreaterEqual(checked, len(keys.KEYS) - 3)  # every key but version and commands carries one


# ---------------------------------------------------------------- AC-2: trust levels and sources

class TrustSources(TempCase):
    def test_U_trust_sources_01_unmanaged_tl1_file_is_ignored_and_explained(self) -> None:
        policy = self.write("org/policy.yml", to_yaml({"guard.mode": "warn", "chat": "slack"}))
        repo = self.project()
        for label, lstat in (("real ownership", None), ("seam: user-owned", ownership(
                self.tmp, [self.tmp / "org"], {policy: os.getuid()}))):
            with self.subTest(label):
                kwargs = {"tl1_paths": [policy]}
                if lstat:
                    kwargs["lstat"] = lstat
                resolved = self.resolve(repo, **kwargs)
                self.assertEqual(resolved.values["chat"], "none")
                self.assertEqual([s.level for s in resolved.sources], [])
                self.assertTrue(any("isn't managed" in w for w in resolved.warnings))
                self.assertTrue(any("isn't managed" in w for w in resolved.explain("chat")["warnings"]))
        (self.tmp / "org").chmod(0o775)
        resolved = self.resolve(repo, tl1_paths=[policy], lstat=ownership(self.tmp, [self.tmp / "org"]))
        self.assertTrue(any("group- or world-writable" in w for w in resolved.warnings))

    def test_U_trust_sources_02_managed_tl1_file_is_read_and_a_broken_one_is_fatal(self) -> None:
        repo = self.project({"guard.mode": "warn"})
        resolved = self.resolve(repo, **self.tl1({"guard.mode": "enforce", "chat": "slack"}))
        self.assertEqual([s.level for s in resolved.sources], ["TL1", "TL4"])
        self.assertEqual(resolved.values["chat"], "slack")
        self.assertEqual(resolved.provenance["guard.mode"]["level"], "TL1")
        self.write("org/policy.yml", "guard: {mode: enforce\n")
        with self.assertRaises(wfconfig.ConfigError) as caught:
            self.resolve(repo, tl1_paths=[self.tmp / "org/policy.yml"], lstat=ownership(self.tmp, [self.tmp / "org"]))
        self.assertEqual(caught.exception.code, "E_CONFIG_SYNTAX")

    def test_U_trust_sources_03_root_owned_symlink_in_the_path_passes(self) -> None:
        self.write("org/policy.yml", to_yaml({"chat": "slack"}))
        (self.tmp / "link").symlink_to(self.tmp / "org")
        lstat = ownership(self.tmp, [self.tmp / "org", self.tmp / "link"])
        self.assertIsNone(wfconfig.managed_path_problem(self.tmp / "link" / "policy.yml", lstat))
        resolved = self.resolve(self.project(), tl1_paths=[self.tmp / "link" / "policy.yml"], lstat=lstat)
        self.assertEqual(resolved.values["chat"], "slack")

    def test_U_trust_sources_04_user_owned_symlink_fails(self) -> None:
        self.write("org/policy.yml", to_yaml({"chat": "slack"}))
        (self.tmp / "link").symlink_to(self.tmp / "org")
        lstat = ownership(self.tmp, [self.tmp / "org"], {self.tmp / "link": os.getuid()})
        problem = wfconfig.managed_path_problem(self.tmp / "link" / "policy.yml", lstat)
        self.assertIn("symlink", problem or "")
        resolved = self.resolve(self.project(), tl1_paths=[self.tmp / "link" / "policy.yml"], lstat=lstat)
        self.assertEqual(resolved.values["chat"], "none")

    def test_U_trust_sources_05_policy_dir_adds_and_never_replaces(self) -> None:
        self.write("org/policy.yml", to_yaml({"guard.mode": "enforce", "chat": "slack"}))
        self.write("dpd/policy.yml", to_yaml({"guard.mode": "warn", "chat": "teams", "graph": "none",
                                              "gate.require": ["checks", "review", "qa", "security"]}))
        lstat = ownership(self.tmp, [self.tmp / "org", self.tmp / "dpd"])
        env = {"DAEDALUS_HOME": str(self.home), "DAEDALUS_POLICY_DIR": str(self.tmp / "dpd")}
        resolved = self.resolve(self.project(), environ=env, tl1_paths=[self.tmp / "org/policy.yml"], lstat=lstat)
        self.assertEqual([s.display for s in resolved.sources],
                         [str(self.tmp / "dpd/policy.yml"), str(self.tmp / "org/policy.yml")])
        self.assertEqual(resolved.values["chat"], "slack")  # the platform path wins over the added one
        self.assertEqual(resolved.values["graph"], "none")  # the added one fills keys the platform doesn't set
        self.assertEqual(resolved.values["guard.mode"], "enforce")  # security: strictest of all TL1 sources
        self.assertIn("security", resolved.values["gate.require"])
        unmanaged = ownership(self.tmp, [self.tmp / "org"])
        resolved = self.resolve(self.project(), environ=env, tl1_paths=[self.tmp / "org/policy.yml"], lstat=unmanaged)
        self.assertEqual([s.display for s in resolved.sources], [str(self.tmp / "org/policy.yml")])
        self.assertTrue(any("dpd/policy.yml exists but isn't managed" in w for w in resolved.warnings))
        env["DAEDALUS_POLICY_DIR"] = "relative/dir"
        resolved = self.resolve(self.project(), environ=env, tl1_paths=[], lstat=lstat)
        self.assertTrue(any("not an absolute path" in w for w in resolved.warnings))

    def test_U_trust_sources_06_workspace_inside_a_work_tree_is_demoted(self) -> None:
        outer = self.git_init("outer")
        repo = self.git_init("outer/sub/repo")
        self.write("outer/.workflow/config.yml", to_yaml({"commands": {".": {"test": "make ws"}}}))
        resolved = self.resolve(repo, outer)
        demoted = [s.to_json() for s in resolved.sources]
        self.assertEqual(demoted, [dict(demoted[0], level="TL4", demoted_from="TL3")])
        self.assertEqual(resolved.command_overrides[0]["level"], "TL4")
        self.assertTrue(any("inside a git work tree" in w for w in resolved.warnings))

    def test_U_trust_sources_07_workspace_that_is_not_a_strict_ancestor_is_demoted(self) -> None:
        repo = self.git_init("repo")
        for workspace, reason in ((self.mkdir("other"), "isn't an ancestor"), (self.mkdir("repo/sub"), "inside the repository")):
            with self.subTest(reason):
                self.write(str((workspace / ".workflow" / "config.yml").relative_to(self.tmp)),
                           to_yaml({"commands": {".": {"lint": "make lint"}}}))
                resolved = self.resolve(repo, workspace)
                self.assertEqual({s.level for s in resolved.sources}, {"TL4"})
                self.assertEqual([o["level"] for o in resolved.command_overrides], ["TL4"])
                self.assertTrue(any(reason in w for w in resolved.warnings), resolved.warnings)
                shutil.rmtree(workspace / ".workflow")

    def test_U_trust_sources_08_a_git_entry_git_refuses_demotes(self) -> None:
        workspace = self.mkdir("ws")
        (workspace / ".git").write_text("gitdir: /nonexistent/daedalus-test\n")
        repo = self.git_init("ws/repo")
        self.assertTrue(trust.inside_work_tree(workspace))
        self.write("ws/.workflow/config.yml", to_yaml({"chat": "slack"}))
        resolved = self.resolve(repo, workspace)
        self.assertEqual([s.level for s in resolved.sources], ["TL4"])
        broken = self.mkdir("broken")
        (broken / ".git").write_text("gitdir: /nonexistent/daedalus-test\n")
        self.mkdir("broken/inner")
        self.assertEqual(trust.top_level(broken / "inner"), (broken, False))
        self.assertEqual(self.resolve(broken / "inner").repo, broken)

    def test_U_trust_sources_09_git_dir_or_work_tree_in_the_environment_demotes(self) -> None:
        workspace = self.tl3({"chat": "slack"})
        repo = self.git_init("ws/repo")
        for name in ("GIT_DIR", "GIT_WORK_TREE"):
            with self.subTest(name):
                self.assertTrue(trust.inside_work_tree(workspace, environ={name: "/somewhere"}))
                resolved = self.resolve(repo, workspace, environ={"DAEDALUS_HOME": str(self.home), name: "/x"})
                self.assertEqual([s.level for s in resolved.sources], ["TL4"])

    def test_U_trust_sources_10_target_without_git_is_a_tl4_project_folder(self) -> None:
        project = self.project({"commands": {".": {"test": "make test"}}})
        resolved = self.resolve(project)
        self.assertEqual((resolved.repo, trust.top_level(project)), (project, (project, False)))
        self.assertEqual([(o["level"], o["cmd"]) for o in resolved.command_overrides], [("TL4", "make test")])
        sub = self.mkdir("ws/proj/sub")  # without git, the target folder itself is the project folder
        self.assertEqual((self.resolve(sub).repo, trust.top_level(sub)), (sub, (sub, False)))
        with self.assertRaises(wfconfig.ConfigError) as caught:
            self.resolve(self.tmp / "missing")
        self.assertEqual(caught.exception.code, "E_REPO_ID")

    def _home_refused(self, home: Path, repo: Path, reason: str, **kw: Any) -> None:
        self.write("passwd-home/.workflow/config.yml", to_yaml({"chat": "teams"}))
        (home / ".workflow").mkdir(parents=True, exist_ok=True)
        (home / ".workflow" / "config.yml").write_text(to_yaml({"chat": "slack"}))
        resolved = self.resolve(repo, environ={"DAEDALUS_HOME": str(home)}, **kw)
        self.assertEqual(resolved.values["chat"], "teams", reason)
        self.assertTrue(any("DAEDALUS_HOME" in w and reason in w for w in resolved.warnings), resolved.warnings)

    def test_U_trust_sources_11_daedalus_home_inside_a_work_tree_is_ignored(self) -> None:
        self.git_init("dotfiles")
        self._home_refused(self.mkdir("dotfiles/home"), self.project(), "inside a git work tree")

    def test_U_trust_sources_12_daedalus_home_inside_the_project_is_ignored(self) -> None:
        project = self.project()
        self._home_refused(self.mkdir("ws/proj/home"), project, "inside the target project folder")

    def test_U_trust_sources_13_daedalus_home_owned_by_another_user_or_writable_is_ignored(self) -> None:
        home = self.mkdir("other-home")
        self._home_refused(home, self.project(), "owned by another user",
                           lstat=ownership(self.tmp, overrides={home: os.getuid() + 1}))
        writable = self.mkdir("open-home", 0o777)
        writable.chmod(0o777)
        self._home_refused(writable, self.project(), "group- or world-writable")
        group = self.mkdir("group-home")
        group.chmod(0o770)
        self._home_refused(group, self.project(), "group- or world-writable")

    def test_U_trust_sources_14_non_git_ancestor_of_the_repo_is_tl3(self) -> None:
        workspace = self.tl3({"chat": "slack", "commands": {".": {"test": "make ws"}}})
        repo = self.git_init("ws/repo")
        resolved = self.resolve(repo, workspace)
        self.assertEqual([s.level for s in resolved.sources], ["TL3"])
        self.assertEqual(resolved.values["chat"], "slack")
        self.assertEqual(resolved.command_overrides[0]["level"], "TL3")
        self.assertEqual(resolved.to_json()["workspace"], str(workspace))
        nested = self.resolve(self.mkdir("ws/proj/a/b"), workspace)
        self.assertEqual(nested.repo, self.tmp / "ws/proj/a/b")  # a non-git target is its own project folder
        self.assertEqual([s.level for s in nested.sources], ["TL3"])

    def test_U_trust_sources_15_honored_home_and_no_git_call_outside_repositories(self) -> None:
        self.tl2({"chat": "slack"})
        resolved = self.resolve(self.project())
        self.assertEqual(resolved.values["chat"], "slack")
        self.assertFalse(any("DAEDALUS_HOME" in w for w in resolved.warnings))
        with mock.patch.object(trust.subprocess, "run") as run:
            self.assertFalse(trust.inside_work_tree(self.tmp))
            self.assertFalse(trust.inside_work_tree(self.home / "does-not-exist"))
        run.assert_not_called()
        repo = self.git_init("repo")
        with mock.patch.object(trust.subprocess, "run", wraps=subprocess.run) as run:
            self.assertTrue(trust.inside_work_tree(repo))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args[0][0][-2:], ["rev-parse", "--is-inside-work-tree"])


# ---------------------------------------------------------------- AC-4: resolution

class Merge(TempCase):
    def test_U_config_merge_01_nearest_wins(self) -> None:
        tl1 = self.tl1({"chat": "teams"})
        self.tl2({"chat": "slack"})
        workspace = self.tl3({"chat": "none"})
        project = self.project({"chat": "teams"})
        self.assertEqual(self.resolve(project, workspace, {"chat": "slack"}, **tl1).provenance["chat"]["level"], "TL5")
        order = []
        for remove in (None, project / ".workflow/config.yml", workspace / ".workflow/config.yml",
                       self.home / ".workflow/config.yml"):
            if remove:
                remove.unlink()
            resolved = self.resolve(project, workspace, **tl1)
            order.append((resolved.provenance["chat"]["level"], resolved.values["chat"]))
        self.assertEqual(order, [("TL4", "teams"), ("TL3", "none"), ("TL2", "slack"), ("TL1", "teams")])

    def test_U_config_merge_02_mappings_merge_recursively(self) -> None:
        self.tl2({"domain": "acme", "tickets": {"system": "linear", "key": "ACME-\\d+"}}, legacy=True)
        resolved = self.resolve(self.project({"tickets": {"system": "github"}}))
        self.assertEqual(resolved.get("tickets"), {"system": "github", "key": "ACME-\\d+", "team": None})
        self.assertEqual(resolved.values["domain"], "acme")

    def test_U_config_merge_03_lists_are_replaced_whole(self) -> None:
        self.tl2({"ignore": ["a/**", "b/**"], "review": {"severity": {"overrides": [{"category": "x", "max": "consider"}]}}})
        resolved = self.resolve(self.project({"ignore": ["c/**"], "review.severity.overrides": [{"family": "FM-1"}]}))
        self.assertEqual(resolved.values["ignore"], ["c/**"])
        self.assertEqual(resolved.values["review.severity.overrides"], [{"family": "FM-1"}])

    def test_U_config_merge_04_unset_falls_through_and_explicit_values_win(self) -> None:
        self.tl2({"domain": "acme", "tickets.key": "ACME-\\d+", "chat": "slack", "ignore": ["a/**"], "graph": "none"})
        self.write("ws/proj/.workflow/config.yml", 'domain:\ntickets:\n  key: null\nchat: ""\nignore: []\ngraph: ~\n')
        resolved = self.resolve(self.mkdir("ws/proj"))
        self.assertEqual((resolved.values["domain"], resolved.values["tickets.key"], resolved.values["chat"],
                          resolved.values["graph"]), ("acme", "ACME-\\d+", "slack", "none"))
        self.assertEqual(resolved.values["ignore"], [])
        self.write("ws/proj/.workflow/config.yml", "domain: none\n")
        self.assertEqual(self.resolve(self.tmp / "ws/proj").values["domain"], "none")

    def test_U_config_merge_05_legacy_file_reads_below_config_at_the_same_level(self) -> None:
        project = self.project({"domain": "from-config"}, legacy={"domain": "from-legacy", "house_rules": ["RULES.md"]})
        resolved = self.resolve(project)
        self.assertEqual([(s.level, s.kind) for s in resolved.sources], [("TL4", "legacy"), ("TL4", "config")])
        self.assertEqual(resolved.values["domain"], "from-config")
        self.assertEqual(resolved.values["house_rules"], ["RULES.md"])
        statuses = {c["source"]: c["status"] for c in resolved.explain("domain")["contributions"]}
        self.assertEqual(statuses, {".argus.yml": "overridden", ".workflow/config.yml": "accepted"})

    def test_U_config_merge_06_legacy_severity_and_post_are_lifted_under_review(self) -> None:
        self.write("ws/proj/.argus.yml", "severity:\n  critical_triggers: [data loss]\npost:\n  inline: false\n"
                   "review:\n  max_findings: 5\n")
        resolved = self.resolve(self.mkdir("ws/proj"))
        self.assertEqual(resolved.values["review.severity.critical_triggers"], ["data loss"])
        self.assertFalse(resolved.values["review.post.inline"])
        self.assertEqual(resolved.values["review.max_findings"], 5)
        self.assertEqual(resolved.explain("review.post.inline")["contributions"][0]["line"], 4)
        self.write("ws/proj/.workflow/config.yml", to_yaml({"review.post.inline": True}))
        self.assertTrue(self.resolve(self.tmp / "ws/proj").values["review.post.inline"])

    def test_U_config_merge_07_user_config_wins_over_the_legacy_user_file(self) -> None:
        self.tl2({"domain": "legacy-domain", "tickets.team": "core"}, legacy=True)
        self.tl2({"domain": "config-domain"})
        resolved = self.resolve(self.project())
        self.assertEqual(resolved.values["domain"], "config-domain")
        self.assertEqual(resolved.values["tickets.team"], "core")
        self.assertEqual(resolved.provenance["domain"]["source"], str(self.home / ".workflow/config.yml"))

    def test_U_config_merge_08_governance_from_tl2_is_advisory_and_lower_levels_are_ignored(self) -> None:
        self.tl2({"governance.risk_components": ["billing"]})
        resolved = self.resolve(self.project({"governance.risk_components": []}), None,
                                {"governance.trust_roots": ["mine"]})
        self.assertEqual(resolved.values["governance.risk_components"], ["billing"])
        self.assertEqual(resolved.advisory, ["governance.risk_components"])
        self.assertEqual(resolved.values["governance.trust_roots"], [])
        reasons = {(r["key"], r["level"]): r["reason"] for r in resolved.ignored}
        self.assertEqual(reasons[("governance.risk_components", "TL4")], "governance keys come from TL1 only")
        self.assertEqual(reasons[("governance.trust_roots", "TL5")], "governance keys come from TL1 only")

    def test_U_config_merge_09_governance_from_tl1_is_authoritative(self) -> None:
        tl1 = self.tl1({"governance.trust_roots": ["org-ci"]})
        self.tl2({"governance.trust_roots": ["mine"]})
        resolved = self.resolve(self.project(), **tl1)
        self.assertEqual(resolved.values["governance.trust_roots"], ["org-ci"])
        self.assertEqual(resolved.advisory, [])
        self.assertEqual([(r["key"], r["level"]) for r in resolved.ignored], [("governance.trust_roots", "TL2")])

    def test_U_config_merge_10_invalid_values_fail_closed_at_tl1_tl2_and_are_ignored_below(self) -> None:
        resolved = self.resolve(self.project({"tickets.system": "jira2", "budgets.qa_rounds": -1}))
        self.assertEqual(resolved.values["tickets.system"], "auto")
        self.assertEqual(resolved.values["budgets.qa_rounds"], 2)
        self.assertEqual({r["key"] for r in resolved.ignored}, {"tickets.system", "budgets.qa_rounds"})
        self.assertTrue(all(r["reason"].startswith("invalid value") for r in resolved.ignored))
        self.write("ws/proj/.workflow/config.yml", "tickets: github\n")
        self.assertTrue(any("'tickets'" in w and "expected a mapping" in w for w in self.resolve(self.tmp / "ws/proj").warnings))
        (self.tmp / "ws/proj/.workflow/config.yml").unlink()
        self.write("home/.workflow/config.yml", "chat: irc\n")
        with self.assertRaises(wfconfig.ConfigError) as caught:
            self.resolve(self.tmp / "ws/proj")
        self.assertEqual((caught.exception.code, caught.exception.line), ("E_CONFIG_INVALID", 1))
        (self.tmp / "home/.workflow/config.yml").unlink()
        with self.assertRaises(wfconfig.ConfigError) as caught:
            self.resolve(self.tmp / "ws/proj", **self.tl1({"guard.mode": "strict"}))
        self.assertEqual((caught.exception.code, caught.exception.line), ("E_CONFIG_INVALID", 1))
        self.write("home/.workflow/config.yml", "tickets: github\n")
        with self.assertRaises(wfconfig.ConfigError):
            self.resolve(self.tmp / "ws/proj")

    def test_U_config_merge_11_unknown_keys_warn_with_the_nearest_key(self) -> None:
        self.write("ws/proj/.workflow/config.yml", "chat: slack\ngaurd:\n  mode: warn\ncompletely_unknown: 1\n")
        warnings = self.resolve(self.mkdir("ws/proj")).warnings
        self.assertIn("unknown key 'gaurd.mode' in .workflow/config.yml:3 (did you mean 'guard.mode'?)", warnings)
        self.assertIn("unknown key 'completely_unknown' in .workflow/config.yml:4", warnings)
        self.assertEqual(keys.nearest("tickets.sytem"), "tickets.system")
        self.assertIsNone(keys.nearest("tickets.zzzzzz"))

    def test_U_config_merge_12_policy_digest_covers_security_and_governance_only(self) -> None:
        project = self.project({"chat": "slack"})
        base = self.resolve(project).policy_digest()
        self.assertRegex(base, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(self.resolve(project, None, {"chat": "teams", "review.header": "x"}).policy_digest(), base)
        self.assertNotEqual(self.resolve(project, None, {"budgets.qa_rounds": 1}).policy_digest(), base)
        self.tl2({"governance.trust_roots": ["x"]})
        self.assertNotEqual(self.resolve(project).policy_digest(), base)
        resolved = self.resolve(project)
        subset = {k: resolved.values[k] for k in keys.digest_keys()}
        manual = json.dumps({"schema": "daedalus.policy-digest/1", "values": subset}, sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(resolved.policy_digest(), "sha256:" + hashlib.sha256(manual).hexdigest())
        self.assertEqual(wfconfig.canonical_bytes({"b": [1, "é"], "a": None}), '{"a":null,"b":[1,"é"]}'.encode("utf-8"))
        with self.assertRaises(ValueError):
            wfconfig.canonical_bytes({"x": float("nan")})

    def test_U_config_merge_13_document_shape_and_command_overrides(self) -> None:
        self.tl2({"commands": {".": {"test": "make user-test", "lint": "make user-lint"}}})
        project = self.project({"commands": {".": {"test": "make SECRET-TEXT"}}})
        resolved = self.resolve(project, None, {"commands": {".": {"build": "make run-option"}}})
        doc = resolved.to_json()
        self.assertEqual(sorted(doc), sorted(["schema", "repo", "workspace", "sources", "values", "provenance",
                                              "ignored", "advisory", "warnings", "policy_digest"]))
        self.assertEqual(doc["schema"], "daedalus.policy/1")
        self.assertEqual(sorted(doc["values"]), sorted(keys.KEYS))
        self.assertEqual(sorted(doc["provenance"]), sorted(keys.KEYS))
        for source in doc["sources"]:
            self.assertEqual(sorted(source), ["kind", "level", "path", "sha256", "version"])
        text = json.dumps(doc)
        for command in ("make SECRET-TEXT", "make user-test", "make run-option"):
            self.assertNotIn(command, text)
        self.assertEqual(doc["values"]["commands"], [{"root": ".", "name": "lint", "channel": "config", "level": "TL2"},
                                                     {"root": ".", "name": "test", "channel": "config", "level": "TL4"}])
        self.assertEqual([(o["level"], o["name"], o["cmd"]) for o in resolved.command_overrides],
                         [("TL4", "test", "make SECRET-TEXT"), ("TL2", "lint", "make user-lint"),
                          ("TL2", "test", "make user-test")])
        self.assertIn(("commands", "TL5"), {(r["key"], r["level"]) for r in resolved.ignored})


# ---------------------------------------------------------------- AC-5: monotonic policy

class Monotonic(TempCase):
    def ignored(self, resolved: wfconfig.Resolved) -> Dict[tuple, str]:
        return {(r["key"], r["level"]): r["reason"] for r in resolved.ignored}

    def test_U_policy_monotonic_01_repository_cannot_disable_the_org_guard(self) -> None:
        tl1 = self.tl1({"guard.mode": "enforce"})
        resolved = self.resolve(self.project({"guard.mode": "off"}), None, {"guard.mode": "warn"}, **tl1)
        self.assertEqual(resolved.values["guard.mode"], "enforce")
        ignored = self.ignored(resolved)
        self.assertTrue(ignored[("guard.mode", "TL4")].startswith("weakens TL1 value"))
        self.assertTrue(ignored[("guard.mode", "TL5")].startswith("weakens TL1 value"))
        explained = resolved.explain("guard.mode")
        self.assertEqual((explained["level"], explained["op"]), ("TL1", "mode-order"))

    def test_U_policy_monotonic_02_per_run_options_cannot_drop_critical_tier_gates(self) -> None:
        tl1 = self.tl1({"gate.require": ["checks", "review", "qa", "security"], "tiers.steps": {"critical": ["review", "qa"]}})
        resolved = self.resolve(self.project(), None, {"gate.require": ["checks"], "tiers.steps.critical": []}, **tl1)
        self.assertEqual(resolved.values["gate.require"], ["checks", "review", "qa", "security"])
        self.assertEqual(resolved.values["tiers.steps"], {"critical": ["review", "qa"]})
        ignored = self.ignored(resolved)
        self.assertIn("can't remove review, qa, security", ignored[("gate.require", "TL5")])
        self.assertIn("can't remove review, qa", ignored[("tiers.steps.critical", "TL5")])

    def test_U_policy_monotonic_03_repository_cannot_raise_a_ceiling(self) -> None:
        self.tl2({"budgets.rework_rounds": 2})
        resolved = self.resolve(self.project({"budgets": {"rework_rounds": 99, "qa_rounds": 50,
                                                          "role_turns": {"implementer": 500, "argus": 10},
                                                          "run_tokens": {"hard": 1000}}}))
        self.assertEqual(resolved.values["budgets.rework_rounds"], 2)
        self.assertEqual(resolved.values["budgets.qa_rounds"], 2)
        self.assertEqual(resolved.values["budgets.role_turns"]["implementer"], 60)
        self.assertEqual(resolved.values["budgets.role_turns"]["argus"], 10)  # tightening is accepted
        self.assertEqual(resolved.values["budgets.run_tokens.hard"], 1000)  # a ceiling where there was none
        ignored = self.ignored(resolved)
        self.assertIn("weakens TL2 value", ignored[("budgets.rework_rounds", "TL4")])
        self.assertIn(("budgets.role_turns.implementer", "TL4"), ignored)

    def test_U_policy_monotonic_04_repository_cannot_mark_its_own_evidence_trusted(self) -> None:
        resolved = self.resolve(self.project({"gate.trusted_classes": ["ci", "human", "repository"]}))
        self.assertEqual(resolved.values["gate.trusted_classes"], ["ci", "human"])
        self.assertIn("can't add repository", self.ignored(resolved)[("gate.trusted_classes", "TL4")])
        narrowed = self.resolve(self.tmp / "ws/proj", None, {"gate.trusted_classes": ["ci"]})
        self.assertEqual(narrowed.values["gate.trusted_classes"], ["ci"])

    def test_U_policy_monotonic_05_repository_cannot_extend_privileged_allowlists(self) -> None:
        tl1 = self.tl1({"exec.env_passthrough": ["PATH", "LANG"]})
        self.tl2({"guard.readonly_bash_allow": ["git status"]})
        resolved = self.resolve(self.project({"exec.env_passthrough": ["PATH", "AWS_SECRET_ACCESS_KEY"],
                                              "guard.readonly_bash_allow": ["rm -rf"]}), **tl1)
        self.assertEqual(resolved.values["exec.env_passthrough"], ["PATH"])
        self.assertEqual(resolved.values["guard.readonly_bash_allow"], ["git status"])
        ignored = self.ignored(resolved)
        self.assertIn("can't add AWS_SECRET_ACCESS_KEY", ignored[("exec.env_passthrough", "TL4")])
        self.assertEqual(ignored[("guard.readonly_bash_allow", "TL4")], "only TL1 and TL2 may set it")

    def test_U_policy_monotonic_06_repository_cannot_waive_org_requirements(self) -> None:
        tl1 = self.tl1({"gate.non_waivable": ["FM-13"]})
        resolved = self.resolve(self.project({"gate.non_waivable": []}), None, {"gate.non_waivable": ["FM-14"]}, **tl1)
        self.assertEqual(resolved.values["gate.non_waivable"], ["FM-13", "FM-14"])
        self.assertIn("can't remove FM-13", self.ignored(resolved)[("gate.non_waivable", "TL4")])


class _Fake:
    """A synthetic source for operator property tests."""

    def __init__(self, level: str) -> None:
        self.display = f"{level}.yml"

    def line_of(self, _path: Any) -> None:
        return None


def contributions(key: keys.Key, values_by_level: Dict[str, Any]) -> List[wfconfig.Contribution]:
    out = []
    for level in keys.LEVELS:
        if level in values_by_level:
            out.append(wfconfig.Contribution(level, _Fake(level), values_by_level[level], None))
    return out


def at_least_as_strict(key: keys.Key, value: Any, anchor: Any) -> bool:
    if key.op in (keys.MODE_ORDER, keys.MAX_ORDER):
        return key.order.index(value) >= key.order.index(anchor)
    if key.op == keys.MIN:
        return anchor is None or (value is not None and value <= anchor)
    if key.op == keys.UNION:
        return set(anchor) <= set(value)
    if key.op in (keys.INTERSECT, keys.TRUSTED_ADD, keys.TL2_ONLY):
        return set(value) <= set(anchor)
    if key.op == keys.OPT_IN_TRUSTED:
        return value == "none" or value == anchor
    raise AssertionError(key.op)


class PolicyOperators(TempCase):
    def table(self, key_name: str, rows: List[tuple]) -> None:
        """rows: (TL1, TL2, TL4, TL5, expected value, expected level); None = the level doesn't set the key."""
        key = keys.KEYS[key_name]
        for tl1, tl2, tl4, tl5, expected, level in rows:
            with self.subTest(key=key_name, row=(tl1, tl2, tl4, tl5)):
                given = {name: value for name, value in (("TL1", tl1), ("TL2", tl2), ("TL4", tl4), ("TL5", tl5))
                         if value is not None}
                outcome = wfconfig._resolve_security_value(key, contributions(key, given), key.default)
                self.assertEqual((outcome.value, outcome.level), (expected, level))

    def property(self, key_name: str, pool: List[Any]) -> None:
        key = keys.KEYS[key_name]
        rng = random.Random(1234)
        for _ in range(300):
            given = {level: rng.choice(pool) for level in keys.LEVELS if rng.random() < 0.6}
            anchor = wfconfig._resolve_security_value(
                key, contributions(key, {k: v for k, v in given.items() if k in ("TL1", "TL2")}), key.default).value
            value = wfconfig._resolve_security_value(key, contributions(key, given), key.default).value
            self.assertTrue(at_least_as_strict(key, value, anchor), (key_name, given, anchor, value))

    def test_PT_policy_ops_01_mode_order(self) -> None:
        self.table("guard.mode", [(None, None, "off", None, "enforce", "default"),
                                  ("warn", None, "enforce", None, "enforce", "TL4"),
                                  ("enforce", "off", None, None, "enforce", "TL1"),
                                  (None, "warn", "off", "enforce", "enforce", "TL5")])
        self.table("gate.mode", [(None, None, "enforce", None, "enforce", "TL4"),
                                 ("enforce", "advisory", "advisory", None, "enforce", "TL1")])
        self.property("guard.mode", list(keys.GUARD_MODES))

    def test_PT_policy_ops_02_min_with_null_as_no_ceiling(self) -> None:
        self.table("budgets.rework_rounds", [(None, None, 99, None, 3, "default"), (None, None, 1, None, 1, "TL4"),
                                             (2, 5, 9, None, 2, "TL1"), (None, 5, None, 4, 4, "TL5")])
        self.table("budgets.run_tokens.hard", [(None, None, 500, None, 500, "TL4"), (None, 900, 1000, 800, 800, "TL5")])
        self.property("budgets.rework_rounds", [0, 1, 2, 3, 5, 99])
        self.property("budgets.run_tokens.soft", [10, 100, 1000])

    def test_PT_policy_ops_03_max_order(self) -> None:
        self.table("tdd.min", [(None, None, "bugfix", None, "bugfix", "TL4"), ("strict", None, "off", None, "strict", "TL1")])
        self.table("gate.approver_role", [(None, None, "read", None, "maintain", "default"),
                                          (None, "write", None, "admin", "admin", "TL5")])
        resolved = self.resolve(self.project({"tiers.floors": {"security": "trivial", "data": "critical"}}), None,
                                None, **self.tl1({"tiers.floors": {"security": "full"}}))
        self.assertEqual(resolved.values["tiers.floors"], {"security": "full", "data": "critical"})
        self.property("tdd.min", list(keys.TDD_LEVELS))
        self.property("gate.approver_role", list(keys.APPROVER_ROLES))

    def test_PT_policy_ops_04_union(self) -> None:
        self.table("gate.require", [(None, None, ["checks"], None, ["checks", "review", "qa"], "default"),
                                    (None, None, ["lint"], None, ["checks", "review", "qa", "lint"], "TL4"),
                                    (["checks"], ["x"], [], ["y"], ["checks", "x", "y"], "TL5")])
        self.property("gate.non_waivable", [[], ["FM-1"], ["FM-2"], ["FM-1", "FM-3"]])

    def test_PT_policy_ops_05_intersect(self) -> None:
        self.table("exec.env_passthrough", [(None, None, ["A"], None, [], "default"),
                                            (None, ["A", "B"], ["B", "C"], None, ["B"], "TL4"),
                                            (["A"], ["A", "B"], None, None, ["A"], "TL1")])
        self.table("gate.trusted_classes", [(None, None, ["ci", "bot"], None, ["ci"], "TL4")])
        self.property("gate.trusted_classes", [[], ["ci"], ["human"], ["ci", "human", "repo"]])

    def test_PT_policy_ops_06_trusted_add(self) -> None:
        self.table("guard.readonly_bash_allow", [(None, None, ["rm"], ["curl"], [], "default"),
                                                 (["ls"], ["cat"], ["rm"], None, ["ls", "cat"], "TL2")])
        self.property("guard.readonly_bash_allow", [[], ["ls"], ["rm"]])

    def test_PT_policy_ops_07_tl2_only(self) -> None:
        self.table("isolation.share_sensitive", [(None, [".env"], [".ssh"], None, [".env"], "TL2"),
                                                 ([".npmrc"], [".env"], None, [".aws"], [".npmrc", ".env"], "TL2")])
        self.property("isolation.share_sensitive", [[], [".env"], [".ssh"]])

    def test_PT_policy_ops_08_opt_in_trusted(self) -> None:
        self.table("telemetry.export", [(None, None, "otlp", None, "none", "default"),
                                        (None, "otlp", None, None, "otlp", "TL2"),
                                        (None, "otlp", "none", None, "none", "TL4"),
                                        ("none", "otlp", None, None, "none", "TL1"),
                                        ("otlp", None, "file", None, "otlp", "TL1")])
        self.property("telemetry.export", ["none", "otlp", "file"])

    def test_PT_policy_ops_09_anchor_rule_cases(self) -> None:
        # (a) a lone repository value can't loosen the hub default
        resolved = self.resolve(self.project({"guard.mode": "off"}))
        self.assertEqual(resolved.values["guard.mode"], "enforce")
        self.assertEqual(resolved.ignored[0]["reason"], "weakens default value (off is weaker than enforce)")
        # (b) the user may loosen the default on their own machine
        self.tl2({"guard.mode": "warn"})
        resolved = self.resolve(self.tmp / "ws/proj")
        self.assertEqual((resolved.values["guard.mode"], resolved.provenance["guard.mode"]["level"]), ("warn", "TL2"))
        # (c) but never a TL1 value
        resolved = self.resolve(self.tmp / "ws/proj", **self.tl1({"guard.mode": "enforce"}))
        self.assertEqual(resolved.values["guard.mode"], "enforce")
        self.assertIn(("guard.mode", "TL2"), {(r["key"], r["level"]) for r in resolved.ignored})
        # (d) and the workspace and repository can still tighten the user's anchor
        (self.tmp / "org/policy.yml").unlink()
        workspace = self.tl3({"guard.mode": "enforce"})
        self.mkdir("ws/repo")
        resolved = self.resolve(self.tmp / "ws/repo", workspace)
        self.assertEqual((resolved.values["guard.mode"], resolved.provenance["guard.mode"]["level"]), ("enforce", "TL3"))


# ---------------------------------------------------------------- AC-6: CLI

class Cli(TempCase):
    def setUp(self) -> None:
        super().setUp()
        for rel, target in (("user-config.yml", "home/.workflow/config.yml"), ("user-argus.yml", "home/.claude/argus.yml"),
                            ("workspace-config.yml", "ws/.workflow/config.yml"),
                            ("repo-config.yml", "ws/repo/.workflow/config.yml"), ("repo-argus.yml", "ws/repo/.argus.yml")):
            self.write(target, (FIX / "levels" / rel).read_text())
        self.repo = self.git_init("ws/repo")
        self.workspace = self.tmp / "ws"
        self.fake_home = self.mkdir("fake-home")

    def run_cli(self, *args: str, env: Optional[Dict[str, str]] = None, cwd: Optional[Path] = None):
        base = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "DAEDALUS_POLICY_DIR")}
        base.update({"DAEDALUS_HOME": str(self.home), "HOME": str(self.fake_home)})
        base.update(env or {})
        return subprocess.run([sys.executable, "-I", "-B", str(WORKFLOW), *args], capture_output=True, text=True,
                              cwd=str(cwd or self.repo), env=base, timeout=60)

    def test_U_config_cli_01_resolve_prints_the_policy_document(self) -> None:
        result = self.run_cli("config", "resolve", "--json", "--workspace", str(self.workspace))
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["schema"], "daedalus.policy/1")
        self.assertEqual(doc["repo"], str(self.repo))
        self.assertEqual(sorted(doc["values"]), sorted(keys.KEYS))
        self.assertEqual([(s["level"], s["kind"]) for s in doc["sources"]],
                         [("TL2", "legacy"), ("TL2", "config"), ("TL3", "config"), ("TL4", "legacy"), ("TL4", "config")])
        values = doc["values"]
        self.assertEqual((values["domain"], values["tickets.system"], values["tickets.key"], values["chat"],
                          values["review.header"], values["review.post.inline"], values["guard.mode"],
                          values["budgets.rework_rounds"]),
                         ("from-user-config", "github", "ACME-\\d+", "slack", "Repo review", False, "warn", 2))
        self.assertRegex(doc["policy_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("make lint", result.stdout)
        self.assertTrue(any("did you mean 'guard.mode'" in w for w in doc["warnings"]))
        text = self.run_cli("config", "resolve", "--workspace", str(self.workspace))
        self.assertEqual(text.returncode, 0)
        self.assertIn("Sources:", text.stdout)
        self.assertIn("policy_digest: sha256:", text.stdout)

    def test_U_config_cli_02_set_is_tl5(self) -> None:
        result = self.run_cli("config", "resolve", "--json", "--set", "chat=teams", "--set", 'guard.mode="off"',
                              "--set", "gate.require=[checks]", "--set", "review.max_findings=3")
        doc = json.loads(result.stdout)
        self.assertEqual((doc["values"]["chat"], doc["provenance"]["chat"]["level"]), ("teams", "TL5"))
        self.assertEqual(doc["values"]["review.max_findings"], 3)
        self.assertEqual(doc["values"]["guard.mode"], "warn")
        self.assertEqual(doc["values"]["gate.require"], ["checks", "review", "qa"])
        self.assertIn(("guard.mode", "TL5"), {(r["key"], r["level"]) for r in doc["ignored"]})
        self.assertEqual(doc["sources"][-1]["kind"], "run")
        for bad in ("noequals", "=x", "a..b=1", "chat=[unclosed", "guard.mode=off"):
            with self.subTest(bad):
                failed = self.run_cli("config", "resolve", "--json", "--set", bad)
                self.assertEqual(failed.returncode, 2)
                self.assertEqual(json.loads(failed.stdout)["error"]["code"], "E_USAGE")
        quoted = json.loads(self.run_cli("config", "resolve", "--json", "--set", "guard.mode=off").stdout)
        self.assertIn("quote", quoted["error"]["fix"])

    def test_U_config_cli_03_explain_shows_value_source_level_class_operator_and_contributions(self) -> None:
        result = self.run_cli("config", "explain", "guard.mode", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        detail = json.loads(result.stdout)
        self.assertEqual((detail["value"], detail["level"], detail["class"], detail["op"]),
                         ("warn", "TL2", "security", "mode-order"))
        self.assertEqual(detail["source"], str(self.home / ".workflow/config.yml"))
        self.assertEqual([(c["level"], c["status"]) for c in detail["contributions"]],
                         [("TL2", "accepted"), ("TL4", "ignored")])
        self.assertIn("weakens TL2 value", detail["contributions"][1]["reason"])
        self.assertEqual(detail["contributions"][1]["line"], 4)  # the `mode:` line of repo-config.yml
        text = self.run_cli("config", "explain", "tickets.system")
        self.assertIn("class: workflow-preference · operator: nearest", text.stdout)
        self.assertIn("TL4 .workflow/config.yml:2: github → accepted", text.stdout)

    def test_U_config_cli_04_get_prints_one_value(self) -> None:
        self.assertEqual(self.run_cli("config", "get", "tickets.system").stdout, "github\n")
        self.assertEqual(self.run_cli("config", "get", "budgets.rework_rounds", "--json").stdout.strip(), "2")
        self.assertEqual(json.loads(self.run_cli("config", "get", "tickets").stdout)["system"], "github")
        self.assertEqual(self.run_cli("config", "get", "budgets.role_turns.argus").stdout.strip(), "40")
        missing = self.run_cli("config", "get", "tickets.sytem", "--json")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("did you mean 'tickets.system'", json.loads(missing.stdout)["error"]["message"])

    def test_U_config_cli_05_exit_codes_and_error_shape(self) -> None:
        self.write("ws/repo/.workflow/config.yml", "base: &anchor\n  a: 1\n")
        failed = self.run_cli("config", "resolve", "--json")
        self.assertEqual(failed.returncode, 3)
        error = json.loads(failed.stdout)["error"]
        self.assertEqual((error["code"], error["file"], error["line"], error["col"]),
                         ("E_CONFIG_SYNTAX", ".workflow/config.yml", 1, 7))
        self.assertTrue(error["fix"] and error["message"])
        self.assertIn("E_CONFIG_SYNTAX", failed.stderr)
        self.assertIn(".workflow/config.yml:1:7", failed.stderr)  # AC-6: code, file, line and fix on stderr
        self.assertIn("fix:", failed.stderr)
        plain = self.run_cli("config", "get", "chat")
        self.assertEqual((plain.returncode, plain.stdout), (3, ""))
        self.write("home/.workflow/config.yml", "chat: irc\n")
        self.write("ws/repo/.workflow/config.yml", "chat: slack\n")
        self.assertEqual(json.loads(self.run_cli("config", "get", "chat", "--json").stdout)["error"]["code"],
                         "E_CONFIG_INVALID")
        for args in (("config",), ("config", "nope"), ("nope",), (), ("config", "resolve", "--bogus")):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)

    def test_U_config_cli_06_workspace_flag_and_claude_project_dir_fallback(self) -> None:
        def level_of_chat(*args: str, env: Optional[Dict[str, str]] = None) -> str:
            doc = json.loads(self.run_cli("config", "resolve", "--json", *args, env=env).stdout)
            return doc["provenance"]["chat"]["level"]
        self.assertEqual(level_of_chat(), "default")
        self.assertEqual(level_of_chat("--workspace", str(self.workspace)), "TL3")
        self.assertEqual(level_of_chat(env={"CLAUDE_PROJECT_DIR": str(self.workspace)}), "TL3")
        other = self.mkdir("elsewhere")
        self.assertEqual(level_of_chat("--workspace", str(other), env={"CLAUDE_PROJECT_DIR": str(self.workspace)}),
                         "default")
        sub = self.mkdir("ws/repo/pkg")
        doc = json.loads(self.run_cli("config", "resolve", "--json", "--repo", str(sub), cwd=self.tmp).stdout)
        self.assertEqual(doc["repo"], str(self.repo))

    def test_U_config_cli_p95_timing(self) -> None:
        ctx = self.ctx()
        samples = []
        for _ in range(50):
            start = time.perf_counter()
            wfconfig.resolve(self.repo, self.workspace, {"chat": "teams"}, ctx=ctx)
            samples.append(time.perf_counter() - start)
        p95 = sorted(samples)[math.ceil(len(samples) * 0.95) - 1]  # nearest rank: the 48th of 50
        print(f"\n    in-process resolve p95 = {p95 * 1000:.1f} ms over 50 runs (target 50 ms, fails above 100 ms)",
              file=sys.stderr)
        self.assertLessEqual(p95, 0.100)

    def test_workflow_py_never_imports_from_the_project_folder(self) -> None:
        canary = self.tmp / "canary"
        payload = f"open({str(canary)!r}, 'w').write('ran')\n"
        for rel in ("json.py", "argparse.py", "lib/__init__.py", "lib/wfconfig.py"):
            self.write(f"ws/repo/{rel}", payload)
        link = self.tmp / "bin" / "workflow.py"
        link.parent.mkdir()
        link.symlink_to(WORKFLOW)
        for script in (WORKFLOW, link):
            with self.subTest(script=str(script)):
                result = subprocess.run([sys.executable, "-I", "-B", str(script), "config", "get", "chat"], cwd=str(self.repo),
                                        capture_output=True, text=True, env=dict(os.environ, DAEDALUS_HOME=str(self.home)))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(canary.exists())


# ---------------------------------------------------------------- AC-10: detector

def load_detector():
    spec = importlib.util.spec_from_file_location("detect_stack_under_test", SCRIPTS / "detect-stack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Detector(TempCase):
    def test_U_trust_carryover_01_unsafe_is_recomputed_and_never_cleared(self) -> None:
        ds = load_detector()
        self.assertIs(ds.UNSAFE_RE, unsafe.UNSAFE_RE)
        self.assertIs(ds.UNSAFE_BODY_RE, unsafe.UNSAFE_BODY_RE)
        old = {"roots": [{"path": ".", "commands": {
            "deploy": {"cmd": "make deploy-all", "source": "/setup", "confidence": "user", "unsafe": False,
                       "trusted": True, "digest": "sha256:forged"},
            "test": {"cmd": "make test", "source": "/setup", "confidence": "user", "confirmed": True, "unsafe": True},
            "lint": {"cmd": "npm run lint", "source": "package.json", "confidence": "script", "confirmed": True,
                     "unsafe": True},
            "bogus": {"cmd": ["not", "a", "string"], "confidence": "user"},
            "junk": "not-a-mapping"}}]}
        new = {"roots": [{"path": ".", "commands": {"lint": {"cmd": "npm run lint", "source": "package.json",
                                                              "confidence": "script"}}}]}
        commands = ds.carry_over(new, old)["roots"][0]["commands"]
        self.assertEqual(commands["deploy"], {"cmd": "make deploy-all", "source": "/setup", "confidence": "user",
                                              "unsafe": True})
        self.assertEqual(commands["test"], {"cmd": "make test", "source": "/setup", "confidence": "user",
                                            "confirmed": True, "unsafe": True})
        self.assertEqual(commands["lint"], {"cmd": "npm run lint", "source": "package.json", "confidence": "script",
                                            "confirmed": True, "unsafe": True})
        self.assertNotIn("bogus", commands)
        self.assertNotIn("junk", commands)
        for entry in commands.values():
            self.assertFalse({"trusted", "digest", "trusted_at"} & set(entry))
        # end to end: a committed profile with a forged `unsafe: false` keeps `unsafe: true` after re-detection
        project = self.mkdir("proj")
        self.write("proj/.workflow/profile.json", json.dumps({"schema": 1, "roots": [{"path": ".", "commands": {
            "release": {"cmd": "./publish.sh", "source": "/setup", "confidence": "user", "unsafe": False,
                        "trusted": True}}}]}))
        out = subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "detect-stack.py"), "--root", str(project), "--stdout"],
                             capture_output=True, text=True, cwd=str(project), timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        release = json.loads(out.stdout)["roots"][0]["commands"]["release"]
        self.assertEqual(release, {"cmd": "./publish.sh", "source": "/setup", "confidence": "user", "unsafe": True})

    def test_U_detector_nowrite_01_unchanged_profile_is_not_rewritten(self) -> None:
        project = self.mkdir("proj")
        self.write("proj/package.json", json.dumps({"name": "x", "scripts": {"test": "jest"}}))
        detect = [sys.executable, "-I", "-B", str(SCRIPTS / "detect-stack.py"), "--root", str(project)]
        profile_path = project / ".workflow" / "profile.json"
        self.assertEqual(subprocess.run(detect, capture_output=True, cwd=str(project), timeout=60).returncode, 0)
        doc = json.loads(profile_path.read_text())
        doc["generated_at"] = "2000-01-01T00:00:00Z"  # the next run computes a different timestamp
        profile_path.write_text(json.dumps(doc, indent=2) + "\n")
        os.utime(profile_path, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        before = (profile_path.read_bytes(), profile_path.stat().st_mtime_ns)
        self.assertEqual(subprocess.run(detect, capture_output=True, cwd=str(project), timeout=60).returncode, 0)
        self.assertEqual((profile_path.read_bytes(), profile_path.stat().st_mtime_ns), before)
        self.write("proj/package.json", json.dumps({"name": "x", "scripts": {"test": "vitest", "lint": "eslint ."}}))
        self.assertEqual(subprocess.run(detect, capture_output=True, cwd=str(project), timeout=60).returncode, 0)
        after = json.loads(profile_path.read_text())
        self.assertNotEqual(profile_path.read_bytes(), before[0])
        self.assertIn("lint", after["roots"][0]["commands"])
        # --confirm still writes when it changes something, and leaves the file alone when it doesn't
        confirm = detect + ["--confirm", ".:lint"]
        self.assertEqual(subprocess.run(confirm, capture_output=True, cwd=str(project), timeout=60).returncode, 0)
        self.assertTrue(json.loads(profile_path.read_text())["roots"][0]["commands"]["lint"]["confirmed"])
        os.utime(profile_path, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        stamp = profile_path.stat().st_mtime_ns
        self.assertEqual(subprocess.run(confirm, capture_output=True, cwd=str(project), timeout=60).returncode, 0)
        self.assertEqual(profile_path.stat().st_mtime_ns, stamp)
        # --set likewise: it writes the entry it changes, and a repeat of the same --set leaves bytes and mtime alone
        set_dev = detect + ["--set", ".:dev=npm run dev"]
        self.assertEqual(subprocess.run(set_dev, capture_output=True, cwd=str(project), timeout=60).returncode, 0)
        self.assertNotEqual(profile_path.stat().st_mtime_ns, stamp)
        self.assertEqual(json.loads(profile_path.read_text())["roots"][0]["commands"]["dev"]["cmd"], "npm run dev")
        os.utime(profile_path, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        before = (profile_path.read_bytes(), profile_path.stat().st_mtime_ns)
        self.assertEqual(subprocess.run(set_dev, capture_output=True, cwd=str(project), timeout=60).returncode, 0)
        self.assertEqual((profile_path.read_bytes(), profile_path.stat().st_mtime_ns), before)

    def test_rules_digest_covers_the_unsafe_vocabulary(self) -> None:
        copy = self.mkdir("hub/scripts")
        shutil.copy2(SCRIPTS / "detect-stack.py", copy / "detect-stack.py")
        shutil.copytree(SCRIPTS / "lib", copy / "lib")
        spec = importlib.util.spec_from_file_location("detect_stack_copy", copy / "detect-stack.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        first = module.rules_digest()
        with open(copy / "lib" / "unsafe.py", "a") as handle:
            handle.write("# vocabulary changed\n")
        self.assertNotEqual(module.rules_digest(), first)


# ---------------------------------------------------------------- PF-9: the QA plugin's own scripts

class BuildQaScripts(TempCase):
    def test_U_build_qa_scripts_01_qa_plugin_copy_resolves_like_the_main_plugin(self) -> None:
        out = self.tmp / "build"
        built = subprocess.run(["bash", str(HUB / "scripts" / "build-plugin.sh"), "--out", str(out)],
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(built.returncode, 0, built.stderr)
        main, qa = (out / "plugins" / name / "scripts" for name in ("daedalus", "daedalus-qa"))
        shipped = ["workflow.py", "detect-stack.py"] + [f"lib/{p.name}" for p in sorted((SCRIPTS / "lib").glob("*.py"))]
        for rel in shipped:  # byte-identical to the source in both plugins, lib/ structure kept
            with self.subTest(script=rel):
                self.assertEqual((qa / rel).read_bytes(), (SCRIPTS / rel).read_bytes())
                self.assertEqual((main / rel).read_bytes(), (SCRIPTS / rel).read_bytes())
        self.assertFalse((qa / "session-init.sh").exists(), "hooks stay in the main plugin")
        self.assertFalse((out / "plugins" / "daedalus-qa" / "skills" / "stacks").exists())

        # Fixture: a TL3 workspace, a TL4 config with a QA setting and a committed override, and a profile
        # with detected (`script`) and `user` entries, so `config commands` re-detects from the QA copy.
        self.write("ws/.workflow/config.yml", "chat: slack\n")
        repo = self.git_init("ws/repo")
        self.write("ws/repo/package.json", json.dumps({"name": "fixture", "scripts": {"test": "jest", "lint": "eslint ."}}))
        self.write("ws/repo/.workflow/config.yml",
                   'qa:\n  base_url: "http://localhost:5173"\ncommands:\n  ".":\n    build: "make dist"\n')
        for extra in ([], ["--set", ".:dev=npm run start:local"]):
            detect = subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "detect-stack.py"), "--root", str(repo),
                                     *extra], capture_output=True, text=True, cwd=str(repo), timeout=60)
            self.assertEqual(detect.returncode, 0, detect.stderr)
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "DAEDALUS_POLICY_DIR")}
        env.update({"DAEDALUS_HOME": str(self.home), "HOME": str(self.mkdir("fake-home"))})

        def run(scripts: Path, *args: str) -> Dict[str, Any]:
            result = subprocess.run([sys.executable, "-I", "-B", str(scripts / "workflow.py"), "config", *args, "--json",
                                     "--repo", str(repo), "--workspace", str(self.tmp / "ws")],
                                    capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        resolved = run(qa, "resolve")
        self.assertEqual(resolved, run(main, "resolve"))
        self.assertEqual((resolved["values"]["qa.base_url"], resolved["provenance"]["chat"]["level"]),
                         ("http://localhost:5173", "TL3"))
        commands = run(qa, "commands")
        self.assertEqual(commands, run(main, "commands"))
        self.assertEqual(commands["redetection"], "ok")
        state = {(r["name"], r["channel"]): (r["trusted"], r["basis"]) for r in commands["commands"]}
        self.assertEqual(state, {("install", "profile"): (True, "detected"), ("test", "profile"): (True, "detected"),
                                 ("lint", "profile"): (True, "detected"), ("dev", "profile"): (False, None),
                                 ("build", "config"): (False, None)})


def build_plugin_functions() -> Dict[str, Any]:
    """scripts/build-plugin.sh's Python (its heredoc minus the final `sys.exit(main())`), run in a fresh namespace."""
    text = (HUB / "scripts" / "build-plugin.sh").read_text(encoding="utf-8")
    source = text.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0].rstrip()
    tail = "sys.exit(main())"
    if not source.endswith(tail):
        raise AssertionError(f"build-plugin.sh's Python no longer ends with {tail}")
    namespace: Dict[str, Any] = {"__name__": "build_plugin_under_test"}
    exec(compile(source[:-len(tail)], "build-plugin.sh", "exec"), namespace)
    return namespace


class BuildCompanionNames(TempCase):
    def test_U_build_companion_names_01_companion_names_main_plugin_commands_with_their_prefix(self) -> None:
        """RW4-AC-2: the companion plugin's Markdown names main-plugin commands as /daedalus:<name> (a
        /daedalus-qa:manual-test session can't count on the main plugin's name table); the match is bounded, so
        paths, prefixed names, longer names and the companion's own commands stay; the main plugin's output is
        byte-identical to a build without the rule, and the script install's source keeps its bare `/setup`."""
        ns = build_plugin_functions()
        names = ns["main_commands"](ns["tracked"]())
        self.assertTrue({"setup", "project-manager", "argus", "argus-scan"} <= set(names), names)
        self.assertNotIn("manual-test", names)
        self.assertTrue(set(names) <= {p.stem for p in (HUB / ".claude" / "commands").glob("*.md")})
        bare = ns["bare_commands"](names)
        prefixed = {
            "/setup": "/daedalus:setup",
            "run /setup --refresh": "run /daedalus:setup --refresh",
            "`/setup`": "`/daedalus:setup`",
            "(/setup)": "(/daedalus:setup)",
            '"/setup -x"': '"/daedalus:setup -x"',
            "ok.\n/project-manager docs/plans/x.md": "ok.\n/daedalus:project-manager docs/plans/x.md",
            "run /setup. Then /argus-scan, /argus; /new-task: go\t/test-gen":
                "run /daedalus:setup. Then /daedalus:argus-scan, /daedalus:argus; /daedalus:new-task: go\t/daedalus:test-gen",
        }
        unchanged = ("docs/setup.md", ".claude/commands/setup.md", "/daedalus:setup", "`/daedalus:setup`", "/setup-x",
                     "/setup.md", "/setup:x", "/setup/", "/setupx", "~/setup", "./setup", "x/setup",
                     "https://example.com/setup", "${CLAUDE_PLUGIN_ROOT}/commands/setup.md", "/manual-test",
                     "/daedalus-qa:manual-test", "/argus-scanner", "/unknown")
        for text, expected in list(prefixed.items()) + [(text, text) for text in unchanged]:
            with self.subTest(text=text):
                self.assertEqual(ns["name_main_commands"](text, bare), expected)
        self.assertEqual(ns["name_main_commands"]("/setup", ns["bare_commands"]([])), "/setup")
        cross = ns["rewrite"]("see `.claude/commands/setup.md`", ns["QA"])  # REF already names it with its prefix
        self.assertEqual(ns["name_main_commands"](cross, bare), cross)
        self.assertIn("/daedalus:setup", cross)

        # The real build, as the hub runs it, against the same build without the companion rule.
        out, plain = self.tmp / "build", self.tmp / "plain"
        built = subprocess.run(["bash", str(HUB / "scripts" / "build-plugin.sh"), "--out", str(out)],
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(built.returncode, 0, built.stderr)
        ns["name_main_commands"] = lambda text, pattern: text
        ns["build"](plain)

        def files(base: Path, plugin: str) -> Dict[str, bytes]:
            root = base / "plugins" / plugin
            return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}

        self.assertEqual(files(out, "daedalus"), files(plain, "daedalus"))
        self.assertEqual((out / ".claude-plugin" / "marketplace.json").read_bytes(),
                         (plain / ".claude-plugin" / "marketplace.json").read_bytes())
        companion, without = files(out, "daedalus-qa"), files(plain, "daedalus-qa")
        self.assertEqual(sorted(companion), sorted(without))
        changed = sorted(rel for rel in companion if companion[rel] != without[rel])
        self.assertIn("commands/manual-test.md", changed)
        self.assertEqual([rel for rel in changed if not rel.endswith(".md")], [])
        manual_test = companion["commands/manual-test.md"].decode("utf-8")
        self.assertIn("run `/daedalus:setup` to trust the command", manual_test)
        self.assertNotIn("`/setup`", manual_test)
        for rel, data in companion.items():
            if rel.endswith(".md"):
                with self.subTest(companion=rel):
                    self.assertIsNone(bare.search(data.decode("utf-8")))
        # The script install's text is the source's, unchanged: it keeps the bare name.
        self.assertIn("run `/setup` to trust the command",
                      (HUB / ".claude" / "commands" / "manual-test.md").read_text(encoding="utf-8"))



def hub_text_files() -> List[Path]:
    """Every text file under .claude/ (the shipped tree), minus the audit log and Finder metadata."""
    files = []
    for path in sorted((HUB / ".claude").rglob("*")):
        if not path.is_file() or path.name in ("audit.log", ".DS_Store"):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(path)
    return files


class Consumers(unittest.TestCase):
    """AC-7: every consumer reads configuration through the resolver, and Daedalus' Python runs isolated (PF-2)."""

    CONFIG_READERS = (
        ".claude/commands/argus.md", ".claude/commands/argus-scan.md", ".claude/commands/setup.md",
        ".claude/commands/daily-report.md", ".claude/commands/manual-test.md", ".claude/commands/feature-plan.md",
        ".claude/commands/apply-ticket.md", ".claude/commands/project-manager.md",
        ".claude/skills/argus/SKILL.md", ".claude/skills/argus/config-template.yml",
        ".claude/skills/ticket-adapters/SKILL.md", ".claude/skills/project-profile/SKILL.md",
        # QA reads the values /manual-test resolved and passed in its brief, never the config files
        ".claude/agents/qa-tester.md", ".claude/skills/manual-qa/SKILL.md",
    )
    # Prose that tells the model to combine config files itself (the rules now live in lib/wfconfig.py).
    MERGE_PROSE = re.compile(r"key by key|merge[sd]? recursively|replaced whole|falls? through|nearest (?:wins|first)"
                             r"|\*\*Precedence\*\*|\*\*Merge rules", re.I)
    NOT_ISOLATED = re.compile(r"\bpython3 (?!-I\b)")
    HOOK_CHILD_NOT_ISOLATED = re.compile(r"sys\.executable,(?!\s*\"-I\")")
    WORKFLOW_CALL = re.compile(r"python3 -I [^`\n]*workflow\.py[`\"]? (?:config|trust) [^`\n]*")

    def test_U_config_consumers_01_resolver_only_and_isolated_python(self) -> None:
        problems: List[str] = []
        for hook in sorted((HUB / ".claude" / "hooks").glob("*.sh")):
            text = hook.read_text(encoding="utf-8")
            if re.search(r"\^overlay:", text):
                problems.append(f"{hook.name}: reads `overlay:` with a regex instead of the resolver")
            for match in self.HOOK_CHILD_NOT_ISOLATED.finditer(text):
                problems.append(f"{hook.name}: starts Python without -I: {match.group(0)!r}")
        session = (HUB / ".claude" / "hooks" / "session-init.sh").read_text(encoding="utf-8")
        self.assertIn("wfconfig.resolve(", session, "session-init.sh must get overlay from the resolver in process")
        self.assertIn("python3 -I -", session)
        for rel in self.CONFIG_READERS:
            text = (HUB / rel).read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                found = self.MERGE_PROSE.search(line)
                if found:
                    problems.append(f"{rel}:{number}: describes a manual merge ({found.group(0)!r})")
            if not re.search(r"config (?:resolve|get|explain)\b", text):
                problems.append(f"{rel}: doesn't read configuration through `workflow.py config resolve`, `get` or `explain`")
        for path in hub_text_files():
            rel = path.relative_to(HUB)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                found = self.NOT_ISOLATED.search(line)
                if found:
                    problems.append(f"{rel}:{number}: `python3` without -I: {line.strip()[:100]}")
                for call in self.WORKFLOW_CALL.finditer(line):
                    if "--workspace" not in call.group(0) and path.suffix == ".md":
                        problems.append(f"{rel}:{number}: workflow.py call without --workspace: {call.group(0)[:100]}")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


if __name__ == "__main__":
    verbosity = 2 if "-v" in sys.argv[1:] else 1
    try:
        result = unittest.main(argv=[sys.argv[0]], verbosity=verbosity, exit=False).result
    finally:
        shutil.rmtree(SAFE_ROOT, ignore_errors=True)
    sys.exit(0 if result.wasSuccessful() else 1)
PY
