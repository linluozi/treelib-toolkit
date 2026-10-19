#!/usr/bin/env python
"""
What the fork adds — a guided tour.

Run it to see the query language, the structural diff, the validator and the
renderers working on one tree.

Author: treelib-toolkit contributors
"""

from treelib import Tree, parse_tree, render, to_html, to_markdown, to_mermaid
from treelib.diff import apply_patch, diff
from treelib.integrity import validate


def build_project():
    """A small project tree with directory/file payloads."""
    tree = Tree()
    tree.create_node("project", "root", data={"kind": "dir", "classes": "workspace"})
    tree.create_node("src", "src", parent="root", data={"kind": "dir", "classes": "dir"})
    tree.create_node("main.py", "main", parent="src", data={"kind": "file", "size": 120, "classes": "py entry"})
    tree.create_node("util.py", "util", parent="src", data={"kind": "file", "size": 40, "classes": "py"})
    tree.create_node("draft.py", "draft", parent="src", data={"kind": "file", "size": 0, "classes": "py draft"})
    tree.create_node("docs", "docs", parent="root", data={"kind": "dir", "classes": "dir"})
    tree.create_node("README.md", "readme", parent="docs", data={"kind": "file", "size": 8, "classes": "md"})
    tree.create_node("build", "build", parent="root", data={"kind": "dir"})
    tree.create_node("out.bin", "out", parent="build", data={"kind": "file", "size": 999})
    return tree


def section(title):
    print("\n" + title)
    print("-" * len(title))


def main():
    tree = build_project()

    section("1. Query: selectors instead of lambdas")
    for selector in (
        "*.py",
        "*.py:leaf",
        "[kind=dir]:has(*.py)",
        "#root > *",
        "*:not(.py):not([kind=file])",
        "[size^='1']",
    ):
        result = tree.query(selector)
        print("  %-34s -> %s" % (selector, result.ids))

    print("\n  attribute access: %s" % tree.query("*.py").attr("size"))

    section("2. Query result as a tree")
    print(tree.query("*.py").to_tree().show(stdout=False).rstrip())

    section("3. Structural diff")
    changed = Tree(tree, deep=True)
    changed.update_node("main", data={"kind": "file", "size": 200, "classes": "py entry"})
    changed.move_node("util", "docs")
    changed.remove_node("readme")
    changed.create_node("setup.py", "setup", parent="root", data={"kind": "file", "classes": "py"})

    changes = diff(tree, changed)
    print("  summary: %s" % changes.summary())
    for line in changes.describe().splitlines():
        print("  " + line)

    replayed = apply_patch(Tree(tree, deep=True), changes)
    print("\n  replay leaves %d change(s) vs target" % len(diff(replayed, changed)))

    section("4. Integrity validation")
    print("  healthy tree: %s" % validate(tree).describe())

    broken = Tree(tree, deep=True)
    broken["main"].successors(broken.identifier).append("ghost")
    print("  corrupted tree:")
    for line in validate(broken).describe().splitlines():
        print("    " + line)

    section("5. Renderers")
    print(to_markdown(tree.query("docs, build").to_tree()))
    print()
    print(to_mermaid(tree.query("*.py").to_tree()))
    print()
    html = to_html(tree, title="Project")
    print(
        "  HTML: %d bytes, %d nodes, no external assets: %s" % (len(html), html.count("<li class="), "http" not in html)
    )

    section("6. Text round-trip")
    text = tree.show(stdout=False)
    restored = parse_tree(text)
    print("  show() -> parse_tree() -> show() identical: %s" % (restored.show(stdout=False) == text))

    section("7. Dispatch by name")
    print("  render(tree, 'mermaid') == to_mermaid(tree): %s" % (render(tree, "mermaid") == to_mermaid(tree)))


if __name__ == "__main__":
    main()
