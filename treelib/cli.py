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
"""Command line interface: ``python -m treelib``.

Subcommands
-----------
``show``      render a tree file as text / markdown / mermaid / dot / html
``query``     run a selector against a tree file
``stats``     node counts, depth, fan-out, leaves
``diff``      structural diff between two tree files
``validate``  check structural invariants
``convert``   rewrite a tree file in another format

Input formats are inferred from the extension: ``.json`` is read with
``Tree.from_json``, ``.txt`` / ``.tree`` with :func:`treelib.parse_tree` (the
indented layout printed by ``Tree.show()``), and ``-`` reads stdin as JSON.
"""

import argparse
import io
import json
import os
import sys

from . import __version__ as _pkg_version
from .diff import diff as _diff
from .exceptions import NodeIDAbsentError
from .integrity import validate as _validate
from .query import QueryError
from .render import FORMATS, render as _render
from .tree import Tree

#: Extensions treated as the indented text layout.
TEXT_SUFFIXES = (".txt", ".tree", ".tree.txt")


# ----------------------------------------------------------------------
# Input
# ----------------------------------------------------------------------
def _read_text(path):
    if path == "-":
        return sys.stdin.read()
    with io.open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def load_tree(path):
    """Load a tree from ``path``; ``-`` means stdin (JSON)."""
    if path == "-":
        return Tree.from_json(sys.stdin.read())
    if not os.path.exists(path):
        raise IOError("no such file: %s" % path)
    lowered = path.lower()
    if lowered.endswith(TEXT_SUFFIXES):
        from .textparse import parse_tree

        return parse_tree(_read_text(path))
    return Tree.from_json(_read_text(path))


# ----------------------------------------------------------------------
# Output helpers
# ----------------------------------------------------------------------
def _write(text, path=None):
    """Write ``text`` to ``path`` (UTF-8, LF) or to stdout."""
    if not text.endswith("\n"):
        text += "\n"
    if path is None or path == "-":
        sys.stdout.write(text)
    else:
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def _emit_rendered(tree, fmt, out, **kwargs):
    text = _render(tree, fmt, **kwargs)
    _write(text, out)


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
def cmd_show(args):
    tree = load_tree(args.file)
    if args.format == "text":
        kwargs = dict(stdout=False, idhidden=not args.show_id, line_type=args.line_type)
        text = tree.show(**kwargs)
        lines = text.splitlines()
        if args.depth is not None:
            # Keep only the first `depth` indentation levels (root = level 0).
            lines = [line for line in lines if _text_level(line) <= args.depth]
        if args.limit is not None:
            lines = lines[: args.limit]
        _write("\n".join(lines), args.out)
        return 0

    kwargs = dict(show_id=args.show_id, limit=args.limit)
    if args.format == "html":
        kwargs["title"] = args.title or os.path.basename(args.file or "tree")
        kwargs["show_id"] = True
    _emit_rendered(tree, args.format, args.out, **kwargs)
    return 0


def _text_level(line):
    """Indentation depth of a rendered tree line (4 chars per level)."""
    stripped = line.lstrip(" │├└─|+")
    prefix = len(line) - len(stripped)
    return max(0, prefix // 4)


def cmd_query(args):
    tree = load_tree(args.file)
    result = tree.query(args.selector)
    if args.format == "ids":
        for nid in result.ids:
            sys.stdout.write(nid + "\n")
    elif args.format == "json":
        payload = [{"id": node.identifier, "tag": node.tag, "data": node.data} for node in result]
        _write(json.dumps(payload, ensure_ascii=False, indent=2), args.out)
    elif args.format == "text":
        _write(result.show(idhidden=not args.show_id), args.out)
    else:
        _write(_render(result.to_tree(), args.format, show_id=args.show_id), args.out)
    if args.count:
        sys.stderr.write("%d node(s) matched\n" % len(result))
    return 0


def cmd_stats(args):
    tree = load_tree(args.file)
    if not tree.nodes:
        # An empty tree has no depth, no fan-out and no levels; report that
        # explicitly instead of letting tree.level(None) raise.
        if args.format == "json":
            payload = {
                "nodes": 0,
                "depth": 0,
                "leaves": 0,
                "branches": 0,
                "max_fanout": 0,
                "max_fanout_node": None,
                "per_level": {},
            }
            _write(json.dumps(payload, ensure_ascii=False, indent=2), args.out)
        else:
            _write("empty tree", args.out)
        return 0

    depths = {nid: tree.level(nid) for nid in tree.nodes}
    fanout = {nid: len(tree[nid].successors(tree.identifier)) for nid in tree.nodes}
    leaves = [nid for nid, count in fanout.items() if count == 0]
    max_depth = max(depths.values())
    widest = max(fanout.items(), key=lambda item: item[1])
    per_level = {}
    for nid, level in depths.items():
        per_level[level] = per_level.get(level, 0) + 1

    if args.format == "json":
        payload = {
            "nodes": len(tree.nodes),
            "depth": max_depth,
            "leaves": len(leaves),
            "branches": len(tree.nodes) - len(leaves),
            "max_fanout": widest[1],
            "max_fanout_node": widest[0],
            "per_level": {str(level): per_level[level] for level in sorted(per_level)},
        }
        _write(json.dumps(payload, ensure_ascii=False, indent=2), args.out)
        return 0

    lines = [
        "nodes      : %d" % len(tree.nodes),
        "depth      : %d" % max_depth,
        "leaves     : %d" % len(leaves),
        "branches   : %d" % (len(tree.nodes) - len(leaves)),
        "max fanout : %d (node %r)" % (widest[1], widest[0]),
        "per level  : " + ", ".join("%d:%d" % (level, per_level[level]) for level in sorted(per_level)),
    ]
    _write("\n".join(lines), args.out)
    return 0


def cmd_diff(args):
    old = load_tree(args.old)
    new = load_tree(args.new)
    result = _diff(old, new, compare_data=not args.ignore_data)

    if args.format == "json":
        _write(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), args.out)
    elif args.format == "markdown":
        lines = ["| kind | node | detail |", "|---|---|---|"]
        for change in result:
            lines.append("| %s | `%s` | %s |" % (change.kind, change.identifier, change.describe()))
        _write("\n".join(lines), args.out)
    else:
        text = result.describe()
        _write(text if text else "no structural changes", args.out)

    if args.exit_code and result:
        return 1
    return 0


def cmd_validate(args):
    tree = load_tree(args.file)
    report = _validate(tree)
    if args.format == "json":
        _write(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), args.out)
    else:
        _write(report.describe(), args.out)
    if args.exit_code and not report.ok:
        return 1
    return 0


def cmd_convert(args):
    tree = load_tree(args.file)
    target = args.to.lower()
    if target == "json":
        _write(tree.to_json(with_data=True, with_identifier=True), args.out)
    elif target in ("text", "tree"):
        _write(tree.show(stdout=False), args.out)
    elif target in FORMATS:
        _emit_rendered(tree, target, args.out)
    else:
        raise ValueError("unknown target format %r" % args.to)
    return 0


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m treelib",
        description="Inspect, query, diff and export treelib trees.",
    )
    parser.add_argument("--version", action="version", version="treelib-toolkit %s" % _pkg_version)
    subparsers = parser.add_subparsers(dest="command")

    show = subparsers.add_parser("show", help="render a tree")
    show.add_argument("file", help="tree file (.json/.txt) or - for stdin JSON")
    show.add_argument("-f", "--format", default="text", choices=("text",) + FORMATS)
    show.add_argument("-o", "--out", default=None, help="output file (default stdout)")
    show.add_argument("--show-id", action="store_true", help="include node identifiers")
    show.add_argument("--line-type", default="ascii-ex", help="text renderer line style")
    show.add_argument("--depth", type=int, default=None, help="truncate below this level")
    show.add_argument("--limit", type=int, default=None, help="stop after N nodes")
    show.add_argument("--title", default=None, help="HTML page title")
    show.set_defaults(func=cmd_show)

    query = subparsers.add_parser("query", help="select nodes with a selector")
    query.add_argument("file")
    query.add_argument("selector", help='e.g. "*.py:leaf" or "#root > *"')
    query.add_argument("-f", "--format", default="ids", choices=("ids", "json", "text") + FORMATS)
    query.add_argument("-o", "--out", default=None)
    query.add_argument("--show-id", action="store_true")
    query.add_argument("--count", action="store_true", help="print match count to stderr")
    query.set_defaults(func=cmd_query)

    stats = subparsers.add_parser("stats", help="shape statistics")
    stats.add_argument("file")
    stats.add_argument("-f", "--format", default="text", choices=("text", "json"))
    stats.add_argument("-o", "--out", default=None)
    stats.set_defaults(func=cmd_stats)

    diff = subparsers.add_parser("diff", help="structural diff of two trees")
    diff.add_argument("old")
    diff.add_argument("new")
    diff.add_argument("-f", "--format", default="text", choices=("text", "json", "markdown"))
    diff.add_argument("-o", "--out", default=None)
    diff.add_argument("--ignore-data", action="store_true", help="compare tags and topology only")
    diff.add_argument("--exit-code", action="store_true", help="exit 1 when differences exist")
    diff.set_defaults(func=cmd_diff)

    validate = subparsers.add_parser("validate", help="check structural invariants")
    validate.add_argument("file")
    validate.add_argument("-f", "--format", default="text", choices=("text", "json"))
    validate.add_argument("-o", "--out", default=None)
    validate.add_argument("--exit-code", action="store_true", help="exit 1 on errors")
    validate.set_defaults(func=cmd_validate)

    convert = subparsers.add_parser("convert", help="convert between formats")
    convert.add_argument("file")
    convert.add_argument("--to", required=True, help="json, text, markdown, mermaid, dot, html")
    convert.add_argument("-o", "--out", default=None)
    convert.set_defaults(func=cmd_convert)

    return parser


def main(argv=None):
    # Windows consoles default to a legacy code page; tree output contains box
    # drawing characters and arbitrary Unicode tags, so force UTF-8 with a
    # replacement policy rather than crashing on the first non-encodable glyph.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover - streams may be redirected
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    try:
        return args.func(args) or 0
    except (IOError, OSError) as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2
    except (NodeIDAbsentError, QueryError, ValueError) as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2
    except BrokenPipeError:  # pragma: no cover - piping into head(1)
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
