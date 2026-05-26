"""QFileSystemWatcher wrapper for .kicad_sch files."""

import os
from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal


class KiCadFileWatcher(QObject):
    """Watch a single .kicad_sch file for changes.

    Handles KiCad's atomic save pattern (delete -> write new -> rename).
    Emits file_changed(str) when the file is modified.

    Signals:
        file_changed(str): emitted with the watched file path on save
    """

    file_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._watcher = QFileSystemWatcher()
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watched_path: str | None = None
        self._rewatch_timer = QTimer()
        self._rewatch_timer.setSingleShot(True)
        self._rewatch_timer.timeout.connect(self._rewatch)

    def watch(self, path: str) -> None:
        """Start watching a .kicad_sch file."""
        if self._watched_path:
            self._watcher.removePath(self._watched_path)
        self._watched_path = os.path.abspath(path)
        self._watcher.addPath(self._watched_path)

    def unwatch(self) -> None:
        """Stop watching."""
        if self._watched_path:
            if self._watched_path in self._watcher.files():
                self._watcher.removePath(self._watched_path)
            self._watched_path = None

    @property
    def watched_path(self) -> str | None:
        return self._watched_path

    def _on_file_changed(self, path: str):
        if not os.path.exists(path):
            self._rewatch_timer.start(200)
            return
        self.file_changed.emit(path)

    def _rewatch(self):
        if self._watched_path and os.path.exists(self._watched_path):
            if self._watched_path not in self._watcher.files():
                self._watcher.addPath(self._watched_path)
            self.file_changed.emit(self._watched_path)
