"""GhwAdapter — parse GHW files by converting to VCD via ghwdump."""

import os
import shutil
import subprocess
import tempfile
import logging

import numpy as np

from pqwave.models.state import ApplicationState
from pqwave.models.vcdfile import VcdFile

logger = logging.getLogger(__name__)


class GhwAdapter:
    """Adapter that converts .ghw files to VCD and parses them via VcdFile.

    Requires ghwdump from GHDL. Install GHDL to get ghwdump.
    """

    def __init__(self, filename: str):
        self.filename = filename
        self._vcd_file = None
        tool = self._resolve_tool()
        self._convert_and_parse(tool)

    def _resolve_tool(self) -> str:
        """Resolve ghwdump path: settings override first, then $PATH."""
        state = ApplicationState()
        custom = state.tool_paths.get("ghwdump", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("ghwdump")
        if found:
            return found
        raise FileNotFoundError(
            "ghwdump not found. Install GHDL and make sure ghwdump "
            "is in $PATH or set the location of your GHDL installation "
            "in Edit > Settings"
        )

    def _convert_and_parse(self, tool: str) -> None:
        """Convert .ghw to temp VCD and parse it.

        ghwdump writes VCD to stdout with the --vcd flag.
        """
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".vcd", prefix="pqwave_ghw_")
        os.close(tmp_fd)
        try:
            with open(tmp_path, 'w') as out:
                result = subprocess.run(
                    [tool, self.filename, "--vcd"],
                    stdout=out,
                    stderr=subprocess.PIPE,
                    text=True
                )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to convert {self.filename} to VCD: "
                    f"{result.stderr.strip()}"
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
