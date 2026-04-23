v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 680 390 680 430 {lab=#net1}
N 680 390 810 390 {lab=#net1}
N 810 390 810 420 {lab=#net1}
N 680 490 680 540 {lab=0}
N 810 480 810 510 {lab=0}
N 680 510 810 510 {lab=0}
C {res.sym} 810 450 0 0 {name=R1
value=1k
footprint=1206
device=resistor
m=1}
C {gnd.sym} 680 540 0 0 {name=l1 lab=0}
C {simulator_commands_shown.sym} 460 320 0 0 {name=COMMANDS
simulator=ngspice
only_toplevel=false
value=".AC dec 5 100 1Meg 
.plot ac vdb(r2)
"}
C {vsource.sym} 680 460 0 0 {name=V1 value="DC 0 AC 1" savecurrent=false}
