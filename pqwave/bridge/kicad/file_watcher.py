"""File watcher for .kicad_sch files — polls mtime, handles atomic saves."""

import os
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class KiCadFileWatcher(QObject):
    """Watch a single .kicad_sch file for changes via mtime polling.

    QFileSystemWatcher does not reliably detect KiCad's atomic save (rename
    temp over target), so we poll mtime every second instead.

    Signals:
        file_changed(str): emitted with the watched file path on save
    """

    file_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._watched_path: str | None = None
        self._last_mtime: float = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._miss_count = 0

    def watch(self, path: str) -> None:
        """Start polling a .kicad_sch file for mtime changes."""
        self._watched_path = os.path.abspath(path)
        self._miss_count = 0
        try:
            self._last_mtime = os.path.getmtime(self._watched_path)
        except OSError:
            self._last_mtime = 0
        self._timer.start(1000)

    def unwatch(self) -> None:
        """Stop polling."""
        self._timer.stop()
        self._watched_path = None
        self._last_mtime = 0

    @property
    def watched_path(self) -> str | None:
        return self._watched_path

    def _poll(self):
        if not self._watched_path:
            return
        try:
            mtime = os.path.getmtime(self._watched_path)
        except OSError:
            self._miss_count += 1
            if self._miss_count > 10:
                self._timer.stop()
            return

        self._miss_count = 0
        if mtime != self._last_mtime:
            self._last_mtime = mtime
            self.file_changed.emit(self._watched_path)
