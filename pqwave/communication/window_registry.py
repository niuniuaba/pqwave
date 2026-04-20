#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Window registry for xschem integration.

This module provides a singleton registry that tracks open pqwave windows,
allowing xschem commands to be routed to the appropriate window based on
raw file path or window ID.
"""

import logging
import weakref
from typing import Optional, Dict, List, Any
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class WindowRegistry(QObject):
    """
    Singleton registry for tracking open pqwave windows.

    Maps window IDs to window instances (weak references) and provides
    lookup by raw file path. Also manages mapping between client connections
    and windows.

    Signals:
        window_registered: Emitted when a window is registered
        window_unregistered: Emitted when a window is unregistered
    """

    _instance: Optional['WindowRegistry'] = None

    # Qt signals
    window_registered = pyqtSignal(str, object)  # window_id, window_ref
    window_unregistered = pyqtSignal(str)        # window_id

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize registry data structures."""
        # window_id -> weak reference to MainWindow
        self._windows: Dict[str, weakref.ReferenceType] = {}
        # raw_file_path -> window_id (first window that opened the file)
        self._raw_file_to_window: Dict[str, str] = {}
        # client_addr -> window_id (active window for this connection)
        self._client_to_window: Dict[str, str] = {}

    def register_window(self, window_id: str, window_instance: Any,
                        raw_file_path: Optional[str] = None) -> None:
        """
        Register a window with the registry.

        Args:
            window_id: Unique identifier for the window
            window_instance: MainWindow instance (will be stored as weakref)
            raw_file_path: Optional raw file path associated with the window
        """
        # Store weak reference
        self._windows[window_id] = weakref.ref(window_instance)

        # Map raw file path to window (if provided)
        if raw_file_path:
            # Only map if not already mapped (first window wins)
            if raw_file_path not in self._raw_file_to_window:
                self._raw_file_to_window[raw_file_path] = window_id
                logger.debug(f"Mapped raw file {raw_file_path} to window {window_id}")
            else:
                logger.debug(f"Raw file {raw_file_path} already mapped to window {self._raw_file_to_window[raw_file_path]}")

        logger.info(f"Registered window {window_id}")
        self.window_registered.emit(window_id, window_instance)

    def unregister_window(self, window_id: str) -> None:
        """Unregister a window and clean up all mappings."""
        if window_id not in self._windows:
            return

        # Remove raw file mappings that point to this window
        raw_files_to_remove = []
        for raw_file, win_id in self._raw_file_to_window.items():
            if win_id == window_id:
                raw_files_to_remove.append(raw_file)
        for raw_file in raw_files_to_remove:
            del self._raw_file_to_window[raw_file]

        # Remove client mappings that point to this window
        clients_to_remove = []
        for client_addr, win_id in self._client_to_window.items():
            if win_id == window_id:
                clients_to_remove.append(client_addr)
        for client_addr in clients_to_remove:
            del self._client_to_window[client_addr]

        del self._windows[window_id]
        logger.info(f"Unregistered window {window_id}")
        self.window_unregistered.emit(window_id)

    def get_window_by_id(self, window_id: str) -> Optional[Any]:
        """
        Get window instance by ID.

        Returns:
            Window instance or None if not found or garbage collected
        """
        if window_id not in self._windows:
            return None
        ref = self._windows[window_id]
        window = ref()
        if window is None:
            # Window was garbage collected, clean up
            self.unregister_window(window_id)
        return window

    def get_window_by_raw_file(self, raw_file_path: str) -> Optional[Any]:
        """
        Get window instance by raw file path.

        Returns:
            Window instance or None if no window mapped to this file
        """
        window_id = self._raw_file_to_window.get(raw_file_path)
        if not window_id:
            return None
        return self.get_window_by_id(window_id)

    def get_window_for_client(self, client_addr: str) -> Optional[Any]:
        """
        Get window instance associated with a client connection.

        Returns:
            Window instance or None if no window assigned
        """
        window_id = self._client_to_window.get(client_addr)
        if not window_id:
            return None
        return self.get_window_by_id(window_id)

    def set_window_for_client(self, client_addr: str, window_id: str) -> None:
        """
        Associate a client connection with a window.

        Args:
            client_addr: Client address string "ip:port"
            window_id: Window ID to associate
        """
        if window_id not in self._windows:
            logger.warning(f"Cannot associate client {client_addr} with unknown window {window_id}")
            return

        self._client_to_window[client_addr] = window_id
        logger.debug(f"Associated client {client_addr} with window {window_id}")

    def remove_client_association(self, client_addr: str) -> None:
        """Remove client-window association."""
        if client_addr in self._client_to_window:
            del self._client_to_window[client_addr]
            logger.debug(f"Removed client association for {client_addr}")

    def get_all_window_ids(self) -> List[str]:
        """Get list of all registered window IDs."""
        return list(self._windows.keys())

    def clear(self) -> None:
        """Clear all registry data (for testing)."""
        self._windows.clear()
        self._raw_file_to_window.clear()
        self._client_to_window.clear()
        logger.debug("Window registry cleared")


# Convenience functions for singleton access
def get_registry() -> WindowRegistry:
    """Get the singleton WindowRegistry instance."""
    return WindowRegistry()