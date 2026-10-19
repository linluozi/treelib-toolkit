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
"""Tests for the selector engine (:mod:`treelib.query`)."""

import unittest

from treelib import Tree
from treelib.query import QueryError, QueryResult, parse


def sample_tree():
    """A file-tree fixture with tags, ids, data attributes and classes."""
    tree = Tree()
    tree.create_node("project", "root", data={"kind": "dir", "classes": "workspace root"})
    tree.create_node("src", "src", parent="root", data={"kind": "dir", "classes": "dir"})
    tree.create_node("main.py", "main", parent="src", data={"kind": "file", "size": 120, "classes": "py entry"})
    tree.create_node("util.py", "util", parent="src", data={"kind": "file", "size": 40, "classes": "py"})
    tree.create_node("draft.py", "draft", parent="src", data={"kind": "file", "size": 0, "classes": "py draft"})
    tree.create_node("docs", "docs", parent="root", data={"kind": "dir", "classes": "dir"})
    tree.create_node("README.md", "readme", parent="docs", data={"kind": "file", "size": 8, "classes": "md"})
    tree.create_node("NOTES.md", "notes", parent="docs", data={"kind": "file", "size": 3, "classes": "md"})
    tree.create_node("build", "build", parent="root", data={"kind": "dir"})
    tree.create_node("out.bin", "out", parent="build", data={"kind": "file", "size": 999})
    return tree


class ParseTests(unittest.TestCase):
    def test_simple_compounds(self):
        selector = parse("div#main.a.b[data-x=1]:leaf")[0]
        compound = selector.compounds[0]
        self.assertEqual(compound.tag, "div")
        self.assertEqual(compound.ids, ["main"])
        self.assertEqual(compound.classes, ["a", "b"])
        self.assertEqual(compound.attrs, [("data-x", "=", "1")])
        self.assertEqual(compound.pseudos, [("leaf", None)])

    def test_combinators(self):
        cases = {
            "a > b": [">"],
            "a b": [" "],
            "a+b": ["+"],
            "a ~ b": ["~"],
            "a > b > c": [">", ">"],
            "a  >  b": [">"],
        }
        for text, expected in cases.items():
            self.assertEqual(parse(text)[0].combinators, expected, text)

    def test_dotted_tag_vs_class(self):
        self.assertEqual(parse("main.py")[0].compounds[0].tag, "main.py")
        self.assertEqual(parse("main.py")[0].compounds[0].classes, [])
        self.assertEqual(parse("*.py")[0].compounds[0].tag, "*")
        self.assertEqual(parse("*.py")[0].compounds[0].classes, ["py"])
        self.assertEqual(parse("*.py.draft")[0].compounds[0].classes, ["py", "draft"])
        self.assertEqual(parse(".py")[0].compounds[0].tag, None)
        self.assertEqual(parse(".py")[0].compounds[0].classes, ["py"])

    def test_selector_list(self):
        self.assertEqual(len(parse("a, b, c")), 3)

    def test_quoted_values(self):
        compound = parse('[title="hello world"]')[0].compounds[0]
        self.assertEqual(compound.attrs, [("title", "=", "hello world")])
        compound = parse("[title='it, s']")[0].compounds[0]
        self.assertEqual(compound.attrs, [("title", "=", "it, s")])

    def test_bad_selectors(self):
        for bad in ("", ">", "a >", "#", "[", "a[", ":nope", ":nth-child(x)", "a,,b", "[a=]", ":has()", "a)b"):
            with self.assertRaises(QueryError, msg=bad):
                parse(bad)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tree = sample_tree()

    def assert_ids(self, selector, expected):
        self.assertEqual(self.tree.query(selector).ids, expected, selector)

    def test_universal_and_tag(self):
        self.assertEqual(len(self.tree.query("*")), 10)
        self.assert_ids("*.py", ["main", "util", "draft"])
        self.assert_ids("main.py", ["main"])
        self.assert_ids("out.bin", ["out"])

    def test_id_and_class(self):
        self.assert_ids("#src", ["src"])
        self.assert_ids(".py", ["main", "util", "draft"])
        self.assert_ids(".py.draft", ["draft"])
        self.assert_ids(".md", ["readme", "notes"])

    def test_attributes(self):
        self.assert_ids("[kind=dir]", ["root", "src", "docs", "build"])
        self.assert_ids("[size=0]", ["draft"])
        self.assert_ids("[size]", ["main", "util", "draft", "readme", "notes", "out"])
        self.assert_ids("[kind=file][size]", ["main", "util", "draft", "readme", "notes", "out"])

    def test_attribute_operators(self):
        self.assert_ids('[size^="1"]', ["main"])
        self.assert_ids('[kind$="r"]', ["root", "src", "docs", "build"])
        self.assert_ids('[classes*="en"]', ["main"])
        self.assert_ids('[classes~="entry"]', ["main"])
        self.assert_ids('[kind!="file"]', ["root", "src", "docs", "build"])

    def test_combinators(self):
        self.assert_ids("#root > *", ["src", "docs", "build"])
        self.assert_ids("#root > * > *", ["main", "util", "draft", "readme", "notes", "out"])
        self.assert_ids("#root *", ["src", "main", "util", "draft", "docs", "readme", "notes", "build", "out"])
        self.assert_ids("#src + #docs", ["docs"])
        self.assert_ids("#src ~ #build", ["build"])
        self.assert_ids("#src + #build", [])

    def test_pseudo_classes(self):
        self.assert_ids(":root", ["root"])
        self.assert_ids(":leaf", ["main", "util", "draft", "readme", "notes", "out"])
        self.assert_ids(":branch", ["root", "src", "docs", "build"])
        self.assert_ids("#src > :first-child", ["main"])
        self.assert_ids("#src > :last-child", ["draft"])
        self.assert_ids("#root > *:nth-child(2)", ["docs"])
        self.assert_ids("#src > *:nth-child(odd)", ["main", "draft"])

    def test_has_and_not(self):
        self.assert_ids("[kind=dir]:has(*.py)", ["root", "src"])
        self.assert_ids("[kind=dir]:has(> #main)", ["src"])
        self.assert_ids("*:not(.py)", ["root", "src", "docs", "readme", "notes", "build", "out"])
        self.assert_ids("*:not([kind=file])", ["root", "src", "docs", "build"])

    def test_contains(self):
        self.assert_ids(":contains(main)", ["main"])
        self.assert_ids(":contains(PY)", ["main", "util", "draft"])
        self.assert_ids(":contains(nothing-here)", [])

    def test_selector_list_is_deduplicated_and_ordered(self):
        self.assert_ids("*.py, *.md", ["main", "util", "draft", "readme", "notes"])
        self.assert_ids("*.py, #main", ["main", "util", "draft"])

    def test_empty_tree(self):
        self.assertEqual(len(Tree().query("*")), 0)

    def test_unknown_node_id(self):
        self.assertEqual(len(self.tree.query("#missing")), 0)


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.tree = sample_tree()
        self.result = self.tree.query("*.py")

    def test_container_protocol(self):
        self.assertEqual(len(self.result), 3)
        self.assertTrue(self.result)
        self.assertEqual(self.result.tags, ["main.py", "util.py", "draft.py"])
        self.assertEqual(self.result.first.tag, "main.py")
        self.assertEqual(self.result.last.tag, "draft.py")
        self.assertIn("main", self.result)
        self.assertEqual(self.result[0].tag, "main.py")
        self.assertEqual(self.result[0:2].ids, ["main", "util"])

    def test_empty_result_is_falsy(self):
        empty = self.tree.query("#nope")
        self.assertFalse(empty)
        self.assertIsNone(empty.first)
        self.assertIsNone(empty.last)

    def test_attr_reads_data_then_node(self):
        self.assertEqual(self.result.attr("kind"), ["file", "file", "file"])
        self.assertEqual(self.result.attr("size"), [120, 40, 0])
        self.assertEqual(self.result.attr("tag"), ["main.py", "util.py", "draft.py"])
        self.assertEqual(self.result.attr("missing", "fallback"), ["fallback"] * 3)

    def test_filter_and_query_chain(self):
        self.assertEqual(self.result.filter(lambda n: n.get_attribute("size") > 0).ids, ["main", "util"])
        subtree = self.tree.query("#root > *")
        self.assertEqual(subtree.query("*.py").ids, ["main", "util", "draft"])

    def test_to_tree_preserves_ancestors(self):
        view = self.result.to_tree()
        # src is the common parent; root is kept as its ancestor.
        self.assertEqual(sorted(view.nodes), ["draft", "main", "root", "src", "util"])
        self.assertEqual(view.root, "root")
        self.assertEqual(view.parent("main").identifier, "src")
        # Placeholder ancestors are marked so they cannot be mistaken for matches.
        self.assertEqual(view["src"].tag, "src (…)")

    def test_to_tree_render(self):
        rendered = self.result.to_tree().show(stdout=False)
        self.assertEqual(rendered, "project (…)\n└── src (…)\n    ├── draft.py\n    ├── main.py\n    └── util.py\n")

    def test_to_tree_empty(self):
        view = self.tree.query("#nope").to_tree()
        self.assertEqual(len(view.nodes), 0)
        self.assertIsNone(view.root)

    def test_equality(self):
        self.assertEqual(self.tree.query("*.py"), self.tree.query("*.py"))
        self.assertNotEqual(self.tree.query("*.py"), self.tree.query("*.md"))
        self.assertIsInstance(self.result, QueryResult)


class NodeHelperTests(unittest.TestCase):
    def test_classes_from_string_and_list(self):
        tree = Tree()
        node = tree.create_node("a", "a", data={"classes": "x y"})
        self.assertEqual(node.get_classes(), ["x", "y"])
        self.assertTrue(node.has_class("x"))
        self.assertFalse(node.has_class("z"))

        tree2 = Tree()
        node2 = tree2.create_node("b", "b", data={"classes": ["p", "q"]})
        self.assertEqual(node2.get_classes(), ["p", "q"])

    def test_no_data_means_no_classes(self):
        tree = Tree()
        node = tree.create_node("a", "a")
        self.assertEqual(node.get_classes(), [])
        self.assertFalse(node.has_attribute("anything"))

    def test_object_data(self):
        class Payload(object):
            def __init__(self):
                self.size = 7

        tree = Tree()
        node = tree.create_node("a", "a", data=Payload())
        self.assertEqual(node.get_attribute("size"), 7)
        self.assertTrue(node.has_attribute("size"))

    def test_falsy_attribute_values(self):
        tree = Tree()
        node = tree.create_node("a", "a", data={"size": 0, "flag": False, "name": ""})
        self.assertTrue(node.has_attribute("size"))
        self.assertEqual(node.get_attribute("size"), 0)
        self.assertEqual(node.get_attribute("flag"), False)


if __name__ == "__main__":
    unittest.main()
