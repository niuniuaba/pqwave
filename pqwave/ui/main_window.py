#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MainWindow - Main application window orchestrating all UI components.

This module provides the MainWindow class that composes all modular UI components
(MenuManager, ControlPanel, PlotWidget, TraceManager, AxisManager) and integrates
them with the ApplicationState singleton.
"""

import sys
import time
import os
import re
import traceback
import json
import socket
from typing import Optional, Tuple
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
    QDialog, QCheckBox, QDialogButtonBox, QLabel, QApplication, QSplitter,
)
from PyQt6.QtCore import Qt as QtCore_Qt
from PyQt6.QtCore import QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont

from pqwave.models.state import ApplicationState, AxisId, ViewboxTheme, FontConfig, AxisConfig
from pqwave.models.rawfile import RawFile
from pqwave.models.raw_converter import write_raw_file, write_vcd_file, FORMAT_CONFIG, extract_traces_to_raw
from pqwave.models.dataset import Dataset
from pqwave.models.trace import AxisAssignment
from pqwave.ui.menu_manager import MenuManager
from pqwave.ui.control_panel import ControlPanel
from pqwave.ui.mc_control_bar import MCControlBar
from pqwave.ui.plot_widget import PlotWidget
from pqwave.ui.trace_manager import TraceManager, SelectableItemSample
from pqwave.ui.settings_widget import SettingsWidget
from pqwave.ui.axis_manager import AxisManager
from pqwave.ui.panel_grid import PanelGrid
from pqwave.ui.mark_panel import MarkPanel
from pqwave.utils.colors import ColorManager
from pqwave.logging_config import get_logger
from pqwave.communication.window_registry import get_registry
from pqwave.ui.keybinding_manager import KeyBindingManager
from pqwave.ui.keybindings_dialog import KeyBindingsDialog
from pqwave.ui.functions_help_dialog import FunctionsHelpDialog
from pqwave.ui.measures_help_dialog import MeasuresHelpDialog
from pqwave.ui.measure_results_widget import MeasureResultsWidget
from pqwave.ui.power_analysis_dialog import PowerAnalysisDialog
from pqwave.measure.measure_engine import evaluate_measure
from pqwave.measure.measure_script_parser import parse_meas_script
from pqwave.digital.eye_renderer import render_overlay, render_persistence
import uuid


logger = get_logger(__name__)

class MainWindow(QMainWindow):
    """Main application window orchestrating all UI components."""

    # Cross-thread mutation signal: forwards SessionAPI mutation events
    # from background threads (REPL Python mode, XschemServer) to the
    # main thread so Qt GUI operations are always thread-safe.
    _mutation_signal = pyqtSignal(str, object)

    def __init__(self, initial_file=None, xschem_ba_port=2021,
                 initial_files=None):
        """
        Initialize MainWindow.

        Args:
            initial_file: Deprecated; single file path (for backward compat).
            initial_files: Optional list of file paths to open.
            xschem_ba_port: TCP port for xschem back-annotation (xschem_listen_port)
        """
        super().__init__()
        self.setWindowTitle("pqwave - SPICE Waveform Viewer")
        self.setGeometry(100, 100, 1200, 800)

        self.state = ApplicationState()
        self.window_id = str(uuid.uuid4())
        self._xschem_ba_port = xschem_ba_port

        if initial_files is None:
            initial_files = []
        if initial_file is not None and initial_file not in initial_files:
            initial_files.insert(0, initial_file)

        self.raw_file_path = initial_files[0] if initial_files else None
        self.state.window_registry.register_window(
            window_id=self.window_id,
            window_instance=self,
            raw_file_path=self.raw_file_path
        )

        self.initial_files = initial_files
        self._project_path = None  # set when project file is saved/loaded

        # Component references (will be initialized in _setup_ui)
        self.menu_manager = None
        self.panel_grid = None
        self.control_panel = None
        self.color_manager = None
        self._bound_plot_widget: Optional[PlotWidget] = None
        self._bound_axis_manager: Optional[AxisManager] = None
        self._bound_trace_manager = None
        self._cursor_sync_in_progress = False
        self._restoring_state = False

        # Raw file reference
        self.raw_file = None

        # Zoom box state
        self.zoom_box_enabled = False

        # Cross-hair cursor state
        self.cross_hair_visible = False
        self.mark_panel = None
        self._measure_results = None  # lazy-created MeasureResultsWidget

        # Xschem pending commands (when raw_file not yet loaded)
        self.pending_xschem_commands = []  # list of (command_type, args, client_addr, connection_state)

        # Setup UI
        self._setup_ui()

        # Connect signals
        self._connect_signals()

        # Load global preferences (theme) and apply to UI
        self._load_global_prefs()
        self.axis_manager._initialize_axes()
        self.plot_widget.apply_fonts(self.state)
        self._apply_ui_font()

        # Flag to prevent double loading from timer
        self.initial_file_loaded = False

        if self.initial_files:
            QTimer.singleShot(100, self._load_initial_files)

    def _setup_ui(self):
        """Create and arrange UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.color_manager = ColorManager()

        self.panel_grid = PanelGrid(self.state, self.color_manager)
        self.control_panel = ControlPanel()
        self.mc_control_bar = None  # Created when MC data is loaded

        self.keybinding_manager = KeyBindingManager()
        callbacks = self._create_menu_callbacks()
        self.menu_manager = MenuManager(self, callbacks, keybinding_manager=self.keybinding_manager)

        # Upper area: panel + control
        upper = QWidget()
        upper_layout = QVBoxLayout()
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(10)
        upper_layout.addWidget(self.panel_grid, 1)
        upper_layout.addWidget(self.control_panel)
        upper.setLayout(upper_layout)

        # Chat panel (resizable, starts hidden)
        from pqwave.ui.chat_panel import ChatPanel
        from pqwave.ui.repl import ReplExecutor

        self.chat_panel = ChatPanel()
        from pqwave.session.api import SessionAPI
        self._repl = ReplExecutor(session=SessionAPI(state=self.state))
        self._ai_translator = None
        self._connect_chat_panel()

        self.chat_panel.visibility_changed.connect(
            lambda visible: setattr(self.state, 'chat_panel_visible', visible)
        )

        # QSplitter: upper (plots + controls) | chat panel (resizable)
        self._main_splitter = QSplitter(QtCore_Qt.Orientation.Vertical)
        self._main_splitter.addWidget(upper)
        self._main_splitter.addWidget(self.chat_panel)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 0)
        self._main_splitter.setChildrenCollapsible(False)
        self.chat_panel.splitter = self._main_splitter

        main_layout.addWidget(self._main_splitter, 1)

        central_widget.setLayout(main_layout)

        self._update_trace_manager_log_modes()

        self._install_keyboard_shortcuts()

    def _connect_chat_panel(self):
        """Wire chat panel command_submitted to REPL and AI translator."""
        self.chat_panel.command_submitted.connect(self._handle_chat_input)

        # Wire SessionAPI mutations → TraceManager for live plot updates.
        # Use the signal bridge so mutations from any thread (REPL background
        # thread, XschemServer network thread) always land on the main thread.
        self._mutation_signal.connect(self._on_mutation_from_signal)
        self._repl._session.set_mutation_callback(self._on_mutation_bridge)

        self._refresh_completions()
        self.chat_panel.append_output(
            "pqwave REPL — type /ai for AI mode, /help for commands, "
            "/clear to reset\n"
        )

    def _refresh_completions(self):
        """Update autocomplete items: slash commands + API commands + signals + functions."""
        from pqwave.session.api import get_command_registry
        from pqwave.llm.templates import _FUNC_MAP

        items = [
            "/ai", "/python", "/clear", "/help", "/backend", "/test-backend",
            "/remember", "/font", "/promote",
        ]
        for name, entry in get_command_registry().items():
            items.append(name)
        try:
            items.extend(self._repl.signals())
        except Exception:
            logger.warning("Failed to get signals for autocomplete", exc_info=True)
        items.extend(_FUNC_MAP.keys())
        self.chat_panel.set_completions(sorted(set(items)))

    def _on_mutation_bridge(self, action: str, **kwargs):
        """Bridge SessionAPI mutation events from any thread to the main thread.

        Called directly by the SessionAPI's mutation callback (may be on a
        background thread). Emits to our class-level signal — since MainWindow
        lives on the main thread, the connected slot auto-executes there.
        """
        self._mutation_signal.emit(action, kwargs)

    @pyqtSlot(str, object)
    def _on_mutation_from_signal(self, action: str, kwargs: dict):
        """Slot connected to _mutation_signal, always runs on the main thread."""
        self._on_session_mutation(action, **kwargs)

    def _on_session_mutation(self, action: str, **kwargs):
        """Sync SessionAPI mutations to the GUI."""
        tm = self.trace_manager
        pw = self.plot_widget

        if action == "add":
            if tm is None:
                return
            expr = str(kwargs.get("expr", ""))
            axis = str(kwargs.get("axis", "Y1"))
            from pqwave.models.trace import AxisAssignment
            axis_enum = AxisAssignment.Y1 if axis.upper() == "Y1" else AxisAssignment.Y2
            x_var = self.state.current_x_var or "time"
            already_plotted = any(v == expr for v, _, _ in tm.traces)
            result = tm.add_trace(expr, str(x_var), axis_enum)
            if result is None and not already_plotted:
                all_sigs = []
                try:
                    all_sigs = self._repl.signals()
                except Exception:
                    pass
                suggestion = self._fuzzy_signal_match(expr, all_sigs)
                msg = f"Signal not found: {expr}"
                if suggestion:
                    msg += f"\nDid you mean: {suggestion}?"
                self.chat_panel.append_output(msg)

        elif action == "remove":
            if tm is None:
                return
            tm.remove_trace_by_variable_name(str(kwargs.get("expr", "")))

        elif action == "remove_all":
            if tm is None:
                return
            tm.clear_traces()

        elif action == "show_trace":
            if tm is None:
                return
            expr = str(kwargs.get("expr", ""))
            tm.set_trace_visible(expr, True)

        elif action == "hide_trace":
            if tm is None:
                return
            expr = str(kwargs.get("expr", ""))
            tm.set_trace_visible(expr, False)

        elif action == "show_all_traces":
            if tm is None:
                return
            tm.set_all_traces_visible(True)

        elif action == "hide_all_traces":
            if tm is None:
                return
            tm.set_all_traces_visible(False)

        elif action == "load":
            path = str(kwargs.get("path", ""))
            import os
            if os.path.exists(path):
                ext = os.path.splitext(path)[1].lower()
                if ext.endswith(".vcd"):
                    self._load_vcd(path, vcd_only=(self.raw_file is None))
                else:
                    self._load_raw_file(path)
                self._refresh_completions()

        elif action == "range":
            if pw is None:
                return
            from pqwave.measure.measure_engine import _parse_value
            xmin = kwargs.get("xmin")
            xmax = kwargs.get("xmax")
            ymin = kwargs.get("ymin")
            ymax = kwargs.get("ymax")

            def _to_float(v):
                if v is None:
                    return None
                if isinstance(v, (int, float)):
                    return float(v)
                try:
                    return _parse_value(str(v))
                except (ValueError, AttributeError):
                    return float(v)

            if xmin is not None or xmax is not None:
                cur = pw.getAxis("bottom").range
                lo = _to_float(xmin) if xmin is not None else cur[0]
                hi = _to_float(xmax) if xmax is not None else cur[1]
                pw.setXRange(lo, hi, padding=0)
            if ymin is not None or ymax is not None:
                cur = pw.getAxis("left").range
                lo = _to_float(ymin) if ymin is not None else cur[0]
                hi = _to_float(ymax) if ymax is not None else cur[1]
                pw.setYRange(lo, hi, padding=0)

        elif action == "log_x":
            on = bool(kwargs.get("on", True))
            config = self.state.get_axis_config(AxisId.X)
            if config.log_mode != on:
                self._toggle_log_axis(AxisId.X)

        elif action == "log_y":
            on = bool(kwargs.get("on", True))
            config = self.state.get_axis_config(AxisId.Y1)
            if config.log_mode != on:
                self._toggle_log_axis(AxisId.Y1)

        # ---- Cursor operations ----

        elif action == "cursor_xa":
            if pw is None: return
            pw.set_cursor_xa_visible(True, kwargs.get("value"))

        elif action == "cursor_xb":
            if pw is None: return
            pw.set_cursor_xb_visible(True, kwargs.get("value"))

        elif action == "cursor_ya":
            if pw is None: return
            pw.set_cursor_yA_visible(True, kwargs.get("value"))

        elif action == "cursor_yb":
            if pw is None: return
            pw.set_cursor_yB_visible(True, kwargs.get("value"))

        elif action == "cursor_delta":
            if pw:
                deltas = pw.get_cursor_deltas()
                self.chat_panel.append_result(deltas)

        elif action == "cursor":
            if pw:
                pos = pw.get_cursor_positions()
                deltas = pw.get_cursor_deltas()
                self.chat_panel.append_result({**pos, **deltas})

        # ---- View toggles ----

        elif action == "grid":
            on = kwargs.get("on")
            if on is None:
                self.toggle_grids()
            elif on and not self.state.grid_visible:
                self.toggle_grids()
            elif not on and self.state.grid_visible:
                self.toggle_grids()

        elif action == "legend":
            on = kwargs.get("on")
            if on is None:
                self.set_legend_visible(not self.state.legend_visible)
            else:
                self.set_legend_visible(on)

        elif action == "cross_hair":
            on = kwargs.get("on")
            if on is not None:
                pw.set_cross_hair_visible(on)
            else:
                self.toggle_cross_hair()

        elif action == "zoom_fit":
            self.zoom_to_fit()

        elif action == "auto_range_x":
            self.auto_range_x()

        elif action == "auto_range_y":
            self.auto_range_y()

        elif action == "title":
            text = kwargs.get("text", "")
            self.plot_widget.setTitle(text)

        # ---- Bus / Digital ----

        elif action == "bus":
            signals = kwargs.get("signals", [])
            tm = self.trace_manager
            if tm and signals:
                # Multi-select matching traces (select_trace deselects others)
                signal_set = set(signals)
                tm.deselect_all()
                for i, trace in enumerate(tm._state_traces):
                    if trace.expression in signal_set:
                        trace.selected = True
                tm.group_selected_as_bus()

        elif action == "expand":
            name = kwargs.get("name", "")
            if self.trace_manager:
                self.trace_manager.expand_bus(bus_trace_name=name)

        elif action == "collapse":
            name = kwargs.get("name", "")
            if self.trace_manager:
                self.trace_manager.collapse_bus(bus_trace_name=name)

        elif action == "set_trace":
            self._set_trace_properties(
                name=str(kwargs.get("name", "")),
                height=kwargs.get("height"),
                width=kwargs.get("width"),
                color=kwargs.get("color"),
                alias=kwargs.get("alias"),
            )

        elif action == "digital":
            sig = kwargs.get("sig", "")
            on = kwargs.get("on", True)
            tm = self.trace_manager
            if tm:
                # Select the trace by name, then toggle its type
                for i, (var, _, _) in enumerate(tm.traces):
                    if var == sig:
                        tm.select_trace(i)
                        tm.toggle_trace_type()
                        break

        # ---- Cursor visibility ----

        elif action == "cursor_xa_visible":
            on = kwargs.get("on", True)
            if on is None:
                on = not pw.cursor_xa_visible
            pw.set_cursor_xa_visible(on)

        elif action == "cursor_xb_visible":
            on = kwargs.get("on", True)
            if on is None:
                on = not pw.cursor_xb_visible
            pw.set_cursor_xb_visible(on)

        elif action == "cursor_ya_visible":
            on = kwargs.get("on", True)
            if on is None:
                on = not pw.cursor_yA_visible
            pw.set_cursor_yA_visible(on)

        elif action == "cursor_yb_visible":
            on = kwargs.get("on", True)
            if on is None:
                on = not pw.cursor_yB_visible
            pw.set_cursor_yB_visible(on)

        # ---- Eye diagram ----

        elif action == "eye":
            sig = str(kwargs.get("sig", ""))
            period = kwargs.get("period")
            if period:
                from pqwave.measure.measure_engine import _parse_value
                t_period = _parse_value(str(period))
                self.state.eye_diagram_config.period = t_period
            # Show the signal if not already a trace, then select it
            tm = self.trace_manager
            if tm and sig:
                # Add the trace if not present
                found = False
                for i, (var, _, _) in enumerate(tm.traces):
                    if var == sig:
                        tm.deselect_all()
                        tm._state_traces[i].selected = True
                        found = True
                        break
                if not found:
                    self._on_session_mutation("add", expr=sig)
                    for i, (var, _, _) in enumerate(tm.traces):
                        if var == sig:
                            tm.deselect_all()
                            tm._state_traces[i].selected = True
                            found = True
                            break
                if found:
                    self._show_eye_diagram()

        # ---- Reload ----

        elif action == "reload":
            if self.raw_file_path:
                self._load_raw_file(self.raw_file_path)

        # ---- Export ----

        elif action == "export_plot":
            path = str(kwargs.get("path", ""))
            panel = self.panel_grid.get_active_panel()
            if panel and path:
                import pyqtgraph.exporters as exp
                pw = panel.plot_widget
                plot_item = pw.plotItem
                exporter = exp.ImageExporter(plot_item)
                exporter.export(path)

        # ---- Theme ----

        elif action == "theme":
            name = str(kwargs.get("name", "")).lower()
            from pqwave.models.state import ViewboxTheme
            if name in ("dark", "light"):
                self.state.viewbox_theme = ViewboxTheme(name)
                self.plot_widget.set_viewbox_theme(self.state.viewbox_theme)

        # ---- X-axis variable ----

        elif action == "change_x":
            var = str(kwargs.get("var", ""))
            tm = self.trace_manager
            if var and tm:
                self.state.current_x_var = var
                self.axis_manager.set_axis_label(AxisId.X, var)
                tm.update_x_variable(var)

        # ---- Zoom ----

        elif action == "zoom_in":
            self.zoom_in()

        elif action == "zoom_out":
            self.zoom_out()

        # ---- Panel management ----

        elif action == "split_horizontal":
            panel = self.panel_grid.get_active_panel()
            if panel:
                self.panel_grid.split_panel(panel.panel_id, "horizontal")

        elif action == "split_vertical":
            panel = self.panel_grid.get_active_panel()
            if panel:
                self.panel_grid.split_panel(panel.panel_id, "vertical")

        elif action == "close_panel":
            self._close_active_panel()

        elif action == "mc_group":
            mc = self.state.mc_collection
            if mc is not None:
                signal = kwargs.get("signal", "")
                pattern = kwargs.get("pattern")
                if pattern:
                    from pqwave.models.rawfile import detect_naming_pattern
                    from pqwave.models.mc_collection import MCRun
                    if self.raw_file is not None:
                        names = self.raw_file.get_trace_names()
                        groups = detect_naming_pattern(names)
                        if signal in groups:
                            mc.runs = [MCRun(dataset_idx=0, step_index=i)
                                       for i in range(groups[signal]["count"])]
                            self._update_mc_control_display()
                            for panel in self.panel_grid.panels.values():
                                panel.trace_manager.rebuild_from_state()

        elif action == "mc_ungroup":
            self.state.mc_collection = None
            if self.mc_control_bar is not None:
                self.mc_control_bar.setVisible(False)
            for panel in self.panel_grid.panels.values():
                panel.trace_manager.rebuild_from_state()

        elif action == "mc_correlation":
            self._on_mc_correlation()
        elif action == "mc_correlation_load":
            from pqwave.models.mc_collection import CorrelationMatrix
            import csv
            mc = self.state.mc_collection
            if mc is None:
                return
            path = kwargs.get("path", "")
            with open(path, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
            headers = rows[0][1:]
            n = len(headers)
            flat = []
            for r in range(n):
                for c in range(n):
                    try:
                        flat.append(float(rows[r + 1][c + 1]))
                    except (IndexError, ValueError):
                        flat.append(0.0 if r != c else 1.0)
            mc._correlation = CorrelationMatrix(params=headers, matrix=flat)
        elif action == "mc_generate":
            from pqwave.session.api import _mc_generate_core
            _mc_generate_core(
                self.state,
                kwargs.get("output_path", ""),
                kwargs.get("output_format", "csv"),
                kwargs.get("runs", 100),
                kwargs.get("seed"),
                kwargs.get("nominals"),
                kwargs.get("sigmas"),
            )

    def _update_mc_control_display(self):
        """Refresh MC control bar from current collection state."""
        mc = self.state.mc_collection
        if mc is None or self.mc_control_bar is None:
            return
        self.mc_control_bar.setVisible(True)
        self.mc_control_bar.set_run_count(len(mc.runs))
        self.mc_control_bar.set_nominal(mc.nominal_index)
        self.mc_control_bar.set_display_mode(mc.display_mode)

    def _get_ai_translator(self):
        """Lazy-init the AI translator on first AI mode use."""
        if self._ai_translator is None:
            from pqwave.llm.translator import AITranslator
            self._ai_translator = AITranslator()
        return self._ai_translator

    def _handle_chat_input(self, text: str):
        """Route chat input to Python REPL or AI translator based on mode."""
        if text.startswith("/"):
            self._handle_meta(text)
            return

        if self.chat_panel.mode == "ai":
            translator = self._get_ai_translator()
            if not translator.is_configured:
                self.chat_panel.append_output(
                    "No AI backend configured. "
                    "Run pqwave --setup-llm or click the gear icon.\n"
                )
                return

            self.chat_panel.append_output("-- Translating...\n")
            try:
                code = translator.translate(text)
                timing = translator.last_timing
                if timing:
                    ms = timing.get("elapsed_ms", 0)
                    backend = timing.get("backend", "?")
                    pt = timing.get("prompt_tokens")
                    ct = timing.get("completion_tokens")
                    if backend == "template":
                        self.chat_panel.append_output(
                            f"  [{backend}] {ms:.0f}ms → {code}\n"
                        )
                    else:
                        if pt and ct:
                            self.chat_panel.append_output(
                                f"  [{backend}] {ms:.0f}ms, "
                                f"{pt}+{ct} tok ({(pt+ct)/max(ms/1000,0.001):.0f} tok/s)"
                                f" → {code}\n"
                            )
                        else:
                            self.chat_panel.append_output(
                                f"  [{backend}] {ms:.0f}ms → {code}\n"
                            )
                        # Show /remember hint for LLM translations
                        n = translator.log_count()
                        self.chat_panel.append_output(
                            f"     [/remember to save ({n} pattern(s) pending)]\n"
                        )
                else:
                    self.chat_panel.append_output(f"  -> {code}\n")
                result = self._repl.run_sync(code)
                if not result.get("ok"):
                    self.chat_panel.append_output(
                        f"  Error: {result.get('error')}\n"
                    )
                elif "result" in result and result["result"] is not None:
                    self.chat_panel.append_result(result["result"])
            except Exception as e:
                logger.exception("AI translation error")
                self.chat_panel.append_output(f"  AI error: {e}\n")
        else:
            # Python mode: execute in background thread
            thread = self._repl.execute(text)
            thread.result_ready.connect(self.chat_panel.append_result)
            thread.error_occurred.connect(
                lambda err: self.chat_panel.append_output(f"Error: {err}\n")
            )

    def _handle_meta(self, text: str):
        """Handle / slash commands."""
        parts = text.split()
        cmd = parts[0].lower() if parts else ""

        if cmd == "/ai":
            model = self._get_ai_translator().model_name
            self.chat_panel.set_ai_mode(model_name=model)
        elif cmd == "/python":
            self.chat_panel.set_python_mode()
        elif cmd == "/clear":
            self.chat_panel.output.clear()
        elif cmd == "/help":
            from pqwave.session.api import get_command_registry
            registry = get_command_registry()
            lines = ["Available commands:", ""]
            for name, entry in sorted(registry.items()):
                lines.append(f"  {entry['signature']}")
                lines.append(f"    {entry['help']}")
            lines.append("")
            lines.append("Slash commands: /ai, /python, /clear, /help,")
            lines.append("  /backend template on|off, /backend llm on|off,")
            lines.append("  /test-backend, /remember, /promote, /font [8-24],")
            lines.append("  /open <filepath>")
            self.chat_panel.append_output("\n".join(lines) + "\n")

        elif cmd == "/backend":
            translator = self._get_ai_translator()
            sub = parts[1].lower() if len(parts) > 1 else ""
            state = parts[2].lower() if len(parts) > 2 else ""
            on = state in ("on", "true", "1", "enable")

            if sub == "template":
                translator.template_enabled = on
                self.chat_panel.append_output(
                    f"-- Template engine: {'ON' if on else 'OFF'}\n"
                )
            elif sub == "llm":
                translator.llm_enabled = on
                if on:
                    from pqwave.llm.backends import get_active_profile_name, get_profile
                    name = get_active_profile_name()
                    profile = get_profile(name) if name else {}
                    model = (profile or {}).get("model", "?")
                    self.chat_panel.append_output(
                        f"-- LLM backend: ON (profile: {name}, model: {model})\n"
                    )
                else:
                    self.chat_panel.append_output("-- LLM backend: OFF\n")
            else:
                from pqwave.llm.backends import get_active_profile_name, get_profile
                name = get_active_profile_name()
                profile = get_profile(name) if name else {}
                model = (profile or {}).get("model", "?")
                self.chat_panel.append_output(
                    "-- Usage: /backend template on|off  or  "
                    "/backend llm on|off\n"
                    f"-- Template: {'ON' if translator.template_enabled else 'OFF'}"
                    f", LLM: {'ON' if translator.llm_enabled else 'OFF'}"
                )
                if name:
                    self.chat_panel.append_output(
                        f" (profile: {name}, model: {model})\n"
                    )
                else:
                    self.chat_panel.append_output("\n")

        elif cmd == "/open":
            path = " ".join(parts[1:])
            if path:
                self._on_session_mutation("load", path=path)
                self.chat_panel.append_output(f"-- Opening: {path}\n")
            else:
                self.chat_panel.append_output("-- Usage: /open <filepath>\n")

        elif cmd == "/test-backend":
            translator = self._get_ai_translator()
            self.chat_panel.append_output("-- Testing LLM connection...\n")
            try:
                resp = translator.test_llm()
                self.chat_panel.append_output(
                    f"-- OK: {resp[:200]}\n"
                )
            except Exception as e:
                self.chat_panel.append_output(f"-- FAILED: {e}\n")

        elif cmd == "/promote":
            # Copy user templates to project-level templates.yaml
            import yaml
            from pqwave.llm.templates import TemplateEngine
            engine = TemplateEngine()
            user_path = engine._user_path()
            proj_path = engine._project_path()
            try:
                with open(user_path, "r", encoding="utf-8") as f:
                    user_data = yaml.safe_load(f) or {}
            except FileNotFoundError:
                self.chat_panel.append_output("-- No user templates to promote.\n")
                return
            except Exception as e:
                logger.warning("Failed to read user templates: %s", e, exc_info=True)
                self.chat_panel.append_output(
                    f"-- Cannot read user templates: {e}\n")
                return
            user_tmpls = user_data.get("templates", [])
            if not user_tmpls:
                self.chat_panel.append_output("-- No user templates to promote.\n")
                return
            # If project YAML is corrupt, don't overwrite it
            if os.path.exists(proj_path):
                try:
                    with open(proj_path, "r", encoding="utf-8") as f:
                        yaml.safe_load(f)
                except Exception as e:
                    self.chat_panel.append_output(
                        f"-- Project templates file is corrupt: {e}\n"
                        f"-- Fix or remove {proj_path} first.\n")
                    return
            new_count = 0
            for t in user_tmpls:
                if self._write_template_yaml(proj_path, t):
                    new_count += 1
            self.chat_panel.append_output(
                f"-- Promoted {new_count} template(s) to project-level.\n"
                f"-- File: {proj_path}\n"
            )

        elif cmd == "/remember":
            translator = self._get_ai_translator()
            sub = parts[1].lower() if len(parts) > 1 else ""

            if sub == "last":
                tmpl = translator.remember_last()
                if tmpl is None:
                    self.chat_panel.append_output(
                        "-- Nothing to remember. Use LLM first.\n"
                    )
                else:
                    self._save_learned_template(tmpl["match"], tmpl["code"])
                    self.chat_panel.append_output(
                        "-- Remembered.\n"
                    )
            else:
                templates = translator.remember_all()
                if not templates:
                    self.chat_panel.append_output(
                        "-- Nothing new to remember.\n"
                    )
                else:
                    for tmpl in templates:
                        self._save_learned_template(tmpl["match"], tmpl["code"])
                    self.chat_panel.append_output(
                        f"-- Remembered {len(templates)} pattern(s).\n"
                    )

        elif cmd == "/font":
            if len(parts) > 1:
                try:
                    size = int(parts[1])
                    self.chat_panel.set_font_size(size)
                    self.chat_panel.append_output(
                        f"-- Font size: {self.chat_panel._font_size}pt\n"
                    )
                except ValueError:
                    self.chat_panel.append_output(
                        "-- Usage: /font <size>  (8–24)\n"
                    )
            else:
                self.chat_panel.append_output(
                    f"-- Font size: {self.chat_panel._font_size}pt\n"
                )

        else:
            self.chat_panel.append_output(f"Unknown command: {text}\n")

    def _save_learned_template(self, pattern: str, code: str):
        """Save to user templates. Also save to project templates if in a git repo."""
        import os, yaml
        from pqwave.llm.templates import TemplateEngine
        engine = TemplateEngine()
        entry = {"match": pattern, "code": code}

        # Always save to user file
        path = engine.ensure_user_file()
        self._write_template_yaml(path, entry)

        # Also save to project file if running from a git repo
        proj_path = engine._project_path()
        if self._is_in_git_repo(os.path.dirname(proj_path)):
            self._write_template_yaml(proj_path, entry)

    @staticmethod
    def _is_in_git_repo(path: str) -> bool:
        """Check if *path* is inside a git repository."""
        import subprocess
        try:
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=path, capture_output=True, check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def _write_template_yaml(path, entry):
        import os, yaml
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            data = {}
        except Exception as e:
            logger.warning("Failed to read templates from %s: %s", path, e,
                           exc_info=True)
            return
        if "templates" not in data or not data["templates"]:
            data["templates"] = []
        # Don't duplicate
        if entry["match"] not in (t.get("match", "") for t in data["templates"]):
            data["templates"].insert(0, entry)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            return True
        return False

    def _create_menu_callbacks(self):
        """Create callback dictionary for menu manager."""
        return {
            'open_file': self.open_file,
            'open_new_window': self.open_new_window,
            'save_current_state': self.save_current_state,
            'save_project_as': self._save_project_as,
            'save_as_data_file': self.save_as_data_file,
            'export_plot_image': self.export_plot_image,
            'convert_raw_data': self.convert_raw_data,
            'edit_trace_properties': self.edit_trace_properties,
            'show_settings': self.show_settings,
            'toggle_toolbar': self.toggle_toolbar,
            'toggle_statusbar': self.toggle_statusbar,
            'toggle_grids': self.toggle_grids,
            'zoom_in': self.zoom_in,
            'zoom_out': self.zoom_out,
            'zoom_to_fit': self.zoom_to_fit,
            'auto_range_x': self.auto_range_x,
            'auto_range_y': self.auto_range_y,
            'enable_zoom_box': self.enable_zoom_box,
            'zoom_in_toolbar': self.zoom_in,
            'zoom_out_toolbar': self.zoom_out,
            'zoom_to_fit_toolbar': self.zoom_to_fit,
            'auto_range_x_toolbar': self.auto_range_x,
            'auto_range_y_toolbar': self.auto_range_y,
            'zoom_box_toolbar': self.enable_zoom_box,
            'toggle_grids_toolbar': self.toggle_grids,
            'toggle_cross_hair': self.toggle_cross_hair,
            'toggle_cross_hair_toolbar': self.toggle_cross_hair,
            'toggle_x_cursor_a': self._toggle_x_cursor_a,
            'toggle_x_cursor_b': self._toggle_x_cursor_b,
            'toggle_y_cursor_A': self._toggle_y_cursor_A,
            'toggle_y_cursor_B': self._toggle_y_cursor_B,
            'show_keybindings': self._show_keybindings,
            'show_functions_help': self._show_functions_help,
            'show_measures_help': self._show_measures_help,
            'show_vector_selection_help': self._show_vector_selection_help,
            'show_repl_help': self._show_repl_help,
            'show_api_help': self._show_api_help,
            'show_mc_guide': self._show_mc_guide,
            'split_horizontal': self._split_panel_horizontal,
            'split_vertical': self._split_panel_vertical,
            'close_panel': self._close_active_panel,
            'compute_trace_stats': self._compute_trace_stats,
            'compute_power_analysis': self._compute_power_analysis,
            'histogram': self._show_histogram,
            'nyquist': self._show_nyquist,
            'bode': self._show_bode,
            'mc_stats': self._on_mc_stats,
            'mc_histogram': self._on_mc_histogram,
            'mc_yield': self._on_mc_yield,
            'mc_scatter': self._on_mc_scatter,
            'mc_sensitivity': self._on_mc_sensitivity,
            'mc_worst': self._on_mc_worst,
            'mc_correlation': self._on_mc_correlation,
            'toggle_digital_analog': self._toggle_digital_analog,
            'group_bus': self._group_bus,
            'eye_diagram': self._show_eye_diagram,
            'threshold_settings': self._show_threshold_settings,
            'save_template': self._on_save_template,
            'load_template': self._on_load_template,
            'manage_templates': self._on_manage_templates,
            'close_dataset': self._on_close_dataset,
            'open_monte_carlo': self._on_open_monte_carlo,
        }

    # --- Delegate properties (route to active panel) ---

    @property
    def plot_widget(self):
        panel = self.panel_grid.get_active_panel()
        return panel.plot_widget if panel else None

    @property
    def trace_manager(self):
        panel = self.panel_grid.get_active_panel()
        return panel.trace_manager if panel else None

    @property
    def axis_manager(self):
        panel = self.panel_grid.get_active_panel()
        return panel.axis_manager if panel else None

    @property
    def legend(self):
        panel = self.panel_grid.get_active_panel()
        return panel.legend if panel else None

    def _connect_signals(self):
        """Connect signals between components."""
        # Connect control panel signals
        self.control_panel.dataset_changed.connect(self._on_dataset_changed)
        self.control_panel.vector_selected.connect(self._on_vector_selected)
        self.control_panel.add_trace_to_axis.connect(self._on_add_trace_to_axis)
        self.control_panel.expression_changed.connect(self._on_expression_changed)
        self.control_panel.function_selected.connect(self._on_function_selected)
        self.control_panel.measure_selected.connect(self._on_measure_selected)
        self.control_panel.run_measure_requested.connect(self._on_run_measure)
        self.control_panel.from_script_requested.connect(self._on_from_script)

        # Connect panel grid signals
        self.panel_grid.panel_activated.connect(self._on_panel_activated)

        # Bind initial panel's plot and axis signals
        initial_panel = self.panel_grid.get_active_panel()
        if initial_panel:
            self._rebind_panel_signals(initial_panel)

        # Connect xschem integration signals
        self._connect_xschem_signals()

        # Back-annotation debounce timer (avoid sending too many updates)
        self._backannotation_timer = QTimer()
        self._backannotation_timer.setSingleShot(True)
        self._backannotation_timer.setInterval(100)  # 100ms debounce
        self._backannotation_timer.timeout.connect(self._send_data_point_update_debounced)
        self._pending_x_value = None  # X value to send when timer fires

        # Xschem back-annotation timer (separate from the data point update above)
        self._xschem_ba_timer = QTimer()
        self._xschem_ba_timer.setSingleShot(True)
        self._xschem_ba_timer.setInterval(250)  # 250ms debounce
        self._xschem_ba_timer.timeout.connect(self._xschem_ba_debounced)
        self._xschem_ba_x = None  # XB cursor value to send when timer fires

    def _rebind_panel_signals(self, panel):
        """Disconnect old panel signals and connect new panel's signals."""
        # Disconnect old plot widget signals
        if self._bound_plot_widget is not None:
            try:
                self._bound_plot_widget.mouse_moved.disconnect(self._on_mouse_moved)
                self._bound_plot_widget.mouse_left.disconnect(self._on_mouse_left)
                self._bound_plot_widget.cursor_xa_changed.disconnect(self._on_cursor_xa_changed)
                self._bound_plot_widget.cursor_xb_changed.disconnect(self._on_cursor_xb_changed)
                self._bound_plot_widget.cursor_yA_changed.disconnect(self._on_cursor_yA_changed)
                self._bound_plot_widget.cursor_yB_changed.disconnect(self._on_cursor_yB_changed)
                self._bound_plot_widget.cursor_y2_changed.disconnect(self._on_cursor_y2_changed)
                self._bound_plot_widget.axis_log_mode_changed.disconnect(self._on_axis_log_mode_changed)
                self._bound_plot_widget.mark_clicked.disconnect(self._on_mark_clicked)
                self._bound_plot_widget.title_changed.disconnect(self._on_plot_title_changed)
            except (TypeError, RuntimeError):
                pass

        # Disconnect old axis manager signals
        if self._bound_axis_manager is not None:
            try:
                self._bound_axis_manager.axis_log_mode_changed.disconnect(
                    self._on_axis_log_mode_changed_from_manager
                )
                self._bound_axis_manager.axis_range_changed.disconnect(self._on_axis_range_changed)
                self._bound_axis_manager.axis_label_changed.disconnect(self._on_axis_label_changed)
            except (TypeError, RuntimeError):
                pass

        # Connect new plot widget signals
        panel.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        panel.plot_widget.mouse_left.connect(self._on_mouse_left)
        panel.plot_widget.cursor_xa_changed.connect(self._on_cursor_xa_changed)
        panel.plot_widget.cursor_xb_changed.connect(self._on_cursor_xb_changed)
        panel.plot_widget.cursor_yA_changed.connect(self._on_cursor_yA_changed)
        panel.plot_widget.cursor_yB_changed.connect(self._on_cursor_yB_changed)
        panel.plot_widget.cursor_y2_changed.connect(self._on_cursor_y2_changed)
        panel.plot_widget.axis_log_mode_changed.connect(self._on_axis_log_mode_changed)
        panel.plot_widget.mark_clicked.connect(self._on_mark_clicked)
        panel.plot_widget.title_changed.connect(self._on_plot_title_changed)
        # Set callbacks for context menus (avoids signal connection issues)
        panel.plot_widget._context_menu_callback = self._on_plot_context_menu

        # Connect trace manager context menu
        try:
            panel.trace_manager.trace_context_menu_requested.disconnect()
        except (TypeError, RuntimeError):
            pass
        panel.trace_manager.trace_context_menu_requested.connect(
            self._on_trace_context_menu)

        # Connect new axis manager signals
        panel.axis_manager.axis_log_mode_changed.connect(
            self._on_axis_log_mode_changed_from_manager
        )
        panel.axis_manager.axis_range_changed.connect(self._on_axis_range_changed)
        panel.axis_manager.axis_label_changed.connect(self._on_axis_label_changed)

        self._bound_plot_widget = panel.plot_widget
        self._bound_axis_manager = panel.axis_manager
        self._bound_trace_manager = panel.trace_manager

    def _on_panel_activated(self, panel_id):
        """Handle active panel change: initialize new panel and rebind signals."""
        if self._restoring_state:
            return
        panel = self.panel_grid.get_panel(panel_id)
        if panel is None:
            return
        self.state.active_panel_id = panel_id
        panel.plot_widget.apply_fonts(self.state)
        panel.axis_manager._initialize_axes()
        self._rebind_panel_signals(panel)

    def _split_panel_horizontal(self) -> None:
        """Split active panel horizontally (side-by-side)."""
        self.panel_grid.split_panel(self.panel_grid.active_panel_id, orientation="horizontal")
        self._sync_split_x_axes()

    def _split_panel_vertical(self) -> None:
        """Split active panel vertically (stacked)."""
        self.panel_grid.split_panel(self.panel_grid.active_panel_id, orientation="vertical")
        self._sync_split_x_axes()

    def _sync_split_x_axes(self) -> None:
        """Link X axes of all panels when mixed-signal overlay is active."""
        panel_list = list(self.panel_grid.panels.values())
        if len(panel_list) > 1:
            active = self.panel_grid.get_active_panel()
            if active is None:
                return
            master_vb = active.plot_widget.plotItem.vb
            for p in panel_list:
                if p is not active:
                    p.plot_widget.plotItem.vb.setXLink(master_vb)

    def _close_active_panel(self) -> None:
        """Close the active panel."""
        self.panel_grid.close_panel(self.panel_grid.active_panel_id)

    # ---- View Templates ----

    def _on_save_template(self):
        """Save current panel view as a named template."""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save Template", "Template name:")
        if ok and name:
            result = self._session.save_template(name)
            if result.get("success"):
                self.statusBar().showMessage(
                    f"Template '{name}' saved", 3000
                )
            else:
                self.statusBar().showMessage(
                    f"Error: {result.get('error')}", 5000
                )

    def _on_load_template(self):
        """Load a saved view template onto the active panel."""
        from pqwave.ui.template_manager_dialog import TemplateManagerDialog
        from PyQt6.QtWidgets import QDialog
        dlg = TemplateManagerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.selected_name
            if name:
                result = self._session.load_template(name)
                if result.get("success"):
                    applied = result.get('applied_expressions', 0)
                    skipped = result.get('skipped_expressions', [])
                    msg = f"Template '{name}' loaded ({applied} traces)"
                    if skipped:
                        msg += f" — {len(skipped)} skipped: {', '.join(skipped[:3])}"
                    self.statusBar().showMessage(msg, 5000)
                else:
                    self.statusBar().showMessage(
                        f"Error: {result.get('error')}", 5000
                    )

    def _on_manage_templates(self):
        """Open the Template Manager dialog."""
        from pqwave.ui.template_manager_dialog import TemplateManagerDialog
        dlg = TemplateManagerDialog(self)
        dlg.exec()

    def _on_close_dataset(self):
        """Close the active dataset and its traces."""
        if not self.state.datasets:
            return
        idx = self.state.current_dataset_idx
        self.state.remove_dataset(idx)
        # If MC collection references removed datasets, clear it
        if self.state.mc_collection:
            mc = self.state.mc_collection
            valid = [r for r in mc.runs if r.dataset_idx != idx]
            if len(valid) != len(mc.runs):
                # Adjust remaining run dataset indices
                for r in valid:
                    if r.dataset_idx > idx:
                        r.dataset_idx -= 1
                mc.runs = valid
            if not mc.runs:
                self.state.mc_collection = None
                if self.mc_control_bar is not None:
                    self.mc_control_bar.setVisible(False)
        # Sync Qt items with surviving state traces for all panels
        for panel in self.panel_grid.panels.values():
            panel.trace_manager.rebuild_from_state()
        self._update_dataset_combo()
        self._update_variable_combo()
        self.auto_range_x()
        self.auto_range_y()

    def _on_open_monte_carlo(self):
        """Open the MC configuration dialog."""
        try:
            from pqwave.ui.mc_open_dialog import MCOpenDialog
        except ImportError:
            QMessageBox.information(self, "Coming Soon",
                                   "Monte Carlo support is coming soon.")
            return
        dialog = MCOpenDialog(self)
        if dialog.exec():
            config = dialog.get_config()
            self._load_mc_data(config)

    def _load_mc_data(self, config):
        """Load Monte Carlo data from dialog configuration."""
        from pqwave.models.rawfile import RawFile, detect_naming_pattern
        from pqwave.models.mc_collection import (
            build_mc_from_stepped, build_mc_from_pattern, build_mc_from_multi_files
        )
        from pqwave.models.dataset import Dataset

        if config.is_stepped:
            raw = RawFile(config.file_path)
            mc = build_mc_from_stepped(raw, config.file_path)
            for ds_idx in range(len(raw.datasets)):
                dataset = Dataset(raw, ds_idx)
                self.state.add_dataset(dataset)
        elif config.is_multi_file:
            for path in config.file_paths:
                raw = RawFile(path)
                for ds_idx in range(len(raw.datasets)):
                    dataset = Dataset(raw, ds_idx)
                    self.state.add_dataset(dataset)
            mc = build_mc_from_multi_files(config.file_paths)
        else:  # pattern
            raw = RawFile(config.file_path)
            for ds_idx in range(len(raw.datasets)):
                dataset = Dataset(raw, ds_idx)
                self.state.add_dataset(dataset)
            pattern = config.grouping_pattern or "vout"
            mc = build_mc_from_pattern(raw, config.file_path, pattern)

        self.state.mc_collection = mc
        self._update_dataset_combo()
        self._update_variable_combo()

        # Create and wire MC control bar on first MC load
        if self.mc_control_bar is None:
            self.mc_control_bar = MCControlBar()
            # Insert below the control panel in the upper layout
            upper = self._main_splitter.widget(0)
            if upper and upper.layout():
                upper.layout().addWidget(self.mc_control_bar)
            self.mc_control_bar.display_mode_changed.connect(self._on_mc_display_changed)
            self.mc_control_bar.envelope_sigma_changed.connect(self._on_mc_sigma_changed)
            self.mc_control_bar.nominal_changed.connect(self._on_mc_nominal_changed)
            self.mc_control_bar.run_filter_changed.connect(self._on_mc_filter_changed)

        self.mc_control_bar.setVisible(True)
        self.mc_control_bar.set_run_count(len(mc.runs))
        self.mc_control_bar.set_nominal(mc.nominal_index)
        self.mc_control_bar.set_display_mode(mc.display_mode)

        self.statusBar().showMessage(f"MC: {len(mc.runs)} runs loaded", 5000)

    def _on_mc_display_changed(self, mode: str):
        """Handle MC control bar display mode change."""
        if self.state.mc_collection:
            self.state.mc_collection.display_mode = mode
            for panel in self.panel_grid.panels.values():
                panel.trace_manager.rebuild_from_state()

    def _on_mc_sigma_changed(self, sigma: float):
        """Handle MC control bar sigma change (envelope mode)."""
        if self.state.mc_collection:
            self.state.mc_collection.envelope_sigma = sigma
            if self.state.mc_collection.display_mode == "envelope":
                for panel in self.panel_grid.panels.values():
                    panel.trace_manager.rebuild_from_state()

    def _on_mc_nominal_changed(self, idx: int):
        """Handle MC control bar nominal run change."""
        if self.state.mc_collection:
            self.state.mc_collection.nominal_index = idx
            for panel in self.panel_grid.panels.values():
                panel.trace_manager.rebuild_from_state()

    def _on_mc_filter_changed(self, value):
        """Handle MC control bar run filter change."""
        if self.state.mc_collection:
            if value == "all":
                self.state.mc_collection.run_filter = None
            else:
                self.state.mc_collection.run_filter = value
            for panel in self.panel_grid.panels.values():
                panel.trace_manager.rebuild_from_state()

    def _connect_xschem_signals(self):
        """Connect xschem command handler signals."""
        if self.state.command_handler is None:
            logger.debug("No xschem command handler available, skipping xschem signal connections")
            return

        # Connect command handler signals to local slots
        self.state.command_handler.table_set_received.connect(self._handle_xschem_table_set)
        self.state.command_handler.copyvar_received.connect(self._handle_xschem_copyvar)
        self.state.command_handler.open_file_received.connect(self._handle_xschem_open_file)
        self.state.command_handler.add_trace_received.connect(self._handle_xschem_add_trace)
        self.state.command_handler.remove_trace_received.connect(self._handle_xschem_remove_trace)
        self.state.command_handler.get_data_point_received.connect(self._handle_xschem_get_data_point)
        self.state.command_handler.close_window_received.connect(self._handle_xschem_close_window)
        self.state.command_handler.list_windows_received.connect(self._handle_xschem_list_windows)
        self.state.command_handler.ping_received.connect(self._handle_xschem_ping)
        self.state.command_handler.invalid_command_received.connect(self._handle_xschem_invalid_command)

        logger.debug(f"Connected xschem signals for window {self.window_id}")

    # Xschem pending commands handling
    def _queue_xschem_command(self, command_type: str, args: dict, client_addr: str, connection_state: dict) -> None:
        """Queue xschem command for processing when raw_file is available."""
        logger.debug(f"Window {self.window_id} queuing {command_type} command from {client_addr}")
        self.pending_xschem_commands.append((command_type, args, client_addr, connection_state))

    def _process_pending_xschem_commands(self) -> None:
        """Process any queued xschem commands."""
        if not self.pending_xschem_commands:
            return
        logger.debug(f"Window {self.window_id} processing {len(self.pending_xschem_commands)} pending commands")
        # Process in order
        for command_type, args, client_addr, connection_state in self.pending_xschem_commands:
            if command_type == 'copyvar':
                self._handle_xschem_copyvar(
                    args['var_name'], args['color'], client_addr, connection_state
                )
            elif command_type == 'add_trace':
                self._handle_xschem_add_trace(
                    args['var_name'], args['axis'], args['color'], client_addr, connection_state
                )
            elif command_type == 'remove_trace':
                self._handle_xschem_remove_trace(
                    args['var_name'], client_addr, connection_state
                )
            elif command_type == 'get_data_point':
                self._handle_xschem_get_data_point(
                    args['x_value'], client_addr, connection_state
                )
            # Note: table_set and open_file are not queued as they trigger file loading
        # Clear processed commands
        self.pending_xschem_commands.clear()

    # Xschem command slot methods
    def _handle_xschem_table_set(self, raw_file: str, client_addr: str, connection_state: dict):
        """Handle xschem table_set command."""
        logger.info(f"Window {self.window_id} received table_set: {raw_file} from {client_addr}")
        # Check if this command is for this window
        is_for_this = self._is_command_for_this_window(client_addr, connection_state, raw_file=raw_file)
        logger.info(f"Window {self.window_id} table_set is_for_this_window: {is_for_this}")
        if not is_for_this:
            logger.info(f"Ignoring table_set, not for this window")
            return
        # Update client-window mapping
        self.state.window_registry.set_window_for_client(client_addr, self.window_id)
        # Load the raw file in this window
        logger.info(f"Loading raw file: {raw_file}")
        self._load_raw_file(raw_file)

    def _handle_xschem_copyvar(self, var_name: str, color: str, client_addr: str, connection_state: dict):
        """Handle xschem copyvar command."""
        logger.info(f"Window {self.window_id} received copyvar: {var_name} color {color} from {client_addr}")
        current_raw_file = connection_state.get('current_raw_file')
        logger.info(f"Current raw file from connection_state: {current_raw_file}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=current_raw_file):
            logger.info(f"Ignoring copyvar, not for this window")
            return

        # Parse color
        rgb = self._parse_color(color)
        if rgb is None:
            logger.warning(f"Invalid color format: {color}, using default red")
            rgb = (255, 0, 0)  # Red

        # Determine axis from variable name
        axis = self._detect_axis_from_var_name(var_name)

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.info(f"Raw file not loaded, queuing copyvar command for {var_name}")
            self._queue_xschem_command('copyvar', {
                'var_name': var_name,
                'color': color,
                'rgb': rgb,
                'axis': axis
            }, client_addr, connection_state)
            return

        # Get current X variable
        x_var = self._get_current_x_var()
        logger.info(f"Current X variable: {x_var}")
        if x_var is None:
            logger.error(f"Cannot add trace: no X variable set (raw file loaded but no X variable?)")
            return

        # Add trace with error collection
        error_messages = []
        logger.info(f"Adding trace for variable {var_name} on axis {axis} with color {color}")
        trace = self.trace_manager.add_trace_from_variable(
            variable_name=var_name,
            x_var_name=x_var,
            y_axis=axis,
            custom_color=rgb,
            error_out=error_messages
        )
        if trace is None:
            error_msg = f"Failed to add trace for variable: {var_name}"
            if error_messages:
                error_msg = f"Failed to add trace: {error_messages[0]}"
            logger.error(error_msg)
        else:
            logger.info(f"Successfully added trace for {var_name} on axis {axis} color {color}")

    def _handle_xschem_open_file(self, raw_file: str, client_addr: str, connection_state: dict):
        """Handle xschem open_file JSON command."""
        logger.debug(f"Window {self.window_id} received open_file: {raw_file} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=raw_file):
            logger.debug(f"Ignoring open_file, not for this window")
            return
        self.state.window_registry.set_window_for_client(client_addr, self.window_id)
        try:
            self._load_raw_file(raw_file)
            self._send_xschem_response(
                client_addr, connection_state,
                status="success",
                data={"loaded": True, "raw_file": raw_file, "window_id": self.window_id}
            )
        except Exception as e:
            logger.error(f"Failed to load raw file {raw_file}: {e}")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error",
                error=f"Failed to load raw file: {e}"
            )

    def _handle_xschem_add_trace(self, var_name: str, axis: str, color: str, client_addr: str, connection_state: dict):
        """Handle xschem add_trace JSON command."""
        logger.debug(f"Window {self.window_id} received add_trace: {var_name} axis {axis} color {color} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=connection_state.get('current_raw_file')):
            logger.debug(f"Ignoring add_trace, not for this window")
            return

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.debug(f"Raw file not loaded, queuing add_trace command for {var_name}")
            self._queue_xschem_command('add_trace', {
                'var_name': var_name,
                'axis': axis,
                'color': color
            }, client_addr, connection_state)
            return

        # Parse color
        rgb = self._parse_color(color)
        if rgb is None:
            logger.warning(f"Invalid color format: {color}, using default red")
            rgb = (255, 0, 0)  # Red

        # Determine axis assignment
        if axis == 'auto':
            y_axis = self._detect_axis_from_var_name(var_name)
        elif axis == 'Y1':
            y_axis = AxisAssignment.Y1
        elif axis == 'Y2':
            y_axis = AxisAssignment.Y2
        else:
            logger.warning(f"Invalid axis '{axis}', defaulting to auto detection")
            y_axis = self._detect_axis_from_var_name(var_name)

        # Get current X variable
        x_var = self._get_current_x_var()
        if x_var is None:
            logger.error(f"Cannot add trace: no X variable set (raw file not loaded?)")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error",
                error="No X variable set (raw file not loaded)"
            )
            return

        # Add trace with error collection
        error_messages = []
        trace = self.trace_manager.add_trace_from_variable(
            variable_name=var_name,
            x_var_name=x_var,
            y_axis=y_axis,
            custom_color=rgb,
            error_out=error_messages
        )
        if trace is None:
            error_msg = f"Failed to add trace for variable: {var_name}"
            if error_messages:
                # Use the first error message for more detail
                error_msg = error_messages[0]
            logger.error(error_msg)
            self._send_xschem_response(
                client_addr, connection_state,
                status="error",
                error=error_msg
            )
        else:
            logger.info(f"Added trace for {var_name} on axis {y_axis} color {color}")
            self._send_xschem_response(
                client_addr, connection_state,
                status="success",
                data={"added": True, "var_name": var_name, "axis": str(y_axis), "color": color}
            )

    def _handle_xschem_remove_trace(self, var_name: str, client_addr: str, connection_state: dict):
        """Handle xschem remove_trace JSON command."""
        logger.debug(f"Window {self.window_id} received remove_trace: {var_name} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=connection_state.get('current_raw_file')):
            logger.debug(f"Ignoring remove_trace, not for this window")
            return

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.debug(f"Raw file not loaded, queuing remove_trace command for {var_name}")
            self._queue_xschem_command('remove_trace', {
                'var_name': var_name
            }, client_addr, connection_state)
            return

        if self.trace_manager is None:
            logger.error("Cannot remove trace: trace_manager not initialized")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error", error="Trace manager not available"
            )
            return

        success = self.trace_manager.remove_trace_by_variable_name(var_name)
        if success:
            logger.info(f"Removed trace for variable '{var_name}'")
            self._send_xschem_response(
                client_addr, connection_state,
                status="success", data={"removed": var_name}
            )
        else:
            logger.warning(f"Trace not found for variable '{var_name}'")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error", error=f"Trace not found for variable '{var_name}'"
            )

    def _handle_xschem_get_data_point(self, x_value: float, client_addr: str, connection_state: dict):
        """Handle xschem get_data_point JSON command."""
        logger.debug(f"Window {self.window_id} received get_data_point: x={x_value} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=connection_state.get('current_raw_file')):
            logger.debug(f"Ignoring get_data_point, not for this window")
            return

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.debug(f"Raw file not loaded, queuing get_data_point command for x={x_value}")
            self._queue_xschem_command('get_data_point', {
                'x_value': x_value
            }, client_addr, connection_state)
            return

        if self.state is None or self.trace_manager is None:
            logger.error("Cannot query data point: state or trace_manager not initialized")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error", error="Application not ready"
            )
            return

        results = self._query_data_point(x_value)
        # Convert numpy types to Python native types for JSON serialization
        # The _query_data_point already converts to float via float()
        # However, y_value may be complex, which is not JSON serializable.
        # We'll replace complex y_value with dict representation.
        serializable_results = []
        for res in results:
            res_copy = res.copy()
            y_val = res_copy.get('y_value')
            if isinstance(y_val, complex) or np.iscomplexobj(y_val):
                # Replace with magnitude/phase representation
                res_copy['y_value'] = {
                    'magnitude': float(np.abs(y_val)),
                    'phase_deg': float(np.angle(y_val, deg=True)),
                    'real': float(y_val.real),
                    'imag': float(y_val.imag)
                }
            elif isinstance(y_val, (np.floating, np.integer)):
                res_copy['y_value'] = float(y_val)
            # y_nearest may also be complex
            y_nearest = res_copy.get('y_nearest')
            if isinstance(y_nearest, complex) or np.iscomplexobj(y_nearest):
                res_copy['y_nearest'] = {
                    'magnitude': float(np.abs(y_nearest)),
                    'phase_deg': float(np.angle(y_nearest, deg=True)),
                    'real': float(y_nearest.real),
                    'imag': float(y_nearest.imag)
                }
            elif isinstance(y_nearest, (np.floating, np.integer)):
                res_copy['y_nearest'] = float(y_nearest)
            # Convert numpy bool to Python bool
            out_of_range = res_copy.get('out_of_range')
            if isinstance(out_of_range, np.bool_):
                res_copy['out_of_range'] = bool(out_of_range)
            serializable_results.append(res_copy)

        self._send_xschem_response(
            client_addr, connection_state,
            status="success",
            data={"x": x_value, "traces": serializable_results}
        )

    def _handle_xschem_close_window(self, window_id: str, client_addr: str, connection_state: dict):
        """Handle xschem close_window JSON command."""
        logger.debug(f"Window {self.window_id} received close_window: window_id={window_id} from {client_addr}")
        # If window_id matches this window, close it
        if window_id == self.window_id:
            self.close()
        # Otherwise ignore (could be for another window)

    def _handle_xschem_list_windows(self, client_addr: str, connection_state: dict):
        """Handle xschem list_windows JSON command."""
        logger.debug(f"Window {self.window_id} received list_windows from {client_addr}")
        registry = self.state.window_registry
        window_ids = registry.get_all_window_ids()
        windows = []
        for win_id in window_ids:
            win = registry.get_window_by_id(win_id)
            if win is not None:
                windows.append({
                    "window_id": win_id,
                    "raw_file": win.raw_file_path,
                    "title": win.windowTitle()
                })
            else:
                # Window reference lost (garbage collected)
                windows.append({
                    "window_id": win_id,
                    "raw_file": None,
                    "title": "(closed)"
                })
        self._send_xschem_response(
            client_addr, connection_state,
            status="success",
            data={"windows": windows}
        )

    def _handle_xschem_ping(self, client_addr: str, connection_state: dict):
        """Handle xschem ping JSON command."""
        logger.debug(f"Window {self.window_id} received ping from {client_addr}")
        from pqwave import __version__
        self._send_xschem_response(
            client_addr, connection_state,
            status="success",
            data={"pong": True, "version": f"pqwave {__version__}"}
        )

    def _handle_xschem_invalid_command(self, command_dict: dict, error_message: str):
        """Handle xschem invalid_command signal."""
        logger.warning(f"Invalid command received: {error_message} - {command_dict}")
        # Extract client info from command dict
        client_addr = command_dict.get('_client_addr', 'unknown')
        connection_state = command_dict.get('_connection_state', {})
        command_id = command_dict.get('id')

        # Only send response for JSON commands (those with an ID)
        if command_id is not None:
            response = {
                "status": "error",
                "error": error_message,
                "id": command_id
            }
            if self.state.command_handler is not None:
                self.state.command_handler.send_response(client_addr, response)
            else:
                logger.error("Cannot send error response: command_handler not available")

    def _is_command_for_this_window(self, client_addr: str, connection_state: dict, raw_file: Optional[str] = None) -> bool:
        """
        Determine if an xschem command is intended for this window.

        Checks:
        1. If client is already associated with this window (via registry)
        2. If raw_file matches this window's raw_file_path
        3. If this is the only window open (default)

        Returns True if command should be processed by this window.
        """
        logger.debug(f"_is_command_for_this_window: client={client_addr}, raw_file={raw_file}, window_id={self.window_id}")
        registry = self.state.window_registry
        # Check client-window mapping
        assigned_window = registry.get_window_for_client(client_addr)
        logger.debug(f"  assigned_window: {assigned_window.window_id if assigned_window else None}")
        if assigned_window is not None:
            # Client already assigned to a window
            return assigned_window.window_id == self.window_id

        # Check raw file mapping
        if raw_file is not None:
            file_window = registry.get_window_by_raw_file(raw_file)
            if file_window is not None:
                return file_window.window_id == self.window_id
            # If raw_file provided and not mapped, and this window has no raw file loaded,
            # accept the command (this window can load the file)
            if self.raw_file is None:
                logger.debug(f"  raw_file not mapped, this window has no raw file, accepting")
                return True

        # If no mapping exists, check if this is the only window
        all_windows = registry.get_all_window_ids()
        if len(all_windows) == 1 and all_windows[0] == self.window_id:
            return True

        # Default: not for this window
        return False

    # Xschem helper methods
    def _send_xschem_response(self, client_addr: str, connection_state: dict,
                              status: str = "success", data: Optional[dict] = None,
                              error: Optional[str] = None) -> bool:
        """
        Send JSON response to xschem client.

        Args:
            client_addr: Client address string "ip:port"
            connection_state: Connection state dict (contains command_id)
            status: "success" or "error"
            data: Optional response data dictionary
            error: Optional error message string

        Returns:
            True if response sent successfully, False otherwise.
        """
        if self.state.command_handler is None:
            logger.warning(f"Cannot send response: command_handler not available")
            return False

        response = {"status": status}
        if data is not None:
            response["data"] = data
        if error is not None:
            response["error"] = error

        # Include command ID if present in connection_state
        command_id = connection_state.get('command_id')
        if command_id is not None:
            response["id"] = command_id

        logger.debug(f"Sending xschem response to {client_addr}: {response}")
        return self.state.command_handler.send_response(client_addr, response)

    def _query_data_point(self, x_value: float) -> list:
        """
        Query data point at x coordinate across all traces in this window.

        Args:
            x_value: X coordinate (linear space)

        Returns:
            List of dictionaries with keys:
            - name: trace name (expression)
            - var_name: variable name (unquoted)
            - y_axis: 'Y1' or 'Y2'
            - color: RGB tuple
            - y_value: interpolated Y value (complex if complex data)
            - magnitude: magnitude (if complex)
            - phase_deg: phase in degrees (if complex)
            - real: real component (if complex)
            - imag: imaginary component (if complex)
            - x_nearest: nearest X data point (for reference)
            - y_nearest: nearest Y data point (for reference)
            - interpolation: 'linear' or 'nearest' (if within range)
            - out_of_range: True if x_value outside trace X range
        """
        results = []
        if self.state is None or not self.state.traces:
            return results

        for trace in self.state.traces:
            x_data = trace.x_data
            y_data = trace.y_data
            if len(x_data) == 0:
                continue

            x_min, x_max = np.min(x_data), np.max(x_data)
            out_of_range = bool(x_value < x_min or x_value > x_max)  # convert numpy bool to Python bool

            # Nearest neighbor indices
            idx = np.abs(x_data - x_value).argmin()
            x_nearest = float(x_data[idx])
            y_nearest = y_data[idx]  # may be complex
            # Convert numpy scalar to Python native type if not complex
            if np.iscomplexobj(y_nearest):
                pass  # keep as numpy complex (handled later)
            elif isinstance(y_nearest, (np.floating, np.integer)):
                y_nearest = float(y_nearest)

            # Linear interpolation if within range and more than one point
            if not out_of_range and len(x_data) > 1:
                # numpy.interp does not support complex; handle separately
                if np.iscomplexobj(y_data):
                    y_real = np.interp(x_value, x_data, y_data.real)
                    y_imag = np.interp(x_value, x_data, y_data.imag)
                    y_interp = y_real + 1j * y_imag
                else:
                    y_interp = np.interp(x_value, x_data, y_data)
                interpolation = 'linear'
                y_value = y_interp
            else:
                interpolation = 'nearest'
                y_value = y_nearest

            # Convert numpy scalar to Python native type if not complex
            if np.iscomplexobj(y_value):
                pass  # keep as numpy complex (handled later)
            elif isinstance(y_value, (np.floating, np.integer)):
                y_value = float(y_value)

            # Build result dict
            result = {
                'name': trace.name,
                'var_name': trace.expression,
                'y_axis': trace.y_axis.value,
                'color': trace.color,
                'y_value': y_value,
                'x_nearest': x_nearest,
                'y_nearest': y_nearest,
                'interpolation': interpolation,
                'out_of_range': out_of_range,
            }

            # Add complex data representation if applicable
            if np.iscomplexobj(y_value):
                result['magnitude'] = float(np.abs(y_value))
                result['phase_deg'] = float(np.angle(y_value, deg=True))
                result['real'] = float(y_value.real)
                result['imag'] = float(y_value.imag)

            results.append(result)

        return results

    def _parse_color(self, color_hex: str) -> Optional[Tuple[int, int, int]]:
        """
        Parse hexadecimal color string to RGB tuple (0-255).

        Supports formats: #rgb, #rgba, #rrggbb, #rrggbbaa
        Returns None if invalid.
        """
        if not color_hex.startswith('#'):
            return None
        hex_str = color_hex[1:]
        length = len(hex_str)
        if length not in (3, 4, 6, 8):
            return None
        try:
            # Expand shorthand
            if length == 3 or length == 4:
                hex_str = ''.join([c*2 for c in hex_str])
                # Now length 6 or 8
            # Convert to integer
            rgb_int = int(hex_str, 16)
            # Extract components (ignore alpha)
            if len(hex_str) >= 6:
                if len(hex_str) == 8:
                    # 8-char hex: RRGGBBAA layout
                    r = (rgb_int >> 24) & 0xFF
                    g = (rgb_int >> 16) & 0xFF
                    b = (rgb_int >> 8) & 0xFF
                else:
                    # 6-char hex: RRGGBB layout
                    r = (rgb_int >> 16) & 0xFF
                    g = (rgb_int >> 8) & 0xFF
                    b = rgb_int & 0xFF
                return (r, g, b)
            else:
                return None
        except ValueError:
            return None

    def _detect_axis_from_var_name(self, var_name: str) -> AxisAssignment:
        """
        Detect appropriate Y axis for a SPICE variable name.

        Rules:
        - Current variables (starting with 'i(') -> Y2
        - Voltage variables (starting with 'v(') -> Y1
        - Default: Y1
        """
        import re
        # Match i(...) or v(...)
        match = re.match(r'^([iv])\(', var_name)
        if match:
            prefix = match.group(1)
            if prefix == 'i':
                return AxisAssignment.Y2
        return AxisAssignment.Y1

    def _connect_mark_panel(self):
        """Connect mark panel signals (called when panel is created)."""
        if self.mark_panel is not None:
            self.mark_panel.mark_deleted_last.connect(self._on_mark_deleted_last)
            self.mark_panel.window_closed.connect(self._on_mark_panel_closed)

    def _update_trace_manager_log_modes(self):
        """Update trace manager with current log mode settings."""
        x_config = self.state.get_axis_config(AxisId.X)
        y1_config = self.state.get_axis_config(AxisId.Y1)
        y2_config = self.state.get_axis_config(AxisId.Y2)

        self.trace_manager.set_log_modes(
            x_log=x_config.log_mode,
            y1_log=y1_config.log_mode,
            y2_log=y2_config.log_mode
        )

    # Menu callbacks

    def open_file(self):
        """Open supported files (.raw, .vcd) — appends to current session."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open File", "",
            "Supported Files (*.raw *.vcd *.json);;All Files (*)"
        )
        if not filename:
            return

        ext = filename.lower()
        if ext.endswith('.json'):
            if self.state.source_files:
                # Block .json in non-fresh sessions
                result = QMessageBox.warning(
                    self, "Cannot Open Project",
                    "State files (.json) can only be opened in a fresh "
                    "session.\n\nOpen in a new window?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
                )
                if result == QMessageBox.StandardButton.Yes:
                    new_window = MainWindow(initial_files=[filename])
                    new_window.show()
                return
            self._load_project(filename)
        elif ext.endswith('.vcd'):
            self._load_vcd(filename, vcd_only=(self.raw_file is None))
        else:
            self._load_raw_file(filename)

    def open_new_window(self):
        """Open a new MainWindow instance."""
        new_window = MainWindow()
        new_window.show()

    def _load_vcd(self, filename: str, vcd_only: bool = False):
        """Internal: parse a VCD file and wire it into the active panel."""
        from pqwave.models.vcdfile import VcdFile

        try:
            vcd = VcdFile(filename)
        except Exception as e:
            QMessageBox.critical(
                self, "VCD Parse Error",
                f"Failed to parse VCD file:\n{e}"
            )
            return

        for panel in self.panel_grid.panels.values():
            panel.trace_manager.set_vcd_file(vcd)

        names = vcd.get_signal_names()
        if not names:
            QMessageBox.warning(
                self, "VCD File",
                f"The VCD file contains no signals.\n\n"
                f"File: {filename}\n\n"
                f"The file may be corrupted or in an unsupported format."
            )
            return

        logger.info(
            f"Loaded VCD: {filename} ({len(names)} signals, timescale={vcd.timescale:.0e}s)")

        # Sync VCD signal names into ApplicationState so SessionAPI.signals() sees them
        self.state.vcd_signal_names = sorted(names)

        self._update_variable_combo()
        self._refresh_completions()

        # Track source file
        from pqwave.models.state import SourceFile
        abs_path = os.path.abspath(filename)
        existing = [s for s in self.state.source_files if s.path == abs_path]
        if not existing:
            self.state.source_files.append(SourceFile(
                path=abs_path, file_type='vcd'))
            self._update_save_as_enabled()

        # Pure VCD mode (no raw file): default X axis to "time" and
        # record the VCD path for per-file state save/restore.
        if self.raw_file is None:
            self.raw_file_path = filename
            self.state.current_x_var = "time"
            self.axis_manager.set_axis_label(AxisId.X, "time")

        # Sync X axes across split panels for mixed-signal overlay
        self._sync_split_x_axes()

    def _load_project(self, json_path: str) -> None:
        """Load a project file (.json), restoring sources and state."""
        import json as _json
        abs_json = os.path.abspath(json_path)
        base_dir = os.path.dirname(abs_json)

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = _json.load(f)
        except Exception as e:
            QMessageBox.critical(
                self, "Project Load Error",
                f"Failed to read project file:\n{e}"
            )
            return

        # Load source files first
        source_files = data.get('source_files', [])
        from pqwave.models.state import SourceFile
        for sf_data in source_files:
            sf = SourceFile.from_dict(sf_data, base_dir)
            if not os.path.exists(sf.path):
                logger.warning(f"Source file not found: {sf.path}")
                QMessageBox.warning(
                    self, "Missing File",
                    f"Source file not found:\n{sf.path}\n\nSkipping."
                )
                continue
            if sf.file_type == 'vcd':
                self._load_vcd(sf.path,
                               vcd_only=(self.raw_file is None))
            else:
                self._load_raw_file(sf.path)

        # Restore per-panel state
        if 'panels' in data:
            self._restore_panels_from_dict(data)

        self._project_path = abs_json
        logger.info(f"Project loaded: {json_path}")

    def convert_raw_data(self):
        """Convert currently loaded raw data to another format."""
        if not self.raw_file or not self.raw_file.datasets:
            QMessageBox.warning(
                self, "No Data",
                "No raw data loaded. Open a raw file first before converting."
            )
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QPushButton

        dataset = self.raw_file.datasets[0]  # Use first dataset
        title = dataset.get('title', 'pqwave conversion')
        date = dataset.get('date', '')
        plotname = dataset.get('plotname', '')
        flags = dataset.get('flags', '')
        variables = dataset.get('variables', [])
        data = dataset.get('data', np.array([]))
        is_ac_or_complex = dataset.get('_is_ac_or_complex', False)

        # Detect source format from spicelib's dialect detection
        detected = self.raw_file.detected_format
        if detected in ('ltspice', 'qspice', 'ngspice', 'xyce'):
            src_format = detected
        else:
            # Fallback to extension-based detection
            src_file = self.raw_file.filename.lower()
            if src_file.endswith('.qraw'):
                src_format = 'qspice'
            else:
                src_format = 'ltspice'

        # Show format selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Convert Raw Data")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout()

        info_label = QLabel(
            f"Source: {src_format.upper()}\n"
            f"Variables: {len(variables)}\n"
            f"Points: {data.shape[0] if data.ndim > 0 else 0}"
        )
        layout.addWidget(info_label)

        layout.addWidget(QLabel("Target format:"))

        format_group = []
        for fmt_key, fmt_config in FORMAT_CONFIG.items():
            label = f"{fmt_key.upper()} ({fmt_config['extension']})"
            rb = QRadioButton(label)
            if fmt_key == src_format:
                rb.setEnabled(False)  # Disable current format
            else:
                rb.setChecked(True)  # Default to first non-source format
            format_group.append((fmt_key, rb))
            layout.addWidget(rb)

        # Button box
        button_layout = QHBoxLayout()
        convert_btn = QPushButton("Convert")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(convert_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        def do_convert():
            target_fmt = None
            for fmt_key, rb in format_group:
                if rb.isChecked():
                    target_fmt = fmt_key
                    break

            if target_fmt is None:
                QMessageBox.warning(dialog, "Error", "Please select a target format.")
                return

            dialog.accept()

            # Show save file dialog
            ext = FORMAT_CONFIG[target_fmt]['extension']
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Converted Raw File",
                "",
                f"Raw Files (*{ext});;All Files (*)"
            )

            if not save_path:
                return

            try:
                write_raw_file(
                    output_path=save_path,
                    title=title,
                    date=date,
                    plotname=plotname,
                    flags=flags,
                    variables=variables,
                    data=data,
                    target_format=target_fmt,
                    is_ac_or_complex=is_ac_or_complex,
                )
                QMessageBox.information(
                    self, "Conversion Successful",
                    f"Converted to {target_fmt.upper()} format:\n{save_path}"
                )
                logger.info(f"Raw data converted to {save_path} ({target_fmt})")
            except Exception as e:
                logger.exception(f"Conversion failed: {e}")
                QMessageBox.critical(
                    self, "Conversion Failed",
                    f"Failed to convert raw data:\n{e}"
                )

        convert_btn.clicked.connect(do_convert)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def save_as_data_file(self):
        """Save currently displayed traces as a data file.

        Disabled for multi-file sessions. Supports raw and VCD source files.
        """
        if len(self.state.source_files) > 1:
            QMessageBox.warning(
                self, "Multi-File Session",
                "Save as data file is only available for single-file sessions."
            )
            return

        panel = self.panel_grid.get_active_panel()
        if panel is None:
            logger.warning("save_as_data_file: no active panel")
            return
        tm = panel.trace_manager
        raw_file = tm.raw_file
        vcd_file = tm.vcd_file

        if raw_file is None and vcd_file is None:
            QMessageBox.warning(
                self, "No Data",
                "No data loaded. Open a file first."
            )
            return

        traces = self.state.traces
        if not traces:
            QMessageBox.warning(
                self, "No Traces",
                "No traces to save. Add traces to the plot first."
            )
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QPushButton

        vcd_only = (raw_file is None and vcd_file is not None)

        if raw_file is not None:
            dataset = raw_file.datasets[0]
            is_ac = dataset.get('_is_ac_or_complex', False)
            detected = raw_file.detected_format
            if detected in ('ltspice', 'qspice', 'ngspice', 'xyce'):
                src_format = detected
            else:
                src_format = 'qspice' if raw_file.filename.lower().endswith('.qraw') else 'ltspice'
        else:
            dataset = None
            is_ac = False
            src_format = 'vcd'

        # Format selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Traces As Data File")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Extracting {len(traces)} trace(s) from {src_format.upper()}"))
        layout.addWidget(QLabel("Target format:"))

        format_group = []
        for fmt_key in FORMAT_CONFIG:
            label = f"{fmt_key.upper()} ({FORMAT_CONFIG[fmt_key]['extension']})"
            rb = QRadioButton(label)
            if vcd_only:
                rb.setChecked(fmt_key == 'vcd')
            else:
                rb.setChecked(fmt_key == src_format)
                if fmt_key == 'vcd':
                    rb.setEnabled(False)
                    rb.setToolTip("VCD output is only available for VCD-sourced data.")
            format_group.append((fmt_key, rb))
            layout.addWidget(rb)

        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        dialog.setLayout(layout)

        def do_save():
            target_fmt = None
            for fmt_key, rb in format_group:
                if rb.isChecked():
                    target_fmt = fmt_key
                    break
            if target_fmt is None:
                QMessageBox.warning(dialog, "Error", "Please select a target format.")
                return

            dialog.accept()

            ext = FORMAT_CONFIG[target_fmt]['extension']
            filter_label = "VCD Files" if target_fmt == 'vcd' else "Raw Files"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Traces As",
                "", f"{filter_label} (*{ext});;All Files (*)"
            )
            if not save_path:
                return

            try:
                if target_fmt == 'vcd':
                    ts = vcd_file.timescale if vcd_file else 1e-9
                    write_vcd_file(save_path, traces, timescale=ts)
                elif raw_file is not None:
                    # Pass custom X variable (if set) so it's preserved in the output
                    x_var = self.state.current_x_var
                    x_var_data = None

                    # FFT traces carry frequency bins as x_data — use those
                    # instead of the original file's sweep variable (time)
                    if any(t.expression.lower().startswith('fft(') for t in traces):
                        x_var = "frequency"
                    elif x_var:
                        try:
                            x_var_data = raw_file.get_variable_data(
                                x_var, self.state.current_dataset_idx
                            )
                        except Exception as e:
                            logger.warning("Failed to get X variable data for '%s': %s", x_var, e)
                            x_var = None  # fall back to default X

                    extract_traces_to_raw(
                        output_path=save_path,
                        traces=traces,
                        raw_file=raw_file,
                        target_format=target_fmt,
                        output_is_ac=is_ac,
                        x_var_name=x_var,
                        x_var_data=x_var_data,
                        dataset_idx=self.state.current_dataset_idx,
                    )
                else:
                    # VCD-only → raw format: build data array from traces
                    x_var = self.state.current_x_var
                    x_var_data = None
                    if x_var and not any(
                        t.expression.lower().startswith('fft(') for t in traces
                    ):
                        x_var_data = traces[0].x_data
                    self._save_vcd_traces_as_raw(
                        save_path, traces, target_fmt, x_var, x_var_data)

                QMessageBox.information(
                    self, "Save Successful",
                    f"Saved {len(traces)} trace(s) as {target_fmt.upper()}:\n{save_path}"
                )
                logger.info(f"Traces saved to {save_path} ({target_fmt})")
            except Exception as e:
                logger.exception(f"Save traces failed: {e}")
                QMessageBox.critical(
                    self, "Save Failed",
                    f"Failed to save traces:\n{e}"
                )

        save_btn.clicked.connect(do_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def export_plot_image(self) -> None:
        """Export the active panel's plot to an image file (PNG, JPG, SVG, etc.)."""
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        pw = panel.plot_widget
        plot_item = pw.plotItem

        from PyQt6.QtWidgets import QFileDialog
        import re
        path, sel_filter = QFileDialog.getSaveFileName(
            self, "Export Plot to Image", "",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;SVG (*.svg);;BMP (*.bmp);;TIFF (*.tiff)")
        if not path:
            return

        # Auto-append extension from the selected filter if missing
        ext_map = {'svg': '.svg', 'png': '.png', 'jpg': '.jpg',
                   'jpeg': '.jpg', 'bmp': '.bmp', 'tiff': '.tiff'}
        has_ext = any(path.lower().endswith(ext) for ext in ext_map)
        if not has_ext:
            m = re.search(r'\*\.(\w+)', sel_filter)
            if m:
                path += '.' + m.group(1)

        try:
            if path.lower().endswith('.svg'):
                from pyqtgraph.exporters import SVGExporter
                exp = SVGExporter(plot_item)
                exp.export(path)
            else:
                from pyqtgraph.exporters import ImageExporter
                exp = ImageExporter(plot_item)
                exp.export(path)
            logger.info(f"Plot exported to {path}")
        except Exception as e:
            logger.exception("Export failed")
            QMessageBox.critical(
                self, "Export Failed",
                f"Failed to export plot:\n{e}")

    def _save_vcd_traces_as_raw(self, path, traces, target_format, x_var_name, x_var_data):
        """Write VCD-only traces to a raw-format file via write_raw_file."""
        import numpy as np

        if not traces:
            logger.warning("_save_vcd_traces_as_raw: no traces to save")
            return
        n_pts = min(len(t.x_data) for t in traces)
        n_vars = len(traces)
        if x_var_name and x_var_data is not None:
            n_vars += 1

        data = np.empty((n_pts, n_vars), dtype=np.float64)
        col = 0
        for t in traces:
            data[:, col] = t.y_data[:n_pts]
            col += 1
        if x_var_name and x_var_data is not None:
            data[:, col] = x_var_data[:n_pts]

        variables = []
        for t in traces:
            variables.append({'name': t.expression, 'type': 'voltage', 'index': len(variables)})
        if x_var_name:
            variables.append({'name': x_var_name, 'type': 'time', 'index': len(variables)})

        write_raw_file(
            output_path=path,
            title='pqwave VCD extraction',
            date='',
            plotname='Transient Analysis',
            flags='real',
            variables=variables,
            data=data,
            target_format=target_format,
            is_ac_or_complex=False,
        )

    def edit_trace_properties(self):
        """Edit trace properties (alias, color, line width)"""
        logger.debug(f"edit_trace_properties called, traces count: {len(self.trace_manager.traces)}")
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLineEdit, QPushButton, QHBoxLayout, QLabel, QComboBox

        # Get traces from trace manager
        traces = self.trace_manager.traces
        if not traces:
            QMessageBox.information(self, "No Traces", "No traces to edit.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Trace Properties")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        # Create list widget for traces
        list_widget = QListWidget()
        for i, (var, plot_item, y_axis) in enumerate(traces):
            list_widget.addItem(f"{i+1}. {var} @ {y_axis}")

        layout.addWidget(list_widget)

        # Create alias edit (store on dialog, not self, to avoid stale refs)
        alias_layout = QHBoxLayout()
        alias_label = QLabel("Alias:")
        dialog.alias_edit = QLineEdit()
        alias_layout.addWidget(alias_label)
        alias_layout.addWidget(dialog.alias_edit)
        layout.addLayout(alias_layout)

        # Create color combo
        color_layout = QHBoxLayout()
        color_label = QLabel("Color:")
        dialog.color_combo = QComboBox()
        # Add color options
        colors = [
            ("Default (auto)", None),
            ("Red", (255, 0, 0)),
            ("Green", (0, 255, 0)),
            ("Blue", (0, 0, 255)),
            ("Yellow", (255, 255, 0)),
            ("Magenta", (255, 0, 255)),
            ("Cyan", (0, 255, 255)),
            ("Orange", (255, 165, 0)),
            ("Purple", (128, 0, 128)),
            ("Brown", (165, 42, 42))
        ]
        for color_name, color_value in colors:
            dialog.color_combo.addItem(color_name, color_value)
        color_layout.addWidget(color_label)
        color_layout.addWidget(dialog.color_combo)
        layout.addLayout(color_layout)

        # Create trace height combo (for digital/bus traces)
        height_layout = QHBoxLayout()
        height_label = QLabel("Height:")
        dialog.height_combo = QComboBox()
        heights = [("1.0x", 1.0), ("1.5x", 1.5), ("2.0x", 2.0), ("3.0x", 3.0)]
        for name, val in heights:
            dialog.height_combo.addItem(name, val)
        height_layout.addWidget(height_label)
        height_layout.addWidget(dialog.height_combo)
        layout.addLayout(height_layout)

        # Create line width combo
        width_layout = QHBoxLayout()
        width_label = QLabel("Line width:")
        dialog.width_combo = QComboBox()
        # Add line width options
        widths = [1, 2, 3, 4, 5]
        for width in widths:
            dialog.width_combo.addItem(str(width), width)
        width_layout.addWidget(width_label)
        width_layout.addWidget(dialog.width_combo)
        layout.addLayout(width_layout)

        # Connect list selection change to update all fields
        list_widget.currentRowChanged.connect(
            lambda row, lw=list_widget: self._update_trace_properties(row, lw))

        # Create buttons
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        # clicked signal passes a bool; absorb it as _ so lw stays the list_widget
        apply_btn.clicked.connect(
            lambda _, lw=list_widget: self._apply_trace_properties(
                lw.currentRow(), lw))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.Window)
        # Keep a hard reference so the dialog object captured by the lambdas
        # below does not get invalidated (WA_DeleteOnClose can cause this).
        self._trace_props_dialog = dialog

        # Select first trace if available
        if traces:
            list_widget.setCurrentRow(0)
            self._update_trace_properties(0, list_widget)

        dialog.show()

    def _update_trace_properties(self, row, list_widget):
        """Update trace properties fields with current trace values"""
        dialog = self._trace_props_dialog
        if 0 <= row < len(self.trace_manager.traces):
            var, plot_item, y_axis = self.trace_manager.traces[row]
            # Update alias field
            dialog.alias_edit.setText(var)

            # Update color combo
            current_color = plot_item.opts['pen'].color()
            current_rgb = (current_color.red(), current_color.green(), current_color.blue())

            # Find matching color in combo
            color_index = 0  # Default to "Default (auto)"
            for i in range(dialog.color_combo.count()):
                color_value = dialog.color_combo.itemData(i)
                if color_value == current_rgb:
                    color_index = i
                    break
            dialog.color_combo.setCurrentIndex(color_index)

            # Update line width combo
            current_width = plot_item.opts['pen'].width()
            width_index = 0  # Default to 1
            for i in range(dialog.width_combo.count()):
                width_value = dialog.width_combo.itemData(i)
                if width_value == current_width:
                    width_index = i
                    break
            dialog.width_combo.setCurrentIndex(width_index)

            # Update height combo (for digital/bus traces)
            # Find trace object to get current height
            trace_obj = None
            for t in self.state.traces:
                if t.name == var:
                    trace_obj = t
                    break
            if trace_obj and trace_obj.trace_type in ('digital', 'bus'):
                h = trace_obj.metadata.get('digital_height', 1.0)
                for i in range(dialog.height_combo.count()):
                    if abs(dialog.height_combo.itemData(i) - h) < 0.01:
                        dialog.height_combo.setCurrentIndex(i)
                        break

    def _apply_trace_properties(self, row, list_widget):
        """Apply trace properties (alias, color, line width)"""
        dialog = self._trace_props_dialog

        if 0 <= row < len(self.trace_manager.traces):
            var, plot_item, y_axis = self.trace_manager.traces[row]

            # Get new values
            new_alias = dialog.alias_edit.text().strip()
            new_color = dialog.color_combo.currentData()
            new_width = dialog.width_combo.currentData()
            new_height = dialog.height_combo.currentData()

            # Find matching Trace object in state
            trace_obj = None
            for trace in self.state.traces:
                if trace.name == var:
                    trace_obj = trace
                    break

            # Update alias if provided
            if new_alias and new_alias != var:
                # Update plot item name (legend)
                plot_item.opts['name'] = new_alias
                # Update Trace object name if found
                if trace_obj:
                    trace_obj.name = new_alias
                # Update list widget display
                list_widget.item(row).setText(f"{row+1}. {new_alias} @ {y_axis}")

            # Bus traces have a second (bottom) line that must mirror
            # the primary line's colour and width.
            bus_bot = (trace_obj.metadata.get('_bus_bot_item')
                       if trace_obj else None)

            if new_color is not None:
                qcolor = QColor(*new_color)
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=qcolor, width=pen.width())
                if hasattr(plot_item, 'setPen'):
                    plot_item.setPen(new_pen)
                else:
                    plot_item.opts['pen'] = new_pen
                    plot_item.update()
                if bus_bot is not None:
                    bus_bot.setPen(new_pen)
                if trace_obj:
                    trace_obj.color = new_color

            if new_width:
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=pen.color(), width=new_width)
                if hasattr(plot_item, 'setPen'):
                    plot_item.setPen(new_pen)
                else:
                    plot_item.opts['pen'] = new_pen
                    plot_item.update()
                if bus_bot is not None:
                    bus_bot.setPen(new_pen)
                if trace_obj:
                    trace_obj.line_width = new_width

            # Apply trace height (digital/bus only) — triggers full redraw
            if (trace_obj and trace_obj.trace_type in ('digital', 'bus')
                    and new_height is not None):
                old_h = trace_obj.metadata.get('digital_height', 1.0)
                if abs(new_height - old_h) > 0.01:
                    trace_obj.metadata['digital_height'] = new_height
                    self.trace_manager.recreate_all_digital()

            self.trace_manager._refresh_legend()

    def _set_trace_properties(self, name: str, height: float = None,
                               width: int = None, color: tuple = None,
                               alias: str = None) -> bool:
        """Set trace properties by name. Returns True if trace was found."""
        tm = self.trace_manager
        if tm is None:
            return False
        import pyqtgraph as pg
        from PyQt6.QtGui import QColor

        # Find the trace by expression or alias
        row = next((i for i, (v, _, _) in enumerate(tm.traces) if v == name), None)
        trace_obj = None
        if row is None:
            # Not found by expression — try alias match in state.traces
            trace_obj = next((t for t in self.state.traces if t.name == name), None)
            if trace_obj is None:
                return False
            row = next((i for i, (v, _, _) in enumerate(tm.traces)
                        if v == trace_obj.expression), None)
            if row is None:
                return False
        var, plot_item, y_axis = tm.traces[row]

        if trace_obj is None:
            trace_obj = next((t for t in self.state.traces if t.name == var), None)
        bus_bot = (trace_obj.metadata.get('_bus_bot_item')
                   if trace_obj else None)

        if alias is not None and alias != var:
            plot_item.opts['name'] = alias
            # Keep original expression in tm.traces for name-based lookups
            if trace_obj:
                trace_obj.name = alias

        if color is not None:
            qcolor = QColor(*color)
            pen = plot_item.opts['pen']
            new_pen = pg.mkPen(color=qcolor, width=pen.width())
            if hasattr(plot_item, 'setPen'):
                plot_item.setPen(new_pen)
            else:
                plot_item.opts['pen'] = new_pen
                plot_item.update()
            if bus_bot is not None:
                bus_bot.setPen(new_pen)
            if trace_obj:
                trace_obj.color = color

        # Apply width BEFORE height (height may trigger recreate_all_digital
        # which reads trace_obj.line_width)
        if width is not None:
            pen = plot_item.opts['pen']
            new_pen = pg.mkPen(color=pen.color(), width=width)
            if hasattr(plot_item, 'setPen'):
                plot_item.setPen(new_pen)
            else:
                plot_item.opts['pen'] = new_pen
                plot_item.update()
            if bus_bot is not None:
                bus_bot.setPen(new_pen)
            if trace_obj:
                trace_obj.line_width = width

        if (height is not None and trace_obj
                and trace_obj.trace_type in ('digital', 'bus')):
            old_h = trace_obj.metadata.get('digital_height', 1.0)
            if abs(height - old_h) > 0.01:
                trace_obj.metadata['digital_height'] = height
                tm.recreate_all_digital()

        tm._refresh_legend()
        return True

    def show_settings(self):
        """Show application settings widget."""
        # Create settings widget if it doesn't exist or was closed
        if not hasattr(self, '_settings_widget') or self._settings_widget is None:
            self._settings_widget = SettingsWidget(
                axis_manager=self.axis_manager,
                application_state=self.state,
                parent=self
            )
            # Connect signals
            self._settings_widget.viewbox_theme_changed.connect(self._on_viewbox_theme_changed)
            self._settings_widget.font_changed.connect(self._on_font_changed)
            self._settings_widget.eye_diagram_changed.connect(self._on_eye_diagram_settings_changed)
            self._settings_widget.destroyed.connect(lambda: setattr(self, '_settings_widget', None))

        # Show and raise the widget
        self._settings_widget.show()
        self._settings_widget.raise_()
        self._settings_widget.activateWindow()

    def _on_plot_title_changed(self, title: str):
        """Handle plot title changes."""
        self.state.plot_title = title
        self.plot_widget.set_plot_title(title)

    def _on_viewbox_theme_changed(self, theme: ViewboxTheme) -> None:
        """Handle viewbox theme changes from settings widget."""
        self.plot_widget.set_viewbox_theme(theme)
        self.plot_widget.apply_fonts(self.state)
        self._save_global_prefs()

    def _on_font_changed(self):
        """Handle font settings changes from settings widget."""
        self.plot_widget.apply_fonts(self.state)
        self._apply_ui_font()
        self._apply_repl_settings()
        self._save_global_prefs()

    def _apply_repl_settings(self) -> None:
        """Apply REPL font and color settings to the chat panel."""
        rf = self.state.repl_font
        if hasattr(self, 'chat_panel'):
            self.chat_panel.apply_settings(
                font_family=rf.family,
                font_size=rf.size or 11,
                fg_color=rf.color,
                bg_color=self.state.repl_bg,
            )

    def _apply_ui_font(self):
        """Apply UI font configuration to the application."""
        fc = self.state.ui_font
        font = QFont()
        if fc.family:
            font.setFamily(fc.family)
        if fc.size > 0:
            font.setPointSize(fc.size)
        if fc.family or fc.size > 0:
            QApplication.instance().setFont(font)
        else:
            QApplication.instance().setFont(QFont())

    def toggle_toolbar(self):
        """Toggle toolbar visibility."""
        self.set_toolbar_visible(not self.menu_manager.toolbar.isVisible())

    def toggle_statusbar(self):
        """Toggle status bar visibility."""
        self.set_statusbar_visible(not self.menu_manager.statusbar.isVisible())

    def toggle_grids(self):
        """Toggle grid visibility."""
        visible = self.axis_manager.get_grid_visible()
        self.axis_manager.set_grid_visible(not visible)

        # Update menu manager toggle state
        self.menu_manager.set_grids_visible(not visible)

    def set_toolbar_visible(self, visible):
        """Set toolbar visibility and update state."""
        self.menu_manager.set_toolbar_visible(visible)
        self.state.toolbar_visible = visible
        self._save_global_prefs()

    def set_statusbar_visible(self, visible):
        """Set status bar visibility and update state."""
        self.menu_manager.set_statusbar_visible(visible)
        self.state.status_bar_visible = visible
        self._save_global_prefs()

    def set_legend_visible(self, visible):
        """Set legend visibility and update state."""
        if self.legend:
            self.legend.setVisible(visible)
        self.state.legend_visible = visible

    def zoom_in(self):
        """Zoom in."""
        if self.plot_widget and self.plot_widget.plotItem:
            self.plot_widget.plotItem.vb.scaleBy(s=(0.8, 0.8))

    def zoom_out(self):
        """Zoom out."""
        if self.plot_widget and self.plot_widget.plotItem:
            self.plot_widget.plotItem.vb.scaleBy(s=(1.25, 1.25))

    def zoom_to_fit(self):
        """Auto-range all axes."""
        self.axis_manager.auto_range_axis(AxisId.X)
        self.axis_manager.auto_range_axis(AxisId.Y1)
        self.axis_manager.auto_range_axis(AxisId.Y2)

    def auto_range_x(self):
        """Auto-range X-axis."""
        self.axis_manager.auto_range_axis(AxisId.X)

    def auto_range_y(self):
        """Auto-range Y axes."""
        self.axis_manager.auto_range_axis(AxisId.Y1)
        self.axis_manager.auto_range_axis(AxisId.Y2)

    def enable_zoom_box(self):
        """Enable/disable zoom box mode."""
        # Toggle zoom box state
        self.zoom_box_enabled = not self.zoom_box_enabled

        # Update plot widget
        if self.plot_widget:
            self.plot_widget.enable_zoom_box(self.zoom_box_enabled)

        # Synchronize menu and toolbar actions
        if self.menu_manager:
            self.menu_manager.actions['zoom_box'].setChecked(self.zoom_box_enabled)
            self.menu_manager.actions['zoom_box_toolbar'].setChecked(self.zoom_box_enabled)

    # Cross-hair cursor and marks

    def toggle_cross_hair(self):
        """Toggle cross-hair cursor ON/OFF.

        When turning ON: shows cross-hair and opens the mark data panel.
        When turning OFF: hides cross-hair, clears all marks, closes mark panel.
        Note: X/Y cursors are independent and not affected by cross-hair toggle.
        """
        self.cross_hair_visible = not self.cross_hair_visible

        # Update plot widget (cross-hair only — X/Y cursors are independent)
        self.plot_widget.set_cross_hair_visible(self.cross_hair_visible)

        # Update menu and toolbar state
        if self.menu_manager:
            self.menu_manager.set_cross_hair_visible(self.cross_hair_visible)

        if self.cross_hair_visible:
            self._open_mark_panel()
        else:
            self._close_mark_panel()

    def _toggle_x_cursor_a(self, checked: bool) -> None:
        """Toggle X cursor a on/off."""
        self.plot_widget.set_cursor_xa_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_x_cursor_a_checked(checked)
        self._update_cursor_status()

    def _toggle_x_cursor_b(self, checked: bool) -> None:
        """Toggle X cursor b on/off."""
        self.plot_widget.set_cursor_xb_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_x_cursor_b_checked(checked)
        self._update_cursor_status()

    def _toggle_y_cursor_A(self, checked: bool) -> None:
        """Toggle Y cursor A on/off."""
        self.plot_widget.set_cursor_yA_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_y_cursor_A_checked(checked)
        self._update_cursor_status()

    def _toggle_y_cursor_B(self, checked: bool) -> None:
        """Toggle Y cursor B on/off."""
        self.plot_widget.set_cursor_yB_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_y_cursor_B_checked(checked)
        self._update_cursor_status()

    def _open_mark_panel(self):
        """Create and show the mark data panel."""
        if self.mark_panel is None:
            self.mark_panel = MarkPanel(parent=self)
            self._connect_mark_panel()
        self.mark_panel.clear_all_marks()
        self.mark_panel.show()
        self.mark_panel.raise_()
        self.mark_panel.activateWindow()

    def _close_mark_panel(self):
        """Close the mark panel and clear all marks."""
        self.plot_widget.clear_marks()
        if self.mark_panel is not None:
            self.mark_panel.close()
            self.mark_panel = None

    @pyqtSlot(float, float, float, float, float)
    def _on_plot_context_menu(self) -> None:
        """Show context menu when right-clicking the plot area."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor
        # Suppress if a trace context menu just closed (avoids spurious
        # re-trigger from plot-item removal during ungroup/expand).
        if getattr(self, '_suppress_plot_menu_until', 0) > time.monotonic():
            return
        menu = QMenu(self)
        menu.addAction("Export Plot to Image...", self.export_plot_image)
        menu.addSeparator()
        menu.addAction("Toggle Grid", self.toggle_grids)
        a = menu.addAction("Auto-range X-axis")
        a.triggered.connect(self.auto_range_x)
        a = menu.addAction("Auto-range Y-axis")
        a.triggered.connect(self.auto_range_y)
        menu.addAction("Zoom to Fit", self.zoom_to_fit)
        menu.exec(QCursor.pos())

    def _find_panel_with_trace(self, trace_name: str):
        """Return the Panel containing *trace_name*, or None."""
        for p in self.panel_grid.panels.values():
            if any(t.name == trace_name for t in p.trace_manager._state_traces):
                return p
        return None

    def _on_trace_context_menu(self, trace_name: str) -> None:
        """Show context menu when right-clicking a trace legend item."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor

        panel = self._find_panel_with_trace(trace_name)
        if panel is None:
            return
        menu = QMenu(self)

        # Find the trace to determine its type
        tm = panel.trace_manager
        trace = next((t for t in tm._state_traces if t.name == trace_name), None)
        ttype = trace.trace_type if trace else 'analog'
        trace_idx = tm._state_traces.index(trace) if trace else -1

        if ttype == 'analog':
            a = menu.addAction("Mark as Digital...")
            a.triggered.connect(
                lambda _, idx=trace_idx, _tm=tm: _tm.type_manager.toggle(
                    _tm._state_traces[idx], idx))
            menu.addSeparator()
            a = menu.addAction("Eye Diagram")
            a.triggered.connect(self._show_eye_diagram)
        elif ttype == 'digital':
            a = menu.addAction("Show as Analog")
            a.triggered.connect(
                lambda _, idx=trace_idx, _tm=tm: _tm.type_manager.toggle(
                    _tm._state_traces[idx], idx))
            a = menu.addAction("Threshold Settings...")
            a.triggered.connect(self._show_threshold_settings)
            a = menu.addAction("Group Into Bus")
            a.triggered.connect(
                lambda _, _tm=tm: _tm.group_selected_as_bus())
            menu.addSeparator()
            a = menu.addAction("Eye Diagram")
            a.triggered.connect(self._show_eye_diagram)
        elif ttype == 'bus':
            fmt_menu = menu.addMenu("Display Format")
            for fmt in ('hex', 'bin', 'dec'):
                a = fmt_menu.addAction(fmt)
                a.triggered.connect(
                    lambda _, f=fmt: self._set_bus_display_format(
                        trace_name, f))
            menu.addSeparator()
            expanded = trace.metadata.get('bus_expanded', False) if trace else False
            a = menu.addAction("Collapse Members" if expanded else "Expand Members")
            a.triggered.connect(
                lambda _, _tm=tm: _tm.toggle_bus_expand(trace_name))
            a = menu.addAction("Ungroup Bus")
            a.triggered.connect(
                lambda _, _tm=tm: _tm.ungroup_bus(trace_name))

        # Common action for all trace types
        menu.addSeparator()
        a = menu.addAction("Remove Trace")
        remove_expr = trace.expression if trace else trace_name
        a.triggered.connect(lambda: tm.remove_trace_by_variable_name(remove_expr))

        self._trace_menu_active = True
        menu.exec(QCursor.pos())
        self._trace_menu_active = False
        # Suppress spurious plot menu for 300ms after trace menu closes.
        self._suppress_plot_menu_until = time.monotonic() + 0.3

    def _set_bus_display_format(self, trace_name: str, fmt: str) -> None:
        """Update bus display format metadata and trigger re-render."""
        panel = self._find_panel_with_trace(trace_name)
        if panel is None:
            return
        trace = next((t for t in self.state.traces if t.name == trace_name), None)
        if trace is not None:
            trace.metadata['bus_display_format'] = fmt
            panel.trace_manager.recreate_trace_plot_item(
                self.state.traces.index(trace))

    def _on_mark_clicked(self, x_vb, y1_vb, x_linear, y1_linear, y2_linear):
        """Handle mark placement from plot widget click.

        Args:
            x_vb, y1_vb: Viewbox coordinates (for mark rendering in plot space)
            x_linear, y1_linear, y2_linear: Linear display values (for data panel)
        """
        self.plot_widget.add_mark_at_position(x_vb, y1_vb)
        if self.mark_panel is not None:
            # Re-show panel if user had closed it via window close button
            self.mark_panel.show()
            self.mark_panel.raise_()
            self.mark_panel.activateWindow()
            self.mark_panel.add_mark(x_linear, y1_linear, y2_linear)

    @pyqtSlot()
    def _on_mark_panel_closed(self):
        """Handle mark panel window close button — hide without destroying."""
        if self.mark_panel is not None:
            self.mark_panel.hide()

    @pyqtSlot()
    def _on_mark_deleted_last(self):
        """Handle mark deletion from mark panel button."""
        self.plot_widget.remove_last_mark()

    # Raw file handling

    def _load_raw_file(self, filename):
        """Load raw file and update UI."""
        try:
            # 1. Parse the new file (does NOT touch self.raw_file yet)
            new_raw_file = RawFile(filename)

            # 2. Replace self.raw_file (old one stays alive via existing datasets)
            self.raw_file = new_raw_file
            # Update window registry mapping
            self._update_window_registry_raw_file(filename)

            # 3. Populate UI with new data (appends to existing)
            for i in range(len(self.raw_file.datasets)):
                dataset = Dataset(self.raw_file, i)
                self.state.add_dataset(dataset)

            # Set current dataset to most recent (only if no dataset was active)
            if self.state.datasets:
                if len(self.state.datasets) == len(self.raw_file.datasets):
                    # First file loaded — set defaults
                    self.state.current_dataset_idx = 0
                    var_names = self.raw_file.get_variable_names(0)
                    if var_names:
                        self.state.current_x_var = var_names[0]
                        logger.info(f"Auto-set X variable to: {self.state.current_x_var}")
                        self.axis_manager.set_axis_label(AxisId.X, self.state.current_x_var)
                # On append, keep current_dataset_idx unchanged and do not
                # reset X variable — the user chose their context deliberately.

            # Update control panel
            self._update_dataset_combo()
            self._update_variable_combo()
            self.control_panel.clear_expression()  # Clear trace expression for new file

            # Set raw file reference in trace manager
            self.trace_manager.set_raw_file(self.raw_file)

            # Update trace manager with current log mode settings from state
            self._update_trace_manager_log_modes()

            # Auto-range axes
            self.auto_range_x()
            self.auto_range_y()

            # Update window title
            self.setWindowTitle(f"pqwave - {filename}")

            # Update status bar dataset label
            self._update_dataset_label()

            logger.info(f"Successfully loaded: {filename}")

            # Track source file
            from pqwave.models.state import SourceFile
            abs_path = os.path.abspath(filename)
            existing = [s for s in self.state.source_files if s.path == abs_path]
            if not existing:
                self.state.source_files.append(SourceFile(
                    path=abs_path, file_type='raw'))
                self._update_save_as_enabled()

            # Step hint for multi-run files opened flat
            if hasattr(self.raw_file, 'step_count') and self.raw_file.step_count > 1:
                self.statusBar().showMessage(
                    f"{self.raw_file.step_count} simulation steps detected — "
                    f"File > Open Monte Carlo... for statistical analysis",
                    8000
                )

            # Process any pending xschem commands that arrived before file was loaded
            self._process_pending_xschem_commands()

        except FileNotFoundError as e:
            self._show_error("File not found", f"File not found: {filename}\n\n{e}")
        except Exception as e:
            logger.exception(f"Error opening file: {filename}")
            error_msg = str(e)
            if "Invalid RAW file" in error_msg:
                self._show_error("Invalid RAW file", f"Invalid RAW file format: {filename}\n\n{error_msg}")
            else:
                self._show_error("Error opening file", f"Error opening file: {filename}\n\n{error_msg}")

    def _update_window_registry_raw_file(self, raw_file_path):
        """Update window registry mapping for this window's raw file."""
        self.raw_file_path = raw_file_path
        # Re-register with new raw file path
        self.state.window_registry.register_window(
            window_id=self.window_id,
            window_instance=self,
            raw_file_path=self.raw_file_path
        )

    def _load_initial_files(self):
        """Load the initial files provided via command line."""
        if self.initial_file_loaded:
            return
        if self.initial_files:
            for f in self.initial_files:
                ext = f.lower()
                if ext.endswith('.json'):
                    self._load_project(f)
                elif ext.endswith('.vcd'):
                    self._load_vcd(f, vcd_only=(self.raw_file is None))
                else:
                    self._load_raw_file(f)
            self.initial_file_loaded = True

    def _update_save_as_enabled(self) -> None:
        """Update the Save As Data File menu action based on source file count."""
        if self.menu_manager:
            self.menu_manager.set_save_as_data_enabled(
                len(self.state.source_files) <= 1
            )

    def _update_dataset_combo(self):
        """Update dataset combo box in control panel."""
        if self.raw_file:
            datasets = []
            for i, dataset in enumerate(self.raw_file.datasets):
                plotname = dataset.get('plotname', f'Dataset {i+1}')
                datasets.append(f"Dataset {i+1}: {plotname}")
            self.control_panel.set_datasets(datasets)

    def _update_variable_combo(self):
        """Update variable combo box in control panel (grouped by source)."""
        groups: dict[str, list[str]] = {}

        # Raw file vectors
        if self.raw_file and self.state.current_dataset_idx is not None:
            raw_vars = self.raw_file.get_variable_names(
                self.state.current_dataset_idx)
            if raw_vars:
                label = os.path.basename(self.raw_file.filename)
                groups[label] = list(raw_vars)

        # VCD vectors (from all panels, deduplicated)
        vcd_names: set[str] = set()
        vcd_label = ""
        for panel in self.panel_grid.panels.values():
            vf = panel.trace_manager.vcd_file
            if vf is not None:
                if not vcd_label:
                    vcd_label = os.path.basename(vf.filename)
                for n in vf.get_signal_names():
                    vcd_names.add(n)
        if vcd_names:
            groups[vcd_label] = sorted(vcd_names)

        if groups:
            self.control_panel.set_variables(groups)

    def _update_dataset_label(self):
        """Update dataset label in status bar."""
        if self.raw_file and self.raw_file.datasets:
            total_datasets = len(self.raw_file.datasets)
            current_dataset = self.state.current_dataset_idx + 1
            self.menu_manager.update_dataset_label(f"{current_dataset}/{total_datasets}")
        else:
            self.menu_manager.update_dataset_label("-")

    # Signal handlers

    @pyqtSlot(int)
    def _on_dataset_changed(self, index):
        """Handle dataset selection change."""
        self.state.current_dataset_idx = index
        self.trace_manager.set_current_dataset(index)
        self._update_variable_combo()
        self._update_dataset_label()
        # Clear trace expression as previous expression may not be valid for new dataset
        self.control_panel.clear_expression()

        # TODO: Update traces for new dataset

    @pyqtSlot(str)
    def _on_vector_selected(self, vector):
        """Handle vector selection."""
        if not vector:
            return

        target = self.control_panel.last_focused_expr
        current_text = target.text()

        # Only skip already-plotted vectors when trace expression is empty
        # (user wants to add as standalone trace). Allow insertion when there's
        # existing text so expressions like mean(v(r1)) can be composed.
        if target is self.control_panel.trace_expr and not current_text.strip():
            for var, _, _ in self.trace_manager.traces:
                if var == vector:
                    return
        if current_text:
            # Split by whitespace to check if vector already present in text
            parts = current_text.split()
            if vector in parts:
                return
            # If cursor is inside function parens, insert at cursor position
            if self._cursor_in_parens(current_text, target.cursorPosition()):
                target.insert(f" {vector} ")
                return
            new_text = f"{current_text} {vector}"
        else:
            new_text = vector
        target.setText(new_text)

    @staticmethod
    def _cursor_in_parens(text: str, pos: int) -> bool:
        """Check if cursor position is inside any parenthesized group."""
        return text[:pos].count('(') > text[:pos].count(')')

    @pyqtSlot(object)
    def _on_function_selected(self, info):
        """Insert a function, constant, or operator at the current cursor position."""
        from pqwave.ui.function_registry import FunctionInfo

        trace_expr = self.control_panel.trace_expr
        cursor = trace_expr.cursorPosition()

        if info.arg_count == 0:
            # Constant: insert name
            trace_expr.insert(info.name)
        else:
            # Function with arguments: insert name() and place cursor inside parens
            trace_expr.insert(f"{info.name}()")
            trace_expr.setCursorPosition(cursor + len(info.name) + 1)

    @pyqtSlot(object)
    def _on_measure_selected(self, info):
        """Insert a measure function signature into the measurement expression."""
        target = self.control_panel.measure_expr
        cursor = target.cursorPosition()

        if info.arg_count == 0:
            target.insert(info.name)
        else:
            target.insert(f"{info.name}()")
            target.setCursorPosition(cursor + len(info.name) + 1)

    @pyqtSlot()
    def _on_run_measure(self):
        """Evaluate measurement expression or script and show results."""
        expr = self.control_panel.get_measure_expression().strip()
        if not expr:
            QMessageBox.warning(self, "No Measurement",
                                "Enter a measurement expression or load a script file first.")
            return

        # File path detection: treat as script file if path exists on disk
        if os.path.isfile(expr):
            self._run_measure_script(expr)
        elif re.match(r'^\.?meas\s', expr, re.IGNORECASE):
            self._run_measure_script_text(expr)
        else:
            self._run_single_measure(expr)

    def _run_single_measure(self, expr: str):
        """Evaluate a single measurement expression."""
        self._ensure_measure_results()
        try:
            value = evaluate_measure(expr, self._measure_get_data)
            self._measure_results.add_result(expr, expr, value, "")
        except Exception as e:
            self._measure_results.add_error(expr, expr, str(e))
        self._measure_results.show()
        self._measure_results.raise_()

    def _run_measure_script(self, filepath: str):
        """Parse and execute a .meas-style script file."""
        self._ensure_measure_results()
        try:
            with open(filepath, 'r') as f:
                script_text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "File Error", f"Cannot read script file:\n{e}")
            return

        results = parse_meas_script(script_text)
        for expr, label in results:
            try:
                value = evaluate_measure(expr, self._measure_get_data)
                self._measure_results.add_result(label, expr, value, "")
            except Exception as e:
                self._measure_results.add_error(label, expr, str(e))
        self._measure_results.show()
        self._measure_results.raise_()

    def _run_measure_script_text(self, text: str):
        """Parse and execute .meas command(s) typed directly into the expr field."""
        self._ensure_measure_results()
        results = parse_meas_script(text)
        for expr, label in results:
            try:
                value = evaluate_measure(expr, self._measure_get_data)
                self._measure_results.add_result(label, expr, value, "")
            except Exception as e:
                self._measure_results.add_error(label, expr, str(e))
        self._measure_results.show()
        self._measure_results.raise_()

    def _ensure_measure_results(self):
        """Lazy-create the MeasureResultsWidget."""
        if self._measure_results is None:
            self._measure_results = MeasureResultsWidget(self)

    @pyqtSlot()
    def _on_from_script(self):
        """Open a file dialog to select a .meas-style script file."""
        if self.raw_file is None:
            QMessageBox.warning(self, "No Data", "Please open a SPICE output file first.")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Measurement Script", "",
            "Text Files (*.txt *.meas *.spice *.sp *.cir);;All Files (*)"
        )
        if not filepath:
            return

        self.control_panel.set_script_mode(filepath)

    @pyqtSlot(str)
    def _on_add_trace_to_axis(self, axis):
        """Handle add trace to axis button click."""
        expression = self.control_panel.trace_expr.text().strip()
        if not expression:
            QMessageBox.warning(self, "No Expression", "Please enter an expression first.")
            return

        # Strip [VCD] prefix from all variable names in the expression.
        # When multiple VCD signals are selected, each has the prefix.
        vcd_prefix = "[VCD] "
        expression = expression.replace(vcd_prefix, "")

        if axis == "X":
            # X button sets X-axis variable
            # For simplicity, treat whole expression as variable name
            x_var = expression.strip()
            # Validate it's a single variable (no spaces)
            if ' ' in x_var:
                QMessageBox.warning(self, "Invalid X-axis", "X-axis can only have one variable/expression.")
                return

            # Store X-axis variable
            self.state.current_x_var = x_var

            # Update X-axis label
            self.axis_manager.set_axis_label(AxisId.X, x_var)

            # Update all existing traces with the new X variable data
            if self.raw_file and self.state.current_dataset_idx is not None:
                x_data = self.raw_file.get_variable_data(x_var, self.state.current_dataset_idx)
                if x_data is not None:
                    self.axis_manager.auto_range_x_from_data(x_data, x_var)
                else:
                    QMessageBox.warning(
                        self, "Variable Not Found",
                        f"Variable '{x_var}' not found in the current dataset."
                    )
                    return

            # Redraw all existing traces against the new X variable
            self.trace_manager.update_x_variable(x_var)

            # Clear expression after successful addition
            self.control_panel.trace_expr.clear()
            logger.info(f"Set X-axis variable to: {x_var}")

        elif axis in ["Y1", "Y2"]:
            # Y1/Y2 buttons add traces
            # VCD-only mode: no X variable needed (VCD timestamps serve as X)
            panel = self.panel_grid.get_active_panel()
            vcd_only = (not self.raw_file and panel
                        and panel.trace_manager.vcd_file is not None)
            if vcd_only:
                x_var = "time"  # placeholder, _add_vcd_trace ignores it
            else:
                x_var = self._get_current_x_var()
                if not x_var:
                    QMessageBox.warning(self, "No X-axis", "Please select an X-axis variable.")
                    return

            # Map axis string to AxisAssignment.
            # Digital (VCD) traces always go to Y1 — a single stacking
            # axis avoids confusing the user with multiple Y scales.
            if axis == "Y2" and panel and panel.trace_manager.vcd_file:
                stripped = expression.strip('\'"').strip()
                if panel.trace_manager.vcd_file.get_signal(stripped):
                    axis = "Y1"

            if axis == "Y1":
                y_axis = AxisAssignment.Y1
            else:  # Y2
                y_axis = AxisAssignment.Y2

            # FFT detection: auto-create frequency-domain panel if needed
            target_trace_manager = self.trace_manager
            if TraceManager._is_fft_expression(expression):
                active_panel = self.panel_grid.get_active_panel()
                if active_panel and active_panel.domain != "frequency":
                    new_panel = self.panel_grid.split_panel(
                        self.panel_grid.active_panel_id, orientation="vertical"
                    )
                    if new_panel:
                        new_panel.domain = "frequency"
                        new_panel.axis_manager.set_axis_label(AxisId.X, "Frequency [Hz]")
                        target_trace_manager = new_panel.trace_manager
                        logger.info(
                            f"Created FFT panel {new_panel.panel_id} for: {expression}"
                        )
                    else:
                        QMessageBox.warning(
                            self, "Cannot Create FFT Panel",
                            "Maximum panel limit reached. Close a panel before adding FFT traces."
                        )
                        return

            # Add trace
            error_out = []
            trace = target_trace_manager.add_trace(expression, x_var, y_axis, error_out=error_out)
            if trace:
                logger.info(f"Added trace: {trace.name} to {y_axis.value}")
                # Clear expression after successful addition
                self.control_panel.trace_expr.clear()
            else:
                detail = error_out[0] if error_out else "Unknown error"
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to add trace: {detail}"
                )
        else:
            logger.warning(f"Unknown axis: {axis}")

    @pyqtSlot(str)
    def _on_expression_changed(self, expression):
        """Handle trace expression text change."""
        # Nothing to do here for now
        pass

    @pyqtSlot(float, float, float)
    def _on_mouse_moved(self, x, y1, y2):
        """Handle mouse movement in plot."""
        self.menu_manager.update_coordinate_label(x, y1, y2)

        # Trigger xschem back-annotation from cross-hair position when ON
        if self.plot_widget.cross_hair_visible:
            self._xschem_ba_x = x  # x is already in linear space
            self._xschem_ba_timer.start()

    @pyqtSlot()
    def _on_mouse_left(self):
        """Handle mouse leaving plot."""
        self.menu_manager.update_coordinate_label(None, None, None)

    @pyqtSlot(float)
    def _on_cursor_xa_changed(self, value):
        """Handle X1 cursor position change — triggers back-annotation + status update."""
        # Convert ViewBox coordinate to linear space if X axis is in log mode
        x_linear = value
        if self.plot_widget.get_axis_log_mode('X'):
            x_linear = self.plot_widget._log_to_linear(value)

        # Store X value and start debounce timer for back-annotation
        self._pending_x_value = x_linear
        self._backannotation_timer.start()

        # Also trigger xschem schematic back-annotation
        self._xschem_ba_x = x_linear
        self._xschem_ba_timer.start()

        self._update_cursor_status()
        self._sync_x_cursor_to_same_domain_panels('XA', value)

    @pyqtSlot(float)
    def _on_cursor_xb_changed(self, value):
        """Handle X2 cursor position change — triggers xschem back-annotation + status update."""
        self._update_cursor_status()

        # Convert ViewBox coordinate to linear space if X axis is in log mode
        x_linear = value
        if self.plot_widget.get_axis_log_mode('X'):
            x_linear = self.plot_widget._log_to_linear(value)

        # Store and start debounce timer for xschem back-annotation
        self._xschem_ba_x = x_linear
        self._xschem_ba_timer.start()

        self._sync_x_cursor_to_same_domain_panels('XB', value)

    @pyqtSlot(float)
    def _on_cursor_yA_changed(self, value):
        """Handle YA cursor position change."""
        self._update_cursor_status()

    @pyqtSlot(float)
    def _on_cursor_yB_changed(self, value):
        """Handle YB cursor position change."""
        self._update_cursor_status()

    @pyqtSlot(float)
    def _on_cursor_y2_changed(self, value):
        """Handle Y2 cursor position change (Y2-axis-specific cursor)."""
        pass

    def _sync_x_cursor_to_same_domain_panels(self, cursor_type: str, value: float) -> None:
        """Sync XA/XB cursor position to all same-domain panels.

        Uses silent setters (blockSignals) to avoid infinite signal loops.
        Only syncs X cursors; Y cursors are per-panel.
        """
        if self._cursor_sync_in_progress:
            return
        active_panel = self.panel_grid.get_active_panel()
        if active_panel is None:
            return
        active_domain = active_panel.domain

        self._cursor_sync_in_progress = True
        try:
            for panel_id, panel in self.panel_grid.panels.items():
                if panel_id == self.panel_grid.active_panel_id:
                    continue
                if panel.domain != active_domain:
                    continue
                if cursor_type == 'XA':
                    panel.plot_widget.set_xa_cursor_position(value)
                elif cursor_type == 'XB':
                    panel.plot_widget.set_xb_cursor_position(value)
        finally:
            self._cursor_sync_in_progress = False

    def _update_cursor_status(self) -> None:
        """Read cursor positions and deltas, update status bar and legend."""
        positions = self.plot_widget.get_cursor_positions()
        deltas = self.plot_widget.get_cursor_deltas()
        if self.menu_manager:
            self.menu_manager.update_cursor_status(positions, deltas)
        self._update_legend_cursor_values()

    def _update_legend_cursor_values(self) -> None:
        """Update trace legend with Y values at visible X cursor positions."""
        positions = self.plot_widget.get_cursor_positions()
        xa = positions.get('xa')
        xb = positions.get('xb')

        # Convert viewbox coordinates to linear space for data interpolation
        xa_lin = (self.plot_widget._log_to_linear(xa)
                  if xa is not None and self.plot_widget._x_log_mode
                  else xa)
        xb_lin = (self.plot_widget._log_to_linear(xb)
                  if xb is not None and self.plot_widget._x_log_mode
                  else xb)

        self.trace_manager.update_legend_cursor_values(xa_lin, xb_lin)

    def _send_data_point_update_debounced(self):
        """Send data point update after debounce timer fires."""
        if self._pending_x_value is not None:
            self._send_data_point_update(self._pending_x_value)
            self._pending_x_value = None

    def _xschem_ba_debounced(self):
        """Send xschem back-annotation after debounce timer fires."""
        if self._xschem_ba_x is not None:
            self._send_xschem_backannotation(self._xschem_ba_x)
            self._xschem_ba_x = None

    def _send_xschem_backannotation(self, x_value: float):
        """Send cursor X position to xschem via TCP for schematic back-annotation.

        Opens a short-lived TCP connection to xschem's built-in command server
        (xschem_listen_port) and sends:

            xschem set annotate_cursor_x <value>

        The connection is closed immediately after sending. Failures are silently
        logged (xschem not running, port not open, etc.).
        """
        try:
            sock = socket.create_connection(('localhost', self._xschem_ba_port), timeout=0.5)
            msg = f"xschem set annotate_cursor_x {x_value:.10g}\n"
            sock.sendall(msg.encode('utf-8'))
            sock.close()
            logger.debug(f"xschem back-annotation sent: x={x_value:.10g}")
        except (socket.error, ConnectionRefusedError, OSError) as e:
            logger.debug(f"xschem back-annotation connection failed: {e}")

    def _send_data_point_update(self, x_value: float):
        """
        Send data point update to all xschem clients connected to this window.

        Args:
            x_value: X coordinate in linear space
        """
        logger.debug(f"_send_data_point_update called with x={x_value}")
        if self.state is None or self.state.command_handler is None:
            logger.debug("State or command_handler is None, returning")
            return

        # Query data points at this X coordinate
        results = self._query_data_point(x_value)
        if not results:
            return

        # Get all clients associated with this window
        registry = self.state.window_registry
        clients = registry.get_clients_for_window(self.window_id)
        logger.debug(f"Found {len(clients)} clients for window {self.window_id}: {clients}")
        if not clients:
            logger.debug("No clients found for this window")
            return

        # Prepare data for JSON serialization (similar to get_data_point response)
        serializable_results = []
        for res in results:
            res_copy = res.copy()
            y_val = res_copy.get('y_value')
            if isinstance(y_val, complex) or np.iscomplexobj(y_val):
                # Replace with magnitude/phase representation
                res_copy['y_value'] = {
                    'magnitude': float(np.abs(y_val)),
                    'phase_deg': float(np.angle(y_val, deg=True)),
                    'real': float(y_val.real),
                    'imag': float(y_val.imag)
                }
            elif isinstance(y_val, (np.floating, np.integer)):
                res_copy['y_value'] = float(y_val)
            # y_nearest may also be complex
            y_nearest = res_copy.get('y_nearest')
            if isinstance(y_nearest, complex) or np.iscomplexobj(y_nearest):
                res_copy['y_nearest'] = {
                    'magnitude': float(np.abs(y_nearest)),
                    'phase_deg': float(np.angle(y_nearest, deg=True)),
                    'real': float(y_nearest.real),
                    'imag': float(y_nearest.imag)
                }
            elif isinstance(y_nearest, (np.floating, np.integer)):
                res_copy['y_nearest'] = float(y_nearest)
            # Convert numpy bool to Python bool
            out_of_range = res_copy.get('out_of_range')
            if isinstance(out_of_range, np.bool_):
                res_copy['out_of_range'] = bool(out_of_range)
            serializable_results.append(res_copy)

        # Send update to each client
        for client_addr in clients:
            # Create update message (similar to get_data_point response but with different command)
            update_msg = {
                "command": "data_point_update",
                "data": {
                    "x": x_value,
                    "traces": serializable_results
                },
                "timestamp": time.time() if 'time' in sys.modules else 0
            }

            # Send via command handler with "json " prefix (xschem expects this format)
            # Get xschem server from command handler
            xschem_server = self.state.command_handler.xschem_server
            if xschem_server is None:
                logger.warning(f"Cannot send data_point_update: xschem server not available")
                continue

            # Parse client address string
            try:
                ip_str, port_str = client_addr.split(':')
                client_addr_tuple = (ip_str, int(port_str))
            except (ValueError, TypeError):
                logger.error(f"Invalid client address format: {client_addr}")
                continue

            # Find client socket
            client_socket = xschem_server.clients.get(client_addr_tuple)
            if not client_socket:
                logger.warning(f"Client socket not found: {client_addr}")
                continue

            # Send JSON command with "json " prefix
            try:
                json_str = json.dumps(update_msg)
                line = f"json {json_str}"
                logger.debug(f"Sending data_point_update to {client_addr}: {line[:100]}...")
                client_socket.sendall((line + '\n').encode('utf-8'))
                logger.debug(f"Sent data_point_update to {client_addr}: x={x_value}")
            except (socket.error, TypeError) as e:
                logger.error(f"Failed to send data_point_update to {client_addr}: {e}")

    # (Cross-hair mark handlers follow below)

    @pyqtSlot(str, bool)
    def _on_axis_log_mode_changed(self, orientation, log_mode):
        """Handle axis log mode change from plot widget."""
        # This signal comes from plot widget's LogAxisItem
        # AxisManager should already handle this via its connection
        # We just need to update trace manager
        self._update_trace_manager_log_modes()

        # Update traces for new log mode
        self.trace_manager.update_traces_for_log_mode()

        # Auto-range the affected axis so the view adjusts to the
        # log10-transformed data range (otherwise the ViewBox keeps
        # its previous linear range, clustering all data at x=0).
        axis_map = {'bottom': AxisId.X, 'left': AxisId.Y1, 'right': AxisId.Y2}
        axis_id = axis_map.get(orientation)
        if axis_id is not None:
            self.axis_manager.auto_range_axis(axis_id)

    @pyqtSlot(str, bool)
    def _on_axis_log_mode_changed_from_manager(self, axis_id, log_mode):
        """Handle axis log mode change from axis manager."""
        # Update trace manager
        self._update_trace_manager_log_modes()

        # Update traces for new log mode
        self.trace_manager.update_traces_for_log_mode()

        # Auto-range the affected axis so the view adjusts to the
        # log10-transformed data range.
        self.axis_manager.auto_range_axis(AxisId(axis_id))

    @pyqtSlot(str, float, float)
    def _on_axis_range_changed(self, axis_id, min_val, max_val):
        """Handle axis range change."""
        # TODO: Update range display if needed
        pass

    @pyqtSlot(str, str)
    def _on_axis_label_changed(self, axis_id, label):
        """Handle axis label change."""
        # TODO: Update label display if needed
        pass

    # Helper methods

    def _get_current_x_var(self):
        """Get current X-axis variable name."""
        # Return stored X variable if set
        if self.state.current_x_var:
            return self.state.current_x_var

        # Otherwise return first variable if available
        if self.raw_file and self.state.current_dataset_idx is not None:
            var_names = self.raw_file.get_variable_names(self.state.current_dataset_idx)
            if var_names:
                return var_names[0]
        return None

    def _measure_get_data(self, name: str):
        """Look up (x_data, y_data) for a vector name in the current dataset.

        Falls back to expression evaluation when the name is not a simple
        variable (e.g. 'v(ac_p)-v(ac_n)').

        Returns (x_data, y_data) as numpy arrays, or None if not found.
        """
        if self.raw_file is None or self.state.current_dataset_idx is None:
            return None

        y_data = self.raw_file.get_variable_data(name, self.state.current_dataset_idx)
        if y_data is None:
            # Try evaluating as an expression (e.g., v(ac_p)-v(ac_n))
            try:
                from pqwave.models.expression import ExprEvaluator
                evaluator = ExprEvaluator(self.raw_file, self.state.current_dataset_idx)
                y_data = evaluator.evaluate(name)
            except Exception:
                return None

        if y_data is None:
            return None

        x_var = self._get_current_x_var()
        x_data = None
        if x_var:
            x_data = self.raw_file.get_variable_data(x_var, self.state.current_dataset_idx)
        if x_data is None:
            x_data = self.raw_file.get_variable_data("time", self.state.current_dataset_idx)
        if x_data is None:
            x_data = np.arange(len(y_data))

        return (x_data, y_data)

    def _show_error(self, title, message):
        """Show error message dialog."""
        logger.error(f"{title}: {message}")
        QMessageBox.warning(self, title, message)

    # Public API for testing

    def get_plot_widget(self):
        """Get plot widget reference (for testing)."""
        return self.plot_widget

    def get_control_panel(self):
        """Get control panel reference (for testing)."""
        return self.control_panel

    def get_trace_manager(self):
        """Get trace manager reference (for testing)."""
        return self.trace_manager

    def get_axis_manager(self):
        """Get axis manager reference (for testing)."""
        return self.axis_manager

    def _global_prefs_path(self) -> str:
        """Return the path to the global preferences JSON file."""
        config_dir = os.path.join(os.path.expanduser("~"), ".pqwave")
        return os.path.join(config_dir, "prefs.json")

    def _save_global_prefs(self) -> None:
        """Save global preferences (theme, fonts, UI toggles) to disk."""
        filepath = self._global_prefs_path()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            data = {
                'viewbox_theme': self.state.viewbox_theme.value,
                'title_font': self.state.title_font.to_dict(),
                'label_font': self.state.label_font.to_dict(),
                'tick_font': self.state.tick_font.to_dict(),
                'ui_font': self.state.ui_font.to_dict(),
                'repl_font': self.state.repl_font.to_dict(),
                'repl_bg': self.state.repl_bg,
                'toolbar_visible': self.state.toolbar_visible,
                'status_bar_visible': self.state.status_bar_visible,
                'chat_panel_visible': self.state.chat_panel_visible,
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save global preferences to %s: %s", filepath, e)

    def _load_global_prefs(self) -> None:
        """Load global preferences from disk and apply to singleton."""
        filepath = self._global_prefs_path()
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Failed to load global preferences from %s: %s", filepath, e)
            try:
                os.remove(filepath)
            except OSError:
                pass
            return

        # Viewbox theme
        theme_str = data.get('viewbox_theme', 'dark')
        try:
            self.state.viewbox_theme = ViewboxTheme(theme_str)
            self.plot_widget.set_viewbox_theme(self.state.viewbox_theme)
        except ValueError as e:
            logger.warning("Invalid viewbox theme in preferences: %s", e)

        # Font configs
        self.state.title_font = FontConfig.from_dict(data.get('title_font', {}))
        self.state.label_font = FontConfig.from_dict(data.get('label_font', {}))
        self.state.tick_font = FontConfig.from_dict(data.get('tick_font', {}))
        self.state.ui_font = FontConfig.from_dict(data.get('ui_font', {}))
        self.state.repl_font = FontConfig.from_dict(data.get('repl_font', {}))
        self.state.repl_bg = data.get('repl_bg', '')
        self.plot_widget.apply_fonts(self.state)
        self._apply_ui_font()
        self._apply_repl_settings()

        # UI toggles
        self.state.toolbar_visible = data.get('toolbar_visible', True)
        self.state.status_bar_visible = data.get('status_bar_visible', True)
        self.state.chat_panel_visible = data.get('chat_panel_visible', False)
        self.set_toolbar_visible(self.state.toolbar_visible)
        self.set_statusbar_visible(self.state.status_bar_visible)
        if self.state.chat_panel_visible and hasattr(self, 'chat_panel'):
            self.chat_panel.setVisible(True)

    def _restore_panels_from_dict(self, data: dict) -> None:
        """Restore state from new per-panel format.

        Maps saved panels to existing panels by position in panel_order,
        since runtime UUIDs differ from saved UUIDs across sessions.
        """
        self._restoring_state = True
        saved_panels = data.get('panels', {})
        saved_order = data.get('panel_order', [])
        saved_active = data.get('active_panel_id', '')

        if not saved_order:
            self._restoring_state = False
            return

        # Build position-based mapping: saved index → current panel_id
        current_order = list(self.state.panel_order)
        saved_to_current: dict[int, str] = {}

        # Ensure panel count matches: create extras if needed
        saved_layout = data.get('panel_layout', [])
        while len(current_order) < len(saved_order):
            last_pid = current_order[-1] if current_order else None
            if last_pid is None:
                break
            split_idx = len(current_order) - 1
            if split_idx < len(saved_layout):
                orientation = saved_layout[split_idx]
            else:
                orientation = "vertical"
            new_panel = self.panel_grid.split_panel(last_pid, orientation=orientation)
            if new_panel is None:
                break
            current_order = list(self.state.panel_order)

        # Close extra panels if saved state has fewer than current
        while len(current_order) > len(saved_order) and len(current_order) > 1:
            extra_pid = current_order[-1]
            if not self.panel_grid.close_panel(extra_pid):
                break
            current_order = list(self.state.panel_order)

        # Map saved panel data to current panels by position
        for i, saved_pid in enumerate(saved_order):
            if i < len(current_order):
                saved_to_current[i] = current_order[i]
                pdata = saved_panels.get(saved_pid, {})
                ps = self.state.panels.get(current_order[i])
                if ps and pdata:
                    if 'axis_configs' in pdata:
                        for key, ax_data in pdata['axis_configs'].items():
                            try:
                                axis_id = AxisId(key)
                                ps.axis_configs[axis_id] = AxisConfig.from_dict(ax_data)
                            except ValueError:
                                continue
                    if 'current_x_var' in pdata:
                        ps.current_x_var = pdata['current_x_var']
                    if 'domain' in pdata:
                        ps.domain = pdata['domain']
                    if 'is_eye_diagram' in pdata:
                        ps.is_eye_diagram = pdata['is_eye_diagram']
                        ps.eye_diagram_trace_name = pdata.get(
                            'eye_diagram_trace_name', '')

        # Restore active panel by position
        if saved_active and saved_active in saved_order:
            saved_idx = saved_order.index(saved_active)
            if saved_idx in saved_to_current:
                new_active_id = saved_to_current[saved_idx]
                self.state.active_panel_id = new_active_id
                # Bypass panel_activated signal during restoration
                self.panel_grid.set_active_panel_id(new_active_id)
                panel = self.panel_grid.get_panel(new_active_id)
                if panel is not None:
                    panel.set_active(True)

        if not self.state.active_panel_id or self.state.active_panel_id not in self.state.panels:
            self.state.active_panel_id = self.panel_grid.active_panel_id

        # Apply axis configs, log modes, and traces to every panel
        _prev_active_id = self.state.active_panel_id

        for i, saved_pid in enumerate(saved_order):
            if i not in saved_to_current:
                continue
            pid = saved_to_current[i]
            panel = self.panel_grid.get_panel(pid)
            if panel is None:
                continue
            pdata = saved_panels.get(saved_pid, {})
            if not pdata:
                continue

            self.state.active_panel_id = pid
            self.panel_grid.set_active_panel_id(pid)

            panel.axis_manager._initialize_axes()
            self._update_trace_manager_log_modes()

            # Eye diagram panels: skip trace plotting; render eye instead.
            if pdata.get('is_eye_diagram'):
                trace_name = pdata.get('eye_diagram_trace_name', '')
                y_data = self._load_eye_trace_data(trace_name)
                if y_data is not None:
                    panel.axis_manager.set_axis_log_mode(AxisId.X, False)
                    panel.axis_manager.set_axis_log_mode(AxisId.Y1, False)
                    self._render_eye_diagram(panel, y_data, trace_name)
            else:
                x_var = pdata.get('current_x_var', 'time')
                self.state.current_x_var = x_var
                self._restore_traces_from_data(pdata.get('traces', []), x_var)

        # Restore the active panel for subsequent title/grid/legend setup
        if _prev_active_id and _prev_active_id in self.state.panels:
            self.state.active_panel_id = _prev_active_id
            self.panel_grid.set_active_panel_id(_prev_active_id)

        # Restore plot title and toggles
        title = data.get('plot_title', '')
        if title:
            self.state.plot_title = title
            self.plot_widget.set_plot_title(title)
        self.state.grid_visible = data.get('grid_visible', True)
        self.state.legend_visible = data.get('legend_visible', True)
        self.axis_manager.set_grid_visible(self.state.grid_visible)
        self.menu_manager.set_grids_visible(self.state.grid_visible)
        self.set_legend_visible(self.state.legend_visible)

        self._restoring_state = False

    def _restore_traces_from_data(self, saved_traces: list, x_var: str) -> None:
        """Re-create traces from saved data and restore visual properties."""
        failed_expressions = []
        for t_data in saved_traces:
            expression = t_data.get('expression', '')
            if not expression:
                continue

            y_axis_str = t_data.get('y_axis', 'Y1')
            y_axis = AxisAssignment.Y1 if y_axis_str == 'Y1' else AxisAssignment.Y2
            color = tuple(t_data.get('color', (0, 0, 255)))

            error_out = []
            trace = self.trace_manager.add_trace(
                expression=expression,
                x_var_name=x_var,
                y_axis=y_axis,
                custom_color=color,
                error_out=error_out,
            )
            if trace is None:
                detail = error_out[0] if error_out else "unknown error"
                failed_expressions.append(f"{expression}: {detail}")
                logger.warning("Failed to restore trace '%s': %s", expression, detail)

        if failed_expressions:
            joined = "\n".join(failed_expressions[:10])
            if len(failed_expressions) > 10:
                joined += f"\n... and {len(failed_expressions) - 10} more"
            logger.warning(
                "Failed to restore %d trace(s) during project load:\n%s",
                len(failed_expressions), joined)

        # Apply saved visual properties (name alias, line width, visibility)
        for saved_t in saved_traces:
            expr = saved_t.get('expression', '')
            if not expr:
                continue
            for st in self.state.traces:
                if st.expression == expr:
                    st.name = saved_t.get('name', expr)
                    st.line_width = saved_t.get('line_width', 1.0)
                    st.visible = saved_t.get('visible', True)
                    st.selected = saved_t.get('selected', False)
                    break

        # Update plot-item pens and names to match state traces
        for i, (_, plot_item, _y_axis) in enumerate(self.trace_manager.traces):
            if i < len(self.state.traces):
                st = self.state.traces[i]
                pen = pg.mkPen(color=st.color, width=st.line_width)
                plot_item.setPen(pen)
                plot_item.opts['name'] = st.name

        # Refresh legend with updated names
        self.trace_manager._refresh_legend()

    def _restore_flat_state_from_dict(self, data: dict) -> None:
        """Restore state from old flat format (backward compat)."""
        # Apply axis configs before adding traces (log mode must be correct)
        if 'axis_configs' in data:
            for key, ax_data in data['axis_configs'].items():
                try:
                    axis_id = AxisId(key)
                    self.state.axis_configs[axis_id] = AxisConfig.from_dict(ax_data)
                except ValueError:
                    continue
            self.axis_manager._initialize_axes()

        # Sync trace manager log modes before re-creating traces
        self._update_trace_manager_log_modes()

        # Apply plot title
        title = data.get('plot_title', '')
        if title:
            self.state.plot_title = title
            self.plot_widget.set_plot_title(title)

        # Apply UI toggles
        self.state.grid_visible = data.get('grid_visible', True)
        self.state.legend_visible = data.get('legend_visible', True)
        self.axis_manager.set_grid_visible(self.state.grid_visible)
        self.menu_manager.set_grids_visible(self.state.grid_visible)
        self.set_legend_visible(self.state.legend_visible)

        # Set current X variable
        self.state.current_x_var = data.get('current_x_var', self.state.current_x_var)

        # Re-create traces from saved expressions
        x_var = self.state.current_x_var
        self._restore_traces_from_data(data.get('traces', []), x_var)

    def save_current_state(self) -> None:
        """Save project to JSON (Ctrl+S / File > Save Project).

        First save: prompts for path (Save As). Subsequent saves: silent.
        """
        if self._project_path is None:
            self._save_project_as()
        else:
            self._save_project(self._project_path)

    def _save_project_as(self) -> None:
        """File > Save Project As — always prompts for path."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "",
            "Project Files (*.json);;All Files (*)"
        )
        if path:
            if not path.endswith('.json'):
                path += '.json'
            self._project_path = path
            self._save_project(path)

    def _save_project(self, path: str) -> None:
        """Write the current project state to *path*."""
        base_dir = os.path.dirname(os.path.abspath(path))

        # Update relative paths
        for sf in self.state.source_files:
            try:
                sf.relative_path = os.path.relpath(sf.path, base_dir)
            except ValueError:
                sf.relative_path = sf.path

        data = self.state.to_per_file_dict()
        data['source_files'] = [sf.to_dict() for sf in self.state.source_files]
        data['version'] = 2
        data['panel_layout'] = self.panel_grid.get_layout_splits()

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Project saved to {path}")
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save project:\n{e}"
            )

    def closeEvent(self, event):
        """Handle window close event."""
        self._save_global_prefs()
        self.state.window_registry.unregister_window(self.window_id)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Keyboard shortcuts (plot-contextual and log-toggles)
    # ------------------------------------------------------------------

    def _install_keyboard_shortcuts(self) -> None:
        """Install keyboard shortcuts that should only fire on the plot widget.

        Single-key toggles (A, B, z, f, +) and arrow keys are installed on the
        central widget with ``WidgetWithChildrenShortcut`` so they don't fire
        when the user is typing in the trace expression input.

        Log-mode toggles (Ctrl+Shift+X/Y/Z) are also installed here since they
        don't have corresponding menu actions.
        """
        from PyQt6.QtGui import QShortcut, QKeySequence
        from PyQt6.QtCore import Qt as QtCore

        pw = self.plot_widget
        ctx_widget = self.centralWidget()
        ctxt = QtCore.ShortcutContext.WidgetWithChildrenShortcut
        seq = self.keybinding_manager.get_sequence

        # ---- single-key toggles (only when plot area has focus) ----
        toggle_map = {
            'toggle_xa_cursor':  lambda: self._toggle_x_cursor_a(not self.plot_widget.cursor_xa_visible),
            'toggle_xb_cursor':  lambda: self._toggle_x_cursor_b(not self.plot_widget.cursor_xb_visible),
            'toggle_ya_cursor':  lambda: self._toggle_y_cursor_A(not self.plot_widget.cursor_yA_visible),
            'toggle_yb_cursor':  lambda: self._toggle_y_cursor_B(not self.plot_widget.cursor_yB_visible),
            'toggle_cross_hair': lambda: self.toggle_cross_hair(),
            'toggle_zoom_box':   lambda: self.enable_zoom_box(),
            'zoom_to_fit_alt':   lambda: self.zoom_to_fit(),
        }

        for action_name, callback in toggle_map.items():
            ks = seq(action_name)
            if ks:
                # For single-character shortcuts, use the character directly.
                # QShortcut with WidgetWithChildrenShortcut will not fire
                # when the trace-expression input has focus.
                sc = QShortcut(QKeySequence(ks), ctx_widget)
                sc.setContext(ctxt)
                sc.activated.connect(callback)

        # ---- arrow keys for cursor movement (plot-contextual) ----
        arrow_map = {
            'move_x_cursor_left':  lambda: pw.move_selected_cursor('left'),
            'move_x_cursor_right': lambda: pw.move_selected_cursor('right'),
            'move_y_cursor_up':    lambda: pw.move_selected_cursor('up'),
            'move_y_cursor_down':  lambda: pw.move_selected_cursor('down'),
        }
        for action_name, callback in arrow_map.items():
            ks = seq(action_name)
            if ks:
                sc = QShortcut(QKeySequence(ks), ctx_widget)
                sc.setContext(ctxt)
                sc.activated.connect(callback)

        # ---- log-mode toggles (global, no menu action) ----
        log_map = {
            'log_x':  lambda: self._toggle_log_axis(AxisId.X),
            'log_y1': lambda: self._toggle_log_axis(AxisId.Y1),
            'log_y2': lambda: self._toggle_log_axis(AxisId.Y2),
        }
        for action_name, callback in log_map.items():
            ks = seq(action_name)
            if ks:
                sc = QShortcut(QKeySequence(ks), self)
                sc.activated.connect(callback)

        # ---- chat panel toggle (global) ----
        ks = seq('toggle_chat_panel')
        if ks and hasattr(self, 'chat_panel'):
            sc = QShortcut(QKeySequence(ks), self)
            sc.activated.connect(self.chat_panel.toggle)

        # ---- digital signal operations (global) ----
        digital_map = {
            'toggle_digital_analog': self._toggle_digital_analog,
            'group_bus':             self._group_bus,
            'eye_diagram':           self._show_eye_diagram,
            'threshold_settings':    self._show_threshold_settings,
        }
        for action_name, callback in digital_map.items():
            ks = seq(action_name)
            if ks:
                sc = QShortcut(QKeySequence(ks), self)
                sc.activated.connect(callback)

        # ---- trace operations (plot-contextual) ----
        trace_map = {
            'remove_trace':      self._remove_selected_trace,
            'add_all_signals':   self._add_all_signals,
            'remove_all_traces': self._remove_all_traces,
        }
        for action_name, callback in trace_map.items():
            ks = seq(action_name)
            if ks:
                sc = QShortcut(QKeySequence(ks), ctx_widget)
                sc.setContext(ctxt)
                sc.activated.connect(callback)

    def _remove_selected_trace(self) -> None:
        """Remove the currently selected trace(s)."""
        tm = self.trace_manager
        if tm is not None:
            tm.remove_selected_traces()

    def _add_all_signals(self) -> None:
        """Add all available signals to the active panel."""
        if self._repl is not None:
            result = self._repl._session.add_all()
            shown = result.get("shown", [])
            if shown:
                self.chat_panel.append_output(
                    f"Added {len(shown)} signal(s)\n")
            else:
                self.chat_panel.append_output(
                    "No signals to add (file loaded?)\n")

    def _remove_all_traces(self) -> None:
        """Remove all traces from the active panel."""
        if self._repl is not None:
            self._repl._session.remove_all()

    def _toggle_log_axis(self, axis_id: AxisId) -> None:
        """Toggle log/linear mode for an axis."""
        config = self.state.get_axis_config(axis_id)

        # Block enabling Y log mode when FFT traces are on that axis
        # (FFT Y data is already in dB, so log mode would double-log it)
        if axis_id in (AxisId.Y1, AxisId.Y2) and not config.log_mode:
            axis_str = axis_id.value
            if any(
                t.expression.lower().startswith('fft(')
                and t.y_axis.value == axis_str
                for t in self.state.traces
            ):
                QMessageBox.information(
                    self, "Log Y Not Available",
                    "FFT traces are already in dB (log scale). "
                    "Log Y mode is not applicable."
                )
                return

        self.axis_manager.set_axis_log_mode(axis_id, not config.log_mode)

    def _show_keybindings(self) -> None:
        """Open the Keybindings help dialog."""
        bindings = self.keybinding_manager.get_all_bindings()
        config_path = self.keybinding_manager._config_path()
        dialog = KeyBindingsDialog(bindings, config_path, self)
        dialog.exec()

    def _show_functions_help(self) -> None:
        """Open the Functions Reference help dialog."""
        dialog = FunctionsHelpDialog(self)
        dialog.exec()

    def _show_measures_help(self) -> None:
        """Open the Measures Reference help dialog."""
        dialog = MeasuresHelpDialog(self)
        dialog.exec()

    def _show_vector_selection_help(self) -> None:
        """Open a help dialog explaining the vector selection widget."""
        from PyQt6.QtWidgets import QMessageBox
        msg = (
            "The Vectors selector lets you pick signals from all loaded files.\n\n"
            "  • Check a box to mark a vector for insertion.\n"
            "  • Ctrl+click a name to add or remove it from the selection.\n"
            "  • Shift+click to select a contiguous range.\n"
            "  • Double-click a single name to add it immediately.\n"
            "  • Close the popup (click outside, press Esc, or click ▼)\n"
            "    to emit all checked vectors at once.\n"
            "  • Use the Filter bar to narrow the list by name substring.\n\n"
            "Checked vectors appear in the Add Trace expression field\n"
            "separated by spaces and can be edited before adding."
        )
        QMessageBox.information(self, "Help — Select Vectors", msg)

    def _show_repl_help(self) -> None:
        """Show REPL usage help."""
        from pqwave.ui.repl_help_dialog import ReplHelpDialog
        dialog = ReplHelpDialog(self)
        dialog.exec()

    def _show_api_help(self) -> None:
        """Show API command reference."""
        from pqwave.ui.api_help_dialog import ApiHelpDialog
        dialog = ApiHelpDialog(self)
        dialog.exec()

    def _show_mc_guide(self) -> None:
        """Show the Monte Carlo user guide."""
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox, QMessageBox,
        )

        from pathlib import Path
        guide_path = Path(__file__).parent.parent.parent / "docs" / "monte_carlo" / "guide.html"
        if not guide_path.exists():
            QMessageBox.warning(
                self, "Not Found",
                f"Monte Carlo guide not found at:\n{guide_path}",
            )
            return

        try:
            html = guide_path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(
                self, "Error",
                f"Failed to read Monte Carlo guide:\n{e}",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Monte Carlo Guide")
        dialog.resize(780, 620)

        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setHtml(html)
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    @staticmethod
    def _fuzzy_signal_match(expr: str, signals: list[str]) -> str | None:
        """Return the best fuzzy match for *expr* among *signals*, or None."""
        if not signals:
            return None
        q = expr.strip().strip('"\'').lower()
        # 1. Case-insensitive exact match
        for s in signals:
            if s.lower() == q:
                return s
        # 2. Case-insensitive prefix match (shortest first)
        prefix_matches = [s for s in signals if s.lower().startswith(q)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        # 3. Case-insensitive substring match
        substring_matches = [s for s in signals if q in s.lower()]
        if len(substring_matches) == 1:
            return substring_matches[0]
        return None

    def _show_scrollable_help(self, title: str, text: str) -> None:
        """Show help text in a scrollable dialog."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QPlainTextEdit,
                                      QDialogButtonBox)
        from PyQt6.QtGui import QFont
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(650, 550)

        layout = QVBoxLayout(dlg)

        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        font = QFont("monospace", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        edit.setFont(font)
        edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(edit, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        dlg.exec()

    def _compute_trace_stats(self) -> None:
        """Compute statistics for selected traces over the visible X range."""
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        tm = panel.trace_manager
        selected = tm.get_selected_traces()
        if not selected:
            if not tm.traces:
                QMessageBox.information(self, "No Traces",
                                        "No traces plotted.")
                return
            selected = [(i, t) for i, t in enumerate(tm.state.traces)]
        tm._show_stats_for_traces(selected)

    def _compute_power_analysis(self) -> None:
        """Compute power analysis for V and I traces over the visible range."""
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        tm = panel.trace_manager
        selected = tm.get_selected_traces()
        if len(selected) != 2:
            QMessageBox.warning(
                self, "Select Two Traces",
                "Select one voltage and one current trace "
                "via Ctrl+click in the legend, then try again."
            )
            return
        v_trace = selected[0][1]
        i_trace = selected[1][1]
        xmin, xmax = panel.plot_widget.plotItem.vb.viewRange()[0]
        if tm.x_log:
            xmin, xmax = 10.0 ** xmin, 10.0 ** xmax
        dlg = PowerAnalysisDialog(self)
        dlg.set_data(
            v_trace.name, i_trace.name,
            v_trace.y_data, i_trace.y_data, v_trace.x_data,
            xmin, xmax,
        )
        dlg.show()

    def _show_histogram(self) -> None:
        """Compute and display histogram in a new split panel."""
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        state = panel.state
        if not state.traces:
            self.statusBar().showMessage("No traces to histogram", 3000)
            return

        from pqwave.ui.histogram_dialog import HistogramDialog
        dlg = HistogramDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        config = dlg.get_config()
        # Prefer selected traces; fall back to first trace
        selected = panel.trace_manager.get_selected_traces()
        if selected:
            trace = selected[0][1]  # (index, Trace) tuple
        else:
            trace = state.traces[0]
        y_data = trace.y_data if trace.y_data is not None else np.array([])

        # Filter to visible X-range if no explicit range given
        if config.range is None and trace.x_data is not None and len(trace.x_data) == len(y_data):
            x_range = panel.plot_widget.getViewBox().viewRange()[0]
            mask = (trace.x_data >= x_range[0]) & (trace.x_data <= x_range[1])
            y_data = y_data[mask]

        from pqwave.analysis.histogram import compute_histogram
        result = compute_histogram(
            y_data, bins=config.bins, range=config.range, norm=config.norm,
        )

        new_panel = self.panel_grid.split_panel(
            self.panel_grid.active_panel_id, orientation="vertical")
        if new_panel is None:
            return

        import pyqtgraph as pg
        width = (np.diff(result["edges"])[0]
                 if len(result["edges"]) > 1 else 1.0)
        bar_item = pg.BarGraphItem(
            x=result["centers"], height=result["counts"],
            width=width,
            brush=(100, 149, 237, 180),
        )
        new_panel.plot_widget.addItem(bar_item)
        new_panel.plot_widget.autoRange()

    def _show_nyquist(self) -> None:
        """Compute and display Nyquist plot in a new split panel."""
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        if self.raw_file is None or self.state.current_dataset_idx is None:
            self.statusBar().showMessage("No data loaded", 3000)
            return

        dataset_idx = self.state.current_dataset_idx
        var_names = self.raw_file.get_variable_names(dataset_idx)

        from pqwave.analysis.nyquist import detect_nyquist_vectors
        auto_pair = detect_nyquist_vectors(var_names)

        from pqwave.ui.nyquist_vector_dialog import NyquistVectorDialog
        dlg = NyquistVectorDialog(var_names, self, auto_pair=auto_pair)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        real_var, imag_var = dlg.selected_pair()

        real_data = self.raw_file.get_variable_data(real_var, dataset_idx)
        imag_data = self.raw_file.get_variable_data(imag_var, dataset_idx)
        if real_data is None or imag_data is None:
            QMessageBox.warning(self, "Data Error",
                                "Could not read vector data.")
            return

        from pqwave.analysis.nyquist import compute_nyquist_trace
        result = compute_nyquist_trace(real=real_data, imag=imag_data)

        if self.panel_grid.panel_count >= 4:
            QMessageBox.information(
                self, "Max Panels",
                "Maximum 4 panels reached. Close a panel first.")
            return

        new_panel = self.panel_grid.split_panel(
            self.panel_grid.active_panel_id, orientation="vertical")
        if new_panel is None:
            return

        import pyqtgraph as pg

        pw = new_panel.plot_widget

        curve = pg.PlotCurveItem(
            result["x"], result["y"],
            pen=pg.mkPen("cyan", width=1),
            skipFiniteCheck=True,
        )
        pw.addItem(curve)
        pw.set_axis_label("X", "Real")
        pw.set_axis_label("Y1", "Imaginary")
        pw.getViewBox().setAspectLocked(True, ratio=1.0)
        pw.autoRange()

    def _show_bode(self) -> None:
        """Compute and display Bode plot in dual split panels (gain + phase)."""
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        if self.raw_file is None or self.state.current_dataset_idx is None:
            self.statusBar().showMessage("No data loaded", 3000)
            return

        dataset_idx = self.state.current_dataset_idx
        var_names = self.raw_file.get_variable_names(dataset_idx)

        from pqwave.analysis.bode import detect_bode_vectors
        auto_pair = detect_bode_vectors(var_names)

        from pqwave.ui.bode_dialog import BodeDialog
        dlg = BodeDialog(var_names, self, auto_pair=auto_pair)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        mag_var, phase_var, freq_var = dlg.selected_vectors()

        mag_data = self.raw_file.get_variable_data(mag_var, dataset_idx)
        phase_data = self.raw_file.get_variable_data(phase_var, dataset_idx)
        if mag_data is None or phase_data is None:
            QMessageBox.warning(self, "Data Error",
                                "Could not read vector data.")
            return

        freq_data = None
        if freq_var:
            freq_data = self.raw_file.get_variable_data(freq_var, dataset_idx)

        from pqwave.analysis.bode import compute_bode
        result = compute_bode(mag_db=mag_data, phase_deg=phase_data,
                              freq=freq_data)

        gain_db = result["gain_db"]
        phase_deg = result["phase_deg"]
        freq = result["freq"]

        # Split panel twice for dual-panel Bode display
        active_id = self.panel_grid.active_panel_id

        gain_panel = self.panel_grid.split_panel(active_id, orientation="vertical")
        if gain_panel is None:
            return

        phase_panel = self.panel_grid.split_panel(
            gain_panel.panel_id, orientation="vertical")
        if phase_panel is None:
            return

        import pyqtgraph as pg

        # --- Gain panel (top) ---
        gain_pw = gain_panel.plot_widget
        gain_curve = pg.PlotCurveItem(
            freq, gain_db,
            pen=pg.mkPen("cyan", width=1),
            skipFiniteCheck=True,
        )
        gain_pw.addItem(gain_curve)
        gain_pw.set_axis_label("X", "Frequency (Hz)")
        gain_pw.set_axis_label("Y1", "Gain (dB)")
        gain_pw.set_axis_log_mode("X", True)
        gain_pw.autoRange()

        # --- Phase panel (bottom) ---
        phase_pw = phase_panel.plot_widget
        phase_curve = pg.PlotCurveItem(
            freq, phase_deg,
            pen=pg.mkPen("cyan", width=1),
            skipFiniteCheck=True,
        )
        phase_pw.addItem(phase_curve)
        phase_pw.set_axis_label("X", "Frequency (Hz)")
        phase_pw.set_axis_label("Y1", "Phase (°)")
        phase_pw.set_axis_log_mode("X", True)
        phase_pw.autoRange()

        # Force initial X-axis sync, then keep synced on future zoom/pan
        phase_pw.plotItem.setXRange(*gain_pw.plotItem.vb.viewRange()[0], padding=0)
        gain_pw.plotItem.vb.sigXRangeChanged.connect(
            lambda: phase_pw.plotItem.setXRange(*gain_pw.plotItem.vb.viewRange()[0], padding=0))

    def _on_mc_stats(self):
        """Handle MC Statistics menu action."""
        if not self.state.mc_collection:
            return
        from pqwave.analysis.multi_run import compute_cross_run_stats
        mc = self.state.mc_collection
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        selected = panel.trace_manager.get_selected_traces()
        if not selected:
            self.statusBar().showMessage("No trace selected for MC statistics", 3000)
            return
        # Get first selected trace's data across all runs
        signal_name = selected[0][0]
        data = self._get_mc_signal_data(signal_name)
        if data is None:
            return
        stats = compute_cross_run_stats(data)
        from pqwave.ui.trace_analysis_dialog import TraceAnalysisDialog
        dialog = TraceAnalysisDialog(self)
        metrics = {
            "Mean (μ)": f"{float(np.mean(stats['mean'])):.4g}",
            "Std (σ)": f"{float(np.mean(stats['std'])):.4g}",
            "Min across runs": f"{float(np.min(stats['min'])):.4g}",
            "Max across runs": f"{float(np.max(stats['max'])):.4g}",
            "Avg σ/μ ratio": f"{float(np.mean(np.abs(stats['std'] / (np.abs(stats['mean']) + 1e-300)))):.4g}",
        }
        dialog.add_trace_result(f"MC: {signal_name} ({mc.active_count} runs)", metrics)
        dialog.exec()

    def _on_mc_histogram(self):
        """Handle MC Histogram menu action."""
        from pqwave.ui.mc_histogram_dialog import MCHistogramDialog
        if not self.state.mc_collection:
            return
        dialog = MCHistogramDialog(self)
        if dialog.exec():
            config = dialog.get_config()
            data = self._get_mc_signal_data(config["signal"])
            if data is None:
                return
            from pqwave.analysis.multi_run import compute_run_measurements
            values = compute_run_measurements(data, config["measure"])
            self._show_mc_histogram_plot(config["signal"], config["measure"], values,
                                          bins=config["bins"], range=config["range"])

    def _on_mc_yield(self):
        """Handle MC Yield menu action."""
        from pqwave.ui.mc_yield_dialog import MCYieldDialog
        if not self.state.mc_collection:
            return
        dialog = MCYieldDialog(self)
        if dialog.exec():
            config = dialog.get_config()
            data = self._get_mc_signal_data(config["signal"])
            if data is None:
                return
            from pqwave.analysis.multi_run import compute_yield
            result = compute_yield(data, config["low"], config["high"], config["measure"])
            self._show_yield_result(config["signal"], config, result)

    def _on_mc_scatter(self):
        """Handle MC Scatter menu action."""
        from pqwave.ui.mc_scatter_dialog import MCScatterDialog
        if not self.state.mc_collection:
            return
        dialog = MCScatterDialog(self, self.state.mc_collection.parameters)
        if dialog.exec():
            config = dialog.get_config()
            data = self._get_mc_signal_data(config["signal"])
            if data is None:
                return
            from pqwave.analysis.multi_run import compute_run_measurements
            measurements = compute_run_measurements(data, config["measure"])
            param_values_full = self.state.mc_collection.parameters.get(config["param"])
            if param_values_full is None:
                self.statusBar().showMessage(
                    f"Parameter '{config['param']}' not annotated", 3000)
                return
            # Filter param_values to match active_runs (measurements already filtered)
            active = self.state.mc_collection.active_runs
            param_values = [param_values_full[i] for i in active
                            if i < len(param_values_full)]
            # Ensure lengths match (truncate longer array)
            n = min(len(measurements), len(param_values))
            self._show_scatter_plot(config, measurements[:n], param_values[:n])

    def _on_mc_sensitivity(self):
        """Handle MC Sensitivity menu action."""
        if not self.state.mc_collection or not self.state.mc_collection.has_parameters:
            self.statusBar().showMessage("No parameters annotated for sensitivity analysis", 3000)
            return
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        selected = panel.trace_manager.get_selected_traces()
        if not selected:
            self.statusBar().showMessage("No trace selected", 3000)
            return
        signal_name = selected[0][0]
        data = self._get_mc_signal_data(signal_name)
        if data is None:
            return
        from pqwave.analysis.multi_run import compute_run_measurements, compute_sensitivity
        measurements = compute_run_measurements(data, "max")
        sensitivity = compute_sensitivity(measurements, {
            k: np.array(v) for k, v in self.state.mc_collection.parameters.items()
        })
        self._show_sensitivity_result(signal_name, sensitivity)

    def _on_mc_worst(self):
        """Handle Worst Cases menu action."""
        if not self.state.mc_collection:
            return
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        selected = panel.trace_manager.get_selected_traces()
        signal_name = selected[0][0] if selected else "v(out)"
        data = self._get_mc_signal_data(signal_name)
        if data is None:
            return
        from pqwave.analysis.multi_run import compute_worst_cases
        mc = self.state.mc_collection
        worst = compute_worst_cases(data, mc.nominal_index, n=5)
        self._show_worst_cases_result(signal_name, worst, mc)

    def _on_mc_correlation(self):
        """Open the MC Correlation Tools dialog."""
        from pqwave.ui.correlation_editor import CorrelationMatrixEditor
        dialog = CorrelationMatrixEditor(self, mc_collection=self.state.mc_collection)
        dialog.exec()

    def _get_mc_signal_data(self, signal_name: str):
        """Get 2D data array (n_runs, n_points) for an MC signal group."""
        import numpy as np
        mc = self.state.mc_collection
        if mc is None or mc.active_count == 0:
            return None
        # Collect data from all active runs
        run_data = []
        for run_idx in mc.active_runs:
            ds_idx, step_idx = mc.get_run_data_indices(run_idx)
            if ds_idx < len(self.state.datasets):
                ds = self.state.datasets[ds_idx]
                var = ds.get_variable(signal_name)
                if var is not None:
                    y = var.y_data if hasattr(var, 'y_data') else np.array(var.data)
                    run_data.append(y)
        if not run_data:
            return None
        # Pad to equal length
        n_points = max(len(y) for y in run_data)
        data = np.zeros((len(run_data), n_points))
        for i, y in enumerate(run_data):
            data[i, :len(y)] = y
        return data

    def _show_mc_histogram_plot(self, signal, measure, values, bins=50, range=None):
        """Show histogram of MC measurement values."""
        from pqwave.analysis.histogram import compute_histogram
        import numpy as np
        if range and range[0] == range[1]:
            range = None
        hist = compute_histogram(values, bins=bins, norm="count", range=range)
        widths = np.diff(hist["edges"])
        # Create a new panel or use active panel for histogram display
        panel_grid = self.panel_grid
        panel_id = panel_grid.split_horizontal()
        panel = panel_grid.panels.get(panel_id)
        if panel is None:
            return
        from pyqtgraph import BarGraphItem
        bar = BarGraphItem(x=hist["centers"], height=hist["counts"],
                           width=widths, brush=(100, 150, 255, 150))
        panel.plot_widget.addItem(bar)
        panel.plot_widget.set_axis_label("X", f"{measure}({signal})")
        panel.plot_widget.set_axis_label("Y1", "Count")
        panel.plot_widget.autoRange()

    def _show_yield_result(self, signal, config, result):
        """Show yield result in status bar and as message."""
        if isinstance(result, np.ndarray):
            avg_yield = float(np.mean(result))
            self.statusBar().showMessage(
                f"Yield ({signal}): avg {avg_yield:.1f}% — "
                f"range [{config['low']:.2g}, {config['high']:.2g}]", 8000)
        else:
            self.statusBar().showMessage(
                f"Yield ({signal}): {result:.1f}% — "
                f"range [{config['low']:.2g}, {config['high']:.2g}]", 8000)

    def _show_scatter_plot(self, config, measurements, param_values):
        """Show scatter plot of measurement vs parameter."""
        panel_grid = self.panel_grid
        panel_id = panel_grid.split_horizontal()
        panel = panel_grid.panels.get(panel_id)
        if panel is None:
            return
        from pyqtgraph import PlotCurveItem
        curve = PlotCurveItem(param_values, measurements, pen=None,
                               symbol='o', symbolSize=8, symbolBrush=(255, 80, 80))
        panel.plot_widget.addItem(curve)
        panel.plot_widget.set_axis_label("X", config["param"])
        panel.plot_widget.set_axis_label("Y1", f"{config['measure']}({config['signal']})")
        panel.plot_widget.autoRange()

    def _show_sensitivity_result(self, signal, sensitivity):
        """Show sensitivity ranking in a simple message box."""
        lines = [f"Sensitivity of max({signal}):", ""]
        for item in sensitivity:
            lines.append(f"  {item['param']}: r = {item['r']:.4f} (p = {item['p']:.4f})")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "MC Sensitivity", "\n".join(lines))

    def _show_worst_cases_result(self, signal, worst, mc):
        """Show worst-case runs in a simple message box."""
        lines = [f"Worst cases for {signal}:", ""]
        for item in worst:
            run_idx = item["run_index"]
            dev = item["deviation"]
            params = mc.parameter_values_for_run(run_idx)
            param_str = ", ".join(f"{k}={v:.3g}" for k, v in params.items())
            lines.append(f"  Run {run_idx}: deviation={dev:.4g}")
            if param_str:
                lines.append(f"    params: {param_str}")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "MC Worst Cases", "\n".join(lines))

    def _toggle_digital_analog(self) -> None:
        """Toggle selected traces between digital and analog view."""
        panel = self.panel_grid.get_active_panel()
        if panel:
            panel.trace_manager.toggle_trace_type()

    def _group_bus(self) -> None:
        """Group selected digital traces into a bus."""
        panel = self.panel_grid.get_active_panel()
        if panel:
            panel.trace_manager.group_selected_as_bus()

    def _show_eye_diagram(self) -> None:
        """Show eye diagram for the first selected trace in a split panel."""
        panel = self.panel_grid.get_active_panel()
        if panel is None:
            return
        selected = panel.trace_manager.get_selected_traces()
        if not selected:
            QMessageBox.information(
                self, "No Trace Selected",
                "Select a trace first (left-click its legend), then use the Eye Diagram shortcut.")
            return
        _idx, trace = selected[0]

        if self.panel_grid.panel_count >= PanelGrid.MAX_PANELS:
            QMessageBox.information(
                self, "Max Panels",
                "Maximum 4 panels reached. Close a panel first.")
            return

        # Split the active panel horizontally (bypass _sync_split_x_axes)
        new_panel = self.panel_grid.split_panel(
            self.panel_grid.active_panel_id, orientation="horizontal")
        if new_panel is None:
            return

        # Force linear axes on the eye panel
        new_panel.axis_manager.set_axis_log_mode(AxisId.X, False)
        new_panel.axis_manager.set_axis_log_mode(AxisId.Y1, False)

        # Store for re-rendering when settings change
        self._eye_diagram_y_data = trace.y_data
        self._eye_diagram_trace_name = trace.name
        self._eye_diagram_panel_id = new_panel.panel_id

        # Mark the panel as an eye diagram panel for project save/load
        pstate = self.state.panels.get(new_panel.panel_id)
        if pstate is not None:
            pstate.is_eye_diagram = True
            pstate.eye_diagram_trace_name = trace.name

        ok = self._render_eye_diagram(new_panel, trace.y_data, trace.name)
        if not ok:
            self.panel_grid.close_panel(new_panel.panel_id)

    def _render_eye_diagram(self, panel, y_data: np.ndarray, trace_name: str) -> bool:
        """Render eye diagram into *panel*.  Returns False if data is unusable."""
        eye_cfg = self.state.eye_diagram_config

        if len(y_data) < eye_cfg.window_size:
            return False

        y_clean = y_data[np.isfinite(y_data)]
        if len(y_clean) == 0:
            return False
        y_min, y_max = float(y_clean.min()), float(y_clean.max())
        yamp = y_max - y_min or 1.0
        ybounds = (y_min - 0.05 * yamp, y_max + 0.05 * yamp)

        pw = panel.plot_widget
        try:
            if eye_cfg.mode == "overlay":
                render_overlay(pw, y_data, eye_cfg.window_size, eye_cfg.offset)
            else:
                render_persistence(pw, y_data, eye_cfg.window_size,
                                   eye_cfg.offset, eye_cfg.fuzz, ybounds)
        except Exception:
            logger.exception("Failed to render eye diagram")
            return False

        # Restore cursor lines removed by clear() during rendering
        pw.ensure_cursors_in_plot()

        n_windows = max(1, (len(y_data) - eye_cfg.offset) // eye_cfg.window_size)
        pw.set_plot_title(f"Eye: {trace_name}  |  {n_windows} windows")

        # Persist axis labels so they survive panel re-activation
        pstate = self.state.panels.get(panel.panel_id)
        if pstate is not None:
            pstate.axis_configs[AxisId.X].label = (
                'Sample' if eye_cfg.mode == 'overlay' else 'UI')
            pstate.axis_configs[AxisId.Y1].label = 'Amplitude'
        return True

    def _on_eye_diagram_settings_changed(self) -> None:
        """Re-render the eye diagram when settings change in the Settings dialog."""
        y_data = getattr(self, '_eye_diagram_y_data', None)
        panel_id = getattr(self, '_eye_diagram_panel_id', None)
        trace_name = getattr(self, '_eye_diagram_trace_name', '')
        if y_data is None or panel_id is None:
            return
        panel = self.panel_grid.get_panel(panel_id)
        if panel is None:
            return
        self._render_eye_diagram(panel, y_data, trace_name)

    def _load_eye_trace_data(self, trace_name: str):
        """Evaluate *trace_name* against any panel's raw file.
        Returns y_data as ndarray, or None on failure.
        """
        if not trace_name:
            return None
        # Search all panels for a raw_file that contains the trace.
        for p in self.panel_grid.panels.values():
            tm = p.trace_manager
            if tm.raw_file is None:
                continue
            try:
                data = tm.raw_file.get_variable_data(trace_name)
                if data is not None and len(data) > 0:
                    return data
            except Exception:
                continue
        return None

    def _show_threshold_settings(self) -> None:
        """Show threshold settings for the first selected digital trace."""
        panel = self.panel_grid.get_active_panel()
        if panel:
            panel.trace_manager.show_threshold_dialog()


if __name__ == "__main__":
    # Simple test runner
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())