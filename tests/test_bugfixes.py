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
"""Regression tests for the defects fixed in treelib-toolkit 1.9.0.

Every test here fails on upstream treelib 1.8.0 (``caesar0301/treelib`` at
``83b3b87``) and passes after the fix. Each one asserts a concrete value rather
than a shape, so deleting the fix makes the test red again.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from treelib import Tree
from treelib.exceptions import DuplicatedNodeIdError


def chain(depth):
    """A single-branch tree ``n0 -> n1 -> ...`` of ``depth`` nodes."""
    tree = Tree()
    tree.create_node("n0", "n0")
    for index in range(1, depth):
        tree.create_node("n%d" % index, "n%d" % index, parent="n%d" % (index - 1))
    return tree


class DeepStructureTests(unittest.TestCase):
    """Recursion limits used to make deep trees unusable."""

    DEPTH = 1500

    def setUp(self):
        self.tree = chain(self.DEPTH)

    def test_to_dict_does_not_recurse(self):
        result = self.tree.to_dict()
        # Walk down explicitly; the value must be a chain of single-key dicts
        # whose final child is the bare tag of the last node.
        node = result
        seen = 0
        while isinstance(node, dict):
            key = next(iter(node))
            self.assertTrue(key.startswith("n"))
            seen += 1
            children = node[key].get("children")
            node = children[0] if children else None
        # Every node except the terminal leaf is an inner dict.
        self.assertEqual(seen, self.DEPTH - 1)
        self.assertEqual(node, "n%d" % (self.DEPTH - 1))

    def test_to_json_does_not_recurse(self):
        text = self.tree.to_json(with_identifier=True)
        self.assertTrue(text.startswith('{"n0"'))
        self.assertEqual(text.count('"id"'), self.DEPTH)

    def test_show_does_not_recurse(self):
        rendered = self.tree.show(stdout=False)
        self.assertEqual(len(rendered.splitlines()), self.DEPTH)
        self.assertTrue(rendered.startswith("n0\n"))

    def test_from_json_does_not_recurse(self):
        text = self.tree.to_json(with_identifier=True)
        restored = Tree.from_json(text)
        self.assertEqual(len(restored.nodes), self.DEPTH)
        self.assertEqual(restored.depth(), self.DEPTH - 1)
        self.assertEqual(restored["n%d" % (self.DEPTH - 1)].tag, "n%d" % (self.DEPTH - 1))

    def test_save2file_does_not_recurse(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "deep.txt")
        self.tree.save2file(path)
        with io.open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), self.DEPTH)

    def test_json_round_trip_preserves_order(self):
        text = self.tree.to_json(with_identifier=True)
        restored = Tree.from_json(text)
        self.assertEqual(list(restored.expand_tree()), list(self.tree.expand_tree()))


class SingleNodeJsonTests(unittest.TestCase):
    """A lone leaf was exported as a bare string and could not be read back."""

    def test_round_trip(self):
        tree = Tree()
        tree.create_node("Only", "only")
        self.assertEqual(tree.to_json(), '"Only"')
        restored = Tree.from_json(tree.to_json())
        self.assertEqual(len(restored.nodes), 1)
        self.assertEqual(restored[restored.root].tag, "Only")

    def test_round_trip_with_identifier(self):
        tree = Tree()
        tree.create_node("Only", "only")
        restored = Tree.from_json(tree.to_json(with_identifier=True))
        self.assertEqual(restored.root, "only")

    def test_non_object_root_is_rejected(self):
        with self.assertRaises(ValueError):
            Tree.from_json("[1, 2, 3]")

    def test_empty_tree_still_raises_on_export(self):
        # Exporting an empty tree raises; that upstream behaviour is unchanged
        # and callers rely on it to detect "nothing to serialise".
        with self.assertRaises(Exception):
            Tree().to_dict()


class Save2FileTests(unittest.TestCase):
    """save2file appended and leaked one handle per rendered line."""

    def setUp(self):
        self.tree = Tree()
        self.tree.create_node("R", "r")
        self.tree.create_node("A", "a", parent="r")
        self.directory = tempfile.mkdtemp()

    def test_second_call_overwrites(self):
        path = os.path.join(self.directory, "t.txt")
        self.tree.save2file(path)
        first = io.open(path, "rb").read()
        self.tree.save2file(path)
        second = io.open(path, "rb").read()
        self.assertEqual(first, second)
        self.assertEqual(second, "R\n└── A\n".encode("utf-8"))

    def test_append_flag_is_opt_in(self):
        path = os.path.join(self.directory, "t.txt")
        self.tree.save2file(path)
        self.tree.save2file(path, append=True)
        content = io.open(path, "rb").read()
        self.assertEqual(content, ("R\n└── A\n" * 2).encode("utf-8"))

    def test_utf8_payload(self):
        tree = Tree()
        tree.create_node("根", "r")
        tree.create_node("子", "c", parent="r")
        path = os.path.join(self.directory, "u.txt")
        tree.save2file(path)
        self.assertEqual(io.open(path, "rb").read(), "根\n└── 子\n".encode("utf-8"))


class ShowLevelTests(unittest.TestCase):
    """show(level=n) indexed an empty list and raised IndexError.

    ``level`` is the indentation level of the first rendered node, not a
    truncation depth: children keep their own connectors.
    """

    def setUp(self):
        self.tree = Tree()
        self.tree.create_node("R", "r")
        self.tree.create_node("A", "a", parent="r")
        self.tree.create_node("A1", "a1", parent="a")
        self.tree.create_node("B", "b", parent="r")

    def test_show_level_one(self):
        self.assertEqual(self.tree.show(level=1, stdout=False), "R\n├── A\n│   └── A1\n└── B\n")

    def test_show_level_two(self):
        self.assertEqual(self.tree.show(level=2, stdout=False), "R\n├── A\n│   └── A1\n└── B\n")

    def test_show_subtree_with_level(self):
        self.assertEqual(self.tree.show(nid="a", level=1, stdout=False), "A\n└── A1\n")

    def test_show_level_zero_is_default(self):
        self.assertEqual(self.tree.show(level=0, stdout=False), self.tree.show(stdout=False))


class GraphvizFilterTests(unittest.TestCase):
    """Filtered-out nodes still produced edges, so Graphviz rejected the file."""

    def setUp(self):
        self.tree = Tree()
        self.tree.create_node("R", "r")
        self.tree.create_node("keep", "k", parent="r")
        self.tree.create_node("drop", "d", parent="r")

    def _source(self, **kwargs):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.tree.to_graphviz(**kwargs)
        return buffer.getvalue()

    def test_no_dangling_edge(self):
        source = self._source(filter=lambda node: node.identifier != "d")
        self.assertNotIn('"d"', source)
        self.assertIn('"r" -> "k"', source)

    def test_returns_source(self):
        source = self.tree.to_graphviz()
        self.assertTrue(source.startswith("digraph tree {"))
        self.assertTrue(source.endswith("}"))
        self.assertIn('"r" -> "d"', source)

    def test_every_edge_endpoint_is_declared(self):
        source = self._source(filter=lambda node: node.identifier != "k")
        declared = set()
        for line in source.splitlines():
            line = line.strip()
            if line.startswith('"') and "[label" in line:
                declared.add(line.split('"')[1])
        for line in source.splitlines():
            if "->" in line:
                left, right = line.strip().split("->")
                self.assertIn(left.strip().strip('"'), declared)
                self.assertIn(right.strip().strip('"'), declared)


class UpdateNodeTests(unittest.TestCase):
    """Renaming onto an existing identifier silently deleted the other node."""

    def setUp(self):
        self.tree = Tree()
        self.tree.create_node("R", "r")
        self.tree.create_node("A", "a", parent="r")
        self.tree.create_node("B", "b", parent="r")

    def test_collision_raises(self):
        with self.assertRaises(DuplicatedNodeIdError):
            self.tree.update_node("a", identifier="b")

    def test_tree_unchanged_after_collision(self):
        try:
            self.tree.update_node("a", identifier="b")
        except DuplicatedNodeIdError:
            pass
        self.assertEqual(sorted(self.tree.nodes), ["a", "b", "r"])
        self.assertEqual(self.tree["a"].tag, "A")
        self.assertEqual(self.tree["b"].tag, "B")

    def test_rename_to_same_identifier_is_allowed(self):
        self.tree.update_node("a", identifier="a")
        self.assertEqual(sorted(self.tree.nodes), ["a", "b", "r"])

    def test_normal_rename_still_works(self):
        self.tree.update_node("a", identifier="renamed")
        self.assertEqual(sorted(self.tree.nodes), ["b", "r", "renamed"])
        self.assertEqual(self.tree.parent("renamed").identifier, "r")

    def test_rename_root(self):
        self.tree.update_node("r", identifier="root2")
        self.assertEqual(self.tree.root, "root2")
        self.assertEqual(self.tree.parent("a").identifier, "root2")

    def test_rename_then_update_tag_in_one_call(self):
        self.tree.update_node("a", identifier="z", tag="Z")
        self.assertEqual(self.tree["z"].tag, "Z")


class RenderEquivalenceTests(unittest.TestCase):
    """The fixes must not change existing output, byte for byte."""

    def test_all_line_types(self):
        tree = Tree()
        tree.create_node("Root", "root")
        tree.create_node("A", "a", parent="root")
        tree.create_node("B", "b", parent="root")
        tree.create_node("A1", "a1", parent="a")
        expected = {
            "ascii": "Root\n|-- A\n|   +-- A1\n+-- B\n",
            "ascii-ex": "Root\n├── A\n│   └── A1\n└── B\n",
            "ascii-exr": "Root\n├── A\n│   ╰── A1\n╰── B\n",
            "ascii-em": "Root\n╠══ A\n║   ╚══ A1\n╚══ B\n",
            "ascii-emv": "Root\n╟── A\n║   ╙── A1\n╙── B\n",
            "ascii-emh": "Root\n╞══ A\n│   ╘══ A1\n╘══ B\n",
        }
        for line_type, wanted in expected.items():
            self.assertEqual(tree.show(line_type=line_type, stdout=False), wanted)

    def test_sorting_variants(self):
        tree = Tree()
        tree.create_node("R", "r")
        for tag in ("b", "a", "C"):
            tree.create_node(tag, tag.lower() + tag, parent="r")
        self.assertEqual(tree.show(stdout=False), "R\n├── C\n├── a\n└── b\n")
        self.assertEqual(tree.show(sorting=False, stdout=False), "R\n├── b\n├── a\n└── C\n")
        self.assertEqual(tree.show(reverse=True, stdout=False), "R\n├── b\n├── a\n└── C\n")

    def test_to_dict_shape(self):
        tree = Tree()
        tree.create_node("A", "a")
        tree.create_node("B", "b", parent="a")
        self.assertEqual(tree.to_dict(), {"A": {"children": ["B"]}})
        tree.create_node("C", "c", parent="a")
        self.assertEqual(tree.to_dict(), {"A": {"children": ["B", "C"]}})

    def test_collapsed_node_is_a_leaf(self):
        tree = Tree()
        tree.create_node("R", "r")
        child = tree.create_node("C", "c", parent="r")
        tree.create_node("G", "g", parent="c")
        child.expanded = False
        self.assertEqual(tree.to_dict(), {"R": {"children": ["C"]}})
        # to_json goes through to_dict, so it must honour the same rule: the
        # grandchild must not appear anywhere in the document.
        payload = tree.to_json(with_identifier=True)
        self.assertNotIn('"g"', payload)
        self.assertNotIn("G", payload)
        self.assertEqual(payload, '{"R": {"id": "r", "children": [{"C": {"id": "c"}}]}}')
        self.assertEqual(tree.show(stdout=False), "R\n└── C\n")

    def test_collapsed_node_with_data(self):
        tree = Tree()
        tree.create_node("R", "r", data={"v": 1})
        child = tree.create_node("C", "c", parent="r", data={"v": 2})
        tree.create_node("G", "g", parent="c", data={"v": 3})
        child.expanded = False
        payload = tree.to_dict(with_data=True)
        self.assertEqual(payload, {"R": {"data": {"v": 1}, "children": [{"C": {"data": {"v": 2}}}]}})

    def test_to_dict_from_subtree(self):
        tree = Tree()
        tree.create_node("R", "r")
        tree.create_node("A", "a", parent="r")
        tree.create_node("B", "b", parent="r")
        self.assertEqual(tree.to_dict(nid="a"), "A")

    def test_to_dict_unknown_node(self):
        tree = Tree()
        tree.create_node("R", "r")
        with self.assertRaises(Exception):
            tree.to_dict(nid="nope")

    def test_unicode_and_quotes(self):
        tree = Tree()
        tree.create_node('根 "quoted"', "r")
        tree.create_node("子\\back", "c", parent="r")
        self.assertEqual(tree.to_json(), json.dumps(tree.to_dict()))


if __name__ == "__main__":
    unittest.main()
