# pqwave-server.tcl — ABC-protocol TCP server for xschem cross-probe
# Deploy to ~/.config/xschem/pqwave-server.tcl
# Load via xschemrc: lappend tcl_files ~/.config/xschem/pqwave-server.tcl
#
# Protocol:
#   $NET: "name"       → probe_net <name>
#   $PART: "ref"       → select_inst <ref>
#   $CLEAR             → xschem unhilight_all
#
# VERSION: 1

global pqwave_port
if {![info exists pqwave_port]} { set pqwave_port 2021 }

proc pqwave_cross_probe_server {sock addr port} {
    fconfigure $sock -blocking 0 -buffering line -encoding utf-8
    fileevent $sock readable [list pqwave_handler $sock]
    puts stderr "pqwave: accepted connection from $addr:$port"
}

proc pqwave_handler {sock} {
    if {[eof $sock]} {
        puts stderr "pqwave: client disconnected"
        close $sock
        return
    }
    if {[catch {gets $sock line} len]} {
        puts stderr "pqwave: read error: $len"
        close $sock
        return
    }
    if {$len < 0} {
        puts stderr "pqwave: EOF"
        close $sock
        return
    }
    set line [string trim $line]
    if {$line eq {}} { return }

    puts stderr "pqwave: received: $line"

    if {[string match {\$NET:*} $line]} {
        if {[regexp {\$NET:\s*"(.*)"} $line -> net]} {
            catch { probe_net $net 1 }
        }
    } elseif {[string match {\$PART:*} $line]} {
        if {[regexp {\$PART:\s*"(.*)"} $line -> ref]} {
            catch { select_inst $ref 1 }
        }
    } elseif {$line eq {$CLEAR}} {
        catch { xschem unhilight_all ; xschem redraw }
    } elseif {$line eq {PING}} {
        puts $sock "PONG"
    }
}

# Start the server
if {[catch {socket -server pqwave_cross_probe_server $pqwave_port} err]} {
    puts stderr "pqwave: failed to start cross-probe server on port $pqwave_port: $err"
} else {
    set pqwave_server_chan $err
    set assigned_port [lindex [fconfigure $pqwave_server_chan -sockname] end]
    puts stderr "pqwave: cross-probe server listening on port $assigned_port"
}
