"""
pqwave - A Wave Viewer for SPICE raw data using spicelib and PyQtGraph
"""

from ._version import __version__

__author__ = "niuniuaba"

__all__ = [
    "__version__",
    "__author__",
    "RawFile",
    "ExprEvaluator",
    "MainWindow",
    "main",
    "SessionAPI",
    "api_command",
    "get_command_registry",
]

# Heavy, optionally- unavailable names are resolved lazily (PEP 562) so that
# `import pqwave` does not pull in PyQt6 just to read __version__, and so that a
# missing GUI dependency does not make the whole package unimportable. This also
# removes the previous `X = None` fallback assignments, which mypy rejected as
# "Cannot assign to a type", and the eager `from .main import main`, which made
# `python -m pqwave.main` warn about re-importing an already-loaded module.
_LAZY = {
    "RawFile": (".models.rawfile", "RawFile"),
    "ExprEvaluator": (".models.expression", "ExprEvaluator"),
    "MainWindow": (".ui.main_window", "MainWindow"),
    "main": (".main", "main"),
    "SessionAPI": (".session.api", "SessionAPI"),
    "api_command": (".session.api", "api_command"),
    "get_command_registry": (".session.api", "get_command_registry"),
}


def __getattr__(name):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    module, attr = target
    try:
        value = getattr(import_module(module, __name__), attr)
    except ImportError as exc:
        raise AttributeError(
            f"pqwave.{name} is unavailable: {exc}"
        ) from exc
    globals()[name] = value          # cache for subsequent lookups
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
