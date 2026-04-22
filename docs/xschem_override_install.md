# Installing xschem_override.tcl for Enhanced Xschem Integration

## Overview

The `xschem_override.tcl` file provides enhanced compatibility between xschem and pqwave/gaw waveform viewers. It dynamically detects which viewer is configured as default and adjusts the TCP port accordingly (2026 for pqwave, 2020 for gaw).

## Installation Steps

### 1. Copy the override file

```bash
# From the pqwave project directory
cp pqwave/communication/xschem_override.tcl ~/.xschem/
```

### 2. Configure xschemrc

Add the following line to your `~/.xschemrc` file:

```tcl
# Load pqwave override after xschem.tcl initialization
set user_startup_commands { source $env(HOME)/.xschem/xschem_override.tcl }
```

### 3. Configure waveform viewers in simrc

Ensure your xschem configuration includes both pqwave and gaw viewers. Here's an example configuration:

```tcl
# Configure pqwave (index 0)
set sim(spicewave,0,cmd) {/path/to/pqwave/venv/bin/pqwave "$n.raw"}
set sim(spicewave,0,name) {pqwave viewer}
set sim(spicewave,0,type) 0      ;# 0 = GAW-style TCP socket
set sim(spicewave,0,args) {2026} ;# TCP port for pqwave
set sim(spicewave,0,rawfile) 1   ;# Send raw file path

# Configure gaw (index 1)  
set sim(spicewave,1,cmd) {$env(HOME)/Apps/gaw/bin/gaw "$n.raw"}
set sim(spicewave,1,name) {Gaw viewer}
set sim(spicewave,1,type) 0      ;# 0 = GAW-style TCP socket
set sim(spicewave,1,args) {2020} ;# TCP port for gaw
set sim(spicewave,1,rawfile) 1   ;# Send raw file path

# Set number of viewers
set sim(spicewave,n) 2

# Set default viewer (0 = pqwave, 1 = gaw)
set sim(spicewave,default) 0
```

### 4. Restart xschem

Restart xschem for the changes to take effect.

## What the Override Does

1. **Dynamic port detection**: Checks `sim(spicewave,default)` to determine which viewer is configured as default
2. **Port selection**: Uses port 2026 for pqwave, 2020 for gaw
3. **Basename table_set**: Sends `table_set basename.raw` instead of full path for gaw compatibility
4. **Backward compatibility**: Maintains compatibility with existing xschem setup_tcp_gaw procedure

## Verification

To verify the override is working:

1. Start xschem with a schematic
2. Run a simulation
3. Press `Alt+G` and select your default viewer
4. Check the terminal output for messages like:
   ```
   PQWAVE OVERRIDE: connecting to localhost 2026 (idx=0)
   PQWAVE OVERRIDE: sending table_set bridge.raw
   ```

## Troubleshooting

### Override not loading
- Ensure `user_startup_commands` is set in `~/.xschemrc`, not in a separate file
- Check that the path to `xschem_override.tcl` is correct
- Verify xschem version supports `user_startup_commands`

### Wrong port being used
- Check `sim(spicewave,default)` value matches your intended viewer
- Verify `sim(spicewave,$idx,cmd)` contains "pqwave" for pqwave detection

### "table not defined" error in gaw
- The override should fix this by sending basename instead of full path
- If error persists, check gaw is configured to listen on port 2020

## Uninstallation

To remove the override:

1. Remove the `user_startup_commands` line from `~/.xschemrc`
2. Delete `~/.xschem/xschem_override.tcl`
3. Restart xschem

## See Also

- [Xschem Integration Documentation](xschem_integration.md) - Complete xschem integration guide
- [README.md](../README.md) - General pqwave documentation
- [Example simrc](example_simrc) - Complete configuration example