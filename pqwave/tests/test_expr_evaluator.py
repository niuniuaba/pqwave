#!/usr/bin/env python3
"""ExprEvaluator extraction tests.

Previously a `__main__`-only script that skipped all real work unless a raw file
was passed on argv, so pytest collected zero tests from it.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from pqwave.models.expression import ExprEvaluator  # noqa: E402
from pqwave.models.rawfile import RawFile  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_RAW = os.path.join(_ROOT, "tests", "bridge.raw")


def _evaluator(path=_DEFAULT_RAW):
    return ExprEvaluator(RawFile(path), 0)


def test_imports_expose_evaluator_and_rawfile():
    assert ExprEvaluator.__name__ == "ExprEvaluator"
    assert RawFile.__name__ == "RawFile"


def test_reports_point_count_from_dataset():
    ev = _evaluator()
    assert ev.n_points > 0, "evaluator has no points"


def test_literal_broadcasts_to_full_length():
    ev = _evaluator()
    result = ev.evaluate("2 + 3")
    assert len(result) == ev.n_points, "literal was not broadcast to the axis length"
    assert np.allclose(result, 5.0)


def test_variable_reference_returns_its_column():
    ev = _evaluator()
    names = ev.raw_file.get_variable_names(0)
    result = ev.evaluate(names[1])
    assert len(result) == ev.n_points
    assert not np.allclose(result, 0.0) or names[1] == "time", (
        f"{names[1]} evaluated to all zeros")


def test_arithmetic_on_a_variable_is_elementwise():
    ev = _evaluator()
    name = ev.raw_file.get_variable_names(0)[1]
    base = ev.evaluate(name)
    shifted = ev.evaluate(f"{name} + 1.5")
    assert np.allclose(shifted, base + 1.5), "variable arithmetic is not elementwise"


def test_known_functions_match_numpy():
    ev = _evaluator()
    name = ev.raw_file.get_variable_names(0)[1]
    data = ev.evaluate(name)
    assert np.allclose(ev.evaluate(f"abs({name})"), np.abs(data))
    assert np.allclose(ev.evaluate(f"sqrt(abs({name}))"), np.sqrt(np.abs(data)))
    assert np.allclose(ev.evaluate(f"sin({name})"), np.sin(data))


def test_precedence_matches_python():
    ev = _evaluator()
    assert np.allclose(ev.evaluate("2 + 3 * 4"), 14.0)
    assert np.allclose(ev.evaluate("(2 + 3) * 4"), 20.0)
    assert np.allclose(ev.evaluate("2 ** 3 ** 2"), 512.0), (
        "exponentiation must be right-associative")
    assert np.allclose(ev.evaluate("-2 ** 2"), -4.0), (
        "unary minus must bind looser than **")


def test_unknown_variable_raises_not_silently_zero():
    ev = _evaluator()
    try:
        result = ev.evaluate("v(definitely_not_present)")
    except Exception:
        return
    raise AssertionError(
        f"unknown variable silently produced {np.asarray(result)[:3]}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv and os.path.exists(argv[0]) else _DEFAULT_RAW
    if argv and not os.path.exists(argv[0]):
        print(f"✗ File not found: {argv[0]}")
        return 1
    print(f"Using {path}")
    tests = [test_imports_expose_evaluator_and_rawfile,
             test_reports_point_count_from_dataset,
             test_literal_broadcasts_to_full_length,
             test_variable_reference_returns_its_column,
             test_arithmetic_on_a_variable_is_elementwise,
             test_known_functions_match_numpy,
             test_precedence_matches_python,
             test_unknown_variable_raises_not_silently_zero]
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
