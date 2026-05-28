## Context

pqwave has a `SchematicBridge` ABC framework (`pqwave/bridge/schem_bridge.py`) designed to integrate external schematic capture tools. KiCad was the first implementation. The framework defines the interface: export netlist, get fixes, probe nets/parts, detect tool, check if running, watch file extensions.

Lepton-EDA (lepton-eda 1.9.18) is a lightweight, mature schematic capture tool in the gEDA family. Unlike KiCad, it has no built-in simulation engine or waveform viewer. Its architecture is C core + Guile Scheme extension layer. Netlist export uses `lepton-netlist -g spice-sdb`, which produces clean SPICE — no post-processing fixes are needed.

Empirical testing confirmed all integration points work:

| Concern | Result |
|---|---|
| Netlist export | `lepton-netlist -g spice-sdb` → clean SPICE, zero fixes |
| ngspice simulation | Valid `.raw` file produced |
| Extension mechanism | `gafrc` loads in GUI process, `open-page-hook` fires after page load |
| Scheme TCP server | Guile sockets create listening TCP server inside lepton-schematic |
| Cross-probe API | `select-object!`, `schematic_canvas_zoom_object` work |
| Back-annotation API | `set-attrib-value!`, `page-append!`, `page-remove!` all verified |
| File format | `.sch` files with `netname=` attributes on net objects |

## Goals / Non-Goals

**Goals:**
- `LeptonBridge` class implementing `SchematicBridge` ABC
- Netlist export via `lepton-netlist -g spice-sdb`
- File watcher for `.sch` files with auto-simulation on save
- Bidirectional cross-probe: pqwave → lepton-schematic net/component highlighting via Scheme TCP server
- Back-annotation: simulation results written onto the schematic (DC bias stamps, floating voltage labels)
- Annotation layer management: add, clear, selective removal
- Session API commands (`lepton_watch`, `lepton_simulate`, `lepton_probe_net`, `lepton_probe_part`, `lepton_clear`, `lepton_config`)
- Companion Scheme script deployed to `~/.config/lepton-eda/scheme/autoload/`
- In-schematic menus (via Scheme plugin): Netlist > SPICE, Simulation > ngspice, Wave View > pqwave — mirrors the instinctive xschem workflow where simulation is driven from within the schematic editor
- Menu integration and control bar in pqwave following the KiCad bridge pattern
- Settings UI for `lepton-netlist` and `ngspice` paths

**Non-Goals:**
- Modifying lepton-eda source code (pure Scheme plugin, no C changes)
- Multi-sheet hierarchical schematic support
- Real-time simulation progress streaming

## Decisions

### D1: Scheme-based cross-probe server, not external process

**Rationale:** Lepton-eda has no built-in cross-probe mechanism. The alternatives were: (a) external process polling, (b) `lepton-cli shell` REPL, (c) Scheme plugin loaded via `gafrc` that starts a TCP server inside lepton-schematic. Option (c) is the cleanest: zero external dependencies, runs in-process with full access to the `(schematic selection)` and `(schematic window)` APIs, and can respond to both `$NET`, `$PART`, and `$ANNOTATE` commands. The Scheme server is ~100 lines of Guile and is deployed as an autoload file.

**Alternatives considered:** External `lepton-cli shell` REPL. Rejected because it's a separate process without GUI access — can't select or highlight objects. File-based IPC (write target net to a file, user manually searches). Rejected as poor UX.

Bidirectional communication uses the same TCP socket: pqwave sends `$NET`/`$PART`/`$CLEAR` commands; lepton-schematic pushes `$SELECTED:net`/`$SELECTED:part` events when the user clicks objects. The `select-objects-hook` (triggered by `o_attrib_add_selected` in C code on every user click) provides the reverse channel — no polling needed.

### D2: Companion Scheme script deployed to user autoload directory

**Rationale:** Lepton-eda loads `~/.config/lepton-eda/scheme/autoload/*.scm` at startup via `system-gafrc`. Dropping `pqwave-server.scm` there makes it auto-start with lepton-schematic. The pqwave bridge writes this file on first use (or user can deploy manually). This follows lepton-eda's documented extension pattern.

**Alternatives considered:** Project-level `gafrc`. Rejected because it would require modifying every project directory, and the server should be available globally.

### D3: No `NetlistFix` instances needed

**Rationale:** Empirical testing with the TwoStageAmp example confirmed `lepton-netlist -g spice-sdb` produces clean SPICE: no leading slashes on node names, BJTs in correct C-B-E order, no `.control` block issues, no diode pin swaps. The `get_netlist_fixes()` method returns an empty list. This could change with other circuits; the ABC allows adding fixes later without modifying the bridge class.

### D4: Same file watcher and simulation pipeline patterns as KiCad

**Rationale:** `QFileSystemWatcher`, `subprocess.run()` for ngspice, lazy instantiation of bridge components — all established patterns from the KiCad bridge. The only difference is the netlist export command (`lepton-netlist` vs `kicad-cli`). Reusing these patterns keeps the codebase consistent and reduces review surface.

### D5: Back-annotation uses three Scheme API levels

**Rationale:** Lepton-eda's Scheme API provides three complementary mechanisms: (a) `select-object!` for transient highlighting, (b) `set-attrib-value!` for persistent attribute stamps (survives save/reload), (c) `page-append!`/`page-remove!` for a managed annotation layer. Each serves a different use case. The pqwave bridge exposes all three via distinct commands (`probe_net`, `annotate_dc`, `clear_annotations`).

### D6: Cross-probe port default: 9424

**Rationale:** Avoids conflict with KiCad (4243) and xschem (2026/2021). Configurable via `lepton_config`.

### D8: In-schematic menus via `define-action-public` + `add-menu`

**Rationale:** Lepton-eda's Scheme API provides `define-action-public` (from `schematic/builtins.scm:170`) for defining new menu actions in pure Scheme, and `add-menu` (from `schematic/menu.scm:46`) for adding menus to the main menu bar before it is built. The `gafrc` autoload runs before `make-main-menu`, so menus added in gafrc are included in the final menu bar. This enables the same intuitive workflow as xschem: the user triggers netlist export, simulation, and waveform viewing directly from lepton-schematic's menus — pqwave's file watcher picks up changes automatically.

Three actions are defined:
- `&spice-netlist`: Runs `lepton-netlist -g spice-sdb -o <basename>.cir <current-page>` via Guile's `system*`, overwriting the previous netlist
- `&sim-ngspice`: Runs `ngspice -b -r <basename>.raw <basename>.cir` via `system*`, writing a `.raw` file
- `&wave-pqwave`: Launches `pqwave <basename>.raw` via `system*`, opening it in the waveform viewer

Three menus are added:
- **Netlist > SPICE** (appended to existing Netlist menu)
- **Simulation > ngspice** (new menu)
- **Wave View > pqwave** (new menu)

**Alternatives considered:** Having the user manually export netlists and run commands from a terminal. Rejected as poor UX — the xschem pattern of in-editor simulation commands is well-established and expected by users.

### D9: Tool detection follows `shutil.which()` with `tool_paths` override

**Rationale:** Same pattern as KiCad's `_resolve_kicad_cli()` and `_resolve_ngspice()`, and consistent with `fst_adapter.py` and `ghw_adapter.py`.

## Risks / Trade-offs

- **[Risk] lepton-netlist backend may produce different output for other circuits** → Mitigation: The `get_netlist_fixes()` method returns an empty list but can be populated later without API changes. Users can report netlist issues and fixes can be added incrementally.
- **[Risk] Scheme server port conflict with other applications** → Mitigation: Port 9424 is configurable. Port conflict prevention pattern from KiCad (distinct from xschem ports) applies.
- **[Risk] Scheme server crashes silently in lepton-schematic** → Mitigation: The server uses Guile's `catch` for all socket operations. Errors are logged to stderr. The pqwave `CrossProbeClient` handles connection failures gracefully (same pattern as KiCad).
- **[Risk] `gafrc`/autoload directory location varies by platform** → Mitigation: Lepton-eda uses `$XDG_CONFIG_HOME/lepton-eda/scheme/autoload/` (Linux) or equivalent. Documented in the bridge's deployment function.
- **[Trade-off] Back-annotation text persists in `.sch` file** → Users must explicitly clear annotations before saving if they want clean schematics. This is documented behavior. A `$CLEAR:ANNOTATIONS` command is provided.
- **[Trade-off] Cross-probe direction: pqwave → schematic uses `select-object!` (no hook feedback to avoid loops); schematic → pqwave uses `select-objects-hook` on user clicks** → Distinct mechanisms prevent infinite ping-pong while enabling both directions.

## Open Questions

- Should annotations auto-clear on file save, or persist until explicitly cleared? (Recommend: persist, with explicit clear command)
- Should the Scheme server support multiple simultaneous pqwave connections? (Recommend: single connection for now, reject additional)
