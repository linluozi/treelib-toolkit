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
"""CSS-inspired selector engine for :class:`treelib.Tree`.

``treelib`` ships traversal primitives (``expand_tree`` with a filter callback)
but no way to *describe* which nodes you want. Every non-trivial lookup ends up
as a nested lambda over ``all_nodes()``, and lambdas cannot be stored in config
files, passed on a command line, or reviewed in a diff.

This module adds a small declarative language::

    tree.query("Folder > *.py:leaf")
    tree.query("#root [kind=file]")
    tree.query("Section:has(Error)")
    tree.query("Note:not(.draft)")

Grammar
-------
::

    selector-list := selector ("," selector)*
    selector      := compound (combinator compound)*
    combinator    := ">" | "+" | "~" | <whitespace>
    compound      := simple+
    simple        := "*" | tag | "#" ident | "." class
                   | "[" attr (op value)? "]"
                   | ":" pseudo ( "(" argument ")" )?

Combinators
-----------
``A B``   descendant of A
``A > B`` direct child of A
``A + B`` immediately following sibling of A
``A ~ B`` any following sibling of A

Attribute operators: ``=``, ``!=``, ``^=``, ``$=``, ``*=``, ``~=``, ``|=``,
plus presence (``[attr]``). ``~=`` matches whitespace-separated words and
``|=`` matches a value or a value prefix followed by ``-`` (BCP-47 style).

Pseudo-classes: ``:root``, ``:leaf``, ``:branch``, ``:expanded``, ``:collapsed``,
``:first-child``, ``:last-child``, ``:only-child``, ``:nth-child(an+b)``,
``:has(selector)``, ``:not(selector)``, ``:contains(text)``.

Values may be quoted with ``"`` or ``'`` to allow spaces and punctuation.
"""

import re

from .exceptions import NodeIDAbsentError

__all__ = ["QueryError", "QueryResult", "Selector", "parse", "query"]

_IDENT_RE = re.compile(r"[A-Za-z0-9_\-\u00a0-\uffff][A-Za-z0-9_\-\u00a0-\uffff]*")
#: Tag names are free text in treelib, so dots are part of a tag run
#: (``main.py``). Class / id / pseudo names stay strict, which is what makes
#: ``*.py.draft`` mean "tag *, class py, class draft".
_TAG_RE = re.compile(r"[A-Za-z0-9_\-.\\\u00a0-\uffff]+")
_ATTR_RE = re.compile(r"\[\s*([^\s\]=!^$*~|]+)\s*(?:([!^$*~|]?=)\s*(.*?))?\s*\]", re.DOTALL)
_NTH_RE = re.compile(r"^\s*(odd|even|[-+]?\d*)\s*(?:n\s*([-+]\s*\d+)?)?\s*$")

_PSEUDO_NO_ARG = {
    "root",
    "leaf",
    "branch",
    "expanded",
    "collapsed",
    "first-child",
    "last-child",
    "only-child",
}
_PSEUDO_ARG = {"nth-child", "has", "not", "contains"}


class QueryError(ValueError):
    """Raised when a selector string cannot be parsed."""


def _unquote(token):
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        body = token[1:-1]
        # Only unescape the quote character and backslash; keep everything else
        # literal so that paths like "C:\dir" survive.
        return body.replace("\\" + token[0], token[0]).replace("\\\\", "\\")
    return token


class _Compound(object):
    """One compound selector: ``tag.class[attr=value]:pseudo``."""

    __slots__ = ("tag", "ids", "classes", "attrs", "pseudos")

    def __init__(self):
        self.tag = None
        self.ids = []
        self.classes = []
        self.attrs = []  # list of (name, op, value)
        self.pseudos = []  # list of (name, argument)

    def is_empty(self):
        return not (self.tag or self.ids or self.classes or self.attrs or self.pseudos)

    def __repr__(self):  # pragma: no cover - debugging aid
        parts = [self.tag or ""]
        parts.extend("#" + i for i in self.ids)
        parts.extend("." + c for c in self.classes)
        parts.extend("[%s%s%s]" % (n, op or "", v if v is not None else "") for n, op, v in self.attrs)
        parts.extend(":" + n + ("(" + a + ")" if a else "") for n, a in self.pseudos)
        return "".join(parts)


class Selector(object):
    """A parsed selector: a chain of compounds joined by combinators."""

    __slots__ = ("compounds", "combinators", "source")

    def __init__(self, compounds, combinators, source):
        self.compounds = compounds
        self.combinators = combinators
        self.source = source

    def __repr__(self):  # pragma: no cover - debugging aid
        return "Selector(%r)" % self.source


def _split_selector_list(text):
    """Split on top-level commas, respecting brackets, parens and quotes."""
    parts, depth, quote, current = [], 0, None, []
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            current.append(char)
        elif char in "([":
            depth += 1
            current.append(char)
        elif char in ")]":
            depth -= 1
            if depth < 0:
                raise QueryError("unbalanced %r in selector %r" % (char, text))
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if quote:
        raise QueryError("unterminated quote in selector %r" % text)
    if depth:
        raise QueryError("unbalanced brackets in selector %r" % text)
    parts.append("".join(current))
    result = [p.strip() for p in parts]
    if any(not p for p in result):
        raise QueryError("empty selector in list %r" % text)
    return result


def _tokenize(selector):
    """Split a single selector into compounds plus the combinators between them.

    ``"a > b"`` becomes ``([a, b], [">"])``. Each combinator is attached to the
    compound that *follows* it, which is the orientation the matcher needs when
    walking right to left.
    """
    entries = []  # list of (preceding_combinator, source)
    current = []
    depth = 0
    quote = None
    pending = None
    index, length = 0, len(selector)

    def close_compound():
        nonlocal pending
        source = "".join(current).strip()
        del current[:]
        if source:
            entries.append((pending, source))
            pending = None
            return True
        return False

    while index < length:
        char = selector[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'":
            quote = char
            current.append(char)
            index += 1
            continue
        if char in "([":
            depth += 1
            current.append(char)
            index += 1
            continue
        if char in ")]":
            depth -= 1
            current.append(char)
            index += 1
            continue
        if depth == 0 and char in ">+~":
            if current:
                close_compound()
            elif pending is not None:
                raise QueryError("double combinator in selector %r" % selector)
            pending = char
            index += 1
            continue
        if depth == 0 and char in " \t\n\r":
            lookahead = index
            while lookahead < length and selector[lookahead] in " \t\n\r":
                lookahead += 1
            if lookahead < length and selector[lookahead] in ">+~":
                # Whitespace hugging an explicit combinator is decorative.
                if current:
                    close_compound()
                index = lookahead
                continue
            if current:
                close_compound()
                pending = " "
            index = lookahead
            continue
        current.append(char)
        index += 1

    if quote:
        raise QueryError("unterminated quote in selector %r" % selector)
    if depth:
        raise QueryError("unbalanced brackets in selector %r" % selector)
    close_compound()
    if pending is not None:
        raise QueryError("selector %r ends with a dangling combinator" % selector)
    if not entries:
        raise QueryError("empty selector %r" % selector)

    compounds = [_parse_compound(source) for _, source in entries]
    combinators = [combinator for combinator, _ in entries[1:]]
    return compounds, combinators


def _parse_compound(source):
    compound = _Compound()
    index, length = 0, len(source)
    if not length:
        raise QueryError("empty compound selector")
    if source[0] in ">+~":
        raise QueryError("selector may not start with a combinator: %r" % source)
    while index < length:
        char = source[index]
        if char == "*":
            if compound.tag is not None:
                raise QueryError("duplicate universal selector in %r" % source)
            compound.tag = "*"
            index += 1
        elif char == "#":
            match = _IDENT_RE.match(source, index + 1)
            if not match:
                raise QueryError("expected identifier after '#' in %r" % source)
            compound.ids.append(match.group(0))
            index = match.end()
        elif char == ".":
            match = _IDENT_RE.match(source, index + 1)
            if not match:
                raise QueryError("expected identifier after '.' in %r" % source)
            compound.classes.append(match.group(0))
            index = match.end()
        elif char == "[":
            match = _ATTR_RE.match(source, index)
            if not match:
                raise QueryError("malformed attribute selector in %r" % source)
            name, op, value = match.group(1), match.group(2), match.group(3)
            if op is not None:
                value = _unquote(value)
                if value == "":
                    raise QueryError("empty value for [%s%s] in %r (quote it if literal)" % (name, op, source))
            compound.attrs.append((name, op, value))
            index = match.end()
        elif char == ":":
            match = _IDENT_RE.match(source, index + 1)
            if not match:
                raise QueryError("expected pseudo-class name after ':' in %r" % source)
            name = match.group(0).lower()
            index = match.end()
            argument = None
            if index < length and source[index] == "(":
                depth, cursor, quote = 1, index + 1, None
                while cursor < length and depth:
                    current = source[cursor]
                    if quote:
                        if current == quote:
                            quote = None
                    elif current in "\"'":
                        quote = current
                    elif current == "(":
                        depth += 1
                    elif current == ")":
                        depth -= 1
                    cursor += 1
                if depth:
                    raise QueryError("unbalanced '(' after :%s in %r" % (name, source))
                argument = source[index + 1 : cursor - 1].strip()
                index = cursor
            if name in _PSEUDO_ARG:
                if argument is None or argument == "":
                    raise QueryError(":%s requires an argument in %r" % (name, source))
                if name == "nth-child":
                    _parse_nth(argument)
                elif name == "contains":
                    argument = _unquote(argument)
            elif name in _PSEUDO_NO_ARG:
                if argument is not None:
                    raise QueryError(":%s takes no argument in %r" % (name, source))
            else:
                raise QueryError(
                    "unknown pseudo-class :%s (known: %s)" % (name, ", ".join(sorted(_PSEUDO_NO_ARG | _PSEUDO_ARG)))
                )
            compound.pseudos.append((name, argument))
        elif compound.is_empty() and char not in "#.[:":
            # Tag text may contain dots: ``main.py`` is a legal treelib tag and
            # file-tree users expect ``tree.query("main.py")`` to work. A dot
            # therefore belongs to the tag *only* while reading the tag, i.e.
            # the tag run is consumed greedily here. ``*.py`` still works
            # because ``*`` closes the tag run immediately, and a leading
            # ``.py`` never enters this branch at all.
            match = _TAG_RE.match(source, index)
            if not match:
                raise QueryError("unexpected character %r in %r" % (char, source))
            compound.tag = match.group(0)
            index = match.end()
        else:
            raise QueryError("unexpected character %r in %r" % (char, source))
    if compound.is_empty():
        raise QueryError("empty compound selector in %r" % source)
    return compound


def _parse_nth(argument):
    """Translate ``an+b`` into (a, b)."""
    text = argument.replace(" ", "")
    if text == "odd":
        return 2, 1
    if text == "even":
        return 2, 0
    match = re.match(r"^([-+]?\d*)n([-+]\d+)?$", text)
    if match:
        raw_a = match.group(1)
        if raw_a in ("", "+"):
            a = 1
        elif raw_a == "-":
            a = -1
        else:
            a = int(raw_a)
        b = int(match.group(2)) if match.group(2) else 0
        return a, b
    try:
        return 0, int(text)
    except ValueError:
        raise QueryError("invalid :nth-child argument %r" % argument)


def parse(text):
    """Parse a selector string into a list of :class:`Selector` objects."""
    if not isinstance(text, str):
        raise QueryError("selector must be a string, got %s" % type(text).__name__)
    selectors = []
    for part in _split_selector_list(text):
        compounds, combinators = _tokenize(part)
        selectors.append(Selector(compounds, combinators, part))
    return selectors


class QueryResult(object):
    """An ordered collection of matched nodes with chainable helpers.

    Iterating yields ``Node`` objects. ``ids`` exposes the identifiers, and the
    aggregate helpers delegate to :class:`treelib.Tree` so that a query result
    can be inspected, rendered or exported without a second pass.
    """

    __slots__ = ("tree", "_ids")

    def __init__(self, tree, ids):
        self.tree = tree
        seen = set()
        ordered = []
        for nid in ids:
            if nid not in seen:
                seen.add(nid)
                ordered.append(nid)
        self._ids = ordered

    # -- container protocol ------------------------------------------------
    def __iter__(self):
        for nid in self._ids:
            yield self.tree[nid]

    def __len__(self):
        return len(self._ids)

    def __bool__(self):
        return bool(self._ids)

    __nonzero__ = __bool__

    def __getitem__(self, index):
        if isinstance(index, slice):
            return QueryResult(self.tree, self._ids[index])
        return self.tree[self._ids[index]]

    def __contains__(self, item):
        nid = item.identifier if hasattr(item, "identifier") else item
        return nid in self._ids

    def __repr__(self):
        return "<QueryResult %d node(s): %s>" % (
            len(self._ids),
            ", ".join(self._ids[:6]) + ("..." if len(self._ids) > 6 else ""),
        )

    def __eq__(self, other):
        if isinstance(other, QueryResult):
            return self._ids == other._ids
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    # -- accessors ---------------------------------------------------------
    @property
    def ids(self):
        """Matched identifiers, in document (pre-order) order."""
        return list(self._ids)

    @property
    def nodes(self):
        """Matched ``Node`` objects."""
        return [self.tree[nid] for nid in self._ids]

    @property
    def tags(self):
        """Matched node tags."""
        return [self.tree[nid].tag for nid in self._ids]

    @property
    def first(self):
        """First match, or ``None``."""
        return self.tree[self._ids[0]] if self._ids else None

    @property
    def last(self):
        """Last match, or ``None``."""
        return self.tree[self._ids[-1]] if self._ids else None

    def ids_only(self):
        """Alias for :attr:`ids` kept for readability at call sites."""
        return list(self._ids)

    # -- chaining ----------------------------------------------------------
    def query(self, selector):
        """Run a further selector, restricted to the matched subtrees."""
        engine = _Engine(self.tree)
        return engine.run(selector, within=self._ids)

    def filter(self, predicate):
        """Keep matches whose node satisfies ``predicate(node)``."""
        return QueryResult(self.tree, [nid for nid in self._ids if predicate(self.tree[nid])])

    def attr(self, name, default=None):
        """Read one attribute from each match.

        Resolution order is ``node.data`` (mapping or object attribute) first,
        then the node itself, so ``result.attr("tag")`` and
        ``result.attr("size")`` both work.
        """
        return [self.tree[nid].get_attribute(name, default) for nid in self._ids]

    def texts(self):
        """Tag of each match, as plain strings."""
        return [str(self.tree[nid].tag) for nid in self._ids]

    def data(self):
        """``node.data`` of each match."""
        return [self.tree[nid].data for nid in self._ids]

    # -- tree views --------------------------------------------------------
    def to_tree(self, identifier=None):
        """Materialise the matches as a new forest-like :class:`Tree`.

        The common ancestor structure is preserved: a match whose parent is not
        itself matched is re-rooted, and ancestors needed to keep the hierarchy
        are inserted as lightweight placeholder nodes. This makes the result
        directly renderable with ``show()``, ``to_json()`` or the exporters.
        """
        from .tree import Tree

        result = Tree(identifier=identifier)
        if not self._ids:
            return result

        keep = set(self._ids)
        # Include the ancestors of every match so the shape is meaningful.
        needed = set(keep)
        for nid in self._ids:
            for ancestor in self.tree.rsearch(nid):
                needed.add(ancestor)

        # Pre-order walk of the original tree, creating nodes as we go.
        pending = [(self.tree.root, None)]
        created = {}
        while pending:
            nid, parent = pending.pop()
            if nid is None:
                continue
            if nid in needed:
                node = self.tree[nid]
                is_placeholder = nid not in keep
                if is_placeholder:
                    tag = "%s (…)" % node.tag
                else:
                    tag = node.tag
                created[nid] = result.create_node(tag=tag, identifier=nid, parent=parent, data=node.data)
                child_parent = nid
            else:
                child_parent = parent
            children = self.tree[nid].successors(self.tree.identifier)
            for child in reversed(children):
                pending.append((child, child_parent))
        return result

    def show(self, **kwargs):
        """Render the matches through :meth:`Tree.show`."""
        kwargs.setdefault("stdout", False)
        return self.to_tree().show(**kwargs)

    def count(self):
        """Number of matches."""
        return len(self._ids)


class _Engine(object):
    """Evaluates parsed selectors against a tree."""

    def __init__(self, tree):
        self.tree = tree
        self.tree_id = tree.identifier
        self._parent_cache = {}
        self._sibling_cache = {}

    # -- tree helpers ------------------------------------------------------
    def _parent(self, nid):
        if nid not in self._parent_cache:
            self._parent_cache[nid] = self.tree[nid].predecessor(self.tree_id)
        return self._parent_cache[nid]

    def _children(self, nid):
        return list(self.tree[nid].successors(self.tree_id))

    def _siblings(self, nid):
        parent = self._parent(nid)
        if parent is None:
            return [nid]
        return self._children(parent)

    def _position(self, nid):
        siblings = self._siblings(nid)
        return siblings.index(nid), len(siblings)

    def _descendants(self, nid, include_self=False):
        """Pre-order descendant ids (iterative, cycle-safe)."""
        result = [nid] if include_self else []
        pending = list(reversed(self._children(nid)))
        seen = {nid}
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            result.append(current)
            pending.extend(reversed(self._children(current)))
        return result

    # -- matching ----------------------------------------------------------
    def _match_compound(self, compound, nid):
        node = self.tree[nid]

        if compound.ids:
            for wanted in compound.ids:
                if nid != wanted:
                    return False

        if compound.tag and compound.tag != "*":
            if str(node.tag) != compound.tag:
                return False

        for name in compound.classes:
            if not node.has_class(name):
                return False

        for name, op, value in compound.attrs:
            if not node.has_attribute(name):
                return False
            if op is None:
                continue
            actual = node.get_attribute(name)
            if not _compare_attribute(actual, op, value):
                return False

        for name, argument in compound.pseudos:
            if not self._match_pseudo(name, argument, nid):
                return False
        return True

    def _match_pseudo(self, name, argument, nid):
        node = self.tree[nid]
        if name == "root":
            return nid == self.tree.root
        if name == "leaf":
            return not self._children(nid)
        if name == "branch":
            return bool(self._children(nid))
        if name == "expanded":
            return bool(node.expanded)
        if name == "collapsed":
            return not node.expanded
        if name == "first-child":
            return self._position(nid)[0] == 0
        if name == "last-child":
            index, total = self._position(nid)
            return index == total - 1
        if name == "only-child":
            return self._position(nid)[1] == 1
        if name == "nth-child":
            a, b = _parse_nth(argument)
            index = self._position(nid)[0] + 1  # 1-based
            if a == 0:
                return index == b
            offset = index - b
            return offset % a == 0 and offset // a >= 0
        if name == "contains":
            needle = argument.lower()
            if needle in str(node.tag).lower():
                return True
            data = node.data
            return needle in str(data).lower() if data is not None else False
        if name == "has":
            inner = _Engine(self.tree)
            inner._parent_cache = self._parent_cache
            inner._sibling_cache = self._sibling_cache
            text = argument.strip()
            # Relative selectors: ":has(> x)" means "has a direct child x",
            # ":has(+ x)" the next sibling, ":has(~ x)" any later sibling.
            # The candidate pool is deliberately widened to the whole tree for
            # sibling forms, because a sibling's own combinator chain may need
            # to look at nodes outside the pool.
            if text[:1] in (">", "+", "~"):
                combinator = text[0]
                remainder = text[1:].strip()
                if not remainder:
                    raise QueryError(":has(%s) needs a selector after the combinator" % combinator)
                if combinator == ">":
                    pool = self._children(nid)
                    if not pool:
                        return False
                    return bool(inner.run(remainder, candidates=pool))
                siblings = self._siblings(nid)
                position = siblings.index(nid)
                if combinator == "+":
                    pool = siblings[position + 1 : position + 2]
                else:
                    pool = siblings[position + 1 :]
                if not pool:
                    return False
                return bool(inner.run(remainder, candidates=pool))
            descendants = self._descendants(nid)
            if not descendants:
                return False
            return bool(inner.run(text, candidates=descendants))
        if name == "not":
            inner = _Engine(self.tree)
            inner._parent_cache = self._parent_cache
            inner._sibling_cache = self._sibling_cache
            matches = inner.run(argument, candidates=[nid])
            return not matches
        raise QueryError("unknown pseudo-class :%s" % name)  # pragma: no cover

    def _match_selector(self, selector, nid):
        """Right-to-left matching of one selector against a single node."""
        return self._match_from(selector, len(selector.compounds) - 1, nid)

    def _match_from(self, selector, index, nid):
        if not self._match_compound(selector.compounds[index], nid):
            return False
        if index == 0:
            return True

        combinator = selector.combinators[index - 1]
        if combinator == ">":
            parent = self._parent(nid)
            return parent is not None and self._match_from(selector, index - 1, parent)

        if combinator == " ":
            parent = self._parent(nid)
            while parent is not None:
                if self._match_from(selector, index - 1, parent):
                    return True
                parent = self._parent(parent)
            return False

        if combinator in ("+", "~"):
            siblings = self._siblings(nid)
            position = siblings.index(nid)
            if combinator == "+":
                candidates = siblings[position - 1 : position] if position else []
            else:
                candidates = siblings[:position]
            for candidate in reversed(candidates):
                if self._match_from(selector, index - 1, candidate):
                    return True
            return False

        raise QueryError("unknown combinator %r" % combinator)  # pragma: no cover

    # -- entry point -------------------------------------------------------
    def run(self, selector_text, candidates=None, within=None):
        """Evaluate ``selector_text`` and return a :class:`QueryResult`.

        Args:
            selector_text: selector string (or an already-parsed selector list).
            candidates: explicit node ids to test, in document order.
            within: node ids whose subtrees form the search universe (used by
                ``QueryResult.query`` to narrow a previous result).

        Filtering never changes *how* ancestors are matched: combinators such as
        ``#root > *`` still walk the real parent chain, so a descendant query
        inside a subtree behaves the same as the corresponding clause of a
        larger selector.
        """
        selectors = parse(selector_text) if isinstance(selector_text, str) else selector_text

        if candidates is not None:
            universe = list(candidates)
        elif within is not None:
            universe = []
            for nid in within:
                universe.extend(self._descendants(nid, include_self=True))
            universe = list(dict.fromkeys(universe))
        elif self.tree.root is None:
            return QueryResult(self.tree, [])
        else:
            universe = self._descendants(self.tree.root, include_self=True)

        matched = set()
        for selector in selectors:
            for nid in universe:
                if nid in matched:
                    continue
                try:
                    if self._match_selector(selector, nid):
                        matched.add(nid)
                except NodeIDAbsentError:  # pragma: no cover - defensive
                    continue

        # Document order, independent of selector order (CSS semantics).
        return QueryResult(self.tree, [nid for nid in universe if nid in matched])


def _compare_attribute(actual, op, expected):
    if op == "=":
        return _loose_equal(actual, expected)
    if op == "!=":
        return not _loose_equal(actual, expected)
    text = "" if actual is None else str(actual)
    if op == "^=":
        return text.startswith(expected)
    if op == "$=":
        return text.endswith(expected)
    if op == "*=":
        return expected in text
    if op == "~=":
        return expected in text.split()
    if op == "|=":
        return text == expected or text.startswith(expected + "-")
    raise QueryError("unknown attribute operator %r" % op)


def _loose_equal(actual, expected):
    """Compare without forcing everything through ``str``.

    ``[count=3]`` should match the integer ``3`` as well as the string ``"3"``,
    but ``[flag=true]`` must not match the string ``"1"``.
    """
    if actual == expected:
        return True
    if isinstance(actual, bool) or isinstance(expected, bool):
        return str(actual).lower() == str(expected).lower()
    return str(actual) == str(expected)


def query(tree, selector):
    """Module-level convenience wrapper around ``Tree.query``."""
    return _Engine(tree).run(selector)
