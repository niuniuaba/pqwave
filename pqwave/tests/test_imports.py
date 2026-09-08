#!/usr/bin/env python3
"""Import surface of the restructured pqwave package.

The original script wrapped every import in try/except that only printed, so a
broken import could never fail it. Each import below is now a real test.
"""

import importlib
import os
import sys

import pqwave  # noqa: E402  (imported for version assertion)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (module path, attribute that must exist in it)
IMPORTS = [
    ("pqwave", "__version__"),
    ("pqwave", "__author__"),
    ("pqwave.models.rawfile", "RawFile"),
    ("pqwave.models.dataset", "Dataset"),
    ("pqwave.models.expression", "ExprEvaluator"),
    ("pqwave.models.trace", "Trace"),
    ("pqwave.models.state", "ApplicationState"),
    ("pqwave.ui.main_window", "MainWindow"),
    ("pqwave.ui.plot_widget", "PlotWidget"),
    ("pqwave.ui.control_panel", "ControlPanel"),
    ("pqwave.ui.trace_manager", "TraceManager"),
    ("pqwave.ui.axis_manager", "AxisManager"),
    ("pqwave.ui.menu_manager", "MenuManager"),
    ("pqwave.utils.colors", "ColorManager"),
    ("pqwave.utils.log_axis", "LogAxisItem"),
]

def test_package_metadata():
    assert isinstance(pqwave.__version__, str) and pqwave.__version__
    assert isinstance(pqwave.__author__, str) and pqwave.__author__


def test_version_matches_installed_metadata():
    """Source version must not drift from the installed distribution metadata.

    The version string used to live in four unsynchronised places, so `pqwave
    --version`, `pqwave.__version__` and the package metadata disagreed.
    """
    from importlib.metadata import PackageNotFoundError, version as dist_version
    import pytest

    try:
        dist = dist_version("pqwave")
    except PackageNotFoundError:
        pytest.skip("pqwave is not installed as a distribution")
    assert pqwave.__version__ == dist, (
        f"pqwave.__version__={pqwave.__version__} but the installed "
        f"distribution reports {dist} -- re-run 'make dev-install'")


def test_all_public_imports_resolve():
    """Every documented public import must resolve to a real attribute."""
    failed = []
    for module_path, attr in IMPORTS:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            failed.append(f"{module_path} (import: {exc})")
            continue
        if not hasattr(mod, attr):
            failed.append(f"{module_path}.{attr} (missing)")
    assert not failed, "broken public imports:\n  " + "\n  ".join(failed)


def test_top_level_package_reexports():
    """`from pqwave import X` must work for the documented public names."""
    import pqwave
    for name in ("RawFile", "ExprEvaluator", "MainWindow", "SessionAPI",
                 "api_command", "get_command_registry"):
        assert hasattr(pqwave, name), f"pqwave.{name} is not exported"


def test_measure_engine_is_importable_cold():
    """`import pqwave.measure.measure_engine` must work as the first import.

    It previously failed: measure_engine pulls in pqwave.ui.measure_registry, and
    pqwave/ui/__init__.py eagerly imported MainWindow, whose own
    `from pqwave.measure.measure_engine import ...` hit the half-initialised
    module. Run it in a clean interpreter so an already-loaded pqwave.ui cannot
    mask the cycle.
    """
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-c",
         "import pqwave.measure.measure_engine"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert proc.returncode == 0, (
        f"cold import of measure_engine failed:\n{proc.stderr[-800:]}")
