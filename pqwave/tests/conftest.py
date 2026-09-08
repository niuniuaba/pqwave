"""Shared test hygiene for the pqwave pytest suite.

Two problems make this suite order-dependent, and both are invisible when each
file is run on its own:

1. Qt lifetime. Tests create top-level widgets and drop them without closing, and
   14 of them constructed a *second* QApplication, which Qt does not allow. The
   second construction tears down the first one's event dispatcher and the process
   died with `Fatal Python error: Segmentation fault` inside
   QWidgetAction::releaseWidget / ~QGuiApplication roughly 12% into a full run.
   Test modules now reuse the instance (see the `QApplication.instance() or ...`
   guard), and this file creates the one canonical QApplication up front.

2. ApplicationState is a process-wide singleton, so datasets, traces and panel
   settings configured by one test leak into the next.
"""

import os
import socket
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

# One QApplication for the whole session, created before any test module is
# imported so that `QApplication.instance()` is never None.
_APP = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(autouse=True)
def _isolate_application_state():
    """Reset the two process-wide singletons around every test.

    ApplicationState is a singleton, so datasets and traces configured by one test
    survive into the next. WindowRegistry is a singleton too, and it keeps
    client-address -> window mappings: that is what made
    `test_command_queuing_and_routing` pass alone but fail in a full run, because
    an earlier test's window had already claimed `127.0.0.1:12345`, so
    `_is_command_for_this_window()` answered "not for you" and the copyvar command
    was dropped instead of queued.

    A full ApplicationState._initialize() is *not* used: several modules build
    state once at import time and legitimately share it across their own tests.
    """
    from pqwave.bridge.xschem.window_registry import WindowRegistry
    from pqwave.models.state import ApplicationState

    def _reset():
        state = ApplicationState()
        state.clear_traces()
        state.clear_datasets()
        WindowRegistry().clear()

    _reset()
    yield
    _reset()


@pytest.fixture(scope="session")
def qapp():
    """The session QApplication (mirrors the pytest-qt name)."""
    return _APP


@pytest.fixture(scope="session")
def repo_root():
    """Absolute path to the repository root (parent of pqwave/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def bridge_raw(repo_root):
    """The primary raw-data fixture, or a skip if it is unavailable.

    Fixtures under tests/ are git-ignored (tests/*.*), so a fresh clone has none
    of them; skip loudly rather than failing with a FileNotFoundError that looks
    like a product bug.
    """
    path = os.path.join(repo_root, "tests", "bridge.raw")
    if not os.path.exists(path):
        pytest.skip(f"untracked local fixture missing: {path}")
    return path


def _loopback_bind_allowed() -> bool:
    """Can this process bind a TCP socket on loopback at all?

    Sandboxed runners commonly deny socket creation/bind with EPERM. The xschem
    and Lepton bridges are TCP servers, so their tests are not runnable there --
    and because WaveReceiver.start() reports bind failures by returning False,
    the assertion failure looks like a product bug rather than a missing
    capability. Probe once and let tests skip with an explicit reason instead.
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False
    finally:
        if sock is not None:
            sock.close()


LOOPBACK_OK = _loopback_bind_allowed()


@pytest.fixture()
def require_loopback():
    """Skip a test that needs to bind or connect a TCP socket."""
    if not LOOPBACK_OK:
        pytest.skip(
            "loopback TCP bind is denied in this environment; the xschem/Lepton "
            "bridge tests need it (run outside the sandbox to exercise them)")


def fixture_path(relative: str) -> str:
    """Absolute path to a file under the repo-root tests/ data directory.

    Raises pytest's skip if the file is absent: the larger performance captures
    (rc_100M.raw, rc_500M.raw, SMPS.qraw) stay git-ignored, so a fresh clone has
    only the handful of fixtures listed in .gitignore. A missing data file is not
    a product failure and must not be reported as one.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, relative)
    if not os.path.exists(path):
        pytest.skip(f"test data not present in this checkout: {relative}")
    return path
