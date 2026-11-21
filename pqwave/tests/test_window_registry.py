"""Regression tests for the xschem WindowRegistry singleton.

The singleton used to keep its instance on a class attribute
(``WindowRegistry._instance``).  PyQt6 builds the dynamic metaobject by walking
class attributes; it found that not-yet-initialised QObject, re-entered
attribute lookup while building the metaobject, and recursed until the C stack
overflowed -- a SIGSEGV on the first ``get_registry()`` call.
"""

from pqwave.bridge.xschem.window_registry import WindowRegistry, get_registry


def test_get_registry_returns_the_singleton():
    assert get_registry() is get_registry()
    assert WindowRegistry() is get_registry()


def test_reset_creates_a_fresh_registry():
    first = get_registry()
    WindowRegistry.reset()
    second = get_registry()
    assert second is not first


def test_signals_still_work_on_the_singleton(qtbot):
    registry = get_registry()
    with qtbot.waitSignal(registry.window_registered, timeout=1000) as blocker:
        registry.window_registered.emit("win-1", object())
    assert blocker.args[0] == "win-1"
