#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RawFile - SPICE raw file parsing using spicelib
"""

import os
import tempfile
import numpy as np
from pqwave.logging_config import get_logger

try:
    from spicelib import RawRead
    SPICELIB_AVAILABLE = True
except ImportError:
    SPICELIB_AVAILABLE = False
    RawRead = None


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Encoding fix for QSPICE .qraw files
# ---------------------------------------------------------------------------
# QSPICE encodes special characters (Greek letters, mathematical symbols) as
# raw bytes in the 0x80–0xFF range.  These bytes are valid in Windows-1252
# (CP1252) but spicelib auto-detects the file as UTF-8.  Bytes like 0xe3
# are not valid UTF-8 start bytes without proper continuations, so spicelib
# replaces them with U+FFFD (), showing as "?" in the UI.
#
# The fix: decode as CP1252, map known special characters to their proper
# Unicode code points, and write a temporary UTF-8 copy for spicelib.

_SPECIAL_CHAR_MAP = {
    # Greek letters (common in QSPICE device models)
    0xe1: '\u03b1',   # α alpha
    0xe2: '\u03b2',   # β beta
    0xe4: '\u03b4',   # δ delta
    0xe5: '\u03b5',   # ε epsilon
    0xe6: '\u03b6',   # ζ zeta
    0xe7: '\u03b7',   # η eta
    0xe8: '\u03b8',   # θ theta
    0xea: '\u03ba',   # κ kappa
    0xeb: '\u03bb',   # λ lambda
    0xec: '\u00b5',   # µ micro sign
    0xed: '\u03bd',   # ν nu
    0xee: '\u03be',   # ξ xi
    0xef: '\u03c0',   # π pi
    0xf1: '\u03c3',   # σ sigma
    0xf4: '\u03c6',   # φ phi
    0xf7: '\u03c9',   # ω omega
    # Mathematical / unit symbols
    0xa7: '\u00b0',   # ° degree sign
    0xf2: '\u03a9',   # Ω ohm
    0xfb: '\u221e',   # ∞ infinity
    0xf6: '\u03c8',   # ψ psi
    0xe0: '\u0391',   # Α Alpha (uppercase)
    0xe3: '\u03b1',   # α alpha (alternate mapping for QSPICE)
    0xf3: '\u03c4',   # τ tau
    0xe9: '\u03b9',   # ι iota
    0xf0: '\u03c1',   # ρ rho
    0xf5: '\u03c7',   # χ chi
    0xf8: '\u221a',   # √ square root
    0xf9: '\u2245',   # ≅ approximately equal to
    0xfa: '\u2265',   # ≥ greater than or equal to
    # CP1252-specific characters found in QSPICE files
    0x86: '\u2020',   # † dagger (used as separator in device names)
    0xab: '\u00ab',   # « left double angle quote (QSPICE suggestion quotes)
    0xbb: '\u00bb',   # » right double angle quote
}


def _fix_cp1252_byte(b: int) -> str:
    """Map a single byte (128-255) to its intended Unicode character."""
    if b in _SPECIAL_CHAR_MAP:
        return _SPECIAL_CHAR_MAP[b]
    # Fall back to standard Latin-1 for bytes we don't recognise
    return chr(b)


def _decode_header_bytes(header_bytes: bytes) -> str:
    """Decode raw file header bytes to a proper Python string.

    Tries UTF-8 strict first, falls back to Latin-1 with special char
    mapping for QSPICE files.
    """
    try:
        return header_bytes.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        pass

    # Decode as Latin-1 (all 256 byte values map 1:1) and fix special chars
    text = header_bytes.decode('latin-1')
    fixed_chars = []
    for ch in text:
        code = ord(ch)
        if code > 127 and code in _SPECIAL_CHAR_MAP:
            fixed_chars.append(_SPECIAL_CHAR_MAP[code])
        else:
            fixed_chars.append(ch)
    return ''.join(fixed_chars)


def _parse_header_variables(raw_bytes: bytes):
    """Parse variable names directly from raw file bytes.

    Returns:
        (variables, is_ac_or_complex) where variables is a list of dicts
        with 'index', 'name', 'type' keys.
    """
    # Find the Binary:/Values: marker to get the header
    for marker in (b'Binary:\n', b'Values:\n'):
        pos = raw_bytes.find(marker)
        if pos >= 0:
            header_bytes = raw_bytes[:pos]
            break
    else:
        header_bytes = raw_bytes

    text = _decode_header_bytes(header_bytes)
    lines = text.split('\n')

    # Find the Variables: line
    var_start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == 'variables:':
            var_start = i + 1
            break

    if var_start is None:
        return [], False

    # Get plot type for complex detection
    plotname = ''
    flags = ''
    for line in lines:
        low = line.lower()
        if low.startswith('plotname:'):
            plotname = line.split(':', 1)[1].strip().lower()
        elif low.startswith('flags:'):
            flags = line.split(':', 1)[1].strip().lower()

    is_ac_or_complex = 'ac' in plotname or 'complex' in flags

    variables = []
    for line in lines[var_start:]:
        if not line.strip():
            continue
        parts = line.lstrip().split('\t')
        if len(parts) < 3:
            continue
        idx = int(parts[0])
        name = parts[1]
        var_type_raw = parts[2]

        # Determine variable type
        name_lower = name.lower()
        if name_lower.startswith('v('):
            var_type = 'voltage'
        elif name_lower.startswith('i('):
            var_type = 'current'
        elif name == 'time':
            var_type = 'time'
        elif name_lower in ('freq', 'frequency', 'hz'):
            var_type = 'frequency'
        else:
            var_type = 'unknown'

        variables.append({'index': idx, 'name': name, 'type': var_type})

    return variables, is_ac_or_complex


def _is_utf16le(filepath: str) -> bool:
    """Detect UTF-16 LE encoding via BOM or zero-byte pattern.

    spicelib handles UTF-16 natively — no preprocessing needed.
    """
    with open(filepath, 'rb') as f:
        first_bytes = f.read(4)
    if len(first_bytes) >= 2:
        if first_bytes[:2] == b'\xff\xfe':
            return True
        if len(first_bytes) >= 4 and first_bytes[1] == 0 and first_bytes[3] == 0:
            return True
    return False


def preprocess_raw_file(filepath: str) -> str:
    """Preprocess a QSPICE raw file for spicelib data reading.

    Only needed when the file has non-ASCII bytes that aren't valid UTF-8.
    Produces a temp file with a Latin-1 → proper-Unicode header and
    unmodified binary data.  spicelib uses this for binary data reading;
    variable names are parsed separately by _parse_header_variables().

    Uses streaming I/O — does NOT read the entire file into memory.

    Returns:
        Path to a temporary file, or the original path if no preprocessing
        was needed.  Caller must clean up if a temp file was created.
    """
    if _is_utf16le(filepath):
        return filepath

    # Scan for binary marker using chunked reads (header is always near the
    # beginning, typically within first 64 KB).
    MAX_HEADER_SCAN = 64 * 1024 * 1024  # 64 MB safety limit
    marker = b'Binary:\n'
    marker_len = len(marker)
    header_end = None
    chunk_size = 64 * 1024
    overlap = marker_len - 1  # handle marker split across chunks
    total_scanned = 0

    with open(filepath, 'rb') as f:
        while total_scanned < MAX_HEADER_SCAN:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            total_scanned += len(chunk)
            offset_in_chunk = chunk.find(marker)
            if offset_in_chunk >= 0:
                header_end = f.tell() - len(chunk) + offset_in_chunk + marker_len
                break
            if header_end is None:
                offset_in_chunk = chunk.find(b'Values:\n')
                if offset_in_chunk >= 0:
                    header_end = f.tell() - len(chunk) + offset_in_chunk + len(b'Values:\n')
                    break
            # Seek back `overlap` bytes so we don't miss a split marker
            f.seek(-overlap, 1)

    if header_end is None:
        raise ValueError(
            f"No Binary:/Values: marker found within first {MAX_HEADER_SCAN // 1024**2} MB. "
            f"File may not be a valid SPICE raw file."
        )
    else:
        with open(filepath, 'rb') as f:
            header_bytes = f.read(header_end)
        binary_offset = header_end

    # Try strict UTF-8 — if it works, no preprocessing needed
    try:
        header_bytes.decode('utf-8', errors='strict')
        return filepath
    except UnicodeDecodeError:
        pass

    # Decode header with special char fix, re-encode as UTF-8
    fixed_header = _decode_header_bytes(header_bytes).encode('utf-8')

    # Write to a temporary file: fixed header + original binary data
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix='.qraw',
        prefix='pqwave_',
    )
    with os.fdopen(tmp_fd, 'wb') as out:
        out.write(fixed_header)
        # Stream binary portion from original file without loading into memory
        with open(filepath, 'rb') as src:
            src.seek(binary_offset)
            while True:
                chunk = src.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                out.write(chunk)

    logger.info(
        f"Preprocessed {filepath} -> {tmp_path} (special chars fixed)"
    )
    return tmp_path

def parse_step_header(header_bytes: bytes) -> dict:
    """Extract step count and parameter info from raw file header.

    Handles QSPICE-style headers where .step param and .param lines
    carry step metadata that spicelib can't extract without a .log file.

    Returns:
        dict with keys: step_count, step_param_names, step_param_values
    """
    result = {"step_count": 0, "step_param_names": [], "step_param_values": {}}
    header_text = header_bytes.decode("utf-8", errors="replace")

    import re
    step_match = re.search(
        r"\.step\s+param\s+(\w+)\s+([\d.e+\-]+)\s+([\d.e+\-]+)\s+([\d.e+\-]+)",
        header_text, re.IGNORECASE
    )
    if step_match:
        name = step_match.group(1)
        start = float(step_match.group(2))
        stop = float(step_match.group(3))
        inc = float(step_match.group(4))
        n_steps = int(round((stop - start) / inc)) + 1
        values = [start + i * inc for i in range(n_steps)]
        result["step_count"] = n_steps
        result["step_param_names"] = [name]
        result["step_param_values"][name] = [
            int(v) if v == int(v) else v for v in values
        ]
        return result

    return result


def detect_naming_pattern(trace_names: list) -> dict:
    """Detect MC run naming patterns like vout0..voutN.

    Handles ngspice type wrappers (v(), i(), n(), p()) by stripping them
    before pattern matching. E.g. v(vout0) → base=vout, idx=0.

    Returns:
        dict of {base_name: {"indices": [0,1,...], "count": N}}
        for each detected group. Single names with no numeric suffix
        are excluded. Groups with only one match are excluded.
    """
    import re
    groups = {}
    pattern = re.compile(r"^(.+?)(\d+)$")
    wrapper = re.compile(r"^[vi]\((.+)\)$")

    for name in trace_names:
        # Strip ngspice type wrapper: v(vout0) → vout0, i(r1) → r1
        wm = wrapper.match(name)
        if wm:
            name = wm.group(1)
        m = pattern.match(name)
        if not m:
            continue
        base = m.group(1)
        idx = int(m.group(2))
        if base not in groups:
            groups[base] = {"indices": [], "count": 0}
        groups[base]["indices"].append(idx)
        groups[base]["count"] = len(groups[base]["indices"])

    return {k: v for k, v in groups.items() if v["count"] > 1}


class RawFile:
    """Parse NGSPICE raw files using spicelib"""
    def __init__(self, filename):
        self.filename = filename
        self.datasets = []
        self.raw_data = None
        self.detected_format = None
        self._tmp_file = None  # Temp file path for preprocessed encoding
        self._mmap_path = None  # Temp file path for np.memmap backing store
        self._name_map = {}    # correct_name -> spicelib_name mapping
        self._data_cache = {}  # (dataset_idx, var_name) -> numpy view
        self._step_count = 0
        self._step_param_names: list = []
        self._step_param_values: dict = {}
        self.parse()
        self._extract_step_info()

    def __del__(self):
        """Clean up temporary files (preprocessed file and memmap backing store).

        Must be robust against Python interpreter shutdown, during which
        built-in modules and globals may already be None.
        """
        try:
            _os = os
            if _os is None:
                return
            for attr in ('_tmp_file', '_mmap_path'):
                path = getattr(self, attr, None)
                if path and _os.path.exists(path):
                    try:
                        _os.unlink(path)
                    except OSError:
                        pass
        except (AttributeError, TypeError):
            # Interpreter shutdown: modules are being torn down
            pass

    def _extract_spicelib_step_info(self):
        """Extract step metadata from spicelib plots before raw_data is released.

        Called from parse() while self.raw_data is still alive.
        """
        if self.raw_data is None:
            return
        try:
            for plot in self.raw_data._plots:
                if hasattr(plot, "steps") and len(plot.steps) > 0:
                    self._step_count = max(self._step_count, len(plot.steps))
                    for step in plot.steps:
                        for key, value in step.items():
                            if key not in self._step_param_names:
                                self._step_param_names.append(key)
                            if key not in self._step_param_values:
                                self._step_param_values[key] = []
                            if value not in self._step_param_values[key]:
                                self._step_param_values[key].append(value)
        except Exception:
            pass

    def _extract_step_info(self):
        """Extract step metadata from header and naming patterns.

        Complements _extract_spicelib_step_info() by parsing the raw
        header for QSPICE-style .step param lines and detecting
        ngspice-style naming patterns (vout0..voutN).
        """
        # Parse header for QSPICE-style step params
        try:
            raw_bytes = self._read_header_bytes()
            header_info = parse_step_header(raw_bytes)
            if header_info["step_count"] > self._step_count:
                self._step_count = header_info["step_count"]
                self._step_param_names = header_info["step_param_names"]
                self._step_param_values = header_info["step_param_values"]
        except Exception:
            pass

        # For ngspice, count is the max count from naming patterns
        if self._step_count == 0:
            try:
                trace_names = self.get_trace_names()
                groups = detect_naming_pattern(trace_names)
                max_count = 0
                for _base, info in groups.items():
                    if info["count"] > max_count:
                        max_count = info["count"]
                self._step_count = max_count
            except Exception:
                pass

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def step_param_names(self) -> list:
        return self._step_param_names

    @property
    def step_param_values(self) -> dict:
        return self._step_param_values

    def get_step_trace_data(self, var_name: str, step: int):
        """Get trace data for a specific variable at a specific step index."""
        if self.raw_data is None or step >= self._step_count:
            return np.array([])
        try:
            plot = self.raw_data._plots[0]
            spicelib_name = self._name_map.get(var_name, var_name)
            trace = plot.get_trace_read(spicelib_name)
            if trace is None:
                return np.array([])
            wave = trace.get_wave(step)
            if isinstance(wave, np.ndarray):
                return wave
            return np.array([wave]) if wave is not None else np.array([])
        except Exception:
            return np.array([])

    def get_trace_names(self) -> list:
        """Get all trace names from the raw file.

        Returns trace names from parsed datasets or falls back to
        header parsing if raw_data has been released.
        """
        if self.datasets:
            return [var["name"] for var in self.datasets[0].get("variables", [])]
        try:
            raw_bytes = self._read_header_bytes()
            vars_list, _ = _parse_header_variables(raw_bytes)
            return [v["name"] for v in vars_list]
        except Exception:
            return []

    def _read_header_bytes(self) -> bytes:
        """Read only the header portion of the raw file (up to Binary:\n).

        Returns the header bytes (including the marker).  Does NOT read
        the entire file into memory — scans using chunked I/O.

        For UTF-16 LE files (LTspice), returns the header decoded from
        UTF-16 and re-encoded as UTF-8 so downstream parsing works.
        """
        is_utf16le = _is_utf16le(self.filename)

        if is_utf16le:
            # Decode the whole header portion as UTF-16 LE.
            # spicelib handles the binary portion natively.
            marker = 'Binary:\n'.encode('utf-16-le')
            values_marker = 'Values:\n'.encode('utf-16-le')
        else:
            marker = b'Binary:\n'
            values_marker = b'Values:\n'

        marker_len = len(marker)
        chunk_size = 64 * 1024
        overlap = marker_len - 1

        with open(self.filename, 'rb') as f:
            buf = bytearray()
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                buf.extend(chunk)
                pos = buf.find(marker)
                if pos >= 0:
                    header = bytes(buf[:pos + marker_len])
                    if is_utf16le:
                        header = header.decode('utf-16-le').encode('utf-8')
                    return header
                pos = buf.find(values_marker)
                if pos >= 0:
                    header = bytes(buf[:pos + len(values_marker)])
                    if is_utf16le:
                        header = header.decode('utf-16-le').encode('utf-8')
                    return header
                # Keep only the last `overlap + marker_len` bytes to bound
                # memory while scanning a file with a very long header.
                keep = overlap + chunk_size
                if len(buf) > keep:
                    buf = buf[-keep:]

        # No marker found — return all bytes read
        return bytes(buf)

    def parse(self):
        """Parse the raw file using spicelib"""
        if not SPICELIB_AVAILABLE:
            raise ImportError("spicelib is not available. Install with: pip install spicelib")

        # Clear data cache from any previous parse
        self._data_cache = {}

        # Read only the header portion for variable name parsing
        # (spicelib's character-by-character header reading breaks multi-byte UTF-8)
        raw_bytes = self._read_header_bytes()

        # Parse variable names directly from bytes (correct UTF-8 decoding)
        correct_variables, is_ac_or_complex = _parse_header_variables(raw_bytes)

        # Preprocess file for encoding (fix QSPICE special characters)
        # This is needed for spicelib to read the binary data
        load_path = preprocess_raw_file(self.filename)
        if load_path != self.filename:
            self._tmp_file = load_path

        try:
            self.raw_data = RawRead(load_path)

            # Save detected dialect before raw_data is released
            self.detected_format = self.raw_data.dialect

            # Get raw properties from spicelib
            raw_props = self.raw_data.get_raw_properties()

            # Get trace names from spicelib (may have garbled chars for
            # multi-byte UTF-8) and build a position-based mapping.
            # Spicelib may have MORE traces than our header vars due to
            # aliases being exposed as separate traces.
            trace_names = self.raw_data.get_trace_names()

            # Build mapping: correct_name -> spicelib_name (by position,
            # up to the count of our header variables)
            correct_to_spicelib = {}
            n_correct = len(correct_variables)
            for i, correct_var in enumerate(correct_variables):
                if i < len(trace_names):
                    correct_to_spicelib[correct_var['name']] = trace_names[i]

            # Store mapping for later use in get_variable_data
            self._name_map = correct_to_spicelib

            # Create variables list using our correctly-decoded names
            variables = []
            for i, correct_var in enumerate(correct_variables):
                # Use our correct type classification
                var = {
                    'index': correct_var['index'],
                    'name': correct_var['name'],
                    'type': correct_var['type']
                }
                variables.append(var)

            # Build list of spicelib trace names for all variables
            all_spicelib_names = [
                correct_to_spicelib.get(cv['name'], cv['name'])
                for cv in correct_variables
            ]

            # Work around spicelib bug: empty _steps list crashes
            # set_steps() with IndexError. This happens with some
            # QSPICE files where step detection produces zero steps.
            # Setting _steps to None skips the set_steps call safely.
            plot = self.raw_data._plots[0]
            if (hasattr(plot, '_steps') and isinstance(plot._steps, list)
                    and len(plot._steps) == 0):
                plot._steps = None

            # Key optimization: pre-read ALL traces at once so spicelib
            # only reads the binary data section once.  Without this,
            # each get_trace() call re-reads the entire file in Normal
            # Access mode (row-interleaved), causing O(N×filesize) I/O
            # and intermediate buffer accumulation.
            #
            # For FastAccess (column-interleaved) this is also efficient
            # since it batches all reads into a single sequential scan.
            plot.read_trace_data(all_spicelib_names)

            # Now get_trace() returns from _read_traces cache (zero I/O)
            # Get data for all traces using our correct variable names.
            # For large files, use np.memmap to avoid keeping a full
            # in-memory copy of the column-stacked matrix.
            data_list = []
            valid_variables = []
            ref_dtype = None
            n_points = None

            for correct_var in correct_variables:
                name = correct_var['name']
                sp_name = correct_to_spicelib.get(name, name)
                try:
                    trace = self.raw_data.get_trace(sp_name)
                    if trace is not None:
                        try:
                            if hasattr(trace, 'get_wave'):
                                data = trace.get_wave()
                            else:
                                data = np.array(trace)

                            # Downcast to float32 to reduce memory usage
                            if data.dtype == np.float64:
                                data = data.astype(np.float32)
                            elif data.dtype == np.complex128:
                                data = data.astype(np.complex64)

                            if ref_dtype is None:
                                ref_dtype = data.dtype
                                n_points = len(data)

                            # Reclassify type with complex awareness
                            if is_ac_or_complex:
                                var_type = 'voltage' if name.lower().startswith('v(') else \
                                           'current' if name.lower().startswith('i(') else 'unknown'
                            else:
                                var_type = correct_var['type']

                            var = {
                                'index': len(valid_variables),
                                'name': name,
                                'type': var_type
                            }
                            valid_variables.append(var)
                            data_list.append(data)

                        except Exception as e:
                            logger.warning(f"Could not convert trace {name} to numpy array: {e}")
                except Exception as e:
                    logger.warning(f"Could not get trace {name}: {e}")
                    continue

            # Build the data matrix
            if data_list:
                estimated_total = n_points * len(valid_variables) * ref_dtype.itemsize
                if estimated_total > 500 * 1024 * 1024:
                    # Use memmap to avoid a second full copy in memory
                    mmap_fd, mmap_path = tempfile.mkstemp(prefix='pqwave_mmap_')
                    os.close(mmap_fd)
                    shape = (n_points, len(valid_variables))
                    try:
                        data = np.memmap(mmap_path, dtype=ref_dtype, mode='w+', shape=shape)
                        for i, arr in enumerate(data_list):
                            data[:, i] = arr
                            del arr
                        data_list.clear()
                        self._mmap_path = mmap_path
                    except Exception:
                        os.unlink(mmap_path)
                        raise
                    logger.info(
                        f"Using memmap for large dataset: {shape}, {estimated_total / 1024**2:.0f} MB"
                    )
                else:
                    data = np.column_stack(data_list)
                    del data_list  # Release list immediately after stack
            else:
                data = np.array([])

            dataset = {
                'title': raw_props.get('Title', ''),
                'date': raw_props.get('Date', ''),
                'plotname': raw_props.get('Plotname', ''),
                'flags': raw_props.get('Flags', ''),
                'variables': valid_variables,
                'data': data,
                '_is_ac_or_complex': is_ac_or_complex,
            }
            self.datasets.append(dataset)

            # Extract step metadata from spicelib while raw_data is still alive
            self._extract_spicelib_step_info()

            # Release spicelib raw_data to free ~50% of parsed memory.
            # All data is now in the memmap/column_stack matrix.
            self.raw_data = None
            logger.info(
                f"Released spicelib raw_data; data retained in memmap/column_stack"
            )

        except Exception as e:
            raise Exception(f"Error parsing file {self.filename}: {e}")

    def get_variable_names(self, dataset_idx=0):
        """Get variable names for a dataset"""
        if dataset_idx < len(self.datasets):
            var_names = [var['name'] for var in self.datasets[dataset_idx]['variables']]
            # Add derived variables for complex vectors
            derived_vars = []
            for var_name in var_names:
                # Check if this is a complex vector (based on plotname or flags)
                dataset = self.datasets[dataset_idx]
                plotname = dataset.get('plotname', '').lower()
                flags = dataset.get('flags', '').lower()
                if 'ac' in plotname or 'complex' in flags:
                    # Add derived variables
                    derived_vars.extend([
                        f'mag({var_name})',
                        f'real({var_name})',
                        f'imag({var_name})',
                        f'ph({var_name})'
                    ])
            return var_names + derived_vars
        return []

    def get_variable_data(self, var_name, dataset_idx=0):
        """Get data for a variable.

        Reads directly from the memmap/column_stack matrix to avoid
        creating duplicate copies. Returns a numpy view (no copy).
        """
        if dataset_idx >= len(self.datasets):
            return None
        dataset = self.datasets[dataset_idx]
        variables = dataset.get('variables', [])
        data_matrix = dataset.get('data')

        if data_matrix is None or data_matrix.size == 0:
            return None

        # Check if var_name is an exact variable name in this dataset first.
        # This prevents function-name interception (e.g. "real(ac_data)" being
        # treated as real() on "ac_data" when it's actually a literal variable name).
        for var in variables:
            if var['name'] == var_name:
                col = var['index']
                if col < data_matrix.shape[1]:
                    view = data_matrix[:, col]
                    self._data_cache[(dataset_idx, var_name)] = view
                    return view

        # Check if it's a derived variable for complex vector
        if var_name.startswith('mag(') and var_name.endswith(')'):
            base_var = var_name[4:-1]
            return self._get_complex_magnitude(base_var, dataset_idx)
        elif var_name.startswith('real(') and var_name.endswith(')'):
            base_var = var_name[5:-1]
            return self._get_complex_real(base_var, dataset_idx)
        elif var_name.startswith('imag(') and var_name.endswith(')'):
            base_var = var_name[5:-1]
            return self._get_complex_imag(base_var, dataset_idx)
        elif var_name.startswith('ph(') and var_name.endswith(')'):
            base_var = var_name[3:-1]
            return self._get_complex_phase(base_var, dataset_idx)
        elif var_name.startswith('re(') and var_name.endswith(')'):
            base_var = var_name[3:-1]
            return self._get_complex_real(base_var, dataset_idx)
        elif var_name.startswith('im(') and var_name.endswith(')'):
            base_var = var_name[3:-1]
            return self._get_complex_imag(base_var, dataset_idx)
        elif var_name.startswith('phase(') and var_name.endswith(')'):
            base_var = var_name[6:-1]
            return self._get_complex_phase(base_var, dataset_idx)
        elif var_name.startswith('cph(') and var_name.endswith(')'):
            base_var = var_name[4:-1]
            return self._get_complex_phase(base_var, dataset_idx)

        # Regular variable: find column index and return view
        cache_key = (dataset_idx, var_name)
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        for var in variables:
            if var['name'] == var_name:
                col = var['index']
                if col < data_matrix.shape[1]:
                    view = data_matrix[:, col]
                    self._data_cache[cache_key] = view
                    return view

        return None

    def _get_complex_magnitude(self, var_name, dataset_idx=0):
        """Get magnitude of complex vector"""
        data = self.get_variable_data(var_name, dataset_idx)
        if data is not None:
            if np.iscomplexobj(data):
                return np.abs(data)
            else:
                return np.abs(data)
        return None

    def _get_complex_real(self, var_name, dataset_idx=0):
        """Get real part of complex vector"""
        data = self.get_variable_data(var_name, dataset_idx)
        if data is not None:
            if np.iscomplexobj(data):
                return np.real(data)
            else:
                return data
        return None

    def _get_complex_imag(self, var_name, dataset_idx=0):
        """Get imaginary part of complex vector"""
        data = self.get_variable_data(var_name, dataset_idx)
        if data is not None:
            if np.iscomplexobj(data):
                return np.imag(data)
            else:
                return np.zeros_like(data)
        return None

    def _get_complex_phase(self, var_name, dataset_idx=0):
        """Get phase of complex vector (in radians)"""
        data = self.get_variable_data(var_name, dataset_idx)
        if data is not None:
            if np.iscomplexobj(data):
                return np.angle(data)
            else:
                return np.zeros_like(data)
        return None

    def get_num_points(self, dataset_idx=0):
        """Get number of points in a dataset"""
        if dataset_idx < len(self.datasets):
            data = self.datasets[dataset_idx].get('data')
            if data is not None and data.size > 0:
                return len(data)
        return 0


if __name__ == "__main__":
    # Simple test
    import sys
    if len(sys.argv) > 1:
        rf = RawFile(sys.argv[1])
        print(f"File: {rf.filename}")
        print(f"Datasets: {len(rf.datasets)}")
        if rf.datasets:
            print(f"Variables: {rf.get_variable_names()}")
    else:
        print("Usage: python rawfile.py <rawfile>")