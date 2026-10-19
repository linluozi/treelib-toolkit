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
"""Alternative renderers for :class:`treelib.Tree`.

``Tree.show()`` targets a terminal and ``Tree.to_graphviz()`` needs Graphviz
installed. Neither helps when the tree has to end up in a README, a chat
message, a browser tab, or a slide. This module adds four self-contained
output formats with no third-party dependency:

``markdown``  nested bullet list, renders on GitHub / GitLab / docs sites
``mermaid``   ``graph TD`` block, renders inline on GitHub and in Notion
``dot``       Graphviz source, same as ``to_graphviz`` but as a string
``html``      a single collapsible page with search, no CDN, no JS deps

All renderers share the same node ordering and filtering options so a tree
looks the same whichever format you pick.
"""

from .exceptions import NodeIDAbsentError

__all__ = ["render", "to_markdown", "to_mermaid", "to_dot", "to_html", "FORMATS"]

FORMATS = ("markdown", "mermaid", "dot", "html")


def _ordered(tree, nid, filter_, key, reverse, sorting, limit):
    """Pre-order walk yielding ``(nid, depth)`` with optional filtering.

    Iterative on purpose: a 2,000-deep chain must render without touching the
    recursion limit.
    """
    if nid is None:
        nid = tree.root
    if nid is None:
        return
    if nid not in tree.nodes:
        raise NodeIDAbsentError("Node '%s' is not in the tree" % nid)

    emitted = 0
    stack = [(nid, 0)]
    while stack:
        current, depth = stack.pop()
        node = tree[current]
        if filter_ is not None and not filter_(node):
            continue
        yield current, depth
        emitted += 1
        if limit is not None and emitted >= limit:
            return
        if not node.expanded:
            continue
        children = [tree[c] for c in node.successors(tree.identifier)]
        if sorting:
            if key is not None:
                children.sort(key=key, reverse=reverse)
            elif reverse:
                children = list(reversed(children))
        for child in reversed(children):
            stack.append((child.identifier, depth + 1))


def _label(node, data_property=None, show_id=False):
    if data_property:
        try:
            text = str(getattr(node.data, data_property))
        except AttributeError:
            text = str(node.tag)
    else:
        text = str(node.tag)
    if show_id:
        return "%s [%s]" % (text, node.identifier)
    return text


def to_markdown(
    tree, nid=None, filter=None, key=None, reverse=False, sorting=True, data_property=None, show_id=False, limit=None
):
    """Render the tree as a nested Markdown bullet list.

    Example output::

        - project
          - src
            - main.py
    """
    lines = []
    for current, depth in _ordered(tree, nid, filter, key, reverse, sorting, limit):
        indent = "  " * depth
        lines.append("%s- %s" % (indent, _label(tree[current], data_property, show_id)))
    return "\n".join(lines)


_MERMAID_UNSAFE = {
    '"': "#quot;",
    "[": "#91;",
    "]": "#93;",
    "(": "#40;",
    ")": "#41;",
    "{": "#123;",
    "}": "#125;",
    "|": "#124;",
    "<": "#60;",
    ">": "#62;",
    "`": "#96;",
}


def _mermaid_escape(text):
    """Mermaid labels break on quotes and brackets; replace them with entities."""
    return "".join(_MERMAID_UNSAFE.get(char, char) for char in text)


def to_mermaid(
    tree,
    nid=None,
    filter=None,
    key=None,
    reverse=False,
    sorting=True,
    data_property=None,
    show_id=False,
    limit=None,
    direction="TD",
):
    """Render the tree as a Mermaid ``graph`` block.

    Node identifiers are Mermaid-safe aliases (``n0``, ``n1``…) mapped to the
    real labels, so identifiers containing dots, spaces or quotes cannot break
    the diagram.
    """
    if direction not in ("TD", "TB", "BT", "LR", "RL"):
        raise ValueError("direction must be one of TD, TB, BT, LR, RL, got %r" % (direction,))

    lines = ["```mermaid", "graph %s" % direction]
    aliases = {}
    for index, (current, depth) in enumerate(_ordered(tree, nid, filter, key, reverse, sorting, limit)):
        alias = "n%d" % index
        aliases[current] = alias
        label = _mermaid_escape(_label(tree[current], data_property, show_id))
        lines.append('    %s["%s"]' % (alias, label))

    for current, depth in _ordered(tree, nid, filter, key, reverse, sorting, limit):
        for child in tree[current].successors(tree.identifier):
            if child in aliases:
                lines.append("    %s --> %s" % (aliases[current], aliases[child]))

    lines.append("```")
    return "\n".join(lines)


def _dot_escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(
    tree,
    nid=None,
    filter=None,
    key=None,
    reverse=False,
    sorting=True,
    data_property=None,
    show_id=False,
    limit=None,
    shape="circle",
    graph="digraph",
):
    """Render the tree as Graphviz DOT source.

    Unlike :meth:`Tree.to_graphviz` this returns the source string, never prints,
    and accepts ``show_id`` / ``limit`` for large trees.
    """
    edge = "->" if graph == "digraph" else "--"
    nodes, edges = [], []
    declared = []
    for current, depth in _ordered(tree, nid, filter, key, reverse, sorting, limit):
        label = _dot_escape(_label(tree[current], data_property, show_id))
        nodes.append('\t"%s" [label="%s", shape=%s]' % (_dot_escape(str(current)), label, shape))
        declared.append(current)

    declared_set = set(declared)
    for current in declared:
        for child in tree[current].successors(tree.identifier):
            # Only emit edges whose both endpoints were rendered, otherwise
            # Graphviz rejects the document with "node not defined".
            if child in declared_set:
                edges.append('\t"%s" %s "%s"' % (_dot_escape(str(current)), edge, _dot_escape(str(child))))

    parts = ["%s tree {" % graph]
    parts.extend(nodes)
    if edges:
        parts.append("")
        parts.extend(edges)
    parts.append("}")
    return "\n".join(parts)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --ink: #2b2119;
    --paper: #faf6f0;
    --panel: #ffffff;
    --amber: #c8892b;
    --terracotta: #b4552f;
    --muted: #8a7a68;
    --line: #e6dccd;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 32px 24px 64px;
    background: var(--paper); color: var(--ink);
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
  }
  .wrap { max-width: 960px; margin: 0 auto; }
  header { border-bottom: 2px solid var(--ink); padding-bottom: 14px; margin-bottom: 18px; }
  h1 { margin: 0 0 6px; font-size: 24px; letter-spacing: .2px; }
  .meta { color: var(--muted); font-size: 13px; }
  .bar { display: flex; gap: 10px; align-items: center; margin: 18px 0 22px; flex-wrap: wrap; }
  input[type=search] {
    flex: 1 1 240px; padding: 9px 12px; font-size: 14px;
    border: 1px solid var(--line); border-radius: 6px; background: var(--panel); color: var(--ink);
  }
  input[type=search]:focus { outline: 2px solid var(--amber); outline-offset: 1px; }
  button {
    padding: 8px 13px; font-size: 13px; cursor: pointer;
    border: 1px solid var(--line); border-radius: 6px;
    background: var(--panel); color: var(--ink);
  }
  button:hover { border-color: var(--amber); color: var(--terracotta); }
  #count { color: var(--muted); font-size: 13px; min-width: 110px; }
  ul.tree, ul.tree ul { list-style: none; margin: 0; padding-left: 20px; }
  ul.tree { padding-left: 0; }
  ul.tree li { position: relative; padding: 2px 0; }
  ul.tree ul li::before {
    content: ""; position: absolute; left: -12px; top: 0; bottom: 0;
    border-left: 1px solid var(--line);
  }
  ul.tree ul li:last-child::before { bottom: 50%; }
  ul.tree ul li::after {
    content: ""; position: absolute; left: -12px; top: 50%; width: 10px;
    border-top: 1px solid var(--line);
  }
  .node {
    display: inline-flex; align-items: baseline; gap: 7px;
    padding: 2px 7px; border-radius: 5px;
  }
  .node:hover { background: #f2e9db; }
  .tag { font-weight: 500; }
  .nid {
    font: 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--muted); background: #f4eee3; padding: 2px 5px; border-radius: 3px;
  }
  .toggle {
    cursor: pointer; user-select: none; color: var(--amber);
    font: 12px/1 ui-monospace, monospace; width: 12px; display: inline-block;
  }
  li.collapsed > ul { display: none; }
  li.hit > .node { background: #fbeecb; box-shadow: inset 0 0 0 1px var(--amber); }
  li.hidden { display: none; }
  .depth-0 > .node .tag { font-size: 17px; font-weight: 600; }
  footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <div class="meta">__META__</div>
  </header>
  <div class="bar">
    <input type="search" id="q" placeholder="Filter by tag or id…" aria-label="Filter nodes">
    <button id="expand">Expand all</button>
    <button id="collapse">Collapse all</button>
    <span id="count"></span>
  </div>
  <ul class="tree">
__TREE__
  </ul>
  <footer>Generated by treelib-toolkit · __COUNT__ node(s)</footer>
</div>
<script>
(function () {
  var items = Array.prototype.slice.call(document.querySelectorAll('ul.tree li'));
  var search = document.getElementById('q');
  var counter = document.getElementById('count');

  function tagOf(li) {
    var tag = li.querySelector(':scope > .node .tag');
    var nid = li.querySelector(':scope > .node .nid');
    return ((tag ? tag.textContent : '') + ' ' + (nid ? nid.textContent : '')).toLowerCase();
  }

  function applyFilter() {
    var needle = search.value.trim().toLowerCase();
    items.forEach(function (li) { li.classList.remove('hidden', 'hit'); });
    if (!needle) {
      items.forEach(function (li) { li.classList.remove('collapsed'); });
      counter.textContent = items.length + ' nodes';
      return;
    }
    var hits = 0;
    items.forEach(function (li) {
      if (tagOf(li).indexOf(needle) !== -1) {
        hits += 1;
        li.classList.add('hit');
        // Reveal ancestors so the hit is visible.
        var parent = li.parentElement.closest('li');
        while (parent) {
          parent.classList.remove('collapsed');
          parent = parent.parentElement.closest('li');
        }
      }
    });
    counter.textContent = hits + ' match' + (hits === 1 ? '' : 'es');
  }

  search.addEventListener('input', applyFilter);
  document.getElementById('expand').addEventListener('click', function () {
    items.forEach(function (li) { li.classList.remove('collapsed'); });
  });
  document.getElementById('collapse').addEventListener('click', function () {
    items.forEach(function (li) {
      if (li.querySelector(':scope > ul')) { li.classList.add('collapsed'); }
    });
  });

  document.addEventListener('click', function (event) {
    var toggle = event.target.closest('.toggle');
    if (!toggle) { return; }
    var li = toggle.closest('li');
    li.classList.toggle('collapsed');
    toggle.textContent = li.classList.contains('collapsed') ? '+' : '−';
  });

  counter.textContent = items.length + ' nodes';
})();
</script>
</body>
</html>
"""


def _html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def to_html(
    tree,
    title="Tree",
    nid=None,
    filter=None,
    key=None,
    reverse=False,
    sorting=True,
    data_property=None,
    show_id=True,
    limit=None,
):
    """Render the tree as a single self-contained interactive HTML page.

    The page has no external assets: it works from ``file://``, inside an
    e-mail attachment, or in a sandboxed preview. Features: live filtering,
    expand/collapse all, per-node collapse, and depth-aware typography.
    """
    # Group nodes by parent first, then serialise top-down. Building a real
    # parent -> children map (instead of patching strings afterwards) is what
    # keeps every <li> paired with exactly one </li> at every depth.
    visible = {}  # parent_id -> [child ids in order]
    roots = []
    parent_of = {}
    for current, depth in _ordered(tree, nid, filter, key, reverse, sorting, limit):
        node = tree[current]
        children = [child for child in node.successors(tree.identifier) if filter is None or filter(tree[child])]
        if sorting:
            if key is not None:
                children.sort(key=lambda cid: key(tree[cid]), reverse=reverse)
            elif reverse:
                children = list(reversed(children))
        visible[current] = children

    # Rebuild the hierarchy from the visible set so a filtered parent does not
    # orphan its children: a visible node whose parent is hidden becomes a root.
    for current in visible:
        parent = tree[current].predecessor(tree.identifier)
        if parent in visible and current != nid:
            parent_of[current] = parent
        else:
            roots.append(current)

    def serialise(node_id, depth, out):
        node = tree[node_id]
        children = [cid for cid in visible.get(node_id, []) if parent_of.get(cid) == node_id]
        has_children = bool(children)
        toggle = '<span class="toggle">−</span>' if has_children else '<span class="toggle"></span>'
        id_markup = '<span class="nid">%s</span>' % _html_escape(node_id) if show_id else ""
        out.append(
            '  <li class="depth-%d">%s<span class="node"><span class="tag">%s</span>%s</span>'
            % (depth, toggle, _html_escape(_label(node, data_property, False)), id_markup)
        )
        if children:
            out.append("    <ul>")
            for child in children:
                serialise(child, depth + 1, out)
            out.append("    </ul>")
        out.append("  </li>")

    rows = []
    for root in roots:
        serialise(root, 0, rows)
    markup = "\n".join(rows)
    count = sum(1 for _ in visible)
    meta = "%d node(s) · depth %d · generated by treelib-toolkit" % (count, tree.depth() if count else 0)
    return (
        _HTML_TEMPLATE.replace("__TITLE__", _html_escape(title))
        .replace("__META__", _html_escape(meta))
        .replace("__TREE__", markup)
        .replace("__COUNT__", str(count))
    )


def render(tree, fmt="markdown", **kwargs):
    """Dispatch to a renderer by name.

    Args:
        fmt: one of :data:`FORMATS` (``markdown``, ``mermaid``, ``dot``, ``html``).
        kwargs: forwarded to the concrete renderer.

    Raises:
        ValueError: for an unknown format name.
    """
    normalised = (fmt or "").strip().lower()
    renderers = {
        "markdown": to_markdown,
        "md": to_markdown,
        "mermaid": to_mermaid,
        "mmd": to_mermaid,
        "dot": to_dot,
        "graphviz": to_dot,
        "html": to_html,
    }
    try:
        renderer = renderers[normalised]
    except KeyError:
        raise ValueError("unknown format %r (choose from %s)" % (fmt, ", ".join(FORMATS)))
    return renderer(tree, **kwargs)
