# NOTICE

This product is a modified version of **treelib**, and includes material
derived from the original work.

## Original work

- **Project:** treelib — *Simple to use for you. Python 2/3 Tree Implementation*
- **Source:** https://github.com/caesar0301/treelib
- **Base commit:** `83b3b87` (*Merge pull request #248 from cmoliverio/support-basic-data*)
- **Base version:** 1.8.0
- **Copyright (C) 2011** Brett Alistair Kromkamp — brettkromkamp@gmail.com
- **Copyright (C) 2012-2025** Xiaming Chen — chenxm35@gmail.com, and other contributors
- **Licence:** Apache License, Version 2.0 — see `LICENSE` (reproduced verbatim,
  unmodified)

## This version

- **Project:** treelib-toolkit
- **Version:** 1.9.0
- **Copyright (C) 2026** treelib-toolkit contributors
- **Licence:** Apache License, Version 2.0

## Statement of changes

As required by Apache License 2.0, §4(b), the following files were modified, and
the following files are new. No file from the original work was removed.

### Modified

| File | Change |
|---|---|
| `treelib/tree.py` | `to_dict`, `to_json`, `from_json`, `save2file`, `to_graphviz`, `update_node`, `show` and the rendering backend rewritten to be iterative and/or corrected; `query()` added; `save2file` gained `append=` |
| `treelib/node.py` | Added `CLASS_ATTRIBUTE`, `_data_lookup`, `has_attribute`, `get_attribute`, `get_classes`, `has_class` (additive; no existing method changed) |
| `treelib/__init__.py` | Re-exports for the new public API; `__version__` added |
| `README.md` | Rewritten to document the fork |
| `HISTORY` | Changelog entry for 1.9.0 |
| `pyproject.toml` | Version 1.9.0; console entry point; package list for the new modules |

### Added

| File | Purpose |
|---|---|
| `treelib/_json.py` | Depth-safe JSON encoder/decoder (byte-identical output to `json`) |
| `treelib/query.py` | CSS-inspired selector engine |
| `treelib/diff.py` | Structural diff and patch replay |
| `treelib/integrity.py` | Structural validation |
| `treelib/render.py` | Markdown / Mermaid / DOT / HTML renderers |
| `treelib/textparse.py` | Parser for the `Tree.show()` text layout |
| `treelib/cli.py` | `python -m treelib` command line |
| `treelib/__main__.py` | Module entry point |
| `tests/test_bugfixes.py` | Regression tests for the fixed defects |
| `tests/test_query.py` | Selector engine tests |
| `tests/test_diff_integrity.py` | Diff and validation tests |
| `tests/test_render.py` | Renderer and text round-trip tests |
| `tests/test_cli.py` | CLI tests |
| `docs/figures/*.png` | Three measurement figures used by the README |
| `docs/figures/data/*.json` | The measurements the figures are drawn from |
| `docs/figures/scripts/*.py` | Scripts that reproduce the JSON and the figures |
| `CHANGELOG.md` | Release notes |

### Unchanged

`LICENSE`, `AUTHORS`, `treelib/exceptions.py`, `treelib/misc.py`,
`treelib/py.typed`, and all seven original test modules under `tests/` are
untouched. The original 211 tests pass without modification.

## Trademarks

`treelib` is the name of the original project. This fork is distributed as
`treelib-toolkit` and does not claim to be the official upstream release.
