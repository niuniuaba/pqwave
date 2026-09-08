"""Single source of truth for the pqwave version string.

Referenced by:
  * ``pqwave/__init__.py``      -> ``pqwave.__version__``
  * ``pqwave/main.py``          -> the ``--version`` CLI output
  * ``pyproject.toml``          -> ``tool.setuptools.dynamic.version``
  * ``setup.py``                -> legacy shim, parsed without importing

Keep this module free of any imports: setuptools resolves it by AST parsing, and
importing the ``pqwave`` package here would drag in PyQt6 at build time.

Bumping a release: change the value below and nothing else.
"""

__version__ = "0.3.4"
