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
"""Tests for :mod:`treelib.render` and :mod:`treelib.textparse`."""

import re
import unittest

from treelib import Tree, parse_tree, render, slugify, to_dot, to_html, to_markdown, to_mermaid
from treelib.textparse import ParseError


def sample():
    tree = Tree()
    tree.create_node("project", "root")
    tree.create_node("src", "src", parent="root")
    tree.create_node("main.py", "main", parent="src")
    tree.create_node("util.py", "util", parent="src")
    tree.create_node("docs", "docs", parent="root")
    tree.create_node("README.md", "readme", parent="docs")
    return tree


class MarkdownTests(unittest.TestCase):
    def test_output(self):
        self.assertEqual(
            to_markdown(sample()),
            "- project\n  - src\n    - main.py\n    - util.py\n  - docs\n    - README.md",
        )

    def test_show_id(self):
        self.assertIn("- src [src]", to_markdown(sample(), show_id=True))

    def test_limit(self):
        self.assertEqual(len(to_markdown(sample(), limit=2).splitlines()), 2)

    def test_filter(self):
        text = to_markdown(sample(), filter=lambda node: node.identifier != "src")
        self.assertNotIn("main.py", text)
        self.assertIn("docs", text)

    def test_start_from_subtree(self):
        self.assertEqual(to_markdown(sample(), nid="src"), "- src\n  - main.py\n  - util.py")

    def test_unsorted(self):
        self.assertEqual(to_markdown(sample(), sorting=False).splitlines()[1], "  - src")


class MermaidTests(unittest.TestCase):
    def test_structure(self):
        text = to_mermaid(sample())
        self.assertTrue(text.startswith("```mermaid\ngraph TD\n"))
        self.assertTrue(text.endswith("```"))
        self.assertIn('n0["project"]', text)
        self.assertIn("n0 --> n1", text)

    def test_quotes_are_escaped(self):
        tree = Tree()
        tree.create_node('a "quoted" [x]', "r")
        text = to_mermaid(tree)
        self.assertNotIn('["a "quoted"', text)
        self.assertIn("#quot;", text)
        self.assertIn("#91;", text)

    def test_direction(self):
        self.assertIn("graph LR", to_mermaid(sample(), direction="LR"))

    def test_invalid_direction(self):
        with self.assertRaises(ValueError):
            to_mermaid(sample(), direction="SIDEWAYS")

    def test_aliases_are_mermaid_safe(self):
        tree = Tree()
        tree.create_node("root", "a.b/c d")
        tree.create_node("c", "x:y", parent="a.b/c d")
        text = to_mermaid(tree)
        self.assertNotIn("a.b/c d[", text)
        self.assertIn("n0 --> n1", text)


class DotTests(unittest.TestCase):
    def test_structure(self):
        text = to_dot(sample())
        self.assertTrue(text.startswith("digraph tree {"))
        self.assertIn('"root" [label="project", shape=circle]', text)
        self.assertIn('"root" -> "src"', text)

    def test_undirected(self):
        self.assertIn('"root" -- "src"', to_dot(sample(), graph="graph"))

    def test_quotes_escaped(self):
        tree = Tree()
        tree.create_node('say "hi"', "r")
        self.assertIn('label="say \\"hi\\""', to_dot(tree))

    def test_no_dangling_edges_with_filter(self):
        text = to_dot(sample(), filter=lambda node: node.identifier != "src")
        self.assertNotIn('"src"', text)
        self.assertNotIn('-> "main"', text)


class HtmlTests(unittest.TestCase):
    def test_self_contained(self):
        html = to_html(sample())
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script src", html)
        self.assertNotIn('<link rel="stylesheet"', html)

    def test_nodes_rendered(self):
        html = to_html(sample())
        self.assertEqual(html.count("<li class="), 6)
        for tag in ("project", "src", "main.py", "util.py", "docs", "README.md"):
            self.assertIn(tag, html)

    def test_depth_classes(self):
        html = to_html(sample())
        self.assertIn('class="depth-0"', html)
        self.assertIn('class="depth-1"', html)
        self.assertIn('class="depth-2"', html)

    def test_tags_are_escaped(self):
        tree = Tree()
        tree.create_node("<script>alert(1)</script>", "r")
        html = to_html(tree)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_title_is_escaped(self):
        html = to_html(sample(), title="a & b <c>")
        self.assertIn("<title>a &amp; b &lt;c&gt;</title>", html)

    def test_balanced_list_markup(self):
        html = to_html(sample())
        body = html.split('<ul class="tree">', 1)[1].rsplit("</ul>", 1)[0]
        # Every <li> opened inside the tree must be closed before the outer </ul>.
        self.assertEqual(body.count("<li"), body.count("</li>"))
        # Nesting must be well formed: parse with a real parser and compare the
        # node count and the depth distribution against the source tree.
        from html.parser import HTMLParser

        class Collector(HTMLParser):
            def __init__(self):
                HTMLParser.__init__(self)
                self.stack = []
                self.depths = []
                self.li_count = 0
                self.errors = []

            def handle_starttag(self, tag, attrs):
                if tag == "li":
                    self.li_count += 1
                    self.depths.append(len([item for item in self.stack if item == "ul"]))
                    self.stack.append(tag)
                elif tag == "ul":
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if tag in ("li", "ul"):
                    if not self.stack:
                        self.errors.append("closing %s with empty stack" % tag)
                        return
                    if self.stack[-1] != tag:
                        self.errors.append("expected </%s> but saw </%s>" % (self.stack[-1], tag))
                        return
                    self.stack.pop()

        collector = Collector()
        collector.feed(body)
        self.assertEqual(collector.errors, [])
        self.assertEqual(collector.li_count, 6)
        # Depths are measured by the parser: root at 0, two branches at 1, and
        # the three leaves at 2.
        self.assertEqual(sorted(collector.depths), [0, 1, 1, 2, 2, 2])
        self.assertEqual(collector.errors, [])

    def test_leaf_has_no_toggle(self):
        html = to_html(sample())
        # main.py is a leaf: its toggle span must be empty.
        self.assertRegex(html, r'<span class="toggle"></span><span class="node"><span class="tag">main\.py</span>')


class RenderDispatchTests(unittest.TestCase):
    def test_known_formats(self):
        tree = sample()
        self.assertEqual(render(tree, "markdown"), to_markdown(tree))
        self.assertEqual(render(tree, "md"), to_markdown(tree))
        self.assertEqual(render(tree, "mermaid"), to_mermaid(tree))
        self.assertEqual(render(tree, "dot"), to_dot(tree))
        self.assertEqual(render(tree, "html"), to_html(tree))

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            render(sample(), "yaml")

    def test_empty_tree(self):
        self.assertEqual(to_markdown(Tree()), "")
        self.assertIn("graph TD", to_mermaid(Tree()))
        self.assertEqual(to_dot(Tree()), "digraph tree {\n}")


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Child A"), "child-a")
        self.assertEqual(slugify("  Spaced  Out  "), "spaced-out")
        self.assertEqual(slugify("a/b:c"), "abc")
        self.assertEqual(slugify(""), "node")
        self.assertEqual(slugify("子"), "子")


class ParseTreeTests(unittest.TestCase):
    def test_round_trip_show_output(self):
        tree = sample()
        text = tree.show(stdout=False)
        restored = parse_tree(text)
        self.assertEqual(restored.show(stdout=False), text)

    def test_all_line_types(self):
        tree = sample()
        for line_type in ("ascii", "ascii-ex", "ascii-exr", "ascii-em", "ascii-emv", "ascii-emh"):
            text = tree.show(line_type=line_type, stdout=False)
            restored = parse_tree(text)
            self.assertEqual(
                restored.show(line_type=line_type, stdout=False),
                text,
                line_type,
            )

    def test_identifiers_restored_when_shown(self):
        tree = sample()
        restored = parse_tree(tree.show(idhidden=False, stdout=False))
        self.assertEqual(sorted(restored.nodes), ["docs", "main", "readme", "root", "src", "util"])

    def test_duplicate_tags_get_unique_ids(self):
        tree = Tree()
        tree.create_node("X", "r")
        tree.create_node("dup", "a", parent="r")
        tree.create_node("dup", "b", parent="r")
        restored = parse_tree(tree.show(stdout=False))
        self.assertEqual(len(restored.nodes), 3)
        self.assertEqual(len(set(restored.nodes)), 3)

    def test_markdown_bullets(self):
        tree = sample()
        markdown = to_markdown(tree)
        restored = parse_tree(markdown)
        self.assertEqual(restored.show(stdout=False), tree.show(stdout=False))

    def test_empty_input(self):
        self.assertEqual(len(parse_tree("").nodes), 0)
        self.assertEqual(len(parse_tree("\n\n  \n").nodes), 0)

    def test_indented_root_rejected(self):
        with self.assertRaises(ParseError):
            parse_tree("    Root")

    def test_unicode_tags(self):
        tree = Tree()
        tree.create_node("根", "r")
        tree.create_node("子节点", "c", parent="r")
        restored = parse_tree(tree.show(stdout=False))
        self.assertEqual(restored["子节点"].tag, "子节点")
        self.assertEqual(restored["根"].tag, "根")

    def test_deep_chain(self):
        tree = Tree()
        tree.create_node("n0", "n0")
        for index in range(1, 300):
            tree.create_node("n%d" % index, "n%d" % index, parent="n%d" % (index - 1))
        restored = parse_tree(tree.show(stdout=False))
        self.assertEqual(len(restored.nodes), 300)
        self.assertEqual(restored.depth(), 299)


if __name__ == "__main__":
    unittest.main()
