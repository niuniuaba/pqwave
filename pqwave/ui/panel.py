#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Panel - Self-contained plot panel bundling PlotWidget, TraceManager, and AxisManager.

Each Panel owns its own PlotWidget, Legend, TraceManager, and AxisManager.
Panels are managed by PanelGrid and emit panel_clicked when the user interacts
with the plot area.
"""

import uuid
from typing import Optional

import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal

from pqwave.models.state import ApplicationState
from pqwave.ui.plot_widget import PlotWidget
from pqwave.ui.trace_manager import TraceManager, SelectableItemSample
from pqwave.ui.axis_manager import AxisManager
from pqwave.utils.colors import ColorManager


class Panel(QWidget):
    """Self-contained plot panel with its own PlotWidget, TraceManager, and AxisManager."""

    panel_clicked = pyqtSignal(str)

    def __init__(
        self,
        application_state: ApplicationState,
        color_manager: Optional[ColorManager] = None,
        parent: Optional[QWidget] = None,
        panel_id: Optional[str] = None,
    ):
        super().__init__(parent)
        self.panel_id = panel_id or str(uuid.uuid4())
        self.state = application_state
        self._color_manager = color_manager or ColorManager()
        self._domain: str = "time"
        self._active: bool = False

        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Plot widget
        self.plot_widget = PlotWidget()
        self._layout.addWidget(self.plot_widget)

        # Legend (uses SelectableItemSample for trace click-to-select)
        self.legend = self.plot_widget.addLegend(sampleType=SelectableItemSample)

        # Axis manager (per-panel axis state)
        self.axis_manager = AxisManager(self.plot_widget, self.state)

        # Trace manager (per-panel trace state)
        self.trace_manager = TraceManager(
            plot_widget=self.plot_widget,
            legend=self.legend,
            application_state=self.state,
            color_manager=self._color_manager,
        )

        # Track mouse press for active-panel tracking
        self.plot_widget.scene().sigMouseClicked.connect(self._on_plot_clicked)

    def _on_plot_clicked(self, event):
        """Emit panel_clicked when the user clicks anywhere in the plot area."""
        # Only emit on mouse press (not release), and only if the click originated
        # within this panel's plot widget viewbox
        if event.double():
            return
        # Check if click target is within our viewbox
        vb = self.plot_widget.plotItem.vb
        if vb.sceneBoundingRect().contains(event.scenePos()):
            self.panel_clicked.emit(self.panel_id)

    # --- Domain ---

    @property
    def domain(self) -> str:
        return self._domain

    @domain.setter
    def domain(self, value: str) -> None:
        self._domain = value

    # --- Active state ---

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        """Update the panel's active visual state."""
        self._active = active
        if active:
            self.setStyleSheet(
                "Panel { border: 1px solid #4A90D9; }"
            )
        else:
            self.setStyleSheet("")

    # --- Component accessors ---

    def get_plot_widget(self) -> PlotWidget:
        return self.plot_widget

    def get_trace_manager(self) -> TraceManager:
        return self.trace_manager

    def get_axis_manager(self) -> AxisManager:
        return self.axis_manager

    def get_legend(self) -> pg.LegendItem:
        return self.legend
