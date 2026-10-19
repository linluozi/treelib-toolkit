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
"""Tests for :mod:`treelib.diff` and :mod:`treelib.integrity`."""

import json
import unittest

from treelib import Node, Tree
from treelib.diff import Change, apply_patch, diff
from treelib.exceptions import DuplicatedNodeIdError, NodeIDAbsentError
from treelib.integrity import ERROR, validate


def build(spec):
    tree = Tree()
    for tag, nid, parent, data in spec:
        tree.create_node(tag, nid, parent=parent, data=data)
    return tree


BASE = [
    ("root", "r", None, {"v": 1}),
    ("a", "a", "r", {"v": 2}),
    ("b", "b", "r", {"v": 3}),
    ("a1", "a1", "a", {"v": 4}),
    ("a2", "a2", "a", {"v": 5}),
    ("b1", "b1", "b", {"v": 6}),
]


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.old = build(BASE)
        self.new = build(
            [
                ("root", "r", None, {"v": 1}),
                ("a", "a", "r", {"v": 99}),  # data change
                ("B renamed", "b", "r", {"v": 3}),  # tag change
                ("a1", "a1", "a", {"v": 4}),
                ("b1", "b1", "b", {"v": 6}),
                ("b2", "b2", "b", {"v": 7}),  # addition
            ]
        )
        self.new.move_node("a1", "b")  # move; a2 is gone (removal)

    def test_summary(self):
        result = diff(self.old, self.new)
        self.assertEqual(result.summary(), {"add": 1, "remove": 1, "move": 1, "update": 2})

    def test_kinds_and_identifiers(self):
        result = diff(self.old, self.new)
        self.assertEqual([change.identifier for change in result.removed], ["a2"])
        self.assertEqual([change.identifier for change in result.added], ["b2"])
        self.assertEqual([change.identifier for change in result.moved], ["a1"])
        self.assertEqual(sorted(change.identifier for change in result.updated), ["a", "b"])

    def test_move_records_both_parents(self):
        change = diff(self.old, self.new).moved[0]
        self.assertEqual(change.old_parent, "a")
        self.assertEqual(change.parent, "b")

    def test_update_records_old_and_new(self):
        changes = {change.identifier: change for change in diff(self.old, self.new).updated}
        self.assertEqual(changes["a"].old_data, {"v": 2})
        self.assertEqual(changes["a"].new_data, {"v": 99})
        self.assertEqual(changes["b"].old_tag, "b")
        self.assertEqual(changes["b"].new_tag, "B renamed")

    def test_identical_trees(self):
        result = diff(self.old, build(BASE))
        self.assertEqual(len(result), 0)
        self.assertFalse(result)
        self.assertEqual(result.describe(), "")

    def test_dict_key_order_is_not_a_change(self):
        old = build([("r", "r", None, {"a": 1, "b": 2})])
        new = build([("r", "r", None, {"b": 2, "a": 1})])
        self.assertEqual(len(diff(old, new)), 0)

    def test_nested_dict_key_order_is_not_a_change(self):
        old = build([("r", "r", None, {"x": {"p": 1, "q": 2}})])
        new = build([("r", "r", None, {"x": {"q": 2, "p": 1}})])
        self.assertEqual(len(diff(old, new)), 0)

    def test_list_order_is_a_change(self):
        old = build([("r", "r", None, {"x": [1, 2]})])
        new = build([("r", "r", None, {"x": [2, 1]})])
        self.assertEqual(len(diff(old, new)), 1)

    def test_ignore_data(self):
        result = diff(self.old, self.new, compare_data=False)
        self.assertEqual([change.identifier for change in result.updated], ["b"])

    def test_additions_are_parent_first(self):
        old = Tree()
        old.create_node("r", "r")
        new = Tree()
        new.create_node("r", "r")
        new.create_node("x", "x", parent="r")
        new.create_node("y", "y", parent="x")
        new.create_node("z", "z", parent="y")
        self.assertEqual([change.identifier for change in diff(old, new).added], ["x", "y", "z"])

    def test_removals_come_first(self):
        result = diff(self.old, self.new)
        kinds = [change.kind for change in result]
        self.assertEqual(kinds[0], "remove")
        self.assertLess(kinds.index("remove"), kinds.index("add"))

    def test_apply_patch_round_trip(self):
        result = diff(self.old, self.new)
        patched = apply_patch(Tree(self.old, deep=True), result)
        self.assertEqual(len(diff(patched, self.new)), 0)
        self.assertEqual(patched.show(stdout=False), self.new.show(stdout=False))

    def test_apply_patch_restores_data_of_added_nodes(self):
        result = diff(self.old, self.new)
        patched = apply_patch(Tree(self.old, deep=True), result)
        self.assertEqual(patched["b2"].data, {"v": 7})

    def test_apply_patch_restores_tag_of_added_nodes(self):
        old = Tree()
        old.create_node("r", "r")
        new = Tree()
        new.create_node("r", "r")
        new.create_node("Pretty Label", "n1", parent="r")
        patched = apply_patch(Tree(old, deep=True), diff(old, new))
        self.assertEqual(patched["n1"].tag, "Pretty Label")

    def test_apply_patch_accepts_a_list(self):
        changes = list(diff(self.old, self.new))
        patched = apply_patch(Tree(self.old, deep=True), changes)
        self.assertEqual(len(diff(patched, self.new)), 0)

    def test_apply_patch_rejects_duplicate_add(self):
        change = Change("add", "r", parent=None, new_tag="r")
        with self.assertRaises(DuplicatedNodeIdError):
            apply_patch(Tree(self.old, deep=True), [change])

    def test_apply_patch_rejects_missing_move_target(self):
        change = Change("move", "ghost", parent="r")
        with self.assertRaises(NodeIDAbsentError):
            apply_patch(Tree(self.old, deep=True), [change])

    def test_apply_patch_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            apply_patch(Tree(self.old, deep=True), [Change("frobnicate", "a")])

    def test_describe_lines(self):
        result = diff(self.old, self.new)
        text = result.describe()
        self.assertIn("- a2", text)
        self.assertIn("+ b2 (parent=b)", text)
        self.assertIn("~ a1 moved: a -> b", text)
        self.assertIn("* a: data", text)

    def test_to_dict_is_json_serialisable(self):
        payload = diff(self.old, self.new).to_dict()
        text = json.dumps(payload, ensure_ascii=False)
        restored = json.loads(text)
        self.assertEqual(restored["old_root"], "r")
        self.assertEqual(len(restored["changes"]), 5)
        add = [item for item in restored["changes"] if item["kind"] == "add"][0]
        self.assertEqual(add["id"], "b2")
        self.assertEqual(add["parent"], "b")
        self.assertEqual(add["tag"], "b2")
        self.assertEqual(add["data"], {"v": 7})

    def test_change_equality(self):
        self.assertEqual(Change("add", "x", parent="r"), Change("add", "x", parent="r"))
        self.assertNotEqual(Change("add", "x", parent="r"), Change("add", "x", parent="q"))


class IntegrityTests(unittest.TestCase):
    def test_healthy_tree(self):
        report = validate(build(BASE))
        self.assertTrue(report.ok)
        self.assertEqual(len(report), 0)
        self.assertEqual(report.describe(), "tree is valid")

    def test_empty_tree_is_valid(self):
        self.assertTrue(validate(Tree()).ok)

    def test_root_with_parent(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree.create_node("a", "a", parent="r")
        tree["r"].set_predecessor("a", tree.identifier)
        report = validate(tree)
        self.assertIn("root_has_parent", report.codes())
        self.assertFalse(report.ok)

    def test_dangling_child(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree["r"].successors(tree.identifier).append("ghost")
        self.assertIn("dangling_child", validate(tree).codes())

    def test_orphan(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree._nodes["lonely"] = Node("lonely", "lonely")
        codes = validate(tree).codes()
        self.assertIn("orphan", codes)
        self.assertIn("unreachable", codes)

    def test_backlink_mismatch(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree.create_node("a", "a", parent="r")
        tree["a"].set_predecessor(None, tree.identifier)
        self.assertIn("backlink_mismatch", validate(tree).codes())

    def test_duplicate_child(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree.create_node("a", "a", parent="r")
        tree["r"].successors(tree.identifier).append("a")
        self.assertIn("duplicate_child", validate(tree).codes())

    def test_cycle(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree.create_node("a", "a", parent="r")
        tree.create_node("b", "b", parent="a")
        # Close the loop: b becomes a child of itself, so the child pointers
        # alone contain a cycle reachable from the root.
        tree["b"].successors(tree.identifier).append("b")
        report = validate(tree)
        self.assertIn("cycle", report.codes())
        self.assertFalse(report.ok)

    def test_self_loop_is_a_cycle(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree.create_node("a", "a", parent="r")
        tree["a"].successors(tree.identifier).append("a")
        report = validate(tree)
        self.assertIn("cycle", report.codes())
        self.assertIn("backlink_mismatch", report.codes())

    def test_root_missing(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree.root = None
        self.assertIn("root_missing", validate(tree).codes())

    def test_root_absent(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree.root = "ghost"
        self.assertIn("root_absent", validate(tree).codes())

    def test_report_json(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree["r"].successors(tree.identifier).append("ghost")
        payload = validate(tree).to_dict()
        self.assertFalse(payload["ok"])
        self.assertGreaterEqual(payload["errors"], 1)
        self.assertEqual(payload["problems"][0]["code"], "dangling_child")
        json.dumps(payload)

    def test_errors_and_warnings_split(self):
        tree = Tree()
        tree.create_node("r", "r")
        tree["r"].successors(tree.identifier).append("ghost")
        report = validate(tree)
        self.assertTrue(all(problem.severity == ERROR for problem in report.errors))
        self.assertEqual(report.warnings, [])

    def test_diff_does_not_break_validation(self):
        tree = build(BASE)
        result = diff(tree, build(BASE))
        apply_patch(tree, result)
        self.assertTrue(validate(tree).ok)


if __name__ == "__main__":
    unittest.main()
