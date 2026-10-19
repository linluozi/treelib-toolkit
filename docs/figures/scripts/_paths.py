"""Shared paths for the figure scripts.

Resolves the fork root and the upstream baseline by walking up from this file, so
the scripts work from any checkout layout. The upstream tree is optional: only
the scripts that compare against it need it.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIGURES = os.path.dirname(HERE)          # docs/figures
DOCS = os.path.dirname(FIGURES)          # docs
ROOT = os.path.dirname(DOCS)             # repository root
DATA = os.path.join(FIGURES, "data")
OUT = FIGURES                            # PNGs live next to this README


def find_upstream():
    """Locate an unmodified treelib 1.8.0 checkout, or return None.

    Looked for in a few conventional places; override with TREELIB_UPSTREAM.
    """
    override = os.environ.get("TREELIB_UPSTREAM")
    candidates = []
    if override:
        candidates.append(override)
    parent = os.path.dirname(ROOT)
    for name in ("treelib-src", "treelib", "_inspect_treelib/treelib-src"):
        candidates.append(os.path.join(parent, name))
    for candidate in candidates:
        marker = os.path.join(candidate, "treelib", "tree.py")
        if os.path.exists(marker):
            # Make sure it is not this fork.
            if os.path.abspath(candidate) != os.path.abspath(ROOT):
                return os.path.abspath(candidate)
    return None


def fork_root():
    return ROOT


def require_upstream():
    upstream = find_upstream()
    if upstream is None:
        sys.exit(
            "upstream treelib checkout not found; set TREELIB_UPSTREAM to its path.\n"
            "Only the comparison scripts need it - plot.py reads the recorded JSON."
        )
    return upstream
