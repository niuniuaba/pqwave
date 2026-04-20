# Xschem Integration for pqwave

## Overview

pqwave can integrate with [xschem](https://xschem.sourceforge.io/stefan/xschem_man/) schematic editor as an external waveform viewer, similar to gaw and BeSpice. This enables a seamless workflow where users can:

1. Click nets in xschem schematics and send them to pqwave for visualization
2. Potentially back-annotate measurement points from waveforms to the schematic

The integration works via TCP socket communication on port 2022 (configurable). xschem uses its built-in `sim(spicewave)` configuration array to support external viewers, requiring no modifications to xschem source code.

## Prerequisites

- pqwave installed and available in PATH (or accessible via absolute path)
- xschem 3.0.0 or later (with `sim(spicewave)` support)
- Both applications running on the same machine (localhost communication)

## Configuration

### 1. Add pqwave to xschemrc

Add the following configuration to your `~/.xschemrc` file (or system-wide `xschemrc`):

```tcl
# Add pqwave to the list of available waveform viewers
# Index 4 (or next available index) - adjust based on existing entries
set sim(spicewave,4,cmd) {pqwave "$n.raw"}
set sim(spicewave,4,name) {pqwave viewer}
set sim(spicewave,4,type) 0      ;# 0 = GAW-style TCP socket
set sim(spicewave,4,args) {2022} ;# TCP port number (default: 2022)
set sim(spicewave,4,rawfile) 1   ;# Send raw file path to viewer
set sim(spicewave,n) 5           ;# Increase viewer count (n = max index + 1)

# Optional: set pqwave as default viewer
set sim(spicewave,default) 4
```

**Important**: Adjust the index `4` based on existing entries in your `sim(spicewave)` array. Check your current xschemrc for existing viewer definitions. The `sim(spicewave,n)` value must be set to the maximum index + 1.

### 2. Verify Configuration

Restart xschem and press `Alt+G` in the schematic window. You should see "pqwave viewer" in the waveform viewer selection dialog.

## Using pqwave with xschem

### Basic Workflow

1. **Start pqwave in server mode** (automatically done when pqwave launches):
   ```bash
   pqwave --xschem-port 2022
   ```
   Or simply launch pqwave normally (server starts by default).

2. **Run a simulation** in xschem (e.g., `Simulation → Netlist & Run`).

3. **Select nets** in the xschem schematic window.

4. **Press `Alt+G`** and select "pqwave viewer" from the dialog.

5. **Observe** pqwave will:
   - Open a new window (or reuse existing window for the same raw file)
   - Load the simulation raw file
   - Plot the selected nets with distinct colors

### Single-Instance Behavior

pqwave implements single-instance server behavior:

- The first pqwave instance starts a TCP server on the specified port (default: 2022)
- Subsequent pqwave instances detect the server is already running and forward commands to it
- This ensures only one pqwave server runs, preventing port conflicts

### Command-Line Options for Xschem Integration

pqwave provides several command-line options for xschem integration:

| Option | Description |
|--------|-------------|
| `--xschem-port PORT` | TCP port for xschem server (default: 2022) |
| `--no-xschem-server` | Disable xschem integration server |
| `--xschem-send COMMAND` | Send command to existing xschem server and exit |

**Examples:**
```bash
# Start pqwave with custom port
pqwave --xschem-port 3030 simulation.raw

# Disable xschem server (useful for testing)
pqwave --no-xschem-server simulation.raw

# Send test command to existing pqwave server
pqwave --xschem-send "table_set /path/to/sim.raw"
```

## Communication Protocol

pqwave supports two command formats over TCP:

### 1. GAW-style Commands (for xschem compatibility)

- `table_set filename.raw` - Sets the raw file for subsequent commands
- `copyvar v(node) sel #color` - Adds a trace for variable `v(node)` with specified color
  - `v(node)` - SPICE variable name (e.g., `v(out)`, `i(v1)`)
  - `sel` - Always "sel" for highlighted nets (required for compatibility)
  - `#color` - Hexadecimal color code (e.g., `#ff0000` for red)

**Example sequence from xschem:**
```
table_set /home/user/simulation.raw
copyvar v(out) sel #ff0000
copyvar i(v1) sel #00ff00
```

### 2. JSON Commands (for advanced control)

Extended protocol using JSON for back-annotation, window management, and scripting:

```json
{"command": "open_file", "args": {"raw_file": "/path/to/sim.raw"}, "id": "req_123"}
```

**Supported JSON commands:**

| Command | Description | Response |
|---------|-------------|----------|
| `ping` | Check server availability | `{"status": "success", "data": {"pong": true, "version": "..."}, "id": "..."}` |
| `open_file` | Open raw file in new or existing window | `{"status": "success", "data": {"window_id": "...", "raw_file": "..."}, "id": "..."}` |
| `add_trace` | Add trace with specific axis and color | `{"status": "success", "data": {"variable": "...", "axis": "..."}, "id": "..."}` |
| `remove_trace` | Remove trace by variable name | `{"status": "success", "data": {"variable": "..."}, "id": "..."}` |
| `get_data_point` | Query data point at specific X value | `{"status": "success", "data": {"x": 0.001, "traces": [...]}, "id": "..."}` |
| `close_window` | Close specific window by ID | `{"status": "success", "data": {"window_id": "..."}, "id": "..."}` |
| `list_windows` | List all open windows | `{"status": "success", "data": {"windows": [...]}, "id": "..."}` |

**Response format:**
```json
{
  "status": "success|error",
  "data": {...},      // Command-specific data (optional)
  "error": "message", // Only present when status="error"
  "id": "request_id"  // Echoes the command ID for correlation
}
```

## Back-Annotation (Advanced)

pqwave supports querying waveform data points for back-annotation to xschem schematics. This requires custom Tcl procedures in xschemrc.

### Example Tcl Procedures for xschemrc

Add these procedures to your `~/.xschemrc` to enable back-annotation:

```tcl
# Query data point from pqwave at specified X value
proc pqwave_query_data_point {x_value} {
  set socket [socket localhost 2022]
  set request_id [clock milliseconds]
  set json_command "{\"command\": \"get_data_point\", \"args\": {\"x\": $x_value}, \"id\": \"$request_id\"}"
  puts $socket "json $json_command"
  flush $socket
  set response [gets $socket]
  close $socket
  return $response
}

# Display data point in xschem message area
proc pqwave_show_data_point {x_value} {
  set response [pqwave_query_data_point $x_value]
  # Parse JSON response (requires Tcl 8.6+ or json package)
  if {[catch {set data [json::json2dict $response]} err]} {
    puts "Error parsing response: $err"
    return
  }
  if {[dict get $data status] eq "success"} {
    set traces [dict get $data data traces]
    foreach trace $traces {
      set var [dict get $trace variable]
      set value [dict get $trace value]
      set magnitude [dict get $trace magnitude]
      set phase [dict get $trace phase]
      puts "  $var = $value (magnitude: $magnitude, phase: ${phase}°)"
    }
  } else {
    puts "Error: [dict get $data error]"
  }
}

# Add menu item to query waveform data (optional)
proc pqwave_add_query_menu {} {
  if {[info procs add_scheme_menu] eq ""} {
    return  ;# xschem menu API not available
  }
  add_scheme_menu "Waveform Data" {
    {"Query at X=1ms" {pqwave_show_data_point 0.001}}
    {"Query at X=10ms" {pqwave_show_data_point 0.01}}
    {"Custom X value..." {
      set x [tk_dialog .pqwave_dialog "Enter X value" \
             "Enter X value (seconds):" "" 0 "0.0"]
      if {$x ne ""} {
        pqwave_show_data_point $x
      }
    }}
  }
}

# Call during xschem initialization
after idle pqwave_add_query_menu
```

**Note:** The above example requires Tcl's `json` package. Install with:
```bash
# Debian/Ubuntu
sudo apt install tcllib

# Or via teacup (ActiveTcl)
teacup install json
```

## Testing the Integration

### Manual Testing with Netcat

Use `netcat` (`nc`) to test TCP communication:

```bash
# Test GAW-style commands
echo -e 'table_set /path/to/sim.raw\ncopyvar v(out) sel #ff0000' | nc localhost 2022

# Test JSON commands
echo 'json {"command":"ping","id":"test1"}' | nc localhost 2022
```

### Using the --xschem-send Command Line Option

pqwave provides a built-in command-line option for sending commands to an existing server:

```bash
# Send GAW-style command
pqwave --xschem-send "table_set /path/to/sim.raw"

# Send JSON command (note the 'json ' prefix)
pqwave --xschem-send 'json {"command":"ping","id":"test1"}'
```

This is useful for scripting and automation without requiring external tools like netcat.

### Testing with xschem

1. Configure xschemrc as described above
2. Launch xschem and open a test schematic
3. Run a simulation (ngspice, xyce, or other supported simulator)
4. Select a net in the schematic
5. Press `Alt+G` and select "pqwave viewer"
6. Verify pqwave opens and displays the trace

## Troubleshooting

### Common Issues

1. **"pqwave viewer" not appearing in xschem Alt+G dialog**
   - Verify the `sim(spicewave)` array configuration in xschemrc
   - Ensure `sim(spicewave,n)` is set correctly (max index + 1)
   - Restart xschem after editing xschemrc

2. **"Connection refused" errors**
   - Ensure pqwave is running with xschem server enabled (not `--no-xschem-server`)
   - Check port number matches (default: 2022)
   - Verify no firewall blocking localhost TCP connections

3. **Traces not appearing in pqwave**
   - Check pqwave logs with `--verbose` or `--debug` flag
   - Verify raw file path is accessible
   - Ensure variable names match SPICE conventions (`v(node)`, `i(source)`)

4. **Multiple pqwave windows opening for same raw file**
   - This is normal if different xschem instances connect
   - pqwave reuses windows based on raw file path and client mapping

### Debugging with Verbose Logging

Start pqwave with verbose logging to see xschem commands:

```bash
pqwave --verbose --xschem-port 2022
```

Or with full debug output:

```bash
pqwave --debug --xschem-port 2022
```

Check the terminal output for messages like:
```
INFO: table_set command from 127.0.0.1:12345: /path/to/sim.raw
INFO: copyvar command from 127.0.0.1:12345: v(out) color #ff0000
```

## Performance Considerations

- **Large raw files**: pqwave queues commands during file loading to prevent timeouts
- **Multiple xschem instances**: Single pqwave server handles all connections efficiently
- **Network latency**: Localhost communication (127.0.0.1) minimizes latency

## Limitations

- Currently supports only TCP socket communication (type 0 in xschem)
- Back-annotation requires custom Tcl procedures in xschemrc
- Complex number data returned in magnitude/phase format by default
- No authentication (localhost only, not a security concern)

## Future Enhancements

Potential future improvements:
- Support for UNIX domain sockets (faster than TCP)
- Built-in xschem Tcl library for easier back-annotation
- Bidirectional communication (pqwave → xschem events)
- Support for multiple simulation runs in same window

## See Also

- [xschem Manual](https://xschem.sourceforge.io/stefan/xschem_man/) - xschem documentation
- [pqwave README](../README.md) - General pqwave documentation
- [GAW Waveform Viewer](https://github.com/StefanSchippers/xschem-gaw) - Reference implementation for xschem integration