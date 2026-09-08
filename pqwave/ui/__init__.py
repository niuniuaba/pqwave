"""
UI components for pqwave.

Names are resolved lazily (PEP 562) instead of being imported eagerly here.

Eagerly importing MainWindow made `import pqwave.ui.anything` construct the whole
GUI stack, and that produced a genuine circular import: measure_engine needs
pqwave.ui.measure_registry, importing `pqwave.ui` ran `main_window`, and
main_window imports measure_engine back -- so a cold
`from pqwave.measure.measure_engine import evaluate_measure` failed with
"cannot import name ... from partially initialized module".
"""

_LAZY = {
    "MenuManager": ".menu_manager",
    "ControlPanel": ".control_panel",
    "PlotWidget": ".plot_widget",
    "TraceManager": ".trace_manager",
    "AxisManager": ".axis_manager",
    "MainWindow": ".main_window",
}

__all__ = sorted(_LAZY)


def __getattr__(name):
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    value = getattr(import_module(module_path, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
