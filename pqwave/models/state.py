#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ApplicationState - Global application state management.

This module provides a singleton class that manages the global state of the
application, including datasets, traces, axis configurations, and UI settings.
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

from .dataset import Dataset
from .trace import Trace, AxisAssignment
from pqwave.communication.window_registry import get_registry, WindowRegistry
from pqwave.communication.command_handler import CommandHandler


class ViewboxTheme(Enum):
    """Viewbox color themes."""
    DARK = 'dark'
    LIGHT = 'light'


# Theme color definitions
THEME_COLORS = {
    ViewboxTheme.DARK: {
        'background': '#000000',
        'foreground': '#E0E0E0',
    },
    ViewboxTheme.LIGHT: {
        'background': '#FFFFFF',
        'foreground': '#000000',
    },
}


class AxisId(Enum):
    """Axis identifiers."""
    X = 'X'
    Y1 = 'Y1'
    Y2 = 'Y2'


@dataclass
class AxisConfig:
    """Configuration for a single axis."""
    label: str = ''
    log_mode: bool = False
    range: Optional[Tuple[float, float]] = None
    visible: bool = True
    grid: bool = True
    auto_range: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'label': self.label,
            'log_mode': self.log_mode,
            'range': self.range,
            'visible': self.visible,
            'grid': self.grid,
            'auto_range': self.auto_range
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AxisConfig':
        """Create from dictionary."""
        raw_range = data.get('range')
        if raw_range is not None:
            raw_range = (float(raw_range[0]), float(raw_range[1]))
        label = data.get('label', '')
        if label.endswith(' (dB)'):
            label = label[:-5]
        return cls(
            label=label,
            log_mode=data.get('log_mode', False),
            range=raw_range,
            visible=data.get('visible', True),
            grid=data.get('grid', True),
            auto_range=data.get('auto_range', True)
        )


@dataclass
class PanelState:
    """Per-panel state: traces, axis configs, domain, and X variable."""
    panel_id: str
    traces: List[Trace] = field(default_factory=list)
    axis_configs: Dict[AxisId, AxisConfig] = field(default_factory=dict)
    domain: str = "time"
    current_x_var: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'panel_id': self.panel_id,
            'traces': [t.to_dict() for t in self.traces],
            'axis_configs': {ax.value: cfg.to_dict() for ax, cfg in self.axis_configs.items()},
            'domain': self.domain,
            'current_x_var': self.current_x_var,
        }

    def to_per_file_dict(self) -> Dict[str, Any]:
        return {
            'panel_id': self.panel_id,
            'traces': [t.to_per_file_dict() for t in self.traces],
            'axis_configs': {ax.value: cfg.to_dict() for ax, cfg in self.axis_configs.items()},
            'domain': self.domain,
            'current_x_var': self.current_x_var,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PanelState':
        axis_configs = {}
        for key, ax_data in data.get('axis_configs', {}).items():
            try:
                axis_id = AxisId(key)
                axis_configs[axis_id] = AxisConfig.from_dict(ax_data)
            except ValueError:
                continue
        for axis_id in AxisId:
            if axis_id not in axis_configs:
                axis_configs[axis_id] = AxisConfig(label=axis_id.value)

        traces = [Trace.from_dict(t) for t in data.get('traces', [])]
        return cls(
            panel_id=data.get('panel_id', ''),
            traces=traces,
            axis_configs=axis_configs,
            domain=data.get('domain', 'time'),
            current_x_var=data.get('current_x_var'),
        )


@dataclass
class FftConfig:
    """Global FFT configuration."""
    window: str = "none"          # window function name
    fft_size: int = 0             # 0 = auto nextpow2
    dc_removal: bool = True
    representation: str = "db"    # db, linear
    x_range_mode: str = "full"    # "full", "current zoom", "manual"
    x_range_start: float = 0.0    # manual range start (seconds)
    x_range_end: float = 0.0      # manual range end (seconds)
    binomial_smooth: int = 0      # 0 = off, N = number of passes

    def to_dict(self) -> Dict[str, Any]:
        return {
            'window': self.window,
            'fft_size': self.fft_size,
            'dc_removal': self.dc_removal,
            'representation': self.representation,
            'x_range_mode': self.x_range_mode,
            'x_range_start': self.x_range_start,
            'x_range_end': self.x_range_end,
            'binomial_smooth': self.binomial_smooth,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FftConfig':
        return cls(
            window=str(data.get('window', 'none')),
            fft_size=int(data.get('fft_size', 0)),
            dc_removal=bool(data.get('dc_removal', True)),
            representation=str(data.get('representation', 'db')),
            x_range_mode=str(data.get('x_range_mode', 'full')),
            x_range_start=float(data.get('x_range_start', 0.0)),
            x_range_end=float(data.get('x_range_end', 0.0)),
            binomial_smooth=int(data.get('binomial_smooth', 0)),
        )


@dataclass
class FontConfig:
    """Font configuration for a UI element group."""
    family: str = ''    # empty = system default
    size: int = 0       # 0 = system default point size
    color: str = ''     # empty = use theme foreground color

    def to_dict(self) -> Dict[str, Any]:
        return {'family': self.family, 'size': self.size, 'color': self.color}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FontConfig':
        return cls(
            family=data.get('family', ''),
            size=data.get('size', 0),
            color=data.get('color', ''),
        )


class ApplicationState:
    """Singleton class managing global application state.

    This class follows the singleton pattern to ensure there's only one
    instance of application state throughout the application.
    """

    _instance: Optional['ApplicationState'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize default state."""
        self.datasets: List[Dataset] = []
        self.current_dataset_idx: int = 0

        # Per-panel state (replaces flat traces / axis_configs / current_x_var)
        self.panels: Dict[str, PanelState] = {}
        self.panel_order: List[str] = []
        self.active_panel_id: Optional[str] = None

        # UI settings
        self.grid_visible: bool = True
        self.legend_visible: bool = True
        self.status_bar_visible: bool = True
        self.toolbar_visible: bool = True
        self.plot_title: str = ''
        self.viewbox_theme: ViewboxTheme = ViewboxTheme.DARK

        # Font configurations (all empty = use defaults)
        self.title_font: FontConfig = FontConfig()
        self.label_font: FontConfig = FontConfig()
        self.tick_font: FontConfig = FontConfig()
        self.ui_font: FontConfig = FontConfig()

        self.fft_config: FftConfig = FftConfig()

        self.window_registry: WindowRegistry = get_registry()
        self.command_handler: Optional[CommandHandler] = None

    # --- Backward-compat properties (route through active panel) ---

    @property
    def traces(self) -> List[Trace]:
        if self.active_panel_id and self.active_panel_id in self.panels:
            return self.panels[self.active_panel_id].traces
        return []

    @traces.setter
    def traces(self, value: List[Trace]) -> None:
        if self.active_panel_id and self.active_panel_id in self.panels:
            self.panels[self.active_panel_id].traces = value

    @property
    def current_x_var(self) -> Optional[str]:
        if self.active_panel_id and self.active_panel_id in self.panels:
            return self.panels[self.active_panel_id].current_x_var
        return None

    @current_x_var.setter
    def current_x_var(self, value: Optional[str]) -> None:
        if self.active_panel_id and self.active_panel_id in self.panels:
            self.panels[self.active_panel_id].current_x_var = value

    @property
    def axis_configs(self) -> Dict[AxisId, AxisConfig]:
        if self.active_panel_id and self.active_panel_id in self.panels:
            return self.panels[self.active_panel_id].axis_configs
        return {}

    @axis_configs.setter
    def axis_configs(self, value: Dict[AxisId, AxisConfig]) -> None:
        if self.active_panel_id and self.active_panel_id in self.panels:
            self.panels[self.active_panel_id].axis_configs = value

    # --- Panel lifecycle ---

    def register_panel(self, panel_id: str, copy_from: Optional[str] = None) -> None:
        """Register a new panel, optionally copying state from an existing panel."""
        if copy_from and copy_from in self.panels:
            import copy
            panel_state = copy.deepcopy(self.panels[copy_from])
            panel_state.panel_id = panel_id
        else:
            panel_state = PanelState(panel_id=panel_id)
            panel_state.axis_configs = {
                AxisId.X: AxisConfig(label='X'),
                AxisId.Y1: AxisConfig(label='Y1'),
                AxisId.Y2: AxisConfig(label='Y2'),
            }
        self.panels[panel_id] = panel_state
        self.panel_order.append(panel_id)
        if self.active_panel_id is None:
            self.active_panel_id = panel_id

    def unregister_panel(self, panel_id: str) -> bool:
        """Remove a panel from state. Returns False if panel not found."""
        if panel_id not in self.panels:
            return False
        del self.panels[panel_id]
        if panel_id in self.panel_order:
            self.panel_order.remove(panel_id)
        if self.active_panel_id == panel_id:
            self.active_panel_id = self.panel_order[0] if self.panel_order else None
        return True

    # Dataset management

    @property
    def current_dataset(self) -> Optional[Dataset]:
        """Get the current dataset."""
        if self.datasets and 0 <= self.current_dataset_idx < len(self.datasets):
            return self.datasets[self.current_dataset_idx]
        return None

    def add_dataset(self, dataset: Dataset) -> int:
        """Add a dataset and return its index."""
        self.datasets.append(dataset)
        return len(self.datasets) - 1

    def remove_dataset(self, dataset_idx: int) -> bool:
        """Remove a dataset by index from all panels."""
        if 0 <= dataset_idx < len(self.datasets):
            for panel_state in self.panels.values():
                panel_state.traces = [t for t in panel_state.traces if t.dataset_idx != dataset_idx]
                for trace in panel_state.traces:
                    if trace.dataset_idx > dataset_idx:
                        trace.dataset_idx -= 1
            self.datasets.pop(dataset_idx)
            if self.current_dataset_idx >= len(self.datasets):
                self.current_dataset_idx = max(0, len(self.datasets) - 1)
            return True
        return False

    def set_current_dataset(self, dataset_idx: int) -> bool:
        """Set current dataset index."""
        if 0 <= dataset_idx < len(self.datasets):
            self.current_dataset_idx = dataset_idx
            return True
        return False

    def clear_datasets(self) -> None:
        """Clear all datasets and associated traces from all panels."""
        self.datasets.clear()
        for panel_state in self.panels.values():
            panel_state.traces.clear()
        self.current_dataset_idx = 0

    # Trace management

    def add_trace(self, trace: Trace) -> None:
        """Add a trace."""
        self.traces.append(trace)

    def remove_trace(self, trace_idx: int) -> bool:
        """Remove a trace by index."""
        if 0 <= trace_idx < len(self.traces):
            self.traces.pop(trace_idx)
            return True
        return False

    def clear_traces(self) -> None:
        """Remove all traces."""
        self.traces.clear()

    def get_traces_for_dataset(self, dataset_idx: int) -> List[Trace]:
        """Get all traces for a specific dataset."""
        return [t for t in self.traces if t.dataset_idx == dataset_idx]

    # Axis configuration

    def get_axis_config(self, axis_id: AxisId) -> AxisConfig:
        """Get configuration for an axis."""
        configs = self.axis_configs
        if axis_id in configs:
            return configs[axis_id]
        return AxisConfig(label=axis_id.value)

    def set_axis_config(self, axis_id: AxisId, config: AxisConfig) -> None:
        """Set configuration for an axis."""
        self.axis_configs[axis_id] = config

    def set_axis_log_mode(self, axis_id: AxisId, log_mode: bool) -> None:
        """Set log mode for an axis."""
        self.axis_configs[axis_id].log_mode = log_mode

    def set_axis_range(self, axis_id: AxisId, range_min: float, range_max: float) -> None:
        """Set range for an axis."""
        self.axis_configs[axis_id].range = (range_min, range_max)
        self.axis_configs[axis_id].auto_range = False

    def set_axis_auto_range(self, axis_id: AxisId) -> None:
        """Enable auto-ranging for an axis."""
        self.axis_configs[axis_id].auto_range = True
        self.axis_configs[axis_id].range = None

    def set_viewbox_theme(self, theme: ViewboxTheme) -> None:
        """Set the viewbox theme."""
        self.viewbox_theme = theme

    # State serialization

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire state to serializable dictionary."""
        result = {
            'datasets': [
                {
                    'title': ds.title,
                    'plotname': ds.plotname,
                    'n_variables': ds.n_variables,
                    'n_points': ds.n_points
                }
                for ds in self.datasets
            ],
            'current_dataset_idx': self.current_dataset_idx,
            'grid_visible': self.grid_visible,
            'legend_visible': self.legend_visible,
            'status_bar_visible': self.status_bar_visible,
            'toolbar_visible': self.toolbar_visible,
            'plot_title': self.plot_title,
            'viewbox_theme': self.viewbox_theme.value,
            'title_font': self.title_font.to_dict(),
            'label_font': self.label_font.to_dict(),
            'tick_font': self.tick_font.to_dict(),
            'ui_font': self.ui_font.to_dict(),
            'fft_config': self.fft_config.to_dict(),
            # Per-panel state (new format)
            'panels': {pid: ps.to_dict() for pid, ps in self.panels.items()},
            'panel_order': list(self.panel_order),
            'active_panel_id': self.active_panel_id,
        }
        # Backward compat: include flat keys for the active panel
        if self.active_panel_id and self.active_panel_id in self.panels:
            ps = self.panels[self.active_panel_id]
            result['traces'] = [t.to_dict() for t in ps.traces]
            result['axis_configs'] = {ax.value: cfg.to_dict() for ax, cfg in ps.axis_configs.items()}
            result['current_x_var'] = ps.current_x_var
        else:
            result['traces'] = []
            result['axis_configs'] = {}
            result['current_x_var'] = None
        return result

    def to_per_file_dict(self) -> Dict[str, Any]:
        """Convert to dict for per-file state (excludes data arrays)."""
        result = {
            'plot_title': self.plot_title,
            'grid_visible': self.grid_visible,
            'legend_visible': self.legend_visible,
            'panels': {pid: ps.to_per_file_dict() for pid, ps in self.panels.items()},
            'panel_order': list(self.panel_order),
            'active_panel_id': self.active_panel_id,
            'fft_config': self.fft_config.to_dict(),
        }
        # Backward compat: include flat keys for the active panel
        if self.active_panel_id and self.active_panel_id in self.panels:
            ps = self.panels[self.active_panel_id]
            result['traces'] = [t.to_per_file_dict() for t in ps.traces]
            result['current_x_var'] = ps.current_x_var
            result['axis_configs'] = {ax.value: cfg.to_dict() for ax, cfg in ps.axis_configs.items()}
        else:
            result['traces'] = []
            result['current_x_var'] = None
            result['axis_configs'] = {}
        return result

    def __repr__(self) -> str:
        total_traces = sum(len(ps.traces) for ps in self.panels.values())
        return f"ApplicationState(datasets={len(self.datasets)}, panels={len(self.panels)}, traces={total_traces}, current={self.current_dataset_idx})"