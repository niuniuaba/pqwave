# Override setup_tcp_gaw to:
# 1. Dynamically determine port from the default viewer's command path
# 2. Send basename (not full path) for table_set
#    (gaw looks up table by name, pqwave uses relative path)

proc setup_tcp_gaw {} {
  global gaw_fd gaw_tcp_address netlist_dir has_x sim

  regsub {/$} $netlist_dir {} netlist_dir
  if { [info exists gaw_fd] } { return 1; }

  # Determine port from the default viewer's configuration
  if {[info exists sim(spicewave,default)]} {
    set idx $sim(spicewave,default)
  } else {
    set idx 0
  }

  # First try to get port from args field (most reliable)
  if {[info exists sim(spicewave,$idx,args)]} {
    set port $sim(spicewave,$idx,args)
    # Ensure port is a number (strip any whitespace or quotes)
    if {![string is integer -strict $port]} {
      # Fall back to command detection
      if {[info exists sim(spicewave,$idx,cmd)]} {
        set cmd $sim(spicewave,$idx,cmd)
        if {[string first "pqwave" $cmd] >= 0} {
          set port 2026
        } else {
          set port 2020
        }
      } else {
        set port 2020
      }
    }
  } elseif {[info exists sim(spicewave,$idx,cmd)]} {
    # Fall back to command detection if args not set
    set cmd $sim(spicewave,$idx,cmd)
    if {[string first "pqwave" $cmd] >= 0} {
      set port 2026
    } else {
      set port 2020
    }
  } else {
    set port 2020
  }
  set gaw_tcp_address [list localhost $port]

  set custom_netlist_file [xschem get netlist_name]
  if {$custom_netlist_file ne {}} {
    set s [file rootname $custom_netlist_file]
  } else {
    set s [file tail [file rootname [xschem get schname 0]]]
  }
  if { ![info exists gaw_fd] && [catch {eval socket $gaw_tcp_address} gaw_fd] } {
    puts "Problems opening socket to gaw on address $gaw_tcp_address"
    unset gaw_fd
    if {[info exists has_x]} {
      tk_messageBox -type ok -title {Tcp socket error} \
       -message [concat "Problems opening socket to gaw on address $gaw_tcp_address. " \
         "Ensure the following line is present uncommented in ~/.gaw/gawrc: up_listenPort = 2020." \
         "If you recently closed gaw the port may be in a TIME_WAIT state for a minute or so ." \
         "Close gaw, Wait a minute or two, then send waves to gaw again."]
    }
    return 0
  }
  fconfigure $gaw_fd -blocking 1 -buffering line -encoding binary -translation binary
  fileevent $gaw_fd readable gaw_echoline
  # Send basename (gaw looks up table by name, not path)
  puts $gaw_fd "table_set $s.raw"
  return 1
}
