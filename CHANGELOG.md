# Changelog

All notable changes to this fork are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Upstream history prior to 1.9.0 is preserved in [`HISTORY`](HISTORY).

## [1.9.0] — 2026-10-19

Fork of `treelib` 1.8.0 (`caesar0301/treelib` @ `83b3b87`). The upstream API is
unchanged; all 211 upstream tests pass unmodified.

### Added

- **Query language** (`treelib.query`, `Tree.query()`): CSS-inspired selectors
  with tag, `#id`, `.class`, `[attr op value]` (`=`, `!=`, `^=`, `$=`, `*=`,
  `~=`, `|=`), and the pseudo-classes `:root`, `:leaf`, `:branch`, `:expanded`,
  `:collapsed`, `:first-child`, `:last-child`, `:only-child`,
  `:nth-child(an+b)`, `:has()` (including relative forms `>`, `+`, `~`),
  `:not()`, `:contains()`. Combinators: descendant, `>`, `+`, `~`. Results are
  ordered, deduplicated, chainable, and convertible back into a `Tree`.
- **Structural diff** (`treelib.diff`): `diff(old, new)` reports `add`,
  `remove`, `move` and `update` changes; `apply_patch(tree, changes)` replays
  them. Data comparison is structural (mapping key order is not a change),
  additions are ordered parent-first, removals come first.
- **Integrity validation** (`treelib.integrity`): `validate(tree)` reports
  missing/absent root, root with a parent, orphans, dangling parent or child
  pointers, backlink mismatches, duplicate children, cycles and unreachable
  nodes — all of them, not just the first.
- **Renderers** (`treelib.render`): `to_markdown`, `to_mermaid`, `to_dot`,
  `to_html`, plus `render(tree, fmt)`. All share `filter`/`key`/`reverse`/
  `sorting`/`limit`/`data_property`/`show_id` and are iterative. The HTML output
  is a single self-contained page with live filtering, expand/collapse all and
  per-node collapse.
- **Text round-trip** (`treelib.textparse`): `parse_tree()` reads back the
  layout printed by `Tree.show()`, for every shipped `line_type`, plus Markdown
  bullet lists and tab indentation.
- **Command line** (`python -m treelib`): `show`, `query`, `stats`, `diff`,
  `validate`, `convert`, with `--exit-code` support for CI.
- **Node helpers**: `has_attribute`, `get_attribute`, `get_classes`,
  `has_class` — used by attribute and class selectors, useful on their own.

### Fixed

- `to_dict()` and `to_json()` no longer raise `RecursionError` on trees deeper
  than the interpreter recursion limit. A 1,500-deep chain serialises normally.
- `from_json()` no longer raises `RecursionError` on deeply nested documents.
- `from_json()` accepts the bare-string form produced by `to_json()` for a
  single-node tree, so `Tree.from_json(tree.to_json())` round-trips for every
  tree. It also rejects non-object roots with a clear `ValueError` instead of an
  `AttributeError`.
- `save2file()` no longer appends to an existing file (a second call used to
  duplicate the whole tree) and no longer opens one file handle per rendered
  line. Pass `append=True` for the old additive behaviour.
- `show(level=n)` no longer raises `IndexError: list index out of range`; the
  `level` parameter is documented as the indentation level of the first node.
- `to_graphviz(filter=…)` no longer emits edges to nodes removed by the filter,
  which made Graphviz reject the document with "node not defined". It now also
  returns the DOT source.
- `update_node(nid, identifier=…)` raises `DuplicatedNodeIdError` when the new
  identifier is already in use, instead of silently dropping the other node and
  leaving its parent pointing at a reused id.
- `show()` and `save2file()` are iterative, so deep chains render without
  `RecursionError`.

### Changed

- `to_graphviz()` returns the DOT source string (previously `None`).
- `save2file()` truncates by default; `append=False` is the new parameter.

### Compatibility

- Python 3.7+, standard library only.
- No upstream method changed signature except `save2file` (new keyword with a
  backwards-compatible default).
- Rendering output is byte-identical to upstream across 192 verified lines.
