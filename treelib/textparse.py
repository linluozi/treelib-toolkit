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
"""Read back the indented layout produced by ``Tree.show()``.

``Tree.show()`` and ``Tree.save2file()`` write a human-readable hierarchy::

    Root
    ├── Child A
    │   └── Grandchild
    └── Child B

Before this module there was no way back: the layout was output only, so a tree
saved for review could not be reopened. :func:`parse_tree` reconstructs the
structure by measuring the indentation prefix of each line, accepting every
``line_type`` shipped with treelib (``ascii``, ``ascii-ex``, ``ascii-exr``,
``ascii-em``, ``ascii-emv``, ``ascii-emh``) plus tab indentation and Markdown
bullet lists.

Node identifiers are generated with :func:`slugify` from the label, made unique
by appending ``-2``, ``-3``… when needed. When the source carries identifiers
(``Tree.show(idhidden=False)`` prints ``tag[id]``), those are used instead.
"""

import re

__all__ = ["parse_tree", "slugify", "ParseError"]

#: Prefix characters that may appear in a rendered connector line. Note that
#: spaces are part of a prefix (``│   ``), so the splitter consumes them
#: greedily only while they are followed by more prefix characters.
#: Includes the rounded corners used by ``ascii-exr`` (``╰ ╮ ╭ ╯``), the double
#: lines used by ``ascii-em*`` (``═ ═``), and the Markdown bullet marker ``*``.
_BOX_CHARS = "│├└─║╠╚╟╙╞╘╰╮╭╯╼╾═┄┈|+`-*"
_INDENT_CHARS = _BOX_CHARS + " \t"
_ID_SUFFIX = re.compile(r"^(?P<tag>.*?)\[(?P<id>[^\[\]]+)\]\s*$")


class ParseError(ValueError):
    """Raised when a text layout cannot be interpreted."""


def slugify(text):
    """Turn a label into a stable, readable identifier.

    ``"Child A"`` -> ``"child-a"``; non-ASCII text is kept (``"子"`` -> ``"子"``),
    since treelib identifiers are plain strings.
    """
    slug = str(text).strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^\w\-\u00a0-\uffff]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "node"


def _split_indent(line):
    """Split a rendered line into (prefix, label).

    The prefix is the run of connector characters and padding spaces before the
    label. Trailing spaces belong to the prefix only if the label that follows
    is preceded by a connector glyph, so a label that legitimately starts with a
    space is not truncated.
    """
    index = 0
    length = len(line)
    while index < length and line[index] in _INDENT_CHARS:
        index += 1
    prefix = line[:index]
    label = line[index:].rstrip("\r\n")
    if not label:
        return prefix, ""
    return prefix, label


def _depth_of(prefix):
    """Derive nesting depth from a connector prefix.

    Tree renderers consume exactly four characters per level (``│   `` or four
    spaces), so ``len(prefix) // 4`` is the depth for every shipped
    ``line_type``. Tabs count as four spaces.

    Markdown bullet lists are the exception: the bullet marker itself occupies
    two characters (``- `` at depth 0, ``  - `` at depth 1), so the marker is
    subtracted before dividing by the two-character stride.
    """
    width = 0
    for char in prefix:
        width += 4 if char == "\t" else 1
    if prefix.rstrip().endswith("-"):
        return max(0, (width - 2) // 2)
    return width // 4


def _label_of(line):
    return _split_indent(line)[1]


def parse_tree(text, identifier=None):
    """Parse an indented tree layout into a :class:`treelib.Tree`.

    Args:
        text: the layout, as produced by ``Tree.show()`` / ``save2file()``.
        identifier: optional identifier for the resulting tree.

    Returns:
        Tree: a new tree. Empty lines are ignored; if the text contains no
        non-empty line an empty tree is returned.

    Raises:
        ParseError: if the first non-empty line is indented (a tree must start
            at the root) or if an indentation jump skips a level.
    """
    from .tree import Tree

    tree = Tree(identifier=identifier)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return tree

    # Each stack entry is (depth, identifier). Depth comes from the prefix
    # length, so every line_type and Markdown bullets parse identically.
    levels = []  # list of (depth, nid)
    used = set()
    first_prefix, first_label = _split_indent(lines[0])
    if first_label and _depth_of(first_prefix):
        raise ParseError("first line is indented by %d level(s); expected the root" % _depth_of(first_prefix))

    for position, line in enumerate(lines):
        prefix, label = _split_indent(line)
        if not label:
            continue
        depth = _depth_of(prefix)

        while levels and depth <= levels[-1][0]:
            levels.pop()

        if not levels and position:
            raise ParseError("line %d (%r) is a second root" % (position + 1, label))

        parent = levels[-1][1] if levels else None

        match = _ID_SUFFIX.match(label)
        if match:
            tag = match.group("tag").strip()
            nid = match.group("id").strip()
        else:
            tag = label
            base = slugify(label)
            nid = base
            suffix = 2
            while nid in used:
                nid = "%s-%d" % (base, suffix)
                suffix += 1

        if nid in used:
            base = nid
            suffix = 2
            while nid in used:
                nid = "%s-%d" % (base, suffix)
                suffix += 1

        used.add(nid)
        tree.create_node(tag=tag, identifier=nid, parent=parent)
        levels.append((depth, nid))

    return tree
