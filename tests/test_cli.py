# Copyright (C) 2026 treelib-toolkit contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""End-to-end tests for the ``python -m treelib`` command line interface."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from treelib import Tree
from treelib.cli import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_tree(directory, name, tree):
    path = os.path.join(directory, name)
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(tree.to_json(with_data=True, with_identifier=True))
    return path


def sample():
    tree = Tree()
    tree.create_node("project", "root", data={"kind": "dir"})
    tree.create_node("src", "src", parent="root", data={"kind": "dir"})
    tree.create_node("main.py", "main", parent="src", data={"kind": "file", "classes": "py"})
    tree.create_node("util.py", "util", parent="src", data={"kind": "file", "classes": "py"})
    tree.create_node("docs", "docs", parent="root", data={"kind": "dir"})
    tree.create_node("README.md", "readme", parent="docs", data={"kind": "file", "classes": "md"})
    return tree


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.tree_path = write_tree(self.directory, "tree.json", sample())

    def run_cli(self, *argv):
        """Run the CLI in-process and capture stdout/stderr."""
        out, err = io.StringIO(), io.StringIO()
        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            code = main(list(argv))
        finally:
            sys.stdout, sys.stderr = stdout, stderr
        return code, out.getvalue(), err.getvalue()


class ShowTests(CliTestCase):
    def test_text(self):
        code, out, err = self.run_cli("show", self.tree_path)
        self.assertEqual(code, 0)
        self.assertEqual(out, "project\n├── docs\n│   └── README.md\n└── src\n    ├── main.py\n    └── util.py\n")

    def test_show_id(self):
        code, out, _ = self.run_cli("show", self.tree_path, "--show-id")
        self.assertIn("main.py[main]", out)

    def test_markdown(self):
        code, out, _ = self.run_cli("show", self.tree_path, "-f", "markdown")
        self.assertTrue(out.startswith("- project\n"))

    def test_mermaid(self):
        code, out, _ = self.run_cli("show", self.tree_path, "-f", "mermaid")
        self.assertIn("graph TD", out)

    def test_dot(self):
        code, out, _ = self.run_cli("show", self.tree_path, "-f", "dot")
        self.assertIn("digraph tree", out)

    def test_html(self):
        code, out, _ = self.run_cli("show", self.tree_path, "-f", "html", "--title", "My Tree")
        self.assertIn("<title>My Tree</title>", out)
        self.assertEqual(out.count("<li class="), 6)

    def test_limit(self):
        code, out, _ = self.run_cli("show", self.tree_path, "--limit", "2")
        self.assertEqual(len(out.splitlines()), 2)

    def test_depth(self):
        code, out, _ = self.run_cli("show", self.tree_path, "--depth", "1")
        self.assertNotIn("main.py", out)
        self.assertIn("src", out)

    def test_out_file(self):
        target = os.path.join(self.directory, "out.txt")
        code, out, _ = self.run_cli("show", self.tree_path, "-o", target)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        with io.open(target, encoding="utf-8") as handle:
            self.assertIn("project", handle.read())

    def test_missing_file(self):
        code, out, err = self.run_cli("show", os.path.join(self.directory, "nope.json"))
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)


class QueryTests(CliTestCase):
    def test_ids(self):
        code, out, _ = self.run_cli("query", self.tree_path, "*.py")
        self.assertEqual(out, "main\nutil\n")

    def test_count_to_stderr(self):
        code, out, err = self.run_cli("query", self.tree_path, "*.py", "--count")
        self.assertIn("2 node(s) matched", err)

    def test_json(self):
        code, out, _ = self.run_cli("query", self.tree_path, "#main", "-f", "json")
        payload = json.loads(out)
        self.assertEqual(payload[0]["id"], "main")
        self.assertEqual(payload[0]["tag"], "main.py")

    def test_text(self):
        code, out, _ = self.run_cli("query", self.tree_path, "[kind=dir]", "-f", "text")
        self.assertIn("project", out)

    def test_markdown(self):
        code, out, _ = self.run_cli("query", self.tree_path, "*.md", "-f", "markdown")
        self.assertIn("README.md", out)

    def test_bad_selector(self):
        code, out, err = self.run_cli("query", self.tree_path, "a >")
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_no_match(self):
        code, out, _ = self.run_cli("query", self.tree_path, "#nope")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class StatsTests(CliTestCase):
    def test_text(self):
        code, out, _ = self.run_cli("stats", self.tree_path)
        self.assertIn("nodes      : 6", out)
        self.assertIn("depth      : 2", out)
        self.assertIn("leaves     : 3", out)
        self.assertIn("per level  : 0:1, 1:2, 2:3", out)

    def test_json(self):
        code, out, _ = self.run_cli("stats", self.tree_path, "-f", "json")
        payload = json.loads(out)
        self.assertEqual(payload["nodes"], 6)
        self.assertEqual(payload["depth"], 2)
        self.assertEqual(payload["leaves"], 3)
        self.assertEqual(payload["per_level"], {"0": 1, "1": 2, "2": 3})

    def test_empty_tree(self):
        # ``to_json`` on an empty tree raises upstream, so write the smallest
        # valid document by hand: a single leaf node is the only shape that
        # round-trips through ``from_json`` for a one-node tree.
        path = os.path.join(self.directory, "empty.json")
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("{}")
        code, out, err = self.run_cli("stats", path)
        self.assertEqual(code, 0, err)
        self.assertIn("empty tree", out)

    def test_empty_tree_json(self):
        path = os.path.join(self.directory, "empty2.json")
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("{}")
        code, out, _ = self.run_cli("stats", path, "-f", "json")
        payload = json.loads(out)
        self.assertEqual(payload["nodes"], 0)
        self.assertEqual(payload["per_level"], {})


class DiffTests(CliTestCase):
    def setUp(self):
        CliTestCase.setUp(self)
        changed = sample()
        changed.update_node("main", data={"kind": "file", "classes": "py", "size": 10})
        changed.move_node("util", "docs")
        changed.remove_node("readme")
        changed.create_node("setup.py", "setup", parent="root", data={"kind": "file"})
        self.changed_path = write_tree(self.directory, "changed.json", changed)

    def test_text(self):
        code, out, _ = self.run_cli("diff", self.tree_path, self.changed_path)
        self.assertIn("- readme", out)
        self.assertIn("+ setup (parent=root)", out)
        self.assertIn("~ util moved: src -> docs", out)
        self.assertIn("* main: data", out)

    def test_identical(self):
        code, out, _ = self.run_cli("diff", self.tree_path, self.tree_path)
        self.assertEqual(code, 0)
        self.assertIn("no structural changes", out)

    def test_exit_code(self):
        code, _, _ = self.run_cli("diff", self.tree_path, self.changed_path, "--exit-code")
        self.assertEqual(code, 1)

    def test_json(self):
        code, out, _ = self.run_cli("diff", self.tree_path, self.changed_path, "-f", "json")
        payload = json.loads(out)
        kinds = sorted({change["kind"] for change in payload["changes"]})
        self.assertEqual(kinds, ["add", "move", "remove", "update"])

    def test_ignore_data(self):
        code, out, _ = self.run_cli("diff", self.tree_path, self.changed_path, "--ignore-data")
        self.assertNotIn("* main", out)

    def test_markdown(self):
        code, out, _ = self.run_cli("diff", self.tree_path, self.changed_path, "-f", "markdown")
        self.assertIn("| kind | node | detail |", out)


class ValidateTests(CliTestCase):
    def test_valid(self):
        code, out, _ = self.run_cli("validate", self.tree_path)
        self.assertEqual(code, 0)
        self.assertIn("tree is valid", out)

    def test_json(self):
        code, out, _ = self.run_cli("validate", self.tree_path, "-f", "json")
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["problems"], [])


class ConvertTests(CliTestCase):
    def test_to_markdown(self):
        code, out, _ = self.run_cli("convert", self.tree_path, "--to", "markdown")
        self.assertTrue(out.startswith("- project"))

    def test_to_json_round_trip(self):
        target = os.path.join(self.directory, "rt.json")
        self.run_cli("convert", self.tree_path, "--to", "json", "-o", target)
        with io.open(target, encoding="utf-8") as handle:
            restored = Tree.from_json(handle.read())
        self.assertEqual(sorted(restored.nodes), sorted(sample().nodes))

    def test_to_text_then_read_back(self):
        target = os.path.join(self.directory, "t.txt")
        self.run_cli("convert", self.tree_path, "--to", "text", "-o", target)
        code, out, _ = self.run_cli("show", target)
        self.assertEqual(out, "project\n├── docs\n│   └── README.md\n└── src\n    ├── main.py\n    └── util.py\n")

    def test_unknown_target(self):
        code, out, err = self.run_cli("convert", self.tree_path, "--to", "yaml")
        self.assertEqual(code, 2)
        self.assertIn("unknown target format", err)


class ParserTests(unittest.TestCase):
    def test_no_command_prints_help(self):
        out = io.StringIO()
        stdout = sys.stdout
        sys.stdout = out
        try:
            code = main([])
        finally:
            sys.stdout = stdout
        self.assertEqual(code, 0)
        self.assertIn("usage:", out.getvalue())

    def test_version(self):
        process = subprocess.run(
            [sys.executable, "-m", "treelib", "--version"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0)
        self.assertIn(b"treelib-toolkit", process.stdout)

    def test_module_entry_point(self):
        """``python -m treelib`` must work as an installed module would."""
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "tree.json")
        tree = sample()
        tree.update_node("main", data={"kind": "file", "classes": "py"})
        tree.update_node("util", data={"kind": "file", "classes": "py"})
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(tree.to_json(with_data=True, with_identifier=True))
        process = subprocess.run(
            [sys.executable, "-m", "treelib", "query", path, "*.py"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.decode("utf-8").split(), ["main", "util"])

    def test_stdin_json(self):
        process = subprocess.run(
            [sys.executable, "-m", "treelib", "stats", "-", "-f", "json"],
            cwd=ROOT,
            input=sample().to_json(with_identifier=True).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout.decode("utf-8"))["nodes"], 6)


if __name__ == "__main__":
    unittest.main()
