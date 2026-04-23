set encoding utf8
set termoption noenhanced
set title "** sch_path: /home/wing/data/eda/xschem/bridge/bridge.sch"
set xlabel "s"
set grid
unset logscale x 
set xrange [0.000000e+00:4.000000e-02]
unset logscale y 
set yrange [-1.100000e+02:1.100000e+02]
#set xtics 1
#set x2tics 1
#set ytics 1
#set y2tics 1
set format y "%g"
set format x "%g"
plot 'bridge.data' using 1:2 with lines lw 1 title "v(ac_p,ac_n)",\
'bridge.data' using 3:4 with lines lw 1 title "v(r1)",\
'bridge.data' using 5:6 with lines lw 1 title "v(r2)"
