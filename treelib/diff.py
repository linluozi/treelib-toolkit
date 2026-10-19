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
"""Structural diff between two trees, plus replayable patches.

Motivation
----------
``treelib`` can serialise a tree but offers no way to describe *what changed*
between two versions of one. Comparing ``to_json()`` strings tells you that
something differs, not that "node ``x`` moved under ``y``" — and JSON key order,
insertion order and generated identifiers all produce false positives.

:func:`diff` matches nodes by identifier and reports the minimal set of
structural operations needed to turn one tree into the other:

============  =========================================================
``add``       identifier exists only in the new tree
``remove``    identifier exists only in the old tree
``move``      identifier exists in both but has a different parent
``update``    identifier exists in both but the tag or data changed
============  =========================================================

:func:`apply_patch` replays a diff onto the old tree, so a diff doubles as a
compact, human-readable transport format.
"""

from .exceptions import DuplicatedNodeIdError, NodeIDAbsentError

__all__ = ["Change", "TreeDiff", "diff", "apply_patch"]


def _freeze(value):
    """Make ``value`` comparable across runs.

    Dicts are unordered by definition, so ``{"a": 1, "b": 2}`` and
    ``{"b": 2, "a": 1}`` must compare equal. Objects without ``__eq__`` fall back
    to their ``repr`` so that a change in payload is at least detected.
    """
    if isinstance(value, dict):
        return ("dict", tuple(sorted((str(key), _freeze(item)) for key, item in value.items())))
    if isinstance(value, (list, tuple)):
        return ("seq", tuple(_freeze(item) for item in value))
    if isinstance(value, (set, frozenset)):
        return ("set", tuple(sorted(repr(_freeze(item)) for item in value)))
    try:
        hash(value)
    except TypeError:
        return ("obj", repr(value))
    return ("val", value)


class Change(object):
    """One structural change between two trees."""

    __slots__ = ("kind", "identifier", "parent", "old_parent", "old_tag", "new_tag", "old_data", "new_data")

    def __init__(
        self,
        kind,
        identifier,
        parent=None,
        old_parent=None,
        old_tag=None,
        new_tag=None,
        old_data=None,
        new_data=None,
    ):
        self.kind = kind
        self.identifier = identifier
        self.parent = parent
        self.old_parent = old_parent
        self.old_tag = old_tag
        self.new_tag = new_tag
        self.old_data = old_data
        self.new_data = new_data

    def __repr__(self):
        if self.kind == "add":
            return "Change(add %r under %r)" % (self.identifier, self.parent)
        if self.kind == "remove":
            return "Change(remove %r)" % (self.identifier,)
        if self.kind == "move":
            return "Change(move %r: %r -> %r)" % (self.identifier, self.old_parent, self.parent)
        return "Change(update %r)" % (self.identifier,)

    def __eq__(self, other):
        if not isinstance(other, Change):
            return NotImplemented
        return (
            all(
                getattr(self, name) == getattr(other, name)
                for name in ("kind", "identifier", "parent", "old_parent", "old_tag", "new_tag")
            )
            and _freeze(self.old_data) == _freeze(other.old_data)
            and _freeze(self.new_data) == _freeze(other.new_data)
        )

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __hash__(self):
        return hash((self.kind, self.identifier))

    def describe(self):
        """One-line human-readable rendering, used by the CLI and reports."""
        if self.kind == "add":
            return "+ %s (parent=%s)" % (self.identifier, self.parent)
        if self.kind == "remove":
            return "- %s" % (self.identifier,)
        if self.kind == "move":
            return "~ %s moved: %s -> %s" % (self.identifier, self.old_parent, self.parent)
        fields = []
        if self.old_tag != self.new_tag:
            fields.append("tag %r -> %r" % (self.old_tag, self.new_tag))
        if _freeze(self.old_data) != _freeze(self.new_data):
            fields.append("data %r -> %r" % (self.old_data, self.new_data))
        return "* %s: %s" % (self.identifier, ", ".join(fields))

    def to_dict(self):
        """JSON-friendly representation."""
        payload = {"kind": self.kind, "id": self.identifier}
        if self.kind in ("add", "move"):
            payload["parent"] = self.parent
        if self.kind == "add":
            payload["tag"] = self.new_tag
            payload["data"] = self.new_data
        if self.kind == "move":
            payload["old_parent"] = self.old_parent
        if self.kind == "update":
            if self.old_tag != self.new_tag:
                payload["tag"] = [self.old_tag, self.new_tag]
            if _freeze(self.old_data) != _freeze(self.new_data):
                payload["data"] = [self.old_data, self.new_data]
        return payload


class TreeDiff(object):
    """The result of :func:`diff`: ordered changes plus convenience helpers."""

    __slots__ = ("changes", "old_root", "new_root")

    def __init__(self, changes, old_root, new_root):
        self.changes = list(changes)
        self.old_root = old_root
        self.new_root = new_root

    def __iter__(self):
        return iter(self.changes)

    def __len__(self):
        return len(self.changes)

    def __bool__(self):
        return bool(self.changes)

    __nonzero__ = __bool__

    def __repr__(self):
        return "<TreeDiff %d change(s)>" % len(self.changes)

    def by_kind(self, kind):
        """Changes of one kind (``add`` / ``remove`` / ``move`` / ``update``)."""
        return [change for change in self.changes if change.kind == kind]

    @property
    def added(self):
        return self.by_kind("add")

    @property
    def removed(self):
        return self.by_kind("remove")

    @property
    def moved(self):
        return self.by_kind("move")

    @property
    def updated(self):
        return self.by_kind("update")

    def summary(self):
        """Counts per kind, e.g. ``{'add': 2, 'remove': 0, ...}``."""
        return {kind: len(self.by_kind(kind)) for kind in ("add", "remove", "move", "update")}

    def describe(self):
        """Multi-line report; empty string when the trees are equivalent."""
        return "\n".join(change.describe() for change in self.changes)

    def to_dict(self):
        return {
            "old_root": self.old_root,
            "new_root": self.new_root,
            "changes": [change.to_dict() for change in self.changes],
        }


def _parent_of(tree, nid):
    return tree[nid].predecessor(tree.identifier)


def diff(old, new, compare_data=True):
    """Compute the structural changes that turn ``old`` into ``new``.

    Args:
        old: the baseline :class:`treelib.Tree`.
        new: the target :class:`treelib.Tree`.
        compare_data: when False, only tags and topology are compared (useful
            when ``data`` holds volatile fields such as timestamps).

    Returns:
        TreeDiff: ordered ``add`` / ``remove`` / ``move`` / ``update`` changes.
        Removals come first, then additions, then moves and updates, so that
        :func:`apply_patch` can replay the list in order without ever creating a
        duplicate identifier.
    """
    old_ids = set(old.nodes)
    new_ids = set(new.nodes)

    removed = []
    for nid in old_ids - new_ids:
        removed.append(Change("remove", nid))

    added = []
    for nid in new_ids - old_ids:
        new_node = new[nid]
        added.append(Change("add", nid, parent=_parent_of(new, nid), new_tag=new_node.tag, new_data=new_node.data))

    moved = []
    updated = []
    for nid in old_ids & new_ids:
        old_parent = _parent_of(old, nid)
        new_parent = _parent_of(new, nid)
        if old_parent != new_parent:
            moved.append(Change("move", nid, parent=new_parent, old_parent=old_parent))

        old_node = old[nid]
        new_node = new[nid]
        old_tag, new_tag = old_node.tag, new_node.tag
        old_data, new_data = old_node.data, new_node.data
        if old_tag != new_tag or (compare_data and _freeze(old_data) != _freeze(new_data)):
            updated.append(
                Change(
                    "update",
                    nid,
                    parent=new_parent,
                    old_parent=old_parent,
                    old_tag=old_tag,
                    new_tag=new_tag,
                    old_data=old_data,
                    new_data=new_data,
                )
            )

    # Deterministic order: removals first, then additions ordered so that a
    # parent is always created before its children.
    def depth_in_new(nid):
        return new.level(nid)

    added.sort(key=lambda change: (depth_in_new(change.identifier), change.identifier))

    return TreeDiff(removed + added + moved + updated, old.root, new.root)


def apply_patch(tree, changes):
    """Replay ``changes`` (a :class:`TreeDiff` or a list of :class:`Change`).

    The patch is applied in place and the tree is returned for chaining.

    Raises:
        NodeIDAbsentError: If a change refers to a node that is not present when
            its turn comes (a patch produced against a different baseline).
        DuplicatedNodeIdError: If an ``add`` targets an identifier already used.
    """
    items = changes.changes if isinstance(changes, TreeDiff) else list(changes)

    for change in items:
        if change.kind == "remove":
            if change.identifier in tree.nodes:
                tree.remove_node(change.identifier)
        elif change.kind == "add":
            if change.identifier in tree.nodes:
                raise DuplicatedNodeIdError("node '%s' already exists" % change.identifier)
            tree.create_node(
                tag=change.new_tag if change.new_tag is not None else change.identifier,
                identifier=change.identifier,
                parent=change.parent,
                data=change.new_data,
            )
        elif change.kind == "move":
            if change.identifier not in tree.nodes:
                raise NodeIDAbsentError("node '%s' is not in the tree" % change.identifier)
            if change.parent is not None and change.parent not in tree.nodes:
                raise NodeIDAbsentError("parent '%s' is not in the tree" % change.parent)
            tree.move_node(change.identifier, change.parent)
        elif change.kind == "update":
            if change.identifier not in tree.nodes:
                raise NodeIDAbsentError("node '%s' is not in the tree" % change.identifier)
            tree.update_node(change.identifier, tag=change.new_tag, data=change.new_data)
        else:
            raise ValueError("unknown change kind %r" % change.kind)

    return tree
