# KiCad Integration User Guide

pqwave integrates with KiCad Eeschema through a connect-and-simulate workflow. This guide covers the integration features and walks through real analysis workflows.

> **No KiCad source modifications required.** Everything works with pre-built KiCad binaries (version 8.0+). KiCad 10+ with IPC API and kicad-python enables back-annotation (stamping simulation values onto the schematic).

## Table of Contents

### Part 1 — Feature Reference
- [Overview: How It Works](#overview-how-it-works)
- [Netlist Pipeline](#netlist-pipeline)
- [Netlist Post-Processor](#netlist-post-processor)
- [Cross-Probe / Back-Annotation](#cross-probe--back-annotation)
- [Session API Commands](#session-api-commands)

### Part 2 — Setup and Worked Tutorials
- [IPC API Setup (KiCad 10+)](#ipc-api-setup-kicad-10)
- [Example Overview](#example-overview)
- [Example 1: Full-Wave Bridge Rectifier](#example-1-full-wave-bridge-rectifier)
- [Example 2: Nonlinear C-V Characterization](#example-2-nonlinear-c-v-characterization)
- [Example 3: BJT Pin Fix Verification](#example-3-bjt-pin-fix-verification)
- [Standalone Scripting Example](#standalone-scripting-example)

---

## Part 1 — Feature Reference

### Overview: How It Works

```
KiCad (stock binary)                    pqwave
───────────────                        ──────
                                       File > KiCad Bridge > Connect
User edits .kicad_sch                  (selects .kicad_sch file)
                                       Simulate Now:
                                         kicad-cli exports netlist
                                         Post-processor fixes:
                                           ✓ strip / from nodes
                                           ✓ fix diode pin order
                                           ✓ fix BJT/MOSFET pin order
                                           ✓ move .control block
                                         ngspice -b -r result.raw
Saves (Ctrl+S) ──► manual re-sim ──►   Loads, displays ALL signals

KiCad 10+ with IPC API:
  DC Annotate  ◄────────────────────   Stamps DC op values as text
  Cursor XA/B  ◄────────────────────   Live value at cursor position
```

pqwave runs the simulation externally via ngspice and loads the results for analysis. Use **Simulate Now** to re-run after schematic changes.

> **Integration levels:** This guide describes the Level 1 integration — simulation pipeline + back-annotation. Cross-probe (highlighting nets/components in KiCad from pqwave) requires upstream KiCad API additions and is not yet available without C++ changes. See the [lessons-learned](lessons-learned.md) for details.

The netlist post-processor fixes four known KiCad export issues automatically:

1. **Node name slashes** — Strips `/` prefix from root-level net names
2. **Diode pin ordering** — Reverses anode/cathode to match SPICE convention
3. **BJT/MOSFET/JFET pin ordering** — Reorders pins to SPICE convention
4. **`.control` block placement** — Moves to correct position before `.end`

### Netlist Pipeline

The KiCad Bridge processes schematics through a three-stage pipeline:

| Stage | Action | Details |
|-------|--------|---------|
| Export | `kicad-cli sch export netlist --format spice` | Generates SPICE netlist from `.kicad_sch` file |
| Post-process | Fix node names, pin ordering, `.control` placement | See [Netlist Post-Processor](#netlist-post-processor) |
| Simulate | `ngspice -b -r output.raw circuit.cir` | Runs batch simulation, produces standard `.raw` file |

**Configuration** — set via **Settings > External Converter Paths** or API:

| Setting | Default | Description |
|---------|---------|-------------|
| `kicad_cli` | auto-detected | Path to kicad-cli binary |
| `ngspice` | auto-detected | Path to ngspice binary |
| Netlist fix: strip slashes | `true` | Remove leading `/` from node names |
| Netlist fix: diode pins | `true` | Swap diode pin order to SPICE convention |
| Netlist fix: BJT/MOSFET pins | `true` | Reorder transistor pins to SPICE convention |

**IPC back-annotation** requires KiCad 10+ with IPC API enabled and kicad-python installed. See [IPC API Setup](#ipc-api-setup-kicad-10).

### Netlist Post-Processor

The post-processor applies four categories of fixes to the exported netlist before simulation:

#### 1. Node Name Normalization

KiCad prefixes root-level net names with `/` (its internal sheet path separator). ngspice treats `/d1` and `d1` as different nodes, which silently breaks behavioral source expressions like `V={V(d1)}`.

| Before (KiCad export) | After (fixed) |
|----------------------|---------------|
| `D1 /d1 /ox D1N4148` | `D1 d1 ox D1N4148` |
| `V1 /AC_P /AC_N SIN(...)` | `V1 AC_P AC_N SIN(...)` |
| `B1 /out 0 V=V(/d1)` | `B1 out 0 V=V(d1)` |

The fix strips leading `/` from all node references — in component connections and inside `V()`/`I()` expressions.

> **Why this matters for real circuits:** Behavioral sources (B-sources) with expressions like `V={V(d1)}` silently read 0 V instead of the actual node voltage when the `/` is present, because `V(d1)` and node `/d1` are different names. Without this fix, models using B-sources produce garbage output.

#### 2. Semiconductor Pin Ordering

KiCad symbols follow IPC standard (pin numbering matches physical package). SPICE expects a fixed logical order per device type. **This affects every diode, BJT, MOSFET, and JFET in every schematic.**

| Device | KiCad Pin Order | SPICE Expects | Fix Applied |
|--------|----------------|---------------|-------------|
| **Diode (D)** | Pin 1=K, Pin 2=A (cathode first) | Anode, Cathode | Swap pins |
| **BJT (Q)** | Varies by package (TO-92, SOT-23, etc.) | Collector, Base, Emitter | Reorder to C-B-E |
| **MOSFET (M)** | Varies by package | Drain, Gate, Source | Reorder to D-G-S |
| **JFET (J)** | Varies by package | Drain, Gate, Source | Reorder to D-G-S |

The post-processor reads `Sim.Pins` from the `.kicad_sch` file to determine the actual symbol pin mapping, then reorders the netlist lines accordingly. A warning is logged to the console for each fixed device.

> **Why this happens:** KiCad's primary purpose is PCB layout, so its symbols follow IPC-7351 (pin 1 = cathode for diodes, pin numbering matches physical package footprints for transistors). SPICE was created in 1971 for circuit simulation and uses a different pin ordering convention. KiCad has an "Alternate Node Sequence" field to bridge this gap, but it's buried in a dialog, resets when changing models, and must be set manually per-symbol. pqwave's post-processor handles it automatically.

#### 3. `.control` Block Placement

KiCad writes schematic text directives in visual order (left-to-right on the sheet), which can place `.control`/`.endc` blocks before circuit elements. The post-processor moves any `.control`...`.endc` block to just before `.end`.

| Before (KiCad export) | After (fixed) |
|----------------------|---------------|
| `.control` / `run` / `write` / `.endc` | `.PARAM ...` |
| `.PARAM ...` | `R1 ... C1 ... V1 ...` |
| `R1 ... C1 ... V1 ...` | `.control` / `run` / `write` / `.endc` |
| `.end` | `.end` |

**Disable individual fixes** via settings if you have manually corrected your schematic or symbol libraries.

### Back-Annotation

**What it is:** Back-annotation stamps simulation results onto the KiCad schematic as text. Two modes are available:

1. **DC Annotate** (button) — stamps the mean voltage of every `v(node)` variable onto the schematic. Best used with DC operating-point or DC-sweep simulations.

2. **Cursor back-annotation** (automatic) — when you move cursor A or B on a trace in pqwave, the trace value at that cursor position is stamped onto the schematic as a single text item. Debounced at 250ms.

Both modes require KiCad 10+ with IPC API enabled and kicad-python installed.

**How it works:** pqwave communicates with KiCad Eeschema via the IPC API (KiCad 10+). Schematic text items are created via `CreateItems` and updated in-place via `UpdateItems`, preserving any user-applied repositioning.

**Requirements:**
- KiCad 10 or newer with IPC API enabled (Preferences → Plugins → Enable IPC API Server)
- `kicad-python` (`kipy`) installed in your pqwave Python environment
- See [IPC API Setup](#ipc-api-setup-kicad-10) for detailed setup instructions

**Fallback behavior:** If the IPC API is unavailable, pqwave falls back to `kicad-cli` for netlist export, but back-annotation is skipped with a status message. The simulation pipeline works without IPC.

### Session API Commands

All KiCad Bridge operations are available through the Session API.

**Pipeline Control:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_connect` | `kicad_connect(path)` | Connect to a .kicad_sch file. |
| `kicad_simulate` | `kicad_simulate(sch_path=None)` | Run export → post-process → ngspice → load. Uses connected path if none given. |
| `kicad_disconnect` | `kicad_disconnect()` | Disconnect from the schematic. |

**Back-Annotation (requires IPC API):**

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_annotate_dc` | `kicad_annotate_dc(voltages=None)` | Stamp DC operating-point values as schematic text. Auto-collects from active panel if no dict given. |
| `kicad_clear_annotations` | `kicad_clear_annotations()` | Remove all back-annotation text from schematic. |

**Configuration:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_config` | `kicad_config(key, value=None)` | Get or set bridge configuration. Keys: `kicad_cli`. |

---

## Part 2 — Setup and Worked Tutorials

### Example Overview

Every tutorial starts from a `.kicad_sch` file in `docs/kicad/examples/`. Open it in KiCad Eeschema to follow along.

| Example | Schematic File | Circuit | Analysis | Demonstrates |
|---------|---------------|---------|----------|-------------|
| Bridge Rectifier | `bridge.kicad_sch` | Full-wave bridge + filter cap | Transient 40 ms, 100 Hz input | Diode pin fix, basic pipeline |
| C-V Characterization | `cdg.kicad_sch` | Nonlinear Cgd model, B-sources, .PARAM/.FUNC | DC sweep × AC via .control loop | Slash fix, .control placement, B-source expressions, multi-run sweep |
| BJT Amplifier | `bjt_amplifier.kicad_sch` | Two-stage BJT amplifier | Transient 10 ms | BJT pin fix, multi-signal analysis |

**Prerequisites:**
- KiCad 8.0+ with `kicad-cli` in PATH
- ngspice 42+ in PATH
- KiCad 10+ with IPC API and kicad-python for back-annotation
- pqwave installed

---

## IPC API Setup (KiCad 10+)

pqwave supports the KiCad IPC API for back-annotation (stamping simulation
values onto the schematic as text).  This requires KiCad 10 or newer with the
IPC API server enabled.

### Prerequisites

1. **KiCad 10 or newer** installed and running
2. **IPC API enabled** in KiCad:
   - Open KiCad → Preferences → Plugins
   - Check "Enable IPC API Server"
   - Restart KiCad
3. **kicad-python** installed in your pqwave Python environment:

   **Option A — install from Git (recommended):**
   ```bash
   pip install git+https://gitlab.com/kicad/code/kicad-python.git
   ```

   **Option B — build from local source:**
   ```bash
   cd /path/to/kicad-python
   git submodule update --init
   pip install -e .
   ```

   The kicad-python version must match your KiCad version.  Building from
   source with the matching kicad submodule ensures API compatibility.

### Verifying the Setup

```bash
python -c "import kipy; print('kicad-python OK')"
```

If you see `ModuleNotFoundError`, the package is not installed.
If you see `kicad-python OK`, you're ready.

### Connection Status

The KiCad control bar shows the connection state:
- **Green**: Connected to schematic, IPC available (back-annotation ready)
- **Green**: Connected to schematic, IPC unavailable (simulation only)
- **Gray**: Not connected

### Troubleshooting

| Problem | Solution |
|---------|----------|
| "kicad-python is required" | Install kicad-python (see above). |
| "Annotation skipped — IPC API not available" | Check KiCad is running with IPC API enabled. Preferences → Plugins → Enable IPC API Server. Restart KiCad. |
| "cannot import name 'SchematicText'" | Your kicad-python is too old (0.7.1 from PyPI). Upgrade from Git or build from source. |
| "IPC API connection failed" | Check `/tmp/kicad/api.sock` exists. Verify KiCad is running. |
| "Connection refused" | KiCad may not have the API server enabled. See above. |

### Workflow (IPC API, Recommended)

1. Open your schematic in **KiCad 10+** (IPC API enabled)
2. In pqwave: **File → KiCad Bridge → Watch Schematic...**
3. Select your `.kicad_sch` file
4. pqwave connects to KiCad via IPC API, exports the SPICE netlist,
   post-processes it, and runs ngspice
5. The `.raw` results load automatically
6. **Cross-probe**: click a trace → right-click "Probe in KiCad" →
   the net highlights in Eeschema

### Workflow (kicad-cli Fallback)

1. Same as above, but without cross-probe capability
2. The control bar shows orange "kicad-cli fallback"
3. Netlist export and simulation still work

---

### Example 1: Full-Wave Bridge Rectifier

A simple circuit with a common but silently-breaking KiCad export bug. The pipeline catches and fixes diode pin ordering, turning a wrong negative output into the correct rectified waveform.

**Start here:** Open `docs/kicad/examples/bridge.kicad_sch` in KiCad Eeschema.

**Circuit:**
- V1: 100 V, 100 Hz sinusoidal AC source
- D1–D4: 1N4148 diodes in full-wave bridge configuration
- C1: 47 µF filter capacitor
- R1+R2: 2 kΩ resistive load (voltage divider)

**Key fix:** All four diodes — KiCad exports them cathode-first (K, A) but SPICE reads anode-first (A, K).

#### Step 1: Set Up and Simulate

1. In pqwave: **File > KiCad Bridge > Connect**.
2. Select **`docs/kicad/examples/bridge/bridge.kicad_sch`**.
3. The bridge status bar shows: **KiCad: bridge.kicad_sch** (green).
4. Click **Simulate Now**.
5. The pipeline runs and loads results.

**Or via API:**
```python
api.kicad_connect("docs/kicad/examples/bridge/bridge.kicad_sch")
api.kicad_simulate()
```

**Expected output:** The console shows four diode pin fixes:
```
[kicad] Fixing D1: swapped pins (K-A → A-K)
[kicad] Fixing D2: swapped pins (K-A → A-K)
[kicad] Fixing D3: swapped pins (K-A → A-K)
[kicad] Fixing D4: swapped pins (K-A → A-K)
[kicad] Simulation complete: 6 signals loaded
```

The signal browser lists: `v(ac_p)`, `v(ac_n)`, `v(r1)`, `v(r2)`, `i(v1)`, `time`.

#### Step 2: View the Rectified Output

1. Double-click **v(r1)** in the signal browser.
2. Double-click **v(ac_p)** to overlay.
3. v(r1) shows a positive DC level (~98 V) with small ripple, overlaid on the sinusoidal v(ac_p).

**Expected output:**
- v(r1) mean: ~+98 V DC (100 V peak − 2 × Vf diode drop)
- v(r1) ripple: ~2 V pk-pk at 100 Hz

> **Without the post-processor:** v(r1) would read ~−98 V — all four diodes are reversed in KiCad's export, so the bridge produces a negative output. The waveform _looks_ correct (same ripple, same magnitude) but has the wrong sign. Users debugging this in KiCad's built-in simulator would see inverted results and not know why.

---

### Example 2: Nonlinear C-V Characterization

A realistic semiconductor characterization case: sweep the DC bias across a nonlinear Cgd capacitance model, run an AC analysis at each bias point, and extract the C-V curve. Demonstrates the netlist post-processor handling a complex case with all four fix categories active simultaneously.

**Start here:** Open `docs/kicad/examples/cdg.kicad_sch` in KiCad Eeschema.

**Circuit:**
- Vd1g1: DC bias source, swept 0–500 V in 1 V steps via `.control` loop
- B_Edg1, B_Edg2: Behavioral voltage sources implementing a nonlinear capacitance model
- Cdg1, Cdg2: Capacitors representing Cgd components
- 14 `.PARAM` definitions + a `.FUNC` defining the Q-V relationship
- `.control` block: `while` loop performing `alter` → `ac` → measure → `destroy` at 501 bias points

**Key fixes active:**
1. **Node slashes** — all 8+ node references (`/d1`, `/ox`, `/ox2`) stripped
2. **`.control` placement** — moved from before `.PARAM` block to before `.end`
3. **B-source expressions** — `V={V(d1)}` references fixed to match de-slashed node names

#### Step 1: Open and Inspect the Netlist Fixes

1. In pqwave: **File > KiCad Bridge > Connect**.
2. Select **`docs/kicad/examples/cdg.kicad_sch`** (if this example exists).
3. Click **Simulate Now**.

**Or via API:**
```python
api.kicad_connect("docs/kicad/examples/cdg.kicad_sch")
result = api.kicad_simulate()

# See everything the post-processor fixed
for fix in api.kicad_fix_info(result["netlist"]):
    print(f"  {fix['type']}: {fix['detail']}")
```

**Expected output:**
```
[kicad] Stripped '/' from 3 node names: /d1→d1, /ox→ox, /ox2→ox2
[kicad] Moved .control block from line 2 to line 38 (before .end)
[kicad] B-source B_Edg1: fixed 2 V() references to match de-slashed nodes
[kicad] B-source B_Edg2: fixed 1 V() reference to match de-slashed nodes
[kicad] Simulation complete: 2 signals loaded, 501 sweep points
```

#### Step 2: Browse the C-V Sweep

1. The `.control` loop sweeps Vd1g1 from 0 to 500 V and records `ac_data[index]` — the small-signal admittance at each bias.
2. Double-click **ac_data** to plot. The signal browser shows 501 data points.
3. The curve shows the nonlinear Cgd(V) characteristic: flat at low bias, transitioning through a knee, then linear at high bias.

> **Under the hood:** The `.control` block runs `ac lin 1 250k 250k` at each DC bias point, measures `Vd1g1#branch` (the AC current through the voltage source), and stores the complex admittance. This is a standard technique for C-V extraction from SPICE simulations — the `.control` scripting language makes it possible to automate what would otherwise require 501 separate simulation runs.

#### Step 3: Extract the C-V Parameters

1. Place **cursor A** at the low-bias plateau (~0–50 V region).
2. Place **cursor B** at a high-bias point (~200 V).
3. Use **Analyze > Expression** to compute the capacitance ratio:

```
mag(ac_data[cursorB]) / mag(ac_data[cursorA])
```

**Expected output:**
- Low-bias capacitance (Cdg1 + Cdg2): ~82 pF (constant)
- C-V curve shows the transition where Cdg1 becomes nonlinear at ~50 V
- High-bias capacitance approaches Cdg2 alone (~82 pF at a=15.9)

> **Without the post-processor:** The B-sources `V={V(d1)}` would reference node `d1` while the actual netlist node is `/d1`. ngspice silently reads 0 V for the nonexistent `d1` node. Every B-source expression evaluates to zero. The ac_data vector would contain nothing but zeros across all 501 bias points — a completely flat line indistinguishable from a wiring error.

---

### Example 3: BJT Pin Fix Verification

Verify that the BJT pin reordering fix is working — and see what happens without it.

**Start here:** Open `docs/kicad/examples/bjt_amplifier.kicad_sch` in KiCad Eeschema.

**Circuit:**
- V1: 1 kHz, 50 mV sinusoidal input
- Q1, Q2: 2N3904 NPN BJTs in common-emitter configuration
- Two-stage amplification with capacitive coupling
- 12 V DC supply

**Key fix:** BJT pin ordering — KiCad's 2N3904 symbol (TO-92 package) has pins E-B-C, but SPICE expects C-B-E.

#### Step 1: Run and Verify the Simulation

1. In pqwave: connect and simulate `bjt_amplifier.kicad_sch`.
2. The chat panel confirms BJT pin fixes:
```
[kicad] Fixing Q1 (2N3904): reordered pins to stage1 Net-_Q1-B_ Net-_Q1-E_ (was Net-_Q1-E_ Net-_Q1-B_ stage1)
[kicad] Fixing Q2 (2N3904): reordered pins to Net-_Q2-C_ Net-_Q2-B_ Net-_Q2-E_ (was Net-_Q2-E_ Net-_Q2-B_ Net-_Q2-C_)
[kicad] Simulation complete: 13 signals loaded
```
3. Plot: double-click **v(in)**, **v(stage1)**, **v(out)**.

**Or via API:**
```python
api.kicad_connect("docs/kicad/examples/bjt_amplifier.kicad_sch")
api.kicad_simulate()
api.select_panel(1)
api.add_trace("v(in)")
api.add_trace("v(stage1)")
api.add_trace("v(out)")
```

**Expected output:**
- v(in): 50 mV amplitude, 1 kHz sine
- v(stage1): inverted, ~111 mV amplitude (gain ~2.2x, 6.9 dB from Q1)
- v(out): ~12 V amplitude, clipped to supply rail (total gain ~240x, 47.6 dB)

> **What's happening:** Stage 1 provides modest voltage gain (~2.2x) with Rc=5k and Re=1k. Stage 2 amplifies further but the output hits the 12 V supply rail, causing clipping. v(out) is effectively a square wave.

#### Step 2: Debug with Cursors

1. v(out) is clipping at the 12 V supply rail — the amplifier is saturating.
2. Place **cursor A** at the clipped peak of v(out).
3. Place **cursor B** on v(stage1) to check the intermediate stage.
4. Use the **Measure** functions to quantify the gain at each stage.

#### Step 3: Verify the BJT Pin Fix

1. Temporarily disable the BJT pin fix to see what happens without it:
```python
api.kicad_config("fix_bjt_pins", False)
api.kicad_simulate()
```
2. The output waveform collapses — wrong pin order swaps collector and emitter, destroying the amplifier's gain.
3. Re-enable:
```python
api.kicad_config("fix_bjt_pins", True)
```

> **Real-world impact:** Every BJT in every KiCad schematic has this issue unless the user manually set Alternate Node Sequence in the SPICE Model dialog. A two-transistor amplifier is simple — imagine a chip with 50 BJTs.

---

### Standalone Scripting Example

A complete Python script that integrates KiCad schematic simulation with pqwave analysis:

```python
import pqwave.session as session

api = session.SessionAPI()

# Connect to a schematic and run simulation
api.kicad_connect("/home/user/projects/amplifier/amplifier.kicad_sch")
result = api.kicad_simulate()

print(f"Simulation complete, raw file: {result['raw_file']}")
print(f"Fixes applied: {len(result.get('fix_info', []))}")
for info in result.get("fix_info", []):
    print(f"  {info}")

# Plot key signals
api.select_panel(1)
api.add_trace("v(out)")
api.add_trace("v(in)")

# Measure gain
gain = api.eval_expr("max(v(out)) / max(v(in))", panel=1)
print(f"Voltage gain: {gain:.2f} ({20 * gain.log10():.1f} dB)")

# Back-annotate DC operating point values (requires IPC API)
api.kicad_annotate_dc()

# Edit schematic in KiCad, re-run simulation when ready
api.kicad_simulate()
```

**Expected output:**
```
Simulation loaded: 12 signals
  fix_diode: D1 — swapped pins (K-A → A-K)
  fix_bjt: Q1 (2N3904) — reordered E-B-C → C-B-E
  fix_bjt: Q2 (2N3904) — reordered E-B-C → C-B-E
  fix_slashes: stripped '/' from 5 node names
Voltage gain: 239.80 (47.6 dB)
```

---

## Troubleshooting

### Simulation produces inverted or zero output

The post-processor may have misidentified a device. Run `kicad_fix_info(netlist)` to see all applied fixes. Temporarily disable individual fixes to isolate:

```python
api.kicad_config("fix_diode_pins", False)
api.kicad_config("fix_bjt_pins", False)
```

### Annotation skipped — IPC API not available

1. Verify KiCad 10+ is running with IPC API enabled: Preferences → Plugins → Enable IPC API Server. Restart KiCad.
2. Verify `kicad-python` is installed: `python -c "import kipy; print('kicad-python OK')"`.
3. If you see `cannot import name 'SchematicText'`, your kicad-python is too old (0.7.1). Upgrade from Git or build from source.
4. Check the KiCad control bar — it shows "IPC ✓" when the API is available.

### "kicad-cli not found"

KiCad's CLI tools ship with the main package. On Linux:

```bash
# Typically at:
export PATH="/usr/lib/kicad/bin:$PATH"
# Or via package manager:
which kicad-cli
```

On Windows, add `C:\Program Files\KiCad\bin` to PATH.

### Behavioral sources (B-sources) produce flat lines or zero

This is almost always the node slash issue. Check that `fix_slashes` is enabled:

```python
api.kicad_config("fix_slashes", True)
```

The fix strips `/` prefixes from all node names. Without it, `V={V(d1)}` references a nonexistent node while the actual node is `/d1`.

### Schematic labels have slashes in them

Use **global labels** instead of local labels in KiCad. Global labels have no sheet path prefix and export cleanly. If you must use local labels, the slash-stripping fix handles the exported netlist.
