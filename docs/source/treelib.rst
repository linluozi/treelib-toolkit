treelib package
===============

Module contents
---------------

.. automodule:: treelib
    :members:
    :undoc-members:
    :show-inheritance:

Submodules
----------

treelib.node module
-------------------

.. automodule:: treelib.node
    :members:
    :undoc-members:
    :show-inheritance:

treelib.tree module
-------------------

.. automodule:: treelib.tree
    :members:
    :undoc-members:
    :show-inheritance:

treelib.plugins module
----------------------

.. automodule:: treelib.plugins
    :members:
    :undoc-members:
    :show-inheritance:

treelib.exceptions module
-------------------------

.. automodule:: treelib.exceptions
    :members:
    :undoc-members:
    :show-inheritance:

treelib.query module
--------------------

CSS-inspired selector engine. See the README for the grammar.

.. automodule:: treelib.query
    :members: parse, query, QueryResult, Selector, QueryError
    :show-inheritance:

treelib.diff module
-------------------

Structural diff between two trees, and patch replay.

.. automodule:: treelib.diff
    :members: diff, apply_patch, TreeDiff, Change
    :show-inheritance:

treelib.integrity module
------------------------

Structural validation.

.. automodule:: treelib.integrity
    :members: validate, is_valid, ValidationReport, Problem
    :show-inheritance:

treelib.render module
---------------------

Markdown, Mermaid, DOT and HTML renderers.

.. automodule:: treelib.render
    :members: render, to_markdown, to_mermaid, to_dot, to_html
    :show-inheritance:

treelib.textparse module
------------------------

Parser for the text layout printed by ``Tree.show()``.

.. automodule:: treelib.textparse
    :members: parse_tree, slugify, ParseError
    :show-inheritance:

treelib.cli module
------------------

``python -m treelib`` command line interface.

.. automodule:: treelib.cli
    :members: main, build_parser, load_tree
    :show-inheritance:
