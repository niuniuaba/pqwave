## Why

QSPICE's simulation engine (by Mike Engelhardt, also the author of LTspice) is a best-in-class SPICE simulator that runs well under Wine on Linux. However, its GUI (schematic editor, waveform viewer) is DirectX-based and does not work correctly under Wine/Vulkan. Linux users who want to use QSPICE's simulation engine currently have no good waveform viewing option — they must either boot into Windows or export data manually.

pqwave already reads `.qraw` files via spicelib, so Linux users can already open QSPICE results. What's missing is the **simulation runner** — the ability to feed a `.cir` netlist to QSPICE's simulator and open the results, all from within pqwave. There is also an opportunity to improve `.qraw` reading fidelity by using QSPICE's own `QUX.exe` export tool when available.

PyQSPICE (Qorvo's official Python wrapper, unmaintained since May 2024) demonstrates the CLI invocation patterns but is Windows-only, uses Pandas instead of NumPy, and has a license incompatible with direct inclusion. We learn from its approach but build a clean, pqwave-native implementation.

## What Changes

### 1. QSPICE Simulator Runner (`bridge/qspice/wrapper.py`)

A headless runner that:
- Detects QSPICE installation via environment variable (`PQWAVE_QSPICE`), ApplicationState tool_paths, and filesystem search (Wine prefixes, common paths)
- Invokes `wine QSPICE64.exe netlist.cir` in the netlist's directory
- Waits for `.qraw` output to appear
- Returns the `.qraw` path for opening in pqwave

Invoked as: `pqwave --qspice-bridge <netlist_file>`

### 2. QUX-based `.qraw` Reader (supplement to spicelib)

When QSPICE is installed, pqwave can use `QUX.exe -Export` to extract data from `.qraw` files as properly-decoded CSV. This is the **official** data extraction path and avoids all encoding issues (no CP1252→Unicode mapping tables needed). spicelib remains the fallback for users without QSPICE installed.

### 3. Tool Path Configuration

A new entry in `ApplicationState.tool_paths`:
- Key: `qspice` — path to `QSPICE64.exe` (or `QSPICE.exe`)
- Settable via Settings > External Converter Paths
- Auto-detected on first launch

### 4. CLI Entry Point

- `pqwave --qspice-bridge <netlist>` — run QSPICE simulation from netlist, open results
- `pqwave --setup-qspice-integration` — guided setup wizard

## Non-Goals

- **No `.qsch` schematic support**: `.qsch` is a binary format tied to QSPICE's GUI (DirectX). Linux users work with `.cir` netlists.
- **No PyQSPICE dependency**: We do not import or bundle any PyQSPICE code. It's unmaintained and Windows-only.
- **No temp files**: `.qraw` output lands in the same directory as the netlist, consistent with QSPICE's normal behavior.
- **No netlist suffix assumptions**: Netlists are plain text files; any extension (or none) is accepted.
