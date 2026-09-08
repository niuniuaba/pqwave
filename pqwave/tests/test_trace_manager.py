#!/usr/bin/env python3
"""TraceManager and ColorManager surface tests.

Previously this was a `__main__`-only script: `pytest` collected zero tests from
it and silently reported success.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pqwave.ui.trace_manager import TraceManager  # noqa: E402
from pqwave.utils.colors import ColorManager  # noqa: E402


def _app():
    return QApplication.instance() or QApplication(sys.argv)


def test_imports_expose_managers():
    assert TraceManager.__name__ == "TraceManager"
    assert ColorManager.__name__ == "ColorManager"


def test_split_expressions_separates_whitespace_but_not_parens():
    """`v(out) v(in)` is two expressions; the parens are not separators."""
    _app()
    assert TraceManager.split_expressions("v(out) v(in)") == ["v(out)", "v(in)"]


def test_split_expressions_splits_on_top_level_spaces_only():
    """Contract: break on spaces at paren depth 0; quotes are stripped.

    Operators are *not* separators, so "2 * v(out)" yields three tokens -- a
    multi-trace entry field, not an expression parser. Recorded here so the
    behaviour is pinned rather than assumed.
    """
    _app()
    cases = {
        "v(out) v(in)": ["v(out)", "v(in)"],
        "v(a)  v(b)": ["v(a)", "v(b)"],           # runs of spaces collapse
        "v(out)-v(in)": ["v(out)-v(in)"],         # no space -> one expression
        "2 * v(out)": ["2", "*", "v(out)"],       # spaces around an operator
        "mag(v(a)) phase(v(a))": ["mag(v(a))", "phase(v(a))"],
        '"v(out)" "v(in)"': ["v(out)", "v(in)"],  # quoting stripped, grouping kept
        "": [],
        "   ": [],
    }
    for expr, expected in cases.items():
        assert TraceManager.split_expressions(expr) == expected, (
            f"split_expressions({expr!r}) -> "
            f"{TraceManager.split_expressions(expr)!r}, expected {expected!r}")


def test_split_expressions_survives_unbalanced_paren():
    """Malformed input must not raise or drop the token."""
    _app()
    assert TraceManager.split_expressions("v(out") == ["v(out"]
    assert TraceManager.split_expressions("v(out)) x") == ["v(out))", "x"]


def test_split_expressions_is_a_static_helper():
    """Callable without a TraceManager instance (used by the session API)."""
    assert callable(TraceManager.split_expressions)


def test_color_manager_cycles_without_reuse_until_reset():
    _app()
    cm = ColorManager()
    seen = [cm.get_next_color() for _ in range(6)]
    assert len(set(seen)) == 6, f"palette repeated a colour early: {seen}"
    cm.reset()
    assert cm.get_next_color() == seen[0], "reset() did not rewind the palette"


def test_color_manager_tracks_manual_usage():
    _app()
    cm = ColorManager()
    colour = cm.get_next_color()
    assert cm.is_color_used(colour), "handed-out colour was not marked used"
    cm.release_color(colour)
    assert not cm.is_color_used(colour), "release_color() did not free it"
    cm.mark_color_used((1, 2, 3))
    assert cm.is_color_used((1, 2, 3)), "mark_color_used() did not stick"


def main():
    tests = [test_imports_expose_managers,
             test_split_expressions_separates_whitespace_but_not_parens,
             test_split_expressions_splits_on_top_level_spaces_only,
             test_split_expressions_survives_unbalanced_paren,
             test_split_expressions_is_a_static_helper,
             test_color_manager_cycles_without_reuse_until_reset,
             test_color_manager_tracks_manual_usage]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"✓ {fn.__name__}")
        except Exception as exc:
            print(f"✗ {fn.__name__}: {exc}")
            failures.append(fn.__name__)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
