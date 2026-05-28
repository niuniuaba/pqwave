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

    # ---- Monte Carlo ----

    def mc_load(self, source: str, source_type: str = "stepped",
                grouping_pattern: str | None = None) -> dict:
        """Load file(s) as Monte Carlo run collection."""
        if self._on_mutation:
            self._on_mutation("mc_load", source=source, source_type=source_type,
                              grouping_pattern=grouping_pattern)
            return {"status": "ok"}
        from pqwave.models.rawfile import RawFile
        from pqwave.models.mc_collection import (
            build_mc_from_stepped, build_mc_from_pattern, build_mc_from_multi_files
        )
        if source_type == "stepped":
            raw = RawFile(source)
            mc = build_mc_from_stepped(raw, source)
        elif source_type == "multi":
            paths = source if isinstance(source, list) else [source]
            mc = build_mc_from_multi_files(paths)
        elif source_type == "pattern":
            raw = RawFile(source)
            mc = build_mc_from_pattern(raw, source, grouping_pattern or "vout")
        else:
            return {"status": "error", "message": f"Unknown source_type: {source_type}"}
        self._state.mc_collection = mc
        return {"status": "ok", "runs": len(mc.runs)}

    def mc_info(self) -> dict:
        """Return info about the current MC collection."""
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "no_mc_data"}
        return {
            "status": "ok",
            "runs": len(mc.runs),
            "nominal": mc.nominal_index,
            "display_mode": mc.display_mode,
            "envelope_sigma": mc.envelope_sigma,
            "parameters": list(mc.parameters.keys()),
            "run_filter": mc.run_filter,
        }

    def mc_style(self, mode: str, sigma: float = 3.0) -> dict:
        """Set MC display mode: spaghetti, envelope, or single."""
        if self._on_mutation:
            self._on_mutation("mc_style", mode=mode, sigma=sigma)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded"}
        mc.display_mode = mode
        mc.envelope_sigma = sigma
        return {"status": "ok"}

    def mc_nominal(self, idx: int) -> dict:
        """Set the nominal run index."""
        if self._on_mutation:
            self._on_mutation("mc_nominal", idx=idx)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded"}
        mc.nominal_index = idx
        return {"status": "ok"}

    def mc_filter(self, runs) -> dict:
        """Set run filter: 'all' (str) or list of run indices."""
        if self._on_mutation:
            self._on_mutation("mc_filter", runs=runs)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded"}
        if runs == "all":
            mc.run_filter = None
        else:
            mc.run_filter = runs
        return {"status": "ok"}

    def mc_param(self, name: str, values: list) -> dict:
        """Annotate runs with parameter values."""
        if self._on_mutation:
            self._on_mutation("mc_param", name=name, values=values)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded"}
        mc.parameters[name] = values
        return {"status": "ok"}

    def mc_group(self, signal: str, pattern: str | None = None) -> dict:
        """Group traces into MC runs by naming pattern.

        In GUI mode, delegates to MainWindow which re-scans the active
        dataset for traces matching the pattern. In headless mode, the
        grouping intent is recorded on the MC collection but no data
        reorganization occurs (call mc_load first).
        """
        if self._on_mutation:
            self._on_mutation("mc_group", signal=signal, pattern=pattern)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded — use mc_load first"}
        # In headless mode, record the grouping intent
        if pattern:
            mc.parameters["_grouping_pattern"] = [pattern]
        return {"status": "ok", "signal": signal, "pattern": pattern}

    def mc_ungroup(self, signal: str) -> dict:
        """Ungroup MC runs back to individual traces.

        In GUI mode, delegates to MainWindow which flattens the MC
        collection and removes MC rendering from all panels.
        In headless mode, clears the MC collection entirely.
        """
        if self._on_mutation:
            self._on_mutation("mc_ungroup", signal=signal)
            return {"status": "ok"}
        self._state.mc_collection = None
        return {"status": "ok", "signal": signal}

    def mc_stats(self, signal: str) -> dict:
        """Compute cross-run statistics for a signal group."""
        if self._on_mutation:
            self._on_mutation("mc_stats", signal=signal)
            return {"status": "ok"}
        data = self._mc_get_signal_data(signal)
        if data is None:
            return {"status": "error", "message": f"No MC data for signal {signal}"}
        from pqwave.analysis.multi_run import compute_cross_run_stats
        stats = compute_cross_run_stats(data)
        return {"status": "ok", "mean": stats["mean"].tolist(),
                "std": stats["std"].tolist(), "min": stats["min"].tolist(),
                "max": stats["max"].tolist()}

    def mc_histogram(self, measurement: str, bins: int = 50,
                     range: tuple | None = None) -> dict:
        """Compute histogram of a measurement across MC runs.

        The measurement string must be of the form 'max(v(out))'
        where the function is one of max/min/mean/rms/pk_pk and the
        argument is a signal name.
        """
        if self._on_mutation:
            self._on_mutation("mc_histogram", measurement=measurement,
                              bins=bins, range=range)
            return {"status": "ok"}
        import re
        m = re.match(r"(\w+)\((.*)\)", measurement)
        if not m:
            return {"status": "error", "message": "Measurement must be of form 'max(v(out))'"}
        measure, signal = m.group(1), m.group(2)
        data = self._mc_get_signal_data(signal)
        if data is None:
            return {"status": "error", "message": f"No MC data for signal {signal}"}
        from pqwave.analysis.multi_run import compute_run_measurements
        values = compute_run_measurements(data, measure)
        from pqwave.analysis.histogram import compute_histogram
        hist = compute_histogram(values, bins=bins, norm="count", range=range)
        return {"status": "ok", "counts": hist["counts"].tolist(),
                "centers": hist["centers"].tolist(), "edges": hist["edges"].tolist()}

    def mc_yield(self, signal: str, low: float, high: float,
                  condition: str | None = None) -> dict:
        """Compute yield of runs within spec limits."""
        if self._on_mutation:
            self._on_mutation("mc_yield", signal=signal, low=low,
                              high=high, condition=condition)
            return {"status": "ok"}
        data = self._mc_get_signal_data(signal)
        if data is None:
            return {"status": "error", "message": f"No MC data for signal {signal}"}
        from pqwave.analysis.multi_run import compute_yield
        result = compute_yield(data, low, high, condition)
        if isinstance(result, float):
            return {"status": "ok", "yield_pct": result}
        return {"status": "ok", "yield_pct": result.tolist()}

    def mc_scatter(self, measurement: str, param: str) -> dict:
        """Scatter plot of measurement vs parameter across runs."""
        if self._on_mutation:
            self._on_mutation("mc_scatter", measurement=measurement, param=param)
            return {"status": "ok"}
        import re
        m = re.match(r"(\w+)\((.*)\)", measurement)
        if not m:
            return {"status": "error", "message": "Measurement must be of form 'max(v(out))'"}
        measure, signal = m.group(1), m.group(2)
        data = self._mc_get_signal_data(signal)
        if data is None:
            return {"status": "error", "message": f"No MC data for signal {signal}"}
        mc = self._state.mc_collection
        if mc is None or not mc.has_parameters or param not in mc.parameters:
            return {"status": "error", "message": f"Parameter {param} not annotated"}
        from pqwave.analysis.multi_run import compute_run_measurements
        measurements = compute_run_measurements(data, measure)
        param_vals = mc.parameters[param]
        return {"status": "ok", "x": list(param_vals),
                "y": measurements.tolist(), "param": param, "measure": measure}

    def mc_worst(self, n: int = 5, metric: str = "max_abs_diff") -> dict:
        """Return worst N runs by deviation from nominal."""
        if self._on_mutation:
            self._on_mutation("mc_worst", n=n, metric=metric)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded"}
        # Use first available signal from the collection's datasets
        signal = "v(out)"
        data = self._mc_get_signal_data(signal)
        if data is None:
            # Try any common signal names
            for candidate in ("v(out)", "V(out)", "v(buf)", "out"):
                data = self._mc_get_signal_data(candidate)
                if data is not None:
                    break
        if data is None:
            return {"status": "error", "message": "No trace data available for worst-case analysis"}
        from pqwave.analysis.multi_run import compute_worst_cases
        worst = compute_worst_cases(data, mc.nominal_index, n, metric)
        return {"status": "ok", "worst": worst}

    def mc_sensitivity(self, measurement: str) -> dict:
        """Rank parameters by impact on measurement."""
        if self._on_mutation:
            self._on_mutation("mc_sensitivity", measurement=measurement)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None or not mc.has_parameters:
            return {"status": "error", "message": "No parameters annotated"}
        import re
        m = re.match(r"(\w+)\((.*)\)", measurement)
        if not m:
            return {"status": "error", "message": "Measurement must be of form 'max(v(out))'"}
        measure, signal = m.group(1), m.group(2)
        data = self._mc_get_signal_data(signal)
        if data is None:
            return {"status": "error", "message": f"No MC data for signal {signal}"}
        from pqwave.analysis.multi_run import compute_run_measurements, compute_sensitivity
        import numpy as np
        measurements = compute_run_measurements(data, measure)
        sensitivity = compute_sensitivity(measurements, {
            k: np.array(v) for k, v in mc.parameters.items()
        })
        return {"status": "ok", "sensitivity": sensitivity}

    def mc_correlation_load(self, path: str) -> dict:
        """Load a correlation matrix from a CSV file onto the MC collection."""
        if self._on_mutation:
            self._on_mutation("mc_correlation_load", path=path)
            return {"status": "ok"}
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded"}
        import csv
        try:
            with open(path, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
        except Exception as e:
            return {"status": "error", "message": str(e)}
        if len(rows) < 2:
            return {"status": "error", "message": "CSV must have header + data"}
        headers = rows[0][1:]
        n = len(headers)
        flat = []
        for r in range(n):
            for c in range(n):
                try:
                    val = float(rows[r + 1][c + 1])
                except (IndexError, ValueError):
                    val = 0.0 if r != c else 1.0
                flat.append(val)
        from pqwave.models.mc_collection import CorrelationMatrix
        mc._correlation = CorrelationMatrix(params=headers, matrix=flat)
        return {"status": "ok", "size": n, "params": headers}

    def mc_correlation_show(self) -> dict:
        """Print the current correlation matrix."""
        mc = self._state.mc_collection
        if mc is None:
            return {"status": "error", "message": "No MC data loaded"}
        cm = mc._correlation
        if cm is None:
            return {"status": "error", "message": "No correlation matrix loaded"}
        dense = cm.get_dense()
        lines = ["  " + " ".join(f"{n:>12s}" for n in cm.params)]
        for i, name in enumerate(cm.params):
            row_str = " ".join(f"{dense[i, j]:12.4f}" for j in range(cm.size))
            lines.append(f"  {name:>10s} {row_str}")
        text = "\n".join(lines)
        return {"status": "ok", "size": cm.size, "text": text}

    def mc_correlation_edit(self) -> dict:
        """Open the Correlation Matrix Editor dialog (GUI only)."""
        if self._on_mutation:
            self._on_mutation("mc_correlation")
            return {"status": "ok"}
        return {"status": "error", "message": "Editor requires GUI"}

    def mc_generate(
        self, output_path: str, output_format: str = "csv",
        runs: int = 100, seed: int | None = None,
        nominals: list[float] | None = None,
        sigmas: list[float] | None = None,
    ) -> dict:
        """Generate correlated parameter values to a file.

        Args:
            output_path: Where to write the output.
            output_format: 'csv', 'tsv', 'ngspice', or 'param'.
            runs: Number of perturbed MC runs.
            seed: RNG seed for reproducibility.
            nominals: Optional per-parameter nominal values. Defaults to zeros.
            sigmas: Optional per-parameter absolute variation. Defaults to 0.1.
        """
        if self._on_mutation:
            self._on_mutation("mc_generate", output_path=output_path,
                              output_format=output_format, runs=runs, seed=seed,
                              nominals=nominals, sigmas=sigmas)
            return {"status": "ok"}
        return _mc_generate_core(
            self._state, output_path, output_format, runs, seed, nominals, sigmas,
        )

    def _mc_get_signal_data(self, signal: str):
        """Get 2D data array (n_runs, n_points) for an MC signal from state."""
        import numpy as np
        mc = self._state.mc_collection
        if mc is None or mc.active_count == 0:
            return None
        run_data = []
        for run_idx in mc.active_runs:
            ds_idx, step_idx = mc.get_run_data_indices(run_idx)
            if ds_idx >= len(self._state.datasets):
                continue
            ds = self._state.datasets[ds_idx]
            var = ds.get_variable(signal) if hasattr(ds, 'get_variable') else None
            if var is not None:
                y = var.y_data if hasattr(var, 'y_data') else np.array(var.data)
                run_data.append(y)
        if not run_data:
            return None
        n_points = max(len(y) for y in run_data)
        data = np.zeros((len(run_data), n_points))
        for i, y in enumerate(run_data):
            data[i, :len(y)] = y
        return data

    # ---- KiCad bridge methods ----

    def kicad_watch(self, path: str) -> dict:
        path = os.path.abspath(path)
        if self._on_mutation:
            self._on_mutation("kicad_watch", path=path)
            return {"status": "ok", "path": path}
        self._kicad_watched_path = path
        return {"status": "ok", "path": path}

    def kicad_simulate(self, sch_path: str | None = None) -> dict:
        path = sch_path or getattr(self, "_kicad_watched_path", None)
        if not path:
            raise ValueError("No .kicad_sch file specified or watched")
        if self._on_mutation:
            self._on_mutation("kicad_simulate", path=path)
            return {"status": "ok", "triggered": True}
        from pqwave.bridge.kicad.bridge import KiCadBridge
        bridge = KiCadBridge()
        result = bridge.simulate(path)
        if result["raw_file"]:
            self.load(result["raw_file"])
        return {"status": "ok", "raw_file": result.get("raw_file", "")}

    def kicad_unwatch(self) -> dict:
        if self._on_mutation:
            self._on_mutation("kicad_unwatch")
            return {"status": "ok"}
        self._kicad_watched_path = None
        return {"status": "ok"}

    def kicad_probe_net(self, name: str) -> dict:
        if self._on_mutation:
            self._on_mutation("kicad_probe_net", name=name)
            return {"status": "ok"}
        from pqwave.bridge.kicad.cross_probe import CrossProbeClient
        client = CrossProbeClient()
        if client.connect_to_kicad():
            client.probe_net(name)
            client.disconnect()
            return {"status": "ok", "net": name}
        return {"status": "error", "message": "KiCad not running"}

    def kicad_probe_part(self, ref: str, pin: str | None = None) -> dict:
        if self._on_mutation:
            self._on_mutation("kicad_probe_part", ref=ref, pin=pin)
            return {"status": "ok"}
        from pqwave.bridge.kicad.cross_probe import CrossProbeClient
        client = CrossProbeClient()
        if client.connect_to_kicad():
            client.probe_part(ref, pin)
            client.disconnect()
            return {"status": "ok", "ref": ref}
        return {"status": "error", "message": "KiCad not running"}

    def kicad_clear(self) -> dict:
        if self._on_mutation:
            self._on_mutation("kicad_clear")
            return {"status": "ok"}
        from pqwave.bridge.kicad.cross_probe import CrossProbeClient
        client = CrossProbeClient()
        if client.connect_to_kicad():
            client.clear()
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "KiCad not running"}

    def kicad_config(self, key: str, value=None) -> dict:
        from pqwave.models.state import ApplicationState
        state = ApplicationState()
        if not hasattr(state, "_kicad_config"):
            state._kicad_config = {
                "auto_simulate": True,
                "crossprobe_port": 4243,
                "fix_slashes": True,
                "fix_diode_pins": True,
                "fix_bjt_pins": True,
            }
        if value is None:
            return {"status": "ok", key: state._kicad_config.get(key)}
        state._kicad_config[key] = value
        return {"status": "ok", key: value}

    # ---- Lepton-EDA bridge methods ----

    def lepton_watch(self, path: str) -> dict:
        """Start watching a .sch file for changes."""
        if self._on_mutation:
            self._on_mutation("lepton_watch", path=path)
            return {"status": "ok"}
        self._lepton_watched_path = path
        return {"status": "ok"}

    def lepton_simulate(self, sch_path: str | None = None) -> dict:
        """Run export -> post-process -> ngspice pipeline."""
        path = sch_path or getattr(self, "_lepton_watched_path", None)
        if not path:
            raise ValueError("No .sch file specified or watched")
        if self._on_mutation:
            self._on_mutation("lepton_simulate", path=path)
            return {"status": "ok"}
        from pqwave.bridge.lepton.bridge import LeptonBridge
        bridge = LeptonBridge()
        return bridge.simulate(path)

    def lepton_unwatch(self) -> dict:
        """Stop watching the schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_unwatch")
            return {"status": "ok"}
        self._lepton_watched_path = None
        return {"status": "ok"}

    def lepton_probe_net(self, name: str) -> dict:
        """Highlight a net in lepton-schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_probe_net", name=name)
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.probe_net(name)
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running or pqwave server not active"}

    def lepton_probe_part(self, ref: str, pin: str | None = None) -> dict:
        """Highlight a component in lepton-schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_probe_part", ref=ref, pin=pin)
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.probe_part(ref, pin)
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_clear(self) -> dict:
        """Clear all lepton-schematic highlights."""
        if self._on_mutation:
            self._on_mutation("lepton_clear")
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.clear()
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_annotate_dc(self, voltages: dict[str, float] | None = None) -> dict:
        """Stamp DC voltages onto lepton-schematic netname attributes."""
        if self._on_mutation:
            self._on_mutation("lepton_annotate_dc", voltages=voltages)
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            for netname, voltage in (voltages or {}).items():
                client.send_command(f"$ANNOTATE:DC {netname} {voltage}")
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_clear_annotations(self) -> dict:
        """Clear all floating labels and DC stamps from lepton-schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_clear_annotations")
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.send_command("$CLEAR:ANNOTATIONS")
            client.send_command("$CLEAR:DC")
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_config(self, key: str, value=None) -> dict:
        """Get or set lepton-eda bridge configuration.

        Keys:
            port: int -- TCP port for cross-probe server (default 9424)
            auto_simulate: bool -- auto-simulate on file save (default True)
            install_server: (write-only) -- install pqwave-server.scm to autoload dir
        """
        if key == "install_server":
            from pqwave.bridge.lepton.cross_probe import install_scheme_server
            return install_scheme_server()

        from pqwave.models.state import ApplicationState
        state = ApplicationState()
        if not hasattr(state, "_lepton_config"):
            state._lepton_config = {"port": 9424, "auto_simulate": True}
        if value is None:
            return {"status": "ok", "data": state._lepton_config.get(key)}
        state._lepton_config[key] = value
        return {"status": "ok"}

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
        elif ext == ".fst":
            info = self._load_fst(abs_path)
        elif ext == ".ghw":
            info = self._load_ghw(abs_path)
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

    def _load_fst(self, path: str) -> dict:
        from pqwave.models.fst_adapter import FstAdapter
        from pqwave.models.dataset import Dataset

        fst = FstAdapter(path)
        dataset = Dataset(fst, 0)
        self._state.add_dataset(dataset)

        if not self._state.active_panel_id:
            self._state.register_panel("panel_0")

        if self._state.datasets:
            self._state.current_dataset_idx = len(self._state.datasets) - 1

        return {
            "file_type": "fst",
            "n_points": dataset.n_points,
            "n_variables": dataset.n_variables,
            "signals": dataset.get_variable_names(),
        }

    def _load_ghw(self, path: str) -> dict:
        from pqwave.models.ghw_adapter import GhwAdapter
        from pqwave.models.dataset import Dataset

        ghw = GhwAdapter(path)
        dataset = Dataset(ghw, 0)
        self._state.add_dataset(dataset)

        if not self._state.active_panel_id:
            self._state.register_panel("panel_0")

        if self._state.datasets:
            self._state.current_dataset_idx = len(self._state.datasets) - 1

        return {
            "file_type": "ghw",
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


def _mc_generate_core(
    state,
    output_path: str,
    output_format: str = "csv",
    runs: int = 100,
    seed: int | None = None,
    nominals: list[float] | None = None,
    sigmas: list[float] | None = None,
) -> dict:
    """Shared implementation for mc_generate — used by API and GUI dispatch."""
    mc = state.mc_collection
    if mc is None:
        return {"status": "error", "message": "No MC data loaded"}
    cm = mc._correlation
    if cm is None:
        return {"status": "error", "message": "No correlation matrix loaded"}

    from pqwave.analysis.correlation import (
        compute_cholesky, generate_correlated_values,
        generate_control_script, generate_csv, generate_param_snippet,
    )
    try:
        L = compute_cholesky(cm)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    n = cm.size
    noms = nominals if nominals else [0.0] * n
    sigs = sigmas if sigmas else [0.1] * n
    params = [
        {"model": "", "param": name, "nominal": noms[i], "logical_name": name}
        for i, name in enumerate(cm.params)
    ]

    values = generate_correlated_values(L, noms, sigs, runs, seed)

    output_format = output_format.lower()
    if output_format == "ngspice":
        missing = [p["logical_name"] for p in params if not p.get("model")]
        if missing:
            return {
                "status": "error",
                "message": (
                    "ngspice format requires model names for all parameters. "
                    f"Missing model for: {', '.join(missing)}. "
                    "Load a .model file first, or use CSV format."
                ),
            }
        generate_control_script(
            params, noms, L, output_path,
            sim_command="tran 1n 100n 0", n_runs=runs, seed=seed,
        )
    elif output_format == "csv":
        generate_csv(values, cm.params, output_path)
    elif output_format == "tsv":
        generate_csv(values, cm.params, output_path, delimiter="\t")
    elif output_format == "param":
        generate_param_snippet(values, cm.params, output_path)
    else:
        return {"status": "error", "message": f"Unknown format: {output_format}"}

    return {"status": "ok", "runs": runs, "params": n, "path": output_path}


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


# ---- Multi-dataset commands ----

@api_command("datasets", "datasets()", "List all loaded datasets")
def _cmd_datasets(session: SessionAPI):
    return session.datasets()

@api_command("unload", "unload(idx)", "Remove a dataset by index")
def _cmd_unload(session: SessionAPI, idx: int):
    return session.unload(idx)


# ---- MC commands ----

@api_command("mc_load", "mc_load(source, source_type='stepped')",
             "Load file(s) as Monte Carlo run collection")
def _cmd_mc_load(session: SessionAPI, source, source_type: str = "stepped",
                 grouping_pattern: str | None = None):
    return session.mc_load(source, source_type, grouping_pattern)

@api_command("mc_info", "mc_info()", "Show current MC collection info")
def _cmd_mc_info(session: SessionAPI):
    return session.mc_info()

@api_command("mc_style", "mc_style(mode, sigma=3)",
             "Set MC display: spaghetti, envelope, or single")
def _cmd_mc_style(session: SessionAPI, mode: str, sigma: float = 3.0):
    return session.mc_style(mode, sigma)

@api_command("mc_nominal", "mc_nominal(idx)", "Set the nominal run index")
def _cmd_mc_nominal(session: SessionAPI, idx: int):
    return session.mc_nominal(idx)

@api_command("mc_filter", "mc_filter(runs)", "Filter runs: 'all' or list of indices")
def _cmd_mc_filter(session: SessionAPI, runs):
    return session.mc_filter(runs)

@api_command("mc_param", "mc_param(name, values)",
             "Annotate runs with parameter values")
def _cmd_mc_param(session: SessionAPI, name: str, values: list):
    return session.mc_param(name, values)

@api_command("mc_stats", "mc_stats(signal)", "Cross-run statistics for a signal")
def _cmd_mc_stats(session: SessionAPI, signal: str):
    return session.mc_stats(signal)

@api_command("mc_histogram", "mc_histogram(measurement, bins=50)",
             "Histogram of a measurement across MC runs")
def _cmd_mc_histogram(session: SessionAPI, measurement: str, bins: int = 50):
    return session.mc_histogram(measurement, bins)

@api_command("mc_yield", "mc_yield(signal, low, high)",
             "Compute yield of runs within spec limits")
def _cmd_mc_yield(session: SessionAPI, signal: str, low: float, high: float):
    return session.mc_yield(signal, low, high)

@api_command("mc_scatter", "mc_scatter(measurement, param)",
             "Scatter plot of measurement vs parameter")
def _cmd_mc_scatter(session: SessionAPI, measurement: str, param: str):
    return session.mc_scatter(measurement, param)

@api_command("mc_worst", "mc_worst(n=5)", "Return worst N runs")
def _cmd_mc_worst(session: SessionAPI, n: int = 5):
    return session.mc_worst(n)

@api_command("mc_sensitivity", "mc_sensitivity(measurement)",
             "Rank parameters by impact on measurement")
def _cmd_mc_sensitivity(session: SessionAPI, measurement: str):
    return session.mc_sensitivity(measurement)

# ---- Correlation commands ----

@api_command("mc_correlation_load", "mc_correlation_load(path)",
             "Load a correlation matrix from CSV onto the MC collection")
def _cmd_mc_correlation_load(session: SessionAPI, path: str):
    return session.mc_correlation_load(path)

@api_command("mc_correlation_show", "mc_correlation_show()",
             "Print the current correlation matrix")
def _cmd_mc_correlation_show(session: SessionAPI):
    return session.mc_correlation_show()

@api_command("mc_correlation_edit", "mc_correlation_edit()",
             "Open the Correlation Matrix Editor dialog (GUI)")
def _cmd_mc_correlation_edit(session: SessionAPI):
    return session.mc_correlation_edit()

@api_command("mc_generate", "mc_generate(path, output_format='csv', runs=100, seed=None, nominals=None, sigmas=None)",
             "Generate correlated parameter values to a file")
def _cmd_mc_generate(session: SessionAPI, path: str, output_format: str = "csv",
                    runs: int = 100, seed: int | None = None,
                    nominals: list[float] | None = None,
                    sigmas: list[float] | None = None):
    return session.mc_generate(path, output_format=output_format, runs=runs, seed=seed,
                               nominals=nominals, sigmas=sigmas)


@api_command("kicad_watch", "kicad_watch(path)",
             "Watch a .kicad_sch file for changes and auto-simulate on save")
def _cmd_kicad_watch(session: SessionAPI, path: str):
    return session.kicad_watch(path)


@api_command("kicad_unwatch", "kicad_unwatch()",
             "Stop watching the KiCad schematic file")
def _cmd_kicad_unwatch(session: SessionAPI):
    return session.kicad_unwatch()


@api_command("kicad_simulate", "kicad_simulate(sch_path=None)",
             "Manually trigger KiCad simulation pipeline")
def _cmd_kicad_simulate(session: SessionAPI, sch_path: str = None):
    return session.kicad_simulate(sch_path)


@api_command("kicad_probe_net", "kicad_probe_net(name)",
             "Cross-probe: highlight a net in KiCad schematic")
def _cmd_kicad_probe_net(session: SessionAPI, name: str):
    return session.kicad_probe_net(name)


@api_command("kicad_probe_part", "kicad_probe_part(ref, pin=None)",
             "Cross-probe: highlight a component or pin in KiCad schematic")
def _cmd_kicad_probe_part(session: SessionAPI, ref: str, pin: str = None):
    return session.kicad_probe_part(ref, pin)


@api_command("kicad_clear", "kicad_clear()",
             "Clear all cross-probe highlights in KiCad")
def _cmd_kicad_clear(session: SessionAPI):
    return session.kicad_clear()


@api_command("kicad_config", "kicad_config(key, value=None)",
             "Get or set KiCad bridge configuration")
def _cmd_kicad_config(session: SessionAPI, key: str, value=None):
    return session.kicad_config(key, value)
