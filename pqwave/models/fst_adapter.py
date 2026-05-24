"""FstAdapter — parse FST files by converting to VCD via fst2vcd."""

import os
import shutil
import subprocess
import tempfile
import logging

import numpy as np

from pqwave.models.state import ApplicationState
from pqwave.models.vcdfile import VcdFile

logger = logging.getLogger(__name__)


class FstAdapter:
    """Adapter that converts .fst files to VCD and parses them via VcdFile.

    Requires fst2vcd from gtkwave. Install via:
        sudo apt install gtkwave
    """

    def __init__(self, filename: str):
        self.filename = filename
        self._vcd_file = None
        tool = self._resolve_tool()
        self._convert_and_parse(tool)

    def _resolve_tool(self) -> str:
        """Resolve fst2vcd path: settings override first, then $PATH."""
        state = ApplicationState()
        custom = state.tool_paths.get("fst2vcd", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("fst2vcd")
        if found:
            return found
        raise FileNotFoundError(
            "fst2vcd not found. Install gtkwave and make sure fst2vcd "
            "is in $PATH or set the location of your gtkwave installation "
            "in Edit > Settings"
        )

    def _convert_and_parse(self, tool: str) -> None:
        """Convert .fst to temp VCD and parse it."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".vcd", prefix="pqwave_fst_")
        os.close(tmp_fd)
        try:
            result = subprocess.run(
                [tool, self.filename, "-o", tmp_path],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                logger.error(
                    "fst2vcd failed for %s: %s",
                    self.filename, result.stderr.strip()
                )
                raise RuntimeError(
                    f"Failed to convert {self.filename} to VCD: {result.stderr.strip()}"
                )
            self._vcd_file = VcdFile(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @property
    def datasets(self) -> list:
        if self._vcd_file is None:
            return []
        return self._vcd_file.datasets

    def get_variable_names(self, dataset_idx: int = 0) -> list:
        if self._vcd_file is None:
            return []
        return self._vcd_file.get_variable_names(dataset_idx)

    def get_variable_data(self, name: str, dataset_idx: int = 0) -> np.ndarray:
        if self._vcd_file is None:
            return None
        return self._vcd_file.get_variable_data(name, dataset_idx)

    def get_num_points(self, dataset_idx: int = 0) -> int:
        if self._vcd_file is None:
            return 0
        return self._vcd_file.get_num_points(dataset_idx)
