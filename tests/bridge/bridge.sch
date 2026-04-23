v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 960 380 1760 780 {flags=graph
y1=0
y2=2
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=10e-6
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node=""
color=""
dataset=-1
unitx=1
logx=0
logy=0
}
N 840 490 840 610 {lab=r2}
N 720 490 720 610 {lab=AC_n}
N 640 490 640 610 {lab=AC_p}
N 640 400 640 430 {lab=#net1}
N 720 400 720 430 {lab=#net1}
N 640 670 640 690 {lab=0}
N 640 690 840 690 {lab=0}
N 840 670 840 690 {lab=0}
N 720 670 720 690 {lab=0}
N 780 580 780 690 {lab=0}
N 550 500 550 520 {lab=AC_p}
N 550 500 640 500 {lab=AC_p}
N 550 590 720 590 {lab=AC_n}
N 840 690 840 720 {lab=0}
N 550 580 550 590 {lab=AC_n}
N 780 400 780 520 {lab=#net1}
N 640 400 840 400 {lab=#net1}
N 840 400 840 430 {lab=#net1}
C {res.sym} 840 460 0 0 {name=R1
value=1k
footprint=1206
device=resistor
m=1}
C {res.sym} 840 640 0 0 {name=R2
value=1k
footprint=1206
device=resistor
m=1}
C {diode.sym} 640 460 2 0 {name=D1 model=D1N4148 area=1
device_model="
.model D1N4148 D(Is=2.55e-9 N=1.75 Rs=42e-3 Cj0=42.4e-12 Vj=0.75 M=0.333 Fc=0.5 Tt=4.32e-6 Bv=800 Ibv=80e-6 Af=1 Kf=0)
"}
C {diode.sym} 720 460 2 0 {name=D2 model=D1N4148 area=1
device_model="
.model D1N4148 D(Is=2.55e-9 N=1.75 Rs=42e-3 Cj0=42.4e-12 Vj=0.75 M=0.333 Fc=0.5 Tt=4.32e-6 Bv=800 Ibv=80e-6 Af=1 Kf=0)
"}
C {diode.sym} 640 640 2 0 {name=D3 model=D1N4148 area=1
device_model="
.model D1N4148 D(Is=2.55e-9 N=1.75 Rs=42e-3 Cj0=42.4e-12 Vj=0.75 M=0.333 Fc=0.5 Tt=4.32e-6 Bv=800 Ibv=80e-6 Af=1 Kf=0)
" }
C {diode.sym} 720 640 2 0 {name=D4 model=D1N4148 area=1
device_model="
.model D1N4148 D(Is=2.55e-9 N=1.75 Rs=42e-3 Cj0=42.4e-12 Vj=0.75 M=0.333 Fc=0.5 Tt=4.32e-6 Bv=800 Ibv=80e-6 Af=1 Kf=0)
"}
C {gnd.sym} 840 720 0 0 {name=l1 lab=0}
C {capa-2.sym} 780 550 0 0 {name=C1
m=1
value=47uF
footprint=1206
device=polarized_capacitor}
C {lab_pin.sym} 550 500 0 0 {name=p1 sig_type=std_logic lab=AC_p}
C {lab_pin.sym} 550 590 0 0 {name=p4 sig_type=std_logic lab=AC_n}
C {vsource.sym} 550 550 0 0 {name=V1 value="SIN(0 100 100)" savecurrent=false}
C {simulator_commands_shown.sym} 460 320 0 0 {name=COMMANDS
simulator=ngspice
only_toplevel=false
value=".control
tran 1e-05 0.04 0
write bridge.raw v(ac_p) v(ac_n) v(r1) v(r2)
gnuplot bridge v(ac_p,ac_n) v(r1) v(r2)
.endc
"}
C {lab_wire.sym} 830 390 0 0 {name=p2 sig_type=std_logic lab=r1}
C {lab_wire.sym} 840 530 0 0 {name=p3 sig_type=std_logic lab=r2}
C {lab_generic.sym} 720 530 0 0 {name=l2 lab=lll value=xxx}
