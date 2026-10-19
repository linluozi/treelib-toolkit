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
"""Structural validation for :class:`treelib.Tree`.

A tree can be corrupted without any exception being raised: a bad ``move_node``
target, a hand-edited ``_nodes`` dict, a node shared between two trees through a
shallow ``paste``, or a cycle introduced by direct pointer manipulation. The
symptom is usually a hang or a nonsensical ``show()`` output far from the cause.

:func:`validate` walks the structure once and reports every inconsistency it
finds as a :class:`Problem`, instead of failing on the first one.
"""

from .exceptions import NodeIDAbsentError

__all__ = ["Problem", "ValidationReport", "validate", "is_valid"]

#: Problem severities. ``error`` means the tree cannot be traversed reliably,
#: ``warning`` means the structure is traversable but suspicious.
ERROR = "error"
WARNING = "warning"


class Problem(object):
    """A single structural problem."""

    __slots__ = ("code", "severity", "identifier", "detail")

    def __init__(self, code, severity, identifier, detail):
        self.code = code
        self.severity = severity
        self.identifier = identifier
        self.detail = detail

    def __repr__(self):
        return "Problem(%s %s %r: %s)" % (self.severity, self.code, self.identifier, self.detail)

    def __eq__(self, other):
        if not isinstance(other, Problem):
            return NotImplemented
        return (self.code, self.severity, self.identifier) == (other.code, other.severity, other.identifier)

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __hash__(self):
        return hash((self.code, self.severity, self.identifier))

    def to_dict(self):
        return {
            "code": self.code,
            "severity": self.severity,
            "id": self.identifier,
            "detail": self.detail,
        }


class ValidationReport(object):
    """Collection of problems found by :func:`validate`."""

    __slots__ = ("problems",)

    def __init__(self, problems):
        self.problems = list(problems)

    def __iter__(self):
        return iter(self.problems)

    def __len__(self):
        return len(self.problems)

    def __bool__(self):
        return not self.problems

    __nonzero__ = __bool__

    def __repr__(self):
        if not self.problems:
            return "<ValidationReport ok>"
        return "<ValidationReport %d problem(s)>" % len(self.problems)

    @property
    def ok(self):
        """True when no ``error``-severity problem was found."""
        return not any(problem.severity == ERROR for problem in self.problems)

    @property
    def errors(self):
        return [problem for problem in self.problems if problem.severity == ERROR]

    @property
    def warnings(self):
        return [problem for problem in self.problems if problem.severity == WARNING]

    def codes(self):
        """Sorted set of problem codes, for quick assertions in tests."""
        return sorted({problem.code for problem in self.problems})

    def describe(self):
        if not self.problems:
            return "tree is valid"
        lines = []
        for problem in self.problems:
            lines.append("%-7s %-22s %-12s %s" % (problem.severity, problem.code, problem.identifier, problem.detail))
        return "\n".join(lines)

    def to_dict(self):
        return {
            "ok": self.ok,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "problems": [problem.to_dict() for problem in self.problems],
        }


def validate(tree):
    """Check the structural invariants of ``tree``.

    Invariants checked:

    * exactly one root, and it is present in ``nodes``;
    * every non-root node has a parent that exists;
    * every child pointer refers to an existing node whose parent points back;
    * every node is reachable from the root (no orphans);
    * the parent/child graph is acyclic;
    * no node appears twice in one parent's child list.

    Returns:
        ValidationReport: all problems found, in a stable order.
    """
    problems = []
    nodes = tree.nodes
    tree_id = tree.identifier

    # -- root ------------------------------------------------------------
    if tree.root is None:
        if nodes:
            problems.append(Problem("root_missing", ERROR, None, "tree has %d node(s) but no root" % len(nodes)))
        return ValidationReport(problems)

    if tree.root not in nodes:
        problems.append(Problem("root_absent", ERROR, tree.root, "root identifier is not in nodes"))
        return ValidationReport(problems)

    # -- parent pointers -------------------------------------------------
    parent_map = {}
    for nid, node in nodes.items():
        try:
            parent = node.predecessor(tree_id)
        except Exception:  # pragma: no cover - defensive against broken dicts
            parent = None
        parent_map[nid] = parent

        if nid == tree.root:
            if parent is not None:
                problems.append(Problem("root_has_parent", ERROR, nid, "root points at parent %r" % (parent,)))
            continue

        if parent is None:
            problems.append(Problem("orphan", ERROR, nid, "non-root node has no parent"))
        elif parent not in nodes:
            problems.append(Problem("dangling_parent", ERROR, nid, "parent %r does not exist" % (parent,)))

    # -- child pointers --------------------------------------------------
    for nid, node in nodes.items():
        try:
            children = list(node.successors(tree_id))
        except Exception:  # pragma: no cover - defensive
            children = []
        seen = set()
        for child in children:
            if child in seen:
                problems.append(Problem("duplicate_child", ERROR, nid, "child %r listed twice" % (child,)))
                continue
            seen.add(child)
            if child not in nodes:
                problems.append(Problem("dangling_child", ERROR, nid, "child %r does not exist" % (child,)))
                continue
            if parent_map.get(child) != nid:
                problems.append(
                    Problem(
                        "backlink_mismatch",
                        ERROR,
                        child,
                        "listed as child of %r but its parent is %r" % (nid, parent_map.get(child)),
                    )
                )

    # -- reachability + cycles -------------------------------------------
    reachable = set()
    on_path = set()
    stack = [(tree.root, iter(_children(nodes, tree.root, tree_id)))]
    reachable.add(tree.root)
    on_path.add(tree.root)
    while stack:
        nid, children = stack[-1]
        advanced = False
        for child in children:
            if child not in nodes:
                continue
            if child in on_path:
                problems.append(Problem("cycle", ERROR, child, "cycle detected below %r" % (nid,)))
                continue
            if child in reachable:
                continue
            reachable.add(child)
            on_path.add(child)
            stack.append((child, iter(_children(nodes, child, tree_id))))
            advanced = True
            break
        if not advanced:
            stack.pop()
            on_path.discard(nid)

    for nid in nodes:
        if nid not in reachable:
            problems.append(Problem("unreachable", ERROR, nid, "node is not reachable from the root"))

    # Stable ordering: severity first, then code, then identifier.
    problems.sort(key=lambda p: (p.severity != ERROR, p.code, str(p.identifier)))
    return ValidationReport(problems)


def _children(nodes, nid, tree_id):
    try:
        return list(nodes[nid].successors(tree_id))
    except KeyError:  # pragma: no cover - defensive
        return []


def is_valid(tree):
    """Convenience wrapper returning ``True`` when :func:`validate` is clean."""
    return validate(tree).ok
