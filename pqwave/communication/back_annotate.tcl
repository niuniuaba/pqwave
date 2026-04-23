# pqwave back-annotation Tcl script for xschem
#
# This script provides procedures for handling data_point_update commands
# from pqwave, enabling live back-annotation of waveform data to xschem schematics.
#
# Installation:
# 1. Copy this file to your xschem configuration directory:
#    cp pqwave/communication/back_annotate.tcl ~/.xschem/
# 2. Add the following line to your ~/.xschemrc file:
#    source $env(HOME)/.xschem/back_annotate.tcl
#
# Dependencies: Tcl json package (install with: sudo apt install tcllib)

# Handle data_point_update command from pqwave
proc handle_data_point_update {json_data} {
  # Parse JSON response (requires Tcl 8.6+ or json package)
  if {[catch {set data [json::json2dict $json_data]} err]} {
    puts "Error parsing data_point_update: $err"
    return
  }

  set x_value [dict get $data data x]
  set traces [dict get $data data traces]

  puts "Cursor at X = ${x_value}s:"
  foreach trace $traces {
    set var_name [dict get $trace var_name]
    set y_value [dict get $trace y_value]

    # Display on schematic (example: update net label)
    # Replace with your schematic annotation logic
    set net_name [lindex [split $var_name "()"] 1]
    if {$net_name ne ""} {
      # Example: Update net label text
      # xschem set net_label $net_name "${y_value:.3f}V"
      puts "  $var_name = $y_value"
    }
  }
}

# Wrapper for gaw_echoline that handles data_point_update commands
# This procedure should be called from your existing gaw_echoline
proc pqwave_gaw_echoline_wrapper {} {
  global gaw_fd
  if {[eof $gaw_fd]} {
    close $gaw_fd
    unset gaw_fd
    return
  }
  set line [gets $gaw_fd]
  if {$line eq ""} return

  # Check if line is a JSON command
  if {[string match "json *" $line]} {
    set json_data [string range $line 5 end]
    set cmd_dict [json::json2dict $json_data]
    set command [dict get $cmd_dict command]

    if {$command eq "data_point_update"} {
      handle_data_point_update $json_data
      return 1  ;# Indicate command was handled
    }
  }

  return 0  ;# Command not handled, continue with normal processing
}

# Complete gaw_echoline implementation with pqwave support
# Only define this if gaw_echoline doesn't already exist
proc pqwave_gaw_echoline_complete {} {
  global gaw_fd
  if {[eof $gaw_fd]} {
    close $gaw_fd
    unset gaw_fd
    return
  }
  set line [gets $gaw_fd]
  if {$line eq ""} return

  # Let pqwave handle data_point_update commands first
  if {[info procs pqwave_gaw_echoline_wrapper] ne ""} {
    if {[pqwave_gaw_echoline_wrapper]} {
      return  ;# Command was handled by pqwave
    }
  }

  # Handle standard GAW-style commands
  if {[string match "table_set *" $line]} {
    set raw_file [string range $line 10 end]
    puts "table_set received: $raw_file"
    # Add your table_set handling logic here
  } elseif {[string match "copyvar *" $line]} {
    # Format: copyvar v(node) sel #color
    set parts [split $line]
    if {[llength $parts] >= 3} {
      set var_name [lindex $parts 1]
      set color [lindex $parts 3]
      puts "copyvar received: $var_name color $color"
      # Add your copyvar handling logic here
    }
  } else {
    puts "Unknown command: $line"
  }
}

# Setup procedure to integrate with xschem
proc pqwave_back_annotation_setup {} {
  # Check if json package is available
  if {[catch {package require json}]} {
    puts "Warning: Tcl json package not found. Install with: sudo apt install tcllib"
    puts "Back-annotation functionality will be limited."
    return
  }

  # If gaw_echoline doesn't exist, define it with pqwave support
  if {[info procs gaw_echoline] eq ""} {
    rename pqwave_gaw_echoline_complete gaw_echoline
    puts "pqwave: Defined gaw_echoline with back-annotation support"
  } else {
    # gaw_echoline already exists - wrap it to add pqwave support
    rename gaw_echoline gaw_echoline_original
    proc gaw_echoline {} {
      global gaw_fd
      if {[eof $gaw_fd]} {
        close $gaw_fd
        unset gaw_fd
        return
      }
      set line [gets $gaw_fd]
      if {$line eq ""} return

      # Let pqwave handle data_point_update commands first
      if {[info procs pqwave_gaw_echoline_wrapper] ne ""} {
        if {[pqwave_gaw_echoline_wrapper]} {
          return  ;# Command was handled by pqwave
        }
      }

      # Call original gaw_echoline for other commands
      gaw_echoline_original
    }
    puts "pqwave: Wrapped existing gaw_echoline with back-annotation support"
  }

  puts "pqwave back-annotation support loaded."
}

# Auto-initialize when sourced
pqwave_back_annotation_setup