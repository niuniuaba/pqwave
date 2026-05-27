# KiCad Integration User Guide

pqwave integrates with KiCad Eeschema through a netlist-based pipeline and a bidirectional TCP cross-probe link. This guide covers the integration features and walks through real analysis workflows.

> **No KiCad source modifications required.** Everything works with pre-built KiCad binaries (version 8.0+).

## Table of Contents

### Part 1 — Feature Reference
- [Overview: How It Works](#overview-how-it-works)
- [Netlist Pipeline](#netlist-pipeline)
- [Netlist Post-Processor](#netlist-post-processor)
- [Cross-Probe (pqwave → KiCad)](#cross-probe-pqwave--kicad)
- [Session API Commands](#session-api-commands)

### Part 2 — Worked Tutorials
- [Example Overview](#example-overview)
- [Example 1: Full-Wave Bridge Rectifier](#example-1-full-wave-bridge-rectifier)
- [Example 2: Nonlinear C-V Characterization](#example-2-nonlinear-c-v-characterization)
- [Example 3: Back-Annotation Workflow](#example-3-back-annotation-workflow)
- [Standalone Scripting Example](#standalone-scripting-example)

---

## Part 1 — Feature Reference

### Overview: How It Works

```
KiCad (stock binary)                    pqwave
───────────────                        ──────
User edits .kicad_sch                  File watcher detects save
Saves (Ctrl+S) ───────────────────►    kicad-cli exports netlist
                                       Post-processor fixes:
                                         ✓ strip / from nodes
                                         ✓ fix diode pin order
                                         ✓ fix BJT/MOSFET pin order
                                         ✓ move .control block
                                       ngspice -b -r result.raw
                                       Loads, displays ALL signals

User clicks trace in pqwave ▼
localhost:4243  ◄──TCP───────────    $NET: "Vout"
KiCad highlights net ◄─────────────   Back-annotates
```

pqwave runs the simulation externally and uses KiCad's built-in cross-probe server (port 4243) for back-annotation.

> **Design note — why probing starts from pqwave, not KiCad:** Probing starts from pqwave, not KiCad — the user selects signals in pqwave's signal browser rather than clicking nets in the schematic. But clicking a trace in pqwave highlights the net in KiCad. pqwave shows every signal from the simulation at once, the user explores freely, and back-annotates to the schematic when they find something worth investigating. The schematic is the design canvas; pqwave is the analysis cockpit.

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

**Configuration** — set via **Settings > KiCad Bridge** or API:

| Setting | Default | Description |
|---------|---------|-------------|
| Watch paths | `[]` | List of directories or `.kicad_sch` files to monitor |
| Auto-simulate | `true` | Run simulation automatically when schematic is saved |
| Simulator | `ngspice` | SPICE simulator binary (must be in PATH) |
| Raw output dir | `$PROJECT_DIR` | Where `.raw` files are written |
| Cross-probe port | `4243` | KiCad Eeschema cross-probe TCP port |
| Netlist fix: strip slashes | `true` | Remove leading `/` from node names |
| Netlist fix: diode pins | `true` | Swap diode pin order to SPICE convention |
| Netlist fix: BJT/MOSFET pins | `true` | Reorder transistor pins to SPICE convention |

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

### Cross-Probe (pqwave → KiCad)

Clicking a trace point in pqwave sends a cross-probe command to KiCad over TCP.

| Trace Click Action | Command Sent | KiCad Behavior |
|-------------------|-------------|----------------|
| Click on any trace | `$NET: "netname"` | Highlights the net on all schematic sheets |
| Click on trace + Shift | `$PART: "refdes"` | Highlights the component symbol |
| Right-click > Probe Pin | `$PART: "ref" $PAD: "pin"` | Highlights a specific pin |

KiCad's cross-probe server runs on `localhost:4243` whenever Eeschema is open. No configuration needed — pqwave auto-detects it.

**Schematic → pqwave direction** is handled by the file watcher. When the user saves the schematic in KiCad, pqwave re-exports, re-simulates, and refreshes. All signals from the `.raw` file appear in pqwave's signal browser.

### Session API Commands

All KiCad Bridge operations are available through the Session API.

**Pipeline Control:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_watch` | `kicad_watch(paths)` | Add schematic files or directories to the watch list. Returns watch status. |
| `kicad_unwatch` | `kicad_unwatch(path)` | Remove a path from the watch list. |
| `kicad_watched` | `kicad_watched()` | List all watched paths and their status. |
| `kicad_simulate` | `kicad_simulate(sch_path)` | Manually trigger export → post-process → simulate for a schematic. |
| `kicad_export` | `kicad_export(sch_path, output=None)` | Export netlist only (no simulation). Returns the netlist text. |

**Post-Processor Control:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_fix_netlist` | `kicad_fix_netlist(netlist_text)` | Apply all post-processing fixes to a netlist string. Returns fixed netlist. |
| `kicad_fix_info` | `kicad_fix_info(netlist_text)` | Dry-run: report what fixes would be applied without changing anything. |

**Cross-Probe:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_probe_net` | `kicad_probe_net(net_name)` | Highlight a net in KiCad schematic. |
| `kicad_probe_part` | `kicad_probe_part(refdes, pin=None)` | Highlight a component or pin in KiCad schematic. |
| `kicad_clear` | `kicad_clear()` | Clear all highlights in KiCad. |

**Configuration:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_config` | `kicad_config(key, value=None)` | Get or set bridge configuration. Keys: `watch_paths`, `auto_simulate`, `simulator`, `raw_output_dir`, `crossprobe_port`, `fix_slashes`, `fix_diode_pins`, `fix_bjt_pins`. |

---

## Part 2 — Worked Tutorials

### Example Overview

Every tutorial starts from a `.kicad_sch` file in `docs/kicad/examples/`. Open it in KiCad Eeschema to follow along.

| Example | Schematic File | Circuit | Analysis | Demonstrates |
|---------|---------------|---------|----------|-------------|
| Bridge Rectifier | `bridge.kicad_sch` | Full-wave bridge + filter cap | Transient 40 ms, 100 Hz input | Diode pin fix, basic pipeline, cross-probe |
| C-V Characterization | `cdg.kicad_sch` | Nonlinear Cgd model, B-sources, .PARAM/.FUNC | DC sweep × AC via .control loop | Slash fix, .control placement, B-source expressions, multi-run sweep |
| Back-Annotation | `back_annotate.kicad_sch` | Two-stage BJT amplifier | Transient 10 ms | BJT pin fix, net/part/pin cross-probe, debug workflow |

**Prerequisites:**
- KiCad 8.0+ with `kicad-cli` in PATH
- ngspice 42+ in PATH
- pqwave installed

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

1. In pqwave: **File > KiCad Bridge > Watch Schematic**.
2. Select **`docs/kicad/examples/bridge.kicad_sch`**.
3. The bridge status bar shows: **Watching 1 schematic**.
4. In KiCad: open the schematic, verify it looks correct, press **Ctrl+S** to save.
5. pqwave auto-detects the save, runs the pipeline, and loads results.

**Or via API:**
```python
api.kicad_watch("docs/kicad/examples/bridge.kicad_sch")
api.kicad_simulate("docs/kicad/examples/bridge.kicad_sch")
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

#### Step 3: Cross-Probe Back to KiCad

1. Make sure KiCad Eeschema is running with `bridge.kicad_sch` open.
2. In pqwave, **right-click** the v(r1) trace and select **Cross-Probe Net**.
3. KiCad highlights the `R1` net — the wire from the bridge output to the filter cap.
4. **Shift+click** the same trace to highlight the component (e.g., D1) instead.

**Or via API:**
```python
api.kicad_probe_net("R1")       # highlight the output net
api.kicad_probe_part("D1")      # highlight diode D1
api.kicad_clear()               # clear all highlights
```

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

1. In pqwave: **File > KiCad Bridge > Watch Schematic**.
2. Select **`docs/kicad/examples/cdg.kicad_sch`**.
3. Click **Simulate Now**.

**Or via API:**
```python
api.kicad_watch("docs/kicad/examples/cdg.kicad_sch")
result = api.kicad_simulate("docs/kicad/examples/cdg.kicad_sch")

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

### Example 3: Back-Annotation Workflow

A complete bidirectional workflow: design a two-stage BJT amplifier in KiCad, simulate in pqwave, find a biasing issue, and back-annotate the problem to the schematic for debugging.

**Start here:** Open `docs/kicad/examples/back_annotate.kicad_sch` in KiCad Eeschema.

**Circuit:**
- V1: 1 kHz, 50 mV sinusoidal input
- Q1, Q2: 2N3904 NPN BJTs in common-emitter configuration
- Two-stage amplification with capacitive coupling
- 12 V DC supply

**Key fix:** BJT pin ordering — KiCad's 2N3904 symbol (TO-92 package) has pins E-B-C, but SPICE expects C-B-E.

#### Step 1: Run and Verify the Simulation

1. In pqwave: watch and simulate `back_annotate.kicad_sch`.
2. The console confirms BJT pin fixes:
```
[kicad] Fixing Q1 (2N3904): reordered pins to stage1 Net-_Q1-B_ Net-_Q1-E_ (was Net-_Q1-E_ Net-_Q1-B_ stage1)
[kicad] Fixing Q2 (2N3904): reordered pins to Net-_Q2-C_ Net-_Q2-B_ Net-_Q2-E_ (was Net-_Q2-E_ Net-_Q2-B_ Net-_Q2-C_)
[kicad] Simulation complete: 13 signals loaded
```
3. Plot: double-click **v(in)**, **v(stage1)**, **v(out)**.

**Or via API:**
```python
api.kicad_watch("docs/kicad/examples/back_annotate.kicad_sch")
api.kicad_simulate("docs/kicad/examples/back_annotate.kicad_sch")
api.select_panel(1)
api.add_trace("v(in)")
api.add_trace("v(stage1)")
api.add_trace("v(out)")
```

**Expected output:**
- v(in): 50 mV amplitude, 1 kHz sine
- v(stage1): inverted, ~111 mV amplitude (gain ~2.2x, 6.9 dB from Q1)
- v(out): ~12 V amplitude, clipped to supply rail (total gain ~240x, 47.6 dB)

> **What's happening:** Stage 1 provides modest voltage gain (~2.2x) with Rc=5k and Re=1k. Stage 2 amplifies further but the output hits the 12 V supply rail, causing clipping. v(out) is effectively a square wave. Use cross-probing to inspect the bias point at each stage.

#### Step 2: Debug with Cross-Probing

1. v(out) is clipping at the 12 V supply rail — the amplifier is saturating.
2. Place **cursor A** at the clipped peak of v(out).
3. **Right-click > Cross-Probe Net** — KiCad highlights the `out` net (Q2's collector).
4. **Shift+click** the cursor — KiCad highlights Q2 itself.
5. In KiCad, inspect Q2's biasing. Rc2=5k and Re2=1k provide high gain, but the signal from stage 1 already drives Q2 into saturation.
6. Now probe v(stage1): place **cursor B** and cross-probe to highlight the `stage1` net at Q1's collector.

#### Step 3: Verify the BJT Pin Fix

1. Temporarily disable the BJT pin fix to see what happens without it:
```python
api.kicad_config("fix_bjt_pins", False)
api.kicad_simulate("docs/kicad/examples/back_annotate.kicad_sch")
```
2. The output waveform collapses — wrong pin order swaps collector and emitter, destroying the amplifier's gain.
3. Re-enable:
```python
api.kicad_config("fix_bjt_pins", True)
```

> **Real-world impact:** Every BJT in every KiCad schematic has this issue unless the user manually set Alternate Node Sequence in the SPICE Model dialog. A two-transistor amplifier is simple — imagine a chip with 50 BJTs.

---

### Standalone Scripting Example

A complete Python script that integrates KiCad schematic editing with pqwave simulation and analysis:

```python
import pqwave.session as session

api = session.SessionAPI()

# Configure the KiCad bridge
api.kicad_config("watch_paths", ["/home/user/projects/amplifier/amplifier.kicad_sch"])
api.kicad_config("auto_simulate", True)
api.kicad_config("simulator", "ngspice")
api.kicad_config("fix_slashes", True)
api.kicad_config("fix_diode_pins", True)
api.kicad_config("fix_bjt_pins", True)

# Watch and run initial simulation
api.kicad_watch("/home/user/projects/amplifier/amplifier.kicad_sch")
result = api.kicad_simulate("/home/user/projects/amplifier/amplifier.kicad_sch")

print(f"Simulation loaded: {result['signal_count']} signals")

# Inspect what the post-processor fixed
fixes = api.kicad_fix_info(result["netlist"])
for fix in fixes:
    print(f"  {fix['type']}: {fix['detail']}")

# Plot key signals
api.select_panel(1)
api.add_trace("v(out)")
api.add_trace("v(in)")

# Measure gain
gain = api.eval_expr("max(v(out)) / max(v(in))", panel=1)
print(f"Voltage gain: {gain:.2f} ({20 * gain.log10():.1f} dB)")

# Cross-probe the output net back to KiCad
api.kicad_probe_net("out")

# The file watcher keeps running in background.
# Save the schematic in KiCad to trigger automatic re-simulation.
# Press Ctrl+C in the REPL to stop watching.
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

### Cross-probe doesn't highlight in KiCad

1. Verify KiCad Eeschema is running and a schematic is open.
2. Verify the port: `api.kicad_config("crossprobe_port")` — default `4243`.
3. Test manually from terminal: `echo '$NET: "GND"' | nc localhost 4243`.
4. KiCad versions before 8.0 may use a different cross-probe protocol.

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
