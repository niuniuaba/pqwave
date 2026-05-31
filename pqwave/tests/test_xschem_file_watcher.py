"""Tests for XschemFileWatcher — mtime+size polling watcher."""

import os
import sys
import tempfile

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QSignalSpy

from pqwave.bridge.xschem.file_watcher import XschemFileWatcher

# QApplication required for Qt signal/timer infrastructure
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


class TestXschemFileWatcher:
    def test_watch_emits_signal_on_change(self):
        watcher = XschemFileWatcher()
        spy = QSignalSpy(watcher.file_changed)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sch", delete=False) as f:
            f.write("* test schematic\n")
            tmp_path = f.name

        try:
            watcher.watch(tmp_path)
            # Modify the file, then manually trigger poll to detect change.
            with open(tmp_path, "a") as f:
                f.write("R1 n1 n2 1k\n")
            watcher._poll()
            assert len(spy) >= 1
            assert spy[0][0] == tmp_path
        finally:
            watcher.unwatch()
            os.unlink(tmp_path)

    def test_poll_no_change_does_not_emit(self):
        watcher = XschemFileWatcher()
        spy = QSignalSpy(watcher.file_changed)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sch", delete=False) as f:
            f.write("* test schematic\n")
            tmp_path = f.name

        try:
            watcher.watch(tmp_path)
            watcher._poll()  # no modification — should not emit
            assert len(spy) == 0
        finally:
            watcher.unwatch()
            os.unlink(tmp_path)

    def test_unwatch_stops_signals(self):
        watcher = XschemFileWatcher()
        watcher.watch("/tmp/nonexistent_test_file.sch")
        assert watcher.watched_path is not None
        watcher.unwatch()
        assert watcher.watched_path is None

    def test_watched_path_property(self):
        watcher = XschemFileWatcher()
        assert watcher.watched_path is None
        watcher.watch("/tmp/test.sch")
        assert watcher.watched_path == os.path.abspath("/tmp/test.sch")
        watcher.unwatch()
