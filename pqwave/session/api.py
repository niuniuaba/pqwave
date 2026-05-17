#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Session API — Qt-free orchestrator for headless and REPL use.

Provides the SessionAPI class and the @api_command decorator for
auto-registering commands from feature modules.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---- Command Registry ----

_COMMAND_REGISTRY: dict[str, dict] = {}


def api_command(name: str, signature: str, help: str):
    """Decorator that registers a function as a session API command.

    Commands registered this way are auto-discovered by the REPL,
    help system, and AI translator prompt.
    """
    def decorator(fn: Callable):
        _COMMAND_REGISTRY[name] = {
            "fn": fn,
            "signature": signature,
            "help": help,
        }
        return fn
    return decorator


def get_command_registry() -> dict[str, dict]:
    """Return the full command registry (for REPL/AI discovery)."""
    return _COMMAND_REGISTRY


def get_template_dir() -> str:
    """Return the directory where view templates are stored."""
    return os.path.join(os.path.expanduser("~"), ".pqwave", "templates")


# ---- Session API ----

class SessionAPI:
    """Qt-free orchestrator for pqwave session operations."""

    def __init__(self, state=None):
        from pqwave.models.state import ApplicationState
        self._state = state or ApplicationState()
        self._on_mutation: Callable | None = None

    def set_mutation_callback(self, cb: Callable | None):
        """Set a callback invoked after state mutations (for GUI sync)."""
        self._on_mutation = cb

    @property
    def state(self):
        return self._state

    # ---- Data lookup ----

    def _resolve_signal(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        """Resolve a signal name to (x_data, y_data). Searches all datasets."""
        name_lower = name.lower()
        for trace in self._state.traces:
            if trace.name.lower() == name_lower or trace.expression.lower() == name_lower:
                return trace.x_data, trace.y_data
        for ds in self._state.datasets:
            var = ds.get_variable(name)
            if var is not None:
                x_var = self._state.current_x_var or "time"
                x_data = ds.get_variable_data(x_var)
                if x_data is None:
                    for xn in ("time", "frequency", "freq"):
                        x_data = ds.get_variable_data(xn)
                        if x_data is not None:
                            break
                if x_data is None:
                    x_data = np.arange(len(var.data))
                return x_data, var.data
        raise KeyError(f"Signal not found: {name!r}")

    def _data_lookup(self, name: str) -> tuple[np.ndarray, np.ndarray] | None:
        """Callable for measure_engine.evaluate_measure get_data parameter."""
        try:
            return self._resolve_signal(name)
        except KeyError:
            return None

    def _resolve_x_var(self) -> str:
        if self._state.current_x_var:
            return self._state.current_x_var
        ds = self._state.current_dataset
        if ds is not None:
            for xn in ("time", "frequency", "freq"):
                if ds.get_variable(xn) is not None:
                    return xn
        return "index"

    # ---- File I/O ----

    def datasets(self) -> list:
        """List all loaded datasets."""
        return [
            {
                "idx": i,
                "title": str(ds),
            }
            for i, ds in enumerate(self._state.datasets)
        ]

    def unload(self, idx: int) -> dict:
        """Remove a dataset by index."""
        if self._on_mutation:
            self._on_mutation("unload", idx=idx)
            return {"status": "ok"}
        success = self._state.remove_dataset(idx)
        if success:
            return {"status": "ok"}
        return {"status": "error", "message": f"Invalid dataset index: {idx}"}

    def load(self, path: str) -> dict:
        """Load a raw, vcd, or json project file into the session."""
        import os
        from pqwave.models.rawfile import RawFile
        from pqwave.models.vcdfile import VcdFile
        from pqwave.models.state import SourceFile

        if self._on_mutation:
            self._on_mutation("load", path=path)
            return {"file_type": os.path.splitext(path)[1].lstrip(".")}

        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path!r}")

        ext = os.path.splitext(path)[1].lower()
        abs_path = os.path.abspath(path)

        if ext == ".json":
            info = self._load_project(abs_path)
        elif ext == ".vcd":
            info = self._load_vcd(abs_path)
        else:
            info = self._load_raw(abs_path)

        self._state.source_files.append(SourceFile(path=abs_path, file_type=ext.lstrip(".")))
        return info

    def _load_raw(self, path: str) -> dict:
        from pqwave.models.rawfile import RawFile
        from pqwave.models.dataset import Dataset

        raw = RawFile(path)
        signals = []
        for ds_idx in range(len(raw.datasets)):
            dataset = Dataset(raw, ds_idx)
            self._state.add_dataset(dataset)
            signals.extend(dataset.get_variable_names(include_derived=True))
            if not self._state.active_panel_id:
                self._state.register_panel("panel_0")

        if self._state.datasets:
            self._state.current_dataset_idx = len(self._state.datasets) - 1

        ds = self._state.current_dataset
        return {
            "file_type": "raw",
            "n_points": ds.n_points if ds else 0,
            "n_variables": ds.n_variables if ds else 0,
            "signals": list(dict.fromkeys(signals)),
        }

    def _load_vcd(self, path: str) -> dict:
        from pqwave.models.vcdfile import VcdFile
        from pqwave.models.dataset import Dataset

        vcd = VcdFile(path)
        dataset = Dataset(vcd, 0)
        self._state.add_dataset(dataset)

        if not self._state.active_panel_id:
            self._state.register_panel("panel_0")

        if self._state.datasets:
            self._state.current_dataset_idx = len(self._state.datasets) - 1

        return {
            "file_type": "vcd",
            "n_points": dataset.n_points,
            "n_variables": dataset.n_variables,
            "signals": dataset.get_variable_names(),
        }

    def _load_project(self, path: str) -> dict:
        return {"error": "Project file loading not yet supported in session API"}

    def signals(self) -> list[str]:
        """List all available signal names across raw datasets and VCD files."""
        names = []
        ds = self._state.current_dataset
        if ds is not None:
            names.extend(ds.get_variable_names(include_derived=True))
        for name in self._state.vcd_signal_names:
            if name not in names:
                names.append(name)
        for trace in self._state.traces:
            if trace.name not in names:
                names.append(trace.name)
        return names

    # ---- Trace display ----

    @staticmethod
    def _expand_range(expr: str, known_signals: list[str]) -> list[str] | None:
        """Expand q1~q4 → ['q1','q2','q3','q4'] if signals match.

        Returns:
            Non-empty list — successfully expanded
            Empty list — pattern matches but no signals found
            None — not a range pattern
        """
        import re
        m = re.match(r'^([a-zA-Z0-9_]\w*?)(\d+)~\1(\d+)$', expr)
        if not m:
            return None
        prefix = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3))
        if start > end:
            start, end = end, start
        candidates = [f"{prefix}{i}" for i in range(start, end + 1)]
        return [c for c in candidates if c in known_signals]

    def add(self, expr, axis: str = "Y1") -> str | list[str]:
        """Add one or more traces to the active panel.

        In GUI mode (callback set), delegates to the callback so TraceManager
        creates the actual PlotCurveItem. In headless mode, creates a Trace
        model in state directly.

        Automatically expands glob patterns (*, ?) and range notation
        (e.g. q1~q4) against the current signal list.
        """
        from pqwave.models.trace import Trace, AxisAssignment

        if isinstance(expr, list):
            return [self.add(e, axis) for e in expr]

        # Expand glob patterns: q* → show_matching("q*")
        # Only when * or ? looks like a glob, not a math operator:
        #   q*, v(q*)  → glob    (no math context)
        #   v(1)*v(2)  → product (digit or ) before *)
        if ('*' in expr or '?' in expr) and not re.search(r'[\d)][*?]|[*?]\d', expr):
            result = self.show_matching(expr)
            return result.get("shown", [])

        # Expand range notation: q1~q4 → add(["q1","q2","q3","q4"])
        if '~' in expr:
            expanded = self._expand_range(expr, self.signals())
            if expanded is not None:
                if not expanded:
                    raise ValueError(
                        f"No signals match range '{expr}'. "
                        f"Available: {', '.join(self.signals()[:20])}"
                    )
                return self.add(expanded, axis)

        # Auto-convert complex signals to magnitude for sensible default
        try:
            _, test_y = self._resolve_signal(expr)
            if np.iscomplexobj(test_y):
                expr = f"mag({expr})"
        except (KeyError, TypeError):
            pass

        if self._on_mutation:
            # GUI mode: tell the callback to add a trace via TraceManager
            self._on_mutation("add", expr=expr, axis=axis)
            return expr

        # Headless mode: create Trace model directly
        x_data, y_data = self._resolve_signal(expr)
        axis_enum = AxisAssignment.Y1 if axis.upper() == "Y1" else AxisAssignment.Y2
        x_var = self._resolve_x_var()

        trace = Trace(
            name=expr,
            expression=expr,
            x_data=x_data,
            y_data=y_data,
            y_axis=axis_enum,
            dataset_idx=self._state.current_dataset_idx,
            metadata={"x_var": x_var},
        )
        self._state.add_trace(trace)
        return expr

    def show(self, expr) -> str:
        """Show a hidden trace (make it visible)."""
        if self._on_mutation:
            self._on_mutation("show_trace", expr=expr)
            return f"Showing trace: {expr}"
        for t in self._state.traces:
            if t.name == expr or t.expression == expr:
                t.visible = True
                return f"Showing trace: {expr}"
        raise ValueError(f"Trace not found: {expr!r}")

    def remove(self, trace_identifier) -> str:
        """Remove a trace by name or index."""
        if self._on_mutation:
            self._on_mutation("remove", expr=trace_identifier)
            return f"Removed trace: {trace_identifier}"

        if isinstance(trace_identifier, int):
            if self._state.remove_trace(trace_identifier):
                return f"Removed trace at index {trace_identifier}"
        else:
            for i, t in enumerate(self._state.traces):
                if t.name == trace_identifier or t.expression == trace_identifier:
                    self._state.remove_trace(i)
                    return f"Removed trace: {trace_identifier}"
        raise ValueError(f"Trace not found: {trace_identifier!r}")

    def hide(self, expr) -> str:
        """Hide a trace (make it invisible)."""
        if self._on_mutation:
            self._on_mutation("hide_trace", expr=expr)
            return f"Hiding trace: {expr}"
        for t in self._state.traces:
            if t.name == expr or t.expression == expr:
                t.visible = False
                return f"Hiding trace: {expr}"
        raise ValueError(f"Trace not found: {expr!r}")

    def remove_all(self) -> str:
        """Remove all traces from the active panel."""
        if self._on_mutation:
            self._on_mutation("remove_all")
            return "Removed all traces"
        self._state.clear_traces()
        return "Removed all traces"

    def hide_all(self) -> str:
        """Make all traces invisible."""
        if self._on_mutation:
            self._on_mutation("hide_all_traces")
            return "Hiding all traces"
        for t in self._state.traces:
            t.visible = False
        return "Hiding all traces"

    # ---- Measurement ----

    def measure(self, expr: str, **kwargs) -> dict:
        """Evaluate a single measurement expression."""
        from pqwave.measure.measure_engine import evaluate_measure

        if kwargs:
            parts = [expr.removesuffix(")")]
            for k, v in kwargs.items():
                key = k.rstrip("_")  # from_ → from (Python kwarg workaround)
                parts.append(f", {key}={v}")
            parts.append(")")
            eval_expr = "".join(parts)
        else:
            eval_expr = expr

        value = evaluate_measure(eval_expr, self._data_lookup)
        return {eval_expr: value}

    def measure_script(self, text: str) -> dict:
        """Execute a .meas-style script and return results."""
        from pqwave.measure.measure_script_parser import parse_meas_script
        from pqwave.measure.measure_engine import evaluate_measure

        results = {}
        for expr, label in parse_meas_script(text):
            try:
                value = evaluate_measure(expr, self._data_lookup)
                key = label if label else expr
                results[key] = value
            except Exception as e:
                key = label if label else expr
                results[key] = f"ERROR: {e}"
        return results

    # ---- Analysis ----

    def fft(self, signal: str, window: str = "hann", from_: str = None,
            to: str = None, **kwargs) -> dict:
        """Compute FFT of a signal. In GUI mode, adds as plot trace."""
        from pqwave.ui.fft_engine import compute_fft
        from pqwave.measure.measure_engine import _parse_value

        if self._on_mutation:
            # Build fft() expression for TraceManager to handle
            expr = f"fft({signal})"
            self._on_mutation("add", expr=expr, axis="Y1")
            return {"signal": signal}

        x_data, y_data = self._resolve_signal(signal)
        x_min = _parse_value(from_) if from_ else None
        x_max = _parse_value(to) if to else None

        fft_kwargs = {"window": window}
        if x_min is not None or x_max is not None:
            fft_kwargs["x_range_mode"] = "manual"
            fft_kwargs["x_range_start"] = x_min if x_min is not None else 0.0
            fft_kwargs["x_range_end"] = x_max if x_max is not None else float(x_data[-1])

        freq, mag = compute_fft(y_data, x_data, **fft_kwargs)
        return {"freq": freq, "mag": mag}

    def power(self, v_signal: str, i_signal: str, from_: str = None,
              to: str = None, v_threshold: float = None) -> dict:
        """Compute instantaneous power P(t) = V(t) * I(t)."""
        from pqwave.analysis.power_analyzer import power_analysis
        from pqwave.measure.measure_engine import _parse_value

        _, v_data = self._resolve_signal(v_signal)
        _, i_data = self._resolve_signal(i_signal)
        t_data, _ = self._resolve_signal(self._resolve_x_var())

        if len(t_data) != len(v_data):
            t_data = np.arange(len(v_data))

        xmin = _parse_value(from_) if from_ else float(t_data[0])
        xmax = _parse_value(to) if to else float(t_data[-1])

        return power_analysis(v_data, i_data, t_data, xmin, xmax, v_threshold)

    def histogram(self, trace: str, bins: int | None = None,
                  range: list[float] | None = None, norm: str = "count") -> dict:
        """Compute histogram of a trace and return the bin data.

        In GUI mode, delegates to the main window for dialog + rendering.
        In headless mode, returns computed bin data directly.
        """
        if self._on_mutation:
            kwargs = {"bins": bins, "range": range, "norm": norm}
            self._on_mutation("histogram", trace=trace,
                              **{k: v for k, v in kwargs.items() if v is not None})
            return {"success": True, "trace": trace}

        from pqwave.analysis.histogram import compute_histogram
        found = None
        for t in self._state.traces:
            if t.name == trace or t.expression == trace:
                found = t
                break
        if found is None:
            return {"success": False, "error": f"Trace '{trace}' not found"}
        y_data = found.y_data if found.y_data is not None else np.array([])
        result = compute_histogram(
            y_data, bins=bins,
            range=tuple(range) if range else None,
            norm=norm,
        )
        return {"success": True, "data": {
            "counts": result["counts"].tolist(),
            "edges": result["edges"].tolist(),
            "centers": result["centers"].tolist(),
        }}

    def nyquist(self, real: str, imag: str, freq: str | None = None) -> dict:
        """Compute a Nyquist trace from real and imaginary vector data.

        Args:
            real: Name of the real-part variable.
            imag: Name of the imaginary-part variable.
            freq: Optional name of the frequency variable.

        Returns:
            dict with ``success`` flag and ``data`` containing
            ``x`` and ``y`` arrays.
        """
        from pqwave.analysis.nyquist import compute_nyquist_trace

        try:
            _, real_data = self._resolve_signal(real)
            _, imag_data = self._resolve_signal(imag)
        except Exception as e:
            return {"success": False, "error": str(e)}

        freq_data = None
        if freq:
            try:
                _, freq_data = self._resolve_signal(freq)
            except Exception:
                pass

        result = compute_nyquist_trace(
            real=real_data, imag=imag_data, freq=freq_data,
        )
        return {"success": True, "data": {
            "x": result["x"].tolist(),
            "y": result["y"].tolist(),
        }}

    def bode(self, mag: str, phase: str, freq: str | None = None) -> dict:
        """Compute a Bode plot from magnitude and phase vector data.

        Args:
            mag: Name of the magnitude (dB) variable.
            phase: Name of the phase (degrees) variable.
            freq: Optional name of the frequency variable.  When omitted the
                frequency axis defaults to integer indices.

        Returns:
            dict with ``success`` flag and ``data`` containing
            ``gain_db``, ``phase_deg``, and ``freq`` arrays.
        """
        from pqwave.analysis.bode import compute_bode

        if self._on_mutation:
            self._on_mutation("bode", mag=mag, phase=phase, freq=freq)
            return {"success": True, "mag": mag, "phase": phase}

        try:
            _, mag_data = self._resolve_signal(mag)
            _, phase_data = self._resolve_signal(phase)
        except Exception as e:
            return {"success": False, "error": str(e)}

        freq_data = None
        if freq:
            try:
                _, freq_data = self._resolve_signal(freq)
            except Exception:
                pass

        result = compute_bode(
            mag_db=mag_data, phase_deg=phase_data, freq=freq_data,
        )
        return {"success": True, "data": {
            "gain_db": result["gain_db"].tolist(),
            "phase_deg": result["phase_deg"].tolist(),
            "freq": result["freq"].tolist(),
        }}

    # ---- View control ----

    def range(self, xmin: float = None, xmax: float = None,
              ymin: float = None, ymax: float = None) -> dict:
        """Set view range of the active panel."""
        if self._on_mutation:
            self._on_mutation("range", xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)
            return {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax}

        from pqwave.models.state import AxisId
        if xmin is not None or xmax is not None:
            cur = self._state.get_axis_config(AxisId.X)
            cur_min, cur_max = cur.range or (0, 1)
            self._state.set_axis_range(
                AxisId.X,
                float(xmin) if xmin is not None else cur_min,
                float(xmax) if xmax is not None else cur_max,
            )
        if ymin is not None or ymax is not None:
            cur = self._state.get_axis_config(AxisId.Y1)
            cur_min, cur_max = cur.range or (0, 1)
            self._state.set_axis_range(
                AxisId.Y1,
                float(ymin) if ymin is not None else cur_min,
                float(ymax) if ymax is not None else cur_max,
            )
        return {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax}

    def log_x(self, on: bool = True) -> dict:
        """Toggle X-axis log mode."""
        if self._on_mutation:
            self._on_mutation("log_x", on=on)
            return {"log_x": on}
        from pqwave.models.state import AxisId
        self._state.set_axis_log_mode(AxisId.X, on)
        return {"log_x": on}

    def log_y(self, on: bool = True) -> dict:
        """Toggle Y-axis log mode."""
        if self._on_mutation:
            self._on_mutation("log_y", on=on)
            return {"log_y": on}
        from pqwave.models.state import AxisId
        self._state.set_axis_log_mode(AxisId.Y1, on)
        return {"log_y": on}

    # ---- Export ----

    def export_csv(self, path: str, signals: list[str] = None) -> dict:
        """Export current traces to CSV.

        Args:
            path: Output file path (*.csv)
            signals: Signal names to export (default: all traces)

        Returns:
            {"path": ..., "signals_exported": ...}
        """
        import os

        if signals is None:
            signals = [t.name for t in self._state.traces]

        rows = {}
        # Collect data for each signal
        for name in signals:
            x_data, y_data = self._resolve_signal(name)
            rows[f"{name}_time"] = x_data
            rows[name] = y_data

        if not rows:
            return {"path": path, "signals_exported": 0}

        # Align to same length
        min_len = min(len(v) for v in rows.values())
        columns = {k: v[:min_len] for k, v in rows.items()}

        header = ",".join(columns.keys())
        data_stack = np.column_stack(list(columns.values()))
        np.savetxt(path, data_stack, delimiter=",", header=header, comments="")

        return {"path": os.path.abspath(path), "signals_exported": len(signals)}

    # ---- Info ----

    def info(self) -> dict:
        """Return session metadata."""
        ds = self._state.current_dataset
        return {
            "datasets": len(self._state.datasets),
            "current_dataset": self._state.current_dataset_idx,
            "n_points": ds.n_points if ds else 0,
            "n_variables": ds.n_variables if ds else 0,
            "n_traces": len(self._state.traces),
            "signals": self.signals(),
            "active_panel": self._state.active_panel_id,
            "num_panels": len(self._state.panels),
        }

    # ---- View Templates ----

    def _template_manager(self):
        from pqwave.templates.manager import TemplateManager
        return TemplateManager(get_template_dir())

    def save_template(self, name: str) -> dict:
        """Save current panel view as a named template."""
        config = {
            "axis_configs": {
                ax.value: cfg.to_dict()
                for ax, cfg in self._state.axis_configs.items()
            },
            "trace_expressions": [
                {
                    "expr": t.expression or t.name,
                    "axis": t.y_axis.value,
                    "color": list(t.color),
                }
                for t in self._state.traces if t.visible
            ],
            "display": {
                "title": self._state.plot_title,
            },
        }
        self._template_manager().save(name, config)
        return {"success": True, "name": name}

    def load_template(self, name: str) -> dict:
        """Load a saved view template onto the active panel."""
        try:
            config = self._template_manager().load(name)
        except FileNotFoundError:
            return {"success": False, "error": f"Template '{name}' not found"}

        from pqwave.models.state import AxisId, AxisConfig

        # Apply axis configs — route through API methods so GUI mutation
        # callback fires and the plot widget is notified to redraw.
        for ax_name, ax_cfg in config.get("axis_configs", {}).items():
            try:
                axis_id = AxisId(ax_name)
                cfg = AxisConfig.from_dict(ax_cfg)

                if axis_id == AxisId.X:
                    self.log_x(cfg.log_mode)
                    if cfg.range and not cfg.auto_range:
                        self.range(xmin=cfg.range[0], xmax=cfg.range[1])
                elif axis_id == AxisId.Y1:
                    self.log_y(cfg.log_mode)
                    if cfg.range and not cfg.auto_range:
                        self.range(ymin=cfg.range[0], ymax=cfg.range[1])
            except Exception:
                logger.warning(
                    "load_template: failed to apply axis config for %s",
                    ax_name,
                    exc_info=True,
                )

        # Apply trace expressions — skip missing vectors gracefully
        applied = 0
        skipped = []
        for te in config.get("trace_expressions", []):
            try:
                self.add(te["expr"], axis=te.get("axis", "Y1"))
                applied += 1
            except Exception:
                logger.warning(
                    "load_template: skipping '%s' — vector not found "
                    "in loaded data",
                    te.get("expr", ""),
                )
                skipped.append(te.get("expr", ""))
                continue

            # Restore saved color
            color = te.get("color")
            if color is not None:
                color_tuple = tuple(color)
                # Update the trace model in state
                for t in reversed(self._state.traces):
                    expr = te["expr"]
                    if t.expression == expr or t.name == expr:
                        t.color = color_tuple
                        break
                # In GUI mode, also update the plot item pen through mutation
                if self._on_mutation:
                    self._on_mutation(
                        "set_trace", name=te["expr"], color=color_tuple
                    )

        # Apply display
        if config.get("display", {}).get("title"):
            self._state.plot_title = config["display"]["title"]

        result: dict = {
            "success": True,
            "name": name,
            "applied_expressions": applied,
        }
        if skipped:
            result["skipped_expressions"] = skipped
            result["warning"] = (
                f"Skipped {len(skipped)} expression(s) "
                f"not found in current data"
            )
        return result

    def list_templates(self) -> dict:
        """List all saved view templates."""
        return {"templates": self._template_manager().list()}

    def help(self, command_name: str = None) -> str:
        """List available commands or get help for a specific command."""
        if command_name:
            if command_name in _COMMAND_REGISTRY:
                entry = _COMMAND_REGISTRY[command_name]
                return f"{entry['signature']}\n  {entry['help']}"
            return f"Unknown command: {command_name!r}"

        lines = ["Available commands:", ""]
        for name, entry in sorted(_COMMAND_REGISTRY.items()):
            lines.append(f"  {entry['signature']}")
            lines.append(f"    {entry['help']}")
            lines.append("")
        return "\n".join(lines) if lines else "No commands registered."

    # ---- Code execution ----

    def execute(self, code: str) -> dict:
        """Execute a line of Python code against this session."""
        namespace = {"session": self, "np": np}
        from functools import partial
        for name, entry in _COMMAND_REGISTRY.items():
            namespace[name] = partial(entry["fn"], self)

        try:
            exec(code, namespace)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- Headless entry ----

    @classmethod
    def run_headless(cls, code: str) -> str:
        """Execute code headless and return JSON result."""
        session = cls()
        result = session.execute(code)
        return json.dumps(result, default=str)

    # ---- Cursor operations ----

    def cursor_xa(self, value=None) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_xa", value=value)
        return {"cursor_xa": value}

    def cursor_xb(self, value=None) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_xb", value=value)
        return {"cursor_xb": value}

    def cursor_ya(self, value=None) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_ya", value=value)
        return {"cursor_ya": value}

    def cursor_yb(self, value=None) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_yb", value=value)
        return {"cursor_yb": value}

    def cursor_delta(self) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_delta")
        return {}

    def cursor(self) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor")
        return {}

    # ---- View toggles ----

    def grid(self, on: bool = None) -> dict:
        if self._on_mutation:
            self._on_mutation("grid", on=on)
        return {"grid": on}

    def legend(self, on: bool = None) -> dict:
        if self._on_mutation:
            self._on_mutation("legend", on=on)
        return {"legend": on}

    def cross_hair(self, on: bool = None) -> dict:
        if self._on_mutation:
            self._on_mutation("cross_hair", on=on)
        return {"cross_hair": on}

    def zoom_fit(self) -> dict:
        if self._on_mutation:
            self._on_mutation("zoom_fit")
        return {}

    def auto_range_x(self) -> dict:
        if self._on_mutation:
            self._on_mutation("auto_range_x")
        return {}

    def auto_range_y(self) -> dict:
        if self._on_mutation:
            self._on_mutation("auto_range_y")
        return {}

    def title(self, text: str = None) -> dict:
        if self._on_mutation:
            self._on_mutation("title", text=text)
        return {"title": text}

    # ---- Add all / wildcard ----

    def add_all(self) -> dict:
        """Plot all available signals."""
        sigs = self.signals()
        shown = []
        for sig in sigs:
            if sig.lower() in ("time", "frequency", "freq"):
                continue
            try:
                self.add(sig)
                shown.append(sig)
            except Exception:
                logger.warning("add_all: failed to add %s", sig, exc_info=True)
        return {"shown": shown}

    def show_all(self) -> str:
        """Make all traces visible."""
        if self._on_mutation:
            self._on_mutation("show_all_traces")
            return "Showing all traces"
        for t in self._state.traces:
            t.visible = True
        return "Showing all traces"

    def show_matching(self, pattern: str) -> dict:
        """Plot all signals matching a glob pattern (e.g., 'v(q*)')."""
        import fnmatch
        sigs = self.signals()
        shown = []
        for sig in sigs:
            if fnmatch.fnmatch(sig, pattern):
                try:
                    self.add(sig)
                    shown.append(sig)
                except Exception:
                    logger.warning("show_matching: failed to add %s", sig, exc_info=True)
        return {"pattern": pattern, "shown": shown}

    # ---- Bus / Digital ----

    def bus(self, signals: list, name: str = "bus") -> dict:
        # Show signals first so they become traces before grouping
        for sig in signals:
            try:
                self.add(sig)
            except Exception:
                logger.warning("bus: failed to add %s", sig, exc_info=True)
        if self._on_mutation:
            self._on_mutation("bus", signals=signals, name=name)
        return {"bus": name, "signals": signals}

    def expand(self, bus_name: str) -> dict:
        if self._on_mutation:
            self._on_mutation("expand", name=bus_name)
        return {"expand": bus_name}

    def collapse(self, bus_name: str) -> dict:
        if self._on_mutation:
            self._on_mutation("collapse", name=bus_name)
        return {"collapse": bus_name}

    def digital(self, sig, on: bool = True) -> dict:
        if self._on_mutation:
            self._on_mutation("digital", sig=sig, on=on)
        return {"digital": sig, "on": on}

    def set_trace(self, name: str, height: float = None, width: int = None,
                  color: tuple = None, alias: str = None) -> dict:
        """Set properties of an existing trace by name."""
        if self._on_mutation:
            self._on_mutation("set_trace", name=name, height=height,
                              width=width, color=color, alias=alias)
        return {"name": name, "height": height, "width": width,
                "color": color, "alias": alias}

    # ---- Cursor visibility ----

    def cursor_xa_visible(self, on: bool = True) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_xa_visible", on=on)
        return {"cursor_xa_visible": on}

    def cursor_xb_visible(self, on: bool = True) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_xb_visible", on=on)
        return {"cursor_xb_visible": on}

    def cursor_ya_visible(self, on: bool = True) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_ya_visible", on=on)
        return {"cursor_ya_visible": on}

    def cursor_yb_visible(self, on: bool = True) -> dict:
        if self._on_mutation:
            self._on_mutation("cursor_yb_visible", on=on)
        return {"cursor_yb_visible": on}

    # ---- Eye diagram ----

    def eye(self, sig: str, period: str = None) -> dict:
        if self._on_mutation:
            self._on_mutation("eye", sig=sig, period=period)
        return {"eye": sig, "period": period}

    # ---- FFT parameters ----

    def fft_config(self, window: str = None, fft_size: int = None,
                   representation: str = None) -> dict:
        from pqwave.models.state import FftConfig
        cfg = self._state.fft_config
        if window:
            cfg.window = window
        if fft_size:
            cfg.fft_size = fft_size
        if representation:
            cfg.representation = representation
        return {"window": cfg.window, "fft_size": cfg.fft_size,
                "representation": cfg.representation}

    # ---- Reload ----

    def reload(self) -> dict:
        if self._on_mutation:
            self._on_mutation("reload")
        return {"reload": True}

    # ---- Export ----

    def export_plot(self, path: str, width: int = 1200, height: int = 800) -> dict:
        if self._on_mutation:
            self._on_mutation("export_plot", path=path, width=width, height=height)
            return {"export_plot": path}

        # Headless fallback: render traces with matplotlib
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return {"export_plot": None,
                    "error": "matplotlib is required for headless export. Install it with: pip install matplotlib"}

        from pqwave.models.state import ViewboxTheme, AxisId
        from pqwave.models.trace import AxisAssignment

        traces = self._state.traces
        axis_configs = self._state.axis_configs
        visible = [t for t in traces if t.visible]
        if not visible:
            return {"export_plot": None, "warning": "No visible traces to export"}

        theme = getattr(self._state, "viewbox_theme", None)
        is_dark = theme == ViewboxTheme.DARK if theme else True

        fig, ax = plt.subplots(figsize=(width / 100, height / 100))

        def _style_axis(axis, ylabel):
            if is_dark:
                axis.set_facecolor("#1a1a1a")
                axis.tick_params(colors="#cccccc")
                for spine in axis.spines.values():
                    spine.set_color("#555555")
                axis.title.set_color("#cccccc")
                axis.xaxis.label.set_color("#cccccc")
                axis.yaxis.label.set_color("#cccccc")
            axis.set_ylabel(ylabel)

        _style_axis(ax, AxisId.Y1.value)

        y1_traces = [t for t in visible if t.y_axis == AxisAssignment.Y1]
        y2_traces = [t for t in visible if t.y_axis == AxisAssignment.Y2]

        ax2 = None
        if y2_traces:
            ax2 = ax.twinx()
            _style_axis(ax2, AxisId.Y2.value)

        for trace in y1_traces:
            r, g, b = trace.color
            ax.plot(trace.x_data, trace.y_data, color=f"#{r:02x}{g:02x}{b:02x}",
                    linewidth=trace.line_width, label=trace.name)

        for trace in y2_traces:
            r, g, b = trace.color
            c = f"#{r:02x}{g:02x}{b:02x}"
            (ax2 if ax2 else ax).plot(trace.x_data, trace.y_data, color=c,
                    linewidth=trace.line_width, label=trace.name)

        if is_dark:
            fig.patch.set_facecolor("#1a1a1a")

        x_cfg = axis_configs.get(AxisId.X)
        if x_cfg and x_cfg.log_mode:
            ax.set_xscale("log")
        y1_cfg = axis_configs.get(AxisId.Y1)
        if y1_cfg and y1_cfg.log_mode:
            ax.set_yscale("log")
        y2_cfg = axis_configs.get(AxisId.Y2)
        if y2_cfg and y2_cfg.log_mode and ax2:
            ax2.set_yscale("log")

        if x_cfg and x_cfg.range and not x_cfg.auto_range:
            r = x_cfg.range
            ax.set_xlim((10.0 ** r[0], 10.0 ** r[1]) if x_cfg.log_mode else r)
        if y1_cfg and y1_cfg.range and not y1_cfg.auto_range:
            r = y1_cfg.range
            ax.set_ylim((10.0 ** r[0], 10.0 ** r[1]) if y1_cfg.log_mode else r)
        if y2_cfg and y2_cfg.range and not y2_cfg.auto_range and ax2:
            r = y2_cfg.range
            ax2.set_ylim((10.0 ** r[0], 10.0 ** r[1]) if y2_cfg.log_mode else r)

        x_label = self._state.current_x_var or "X"
        ax.set_xlabel(x_label)

        lines, labels = ax.get_legend_handles_labels()
        if ax2:
            l2, lab2 = ax2.get_legend_handles_labels()
            lines.extend(l2)
            labels.extend(lab2)
        if lines:
            ax.legend(lines, labels, loc="upper right",
                      facecolor="#2a2a2a" if is_dark else "#ffffff",
                      edgecolor="#555555" if is_dark else "#cccccc",
                      labelcolor="#cccccc" if is_dark else "#000000")

        fig.tight_layout()
        fig.savefig(path, dpi=100, facecolor=fig.get_facecolor())
        plt.close(fig)
        return {"export_plot": path}

    # ---- Theme ----

    def theme(self, name: str = None) -> dict:
        if self._on_mutation:
            self._on_mutation("theme", name=name)
        return {"theme": name}

    # ---- X-axis variable ----

    def change_x(self, var: str) -> dict:
        if self._on_mutation:
            self._on_mutation("change_x", var=var)
        return {"change_x": var}

    # ---- Zoom ----

    def zoom_in(self) -> dict:
        if self._on_mutation:
            self._on_mutation("zoom_in")
        return {}

    def zoom_out(self) -> dict:
        if self._on_mutation:
            self._on_mutation("zoom_out")
        return {}

    # ---- Panel management ----

    def split_horizontal(self) -> dict:
        if self._on_mutation:
            self._on_mutation("split_horizontal")
        return {}

    def split_vertical(self) -> dict:
        if self._on_mutation:
            self._on_mutation("split_vertical")
        return {}

    def close_panel(self) -> dict:
        if self._on_mutation:
            self._on_mutation("close_panel")
        return {}


# ---- Core command registrations ----
# Registered here (not in feature modules) to avoid circular imports
# since session/api.py imports from measure_engine, fft_engine, etc.
# The @api_command decorator is available for future modules without circular deps.


@api_command("measure", "measure(expr, from_=None, to=None, ...)",
             "Evaluate a measurement expression (avg, rms, rise_time, etc.)")
def _cmd_measure(session: SessionAPI, expr: str, **kwargs):
    return session.measure(expr, **kwargs)


@api_command("measure_script", "measure_script(text)",
             "Execute a .meas-style script")
def _cmd_measure_script(session: SessionAPI, text: str):
    return session.measure_script(text)


@api_command("add", "add(expr, axis='Y1')",
             "Add a trace to the active panel")
def _cmd_add(session: SessionAPI, expr, axis: str = "Y1"):
    return session.add(expr, axis)


@api_command("show", "show(expr)",
             "Show a hidden trace (make it visible)")
def _cmd_show(session: SessionAPI, expr):
    return session.show(expr)


@api_command("add_all", "add_all()",
             "Add all available signals to the active panel")
def _cmd_add_all(session: SessionAPI):
    return session.add_all()


@api_command("show_all", "show_all()",
             "Make all traces visible")
def _cmd_show_all(session: SessionAPI):
    return session.show_all()


@api_command("remove", "remove(trace_identifier)",
             "Remove a trace by name or index")
def _cmd_remove(session: SessionAPI, trace_identifier):
    return session.remove(trace_identifier)


@api_command("remove_all", "remove_all()",
             "Remove all traces from the active panel")
def _cmd_remove_all(session: SessionAPI):
    return session.remove_all()


@api_command("hide", "hide(expr)",
             "Hide a trace (make it invisible)")
def _cmd_hide(session: SessionAPI, expr):
    return session.hide(expr)


@api_command("hide_all", "hide_all()",
             "Make all traces invisible")
def _cmd_hide_all(session: SessionAPI):
    return session.hide_all()


@api_command("fft", "fft(signal, window='hann', from_=None, to=None)",
             "Compute FFT of a signal")
def _cmd_fft(session: SessionAPI, signal: str, window: str = "hann",
             from_: str = None, to: str = None, **kwargs):
    return session.fft(signal, window=window, from_=from_, to=to, **kwargs)


@api_command("power", "power(v_signal, i_signal, from_=None, to=None, v_threshold=None)",
             "Compute instantaneous power P(t) = V(t) * I(t)")
def _cmd_power(session: SessionAPI, v_signal: str, i_signal: str,
               from_: str = None, to: str = None, v_threshold: float = None):
    return session.power(v_signal, i_signal, from_=from_, to=to, v_threshold=v_threshold)


@api_command("histogram", "histogram(trace, bins=None, range=None, norm='count')",
             "Compute histogram of a trace")
def _cmd_histogram(session: SessionAPI, trace: str, **kwargs):
    return session.histogram(trace, **kwargs)


@api_command("nyquist", "nyquist(real, imag, freq=None)",
             "Render a Nyquist plot from real and imaginary vector data")
def _cmd_nyquist(session: SessionAPI, real: str, imag: str, freq: str | None = None):
    return session.nyquist(real, imag, freq)


@api_command("bode", "bode(mag, phase, freq=None)",
             "Render a Bode plot (gain/phase vs frequency)")
def _cmd_bode(session: SessionAPI, mag: str, phase: str, freq: str | None = None):
    return session.bode(mag, phase, freq)


@api_command("load", "load(path)",
             "Load a raw, vcd, or json project file")
def _cmd_load(session: SessionAPI, path: str):
    return session.load(path)


@api_command("signals", "signals()",
             "List all available signal names")
def _cmd_signals(session: SessionAPI):
    return session.signals()


@api_command("show_matching", "show_matching(pattern)",
             "Plot signals matching a glob pattern (e.g., 'v(q*)')")
def _cmd_show_matching(session: SessionAPI, pattern: str):
    return session.show_matching(pattern)


@api_command("range", "range(xmin=None, xmax=None, ymin=None, ymax=None)",
             "Set view range of the active panel")
def _cmd_range(session: SessionAPI, xmin: float = None, xmax: float = None,
               ymin: float = None, ymax: float = None):
    return session.range(xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)


@api_command("log_x", "log_x(on=True)",
             "Toggle X-axis log mode")
def _cmd_log_x(session: SessionAPI, on: bool = True):
    return session.log_x(on)


@api_command("log_y", "log_y(on=True)",
             "Toggle Y-axis log mode")
def _cmd_log_y(session: SessionAPI, on: bool = True):
    return session.log_y(on)


@api_command("info", "info()",
             "Return session metadata")
def _cmd_info(session: SessionAPI):
    return session.info()


@api_command("export_csv", "export_csv(path, signals=None)",
             "Export current traces to a CSV file")
def _cmd_export_csv(session: SessionAPI, path: str, signals=None):
    return session.export_csv(path, signals)


@api_command("export_plot", "export_plot(path, width=1200, height=800)",
             "Export current plot to PNG/SVG (requires GUI)")
def _cmd_export_plot(session: SessionAPI, path: str,
                     width: int = 1200, height: int = 800):
    return session.export_plot(path, width, height)


# ---- Cursor commands ----

@api_command("cursor_xa", "cursor_xa(value)",
             "Set XA cursor position (supports SPICE suffixes: 1m, 1u)")
def _cmd_cursor_xa(session: SessionAPI, value=None):
    return session.cursor_xa(value)

@api_command("cursor_xb", "cursor_xb(value)",
             "Set XB cursor position")
def _cmd_cursor_xb(session: SessionAPI, value=None):
    return session.cursor_xb(value)

@api_command("cursor_ya", "cursor_ya(value)",
             "Set YA cursor position")
def _cmd_cursor_ya(session: SessionAPI, value=None):
    return session.cursor_ya(value)

@api_command("cursor_yb", "cursor_yb(value)",
             "Set YB cursor position")
def _cmd_cursor_yb(session: SessionAPI, value=None):
    return session.cursor_yb(value)

@api_command("cursor_delta", "cursor_delta()",
             "Get delta between XA/XB and YA/YB cursors")
def _cmd_cursor_delta(session: SessionAPI):
    return session.cursor_delta()

@api_command("cursor", "cursor()",
             "Get all cursor positions and deltas")
def _cmd_cursor(session: SessionAPI):
    return session.cursor()


# ---- View toggle commands ----

@api_command("grid", "grid(on=True)",
             "Toggle or set grid visibility")
def _cmd_grid(session: SessionAPI, on: bool = None):
    return session.grid(on)

@api_command("legend", "legend(on=True)",
             "Toggle or set legend visibility")
def _cmd_legend(session: SessionAPI, on: bool = None):
    return session.legend(on)

@api_command("cross_hair", "cross_hair(on=True)",
             "Toggle or set crosshair visibility")
def _cmd_cross_hair(session: SessionAPI, on: bool = None):
    return session.cross_hair(on)

@api_command("zoom_fit", "zoom_fit()",
             "Zoom to fit all traces in view")
def _cmd_zoom_fit(session: SessionAPI):
    return session.zoom_fit()

@api_command("auto_range_x", "auto_range_x()",
             "Auto-range X axis")
def _cmd_auto_range_x(session: SessionAPI):
    return session.auto_range_x()

@api_command("auto_range_y", "auto_range_y()",
             "Auto-range Y axis")
def _cmd_auto_range_y(session: SessionAPI):
    return session.auto_range_y()

@api_command("title", "title(text)",
             "Set plot title")
def _cmd_title(session: SessionAPI, text: str = None):
    return session.title(text)


# ---- Bus / Digital commands ----

@api_command("bus", "bus(signals, name='bus')",
             "Group digital signals into a bus (e.g., bus(['d0','d1']))")
def _cmd_bus(session: SessionAPI, signals, name: str = "bus"):
    return session.bus(signals, name)

@api_command("expand", "expand(bus_name)",
             "Expand bus members to show individual bits")
def _cmd_expand(session: SessionAPI, bus_name: str):
    return session.expand(bus_name)

@api_command("collapse", "collapse(bus_name)",
             "Collapse bus members to hide individual bits")
def _cmd_collapse(session: SessionAPI, bus_name: str):
    return session.collapse(bus_name)

@api_command("digital", "digital(sig, on=True)",
             "Toggle digital/analog view for a signal")
def _cmd_digital(session: SessionAPI, sig, on: bool = True):
    return session.digital(sig, on)


# ---- Cursor visibility commands ----

@api_command("cursor_xa_visible", "cursor_xa_visible(on=True)",
             "Show/hide XA cursor")
def _cmd_cursor_xa_visible(session: SessionAPI, on: bool = True):
    return session.cursor_xa_visible(on)

@api_command("cursor_xb_visible", "cursor_xb_visible(on=True)",
             "Show/hide XB cursor")
def _cmd_cursor_xb_visible(session: SessionAPI, on: bool = True):
    return session.cursor_xb_visible(on)

@api_command("cursor_ya_visible", "cursor_ya_visible(on=True)",
             "Show/hide YA cursor")
def _cmd_cursor_ya_visible(session: SessionAPI, on: bool = True):
    return session.cursor_ya_visible(on)

@api_command("cursor_yb_visible", "cursor_yb_visible(on=True)",
             "Show/hide YB cursor")
def _cmd_cursor_yb_visible(session: SessionAPI, on: bool = True):
    return session.cursor_yb_visible(on)


# ---- Eye diagram ----

@api_command("eye", "eye(sig, period=None)",
             "Show eye diagram for a signal (period supports suffixes: 100n)")
def _cmd_eye(session: SessionAPI, sig: str, period: str = None):
    return session.eye(sig, period)

@api_command("fft_config", "fft_config(window=None, fft_size=None, representation=None)",
             "Configure FFT parameters (window, fft_size, representation=linear|db)")
def _cmd_fft_config(session: SessionAPI, window: str = None,
                    fft_size: int = None, representation: str = None):
    return session.fft_config(window=window, fft_size=fft_size,
                              representation=representation)

# ---- Reload / Export ----

@api_command("reload", "reload()",
             "Re-read the current file (post-simulation refresh)")
def _cmd_reload(session: SessionAPI):
    return session.reload()

@api_command("theme", "theme(name)",
             "Set plot theme (dark or light)")
def _cmd_theme(session: SessionAPI, name: str = None):
    return session.theme(name)


@api_command("change_x", "change_x(var)",
             "Change the X-axis variable (e.g., change_x('v(r2)'))")
def _cmd_change_x(session: SessionAPI, var: str):
    return session.change_x(var)


# ---- Zoom ----

@api_command("zoom_in", "zoom_in()", "Zoom in")
def _cmd_zoom_in(session: SessionAPI):
    return session.zoom_in()

@api_command("zoom_out", "zoom_out()", "Zoom out")
def _cmd_zoom_out(session: SessionAPI):
    return session.zoom_out()


# ---- Panel management ----

@api_command("split_horizontal", "split_horizontal()",
             "Split active panel horizontally")
def _cmd_split_horizontal(session: SessionAPI):
    return session.split_horizontal()

@api_command("split_vertical", "split_vertical()",
             "Split active panel vertically")
def _cmd_split_vertical(session: SessionAPI):
    return session.split_vertical()

@api_command("close_panel", "close_panel()",
             "Close the active panel")
def _cmd_close_panel(session: SessionAPI):
    return session.close_panel()


@api_command("set_trace", "set_trace(name, height=None, width=None, color=None, alias=None)",
             "Set trace properties: height, line width, color, alias")
def _cmd_set_trace(session: SessionAPI, name: str, height: float = None,
                   width: int = None, color=None, alias: str = None):
    return session.set_trace(name, height=height, width=width,
                             color=color, alias=alias)


# ---- View Templates ----

@api_command("save_template", "save_template(name)",
             "Save current panel view as a named template")
def _cmd_save_template(session: SessionAPI, name: str):
    return session.save_template(name)

@api_command("load_template", "load_template(name)",
             "Load a saved view template onto the active panel")
def _cmd_load_template(session: SessionAPI, name: str):
    return session.load_template(name)

@api_command("list_templates", "list_templates()",
             "List all saved view templates")
def _cmd_list_templates(session: SessionAPI):
    return session.list_templates()
