#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PanelGrid - QSplitter-based multi-panel container.

Manages a recursive QSplitter tree of Panel widgets, supporting split/close
operations with a maximum of 4 panels (2x2 grid). Tracks the active panel
(last-clicked) and emits signals for panel lifecycle events.
"""

import uuid
from typing import Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter

from pqwave.models.state import ApplicationState
from pqwave.ui.panel import Panel
from pqwave.utils.colors import ColorManager


class PanelGrid(QWidget):
    """QSplitter-based multi-panel container with active-panel tracking."""

    MAX_PANELS = 4

    panel_activated = pyqtSignal(str)
    panel_closed = pyqtSignal(str)

    def __init__(
        self,
        application_state: ApplicationState,
        color_manager: Optional[ColorManager] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.state = application_state
        self._color_manager = color_manager or ColorManager()
        self._panels: Dict[str, Panel] = {}
        self._active_panel_id: str = ""

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._create_initial_panel()

    # --- Initialization ---

    def _create_initial_panel(self) -> None:
        panel_id = str(uuid.uuid4())
        self.state.register_panel(panel_id)
        panel = Panel(self.state, self._color_manager, self, panel_id=panel_id)
        self._panels[panel.panel_id] = panel
        self._active_panel_id = panel.panel_id
        panel.panel_clicked.connect(self._on_panel_clicked)
        panel.set_active(True)
        self._layout.addWidget(panel)

    # --- Active panel ---

    def _on_panel_clicked(self, panel_id: str) -> None:
        if panel_id == self._active_panel_id:
            return
        if self._active_panel_id in self._panels:
            self._panels[self._active_panel_id].set_active(False)
        self._active_panel_id = panel_id
        self.state.active_panel_id = panel_id
        if panel_id in self._panels:
            self._panels[panel_id].set_active(True)
        self.panel_activated.emit(panel_id)

    def set_active_panel_id(self, panel_id: str) -> None:
        """Set active panel without emitting panel_activated signal.

        Used during state restoration where the signal would fire
        on a partially-configured panel.
        """
        self._active_panel_id = panel_id

    def get_active_panel(self) -> Optional[Panel]:
        return self._panels.get(self._active_panel_id)

    @property
    def active_panel_id(self) -> str:
        return self._active_panel_id

    # --- Panel access ---

    def get_panel(self, panel_id: str) -> Optional[Panel]:
        return self._panels.get(panel_id)

    @property
    def panels(self) -> Dict[str, Panel]:
        return dict(self._panels)

    @property
    def panel_count(self) -> int:
        return len(self._panels)

    # --- Split ---

    def split_panel(
        self, panel_id: str, orientation: str = "vertical"
    ) -> Optional[Panel]:
        """Split a panel into two, creating and returning a new Panel.

        orientation: "vertical" (stacked) or "horizontal" (side-by-side).
        Returns None if max panels reached or panel_id not found.
        """
        if self.panel_count >= self.MAX_PANELS:
            return None

        panel = self._panels.get(panel_id)
        if panel is None:
            return None

        new_panel_id = str(uuid.uuid4())
        self.state.register_panel(new_panel_id, copy_from=panel_id)
        new_panel = Panel(self.state, self._color_manager, self, panel_id=new_panel_id)
        self._panels[new_panel.panel_id] = new_panel
        new_panel.panel_clicked.connect(self._on_panel_clicked)

        # Propagate raw_file and current_dataset from source panel so the
        # new panel can evaluate expressions immediately.
        src_raw_file = panel.trace_manager.raw_file
        if src_raw_file is not None:
            new_panel.trace_manager.set_raw_file(src_raw_file)
            new_panel.trace_manager.set_current_dataset(
                panel.trace_manager.current_dataset
            )

        splitter = QSplitter()
        splitter.setOrientation(
            Qt.Orientation.Vertical
            if orientation == "vertical"
            else Qt.Orientation.Horizontal
        )

        total = panel.height() if orientation == "vertical" else panel.width()
        parent_splitter = panel.parentWidget()
        saved_sizes = None
        if isinstance(parent_splitter, QSplitter):
            saved_sizes = parent_splitter.sizes()

        self._replace_in_parent(panel, splitter)
        splitter.addWidget(panel)
        splitter.addWidget(new_panel)
        half = max(total // 2, 50)
        splitter.setSizes([half, half])

        if saved_sizes is not None:
            splitter.parentWidget().setSizes(saved_sizes)

        self._on_panel_clicked(new_panel.panel_id)
        return new_panel

    # --- Close ---

    def close_panel(self, panel_id: str) -> bool:
        """Close a panel. Returns False if it's the last remaining panel."""
        if self.panel_count <= 1:
            return False

        panel = self._panels.pop(panel_id, None)
        if panel is None:
            return False

        # Unregister from state before Qt cleanup so state stays consistent
        # even if disconnect() or reparenting raises.
        self.state.unregister_panel(panel_id)

        try:
            panel.panel_clicked.disconnect(self._on_panel_clicked)
        except TypeError:
            pass  # already disconnected

        parent = panel.parentWidget()

        if isinstance(parent, QSplitter):
            panel.setParent(None)
            if parent.count() == 1:
                remaining = parent.widget(0)
                self._replace_in_parent(parent, remaining)
                parent.setParent(None)
            elif parent.count() == 0:
                self._replace_in_parent(parent, None)
                parent.setParent(None)
        else:
            self._layout.removeWidget(panel)
            panel.setParent(None)

        if panel_id == self._active_panel_id:
            new_active = next(iter(self._panels.keys()))
            self._active_panel_id = new_active
            self.state.active_panel_id = new_active
            if new_active in self._panels:
                self._panels[new_active].set_active(True)

        self.panel_closed.emit(panel_id)
        return True

    # --- Internal helpers ---

    def _replace_in_parent(
        self, old_widget: QWidget, new_widget: Optional[QWidget]
    ) -> None:
        """Replace old_widget with new_widget in the widget tree.

        Handles widgets directly in our layout or nested inside QSplitters.
        If new_widget is None, old_widget is simply removed.
        """
        idx = self._layout.indexOf(old_widget)
        if idx >= 0:
            self._layout.removeWidget(old_widget)
            old_widget.setParent(None)
            if new_widget is not None:
                self._layout.insertWidget(idx, new_widget)
            return

        parent = old_widget.parentWidget()
        if isinstance(parent, QSplitter):
            idx = parent.indexOf(old_widget)
            if idx >= 0:
                old_widget.setParent(None)
                if new_widget is not None:
                    parent.insertWidget(idx, new_widget)
