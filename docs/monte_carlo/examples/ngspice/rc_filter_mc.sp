* RC Low-Pass Filter — Monte Carlo Example
* Varies R and C across 21 runs. Output vectors named vout0..vout20.
* Companion file rc_filter_params.csv lists R and C values per run.
*
* Run: ngspice -b -o rc_filter_mc.log rc_filter_mc.sp
* Load in pqwave: File > Open Monte Carlo > Single file with named runs
*   Base name: vout

V1 in 0 AC 1 DC 0
R1 in out 10k
C1 out 0 10n

.control
  let mc_runs = 20
  let run = 0

  * R values per run
  let Rv = vector(21)
  let Rv[0]  = 10k  ; let Rv[1]  = 1k   ; let Rv[2]  = 2.2k
  let Rv[3]  = 4.7k ; let Rv[4]  = 10k  ; let Rv[5]  = 22k
  let Rv[6]  = 47k  ; let Rv[7]  = 100k ; let Rv[8]  = 1.5k
  let Rv[9]  = 3.3k ; let Rv[10] = 6.8k ; let Rv[11] = 15k
  let Rv[12] = 33k  ; let Rv[13] = 68k  ; let Rv[14] = 1k
  let Rv[15] = 4.7k ; let Rv[16] = 22k  ; let Rv[17] = 47k
  let Rv[18] = 100k ; let Rv[19] = 2.2k ; let Rv[20] = 10k

  * C values per run
  let Cv = vector(21)
  let Cv[0]  = 10n  ; let Cv[1]  = 10n  ; let Cv[2]  = 1n
  let Cv[3]  = 2.2n ; let Cv[4]  = 4.7n ; let Cv[5]  = 10n
  let Cv[6]  = 22n  ; let Cv[7]  = 47n  ; let Cv[8]  = 100n
  let Cv[9]  = 1n   ; let Cv[10] = 2.2n ; let Cv[11] = 4.7n
  let Cv[12] = 10n  ; let Cv[13] = 22n  ; let Cv[14] = 47n
  let Cv[15] = 100n ; let Cv[16] = 1n   ; let Cv[17] = 4.7n
  let Cv[18] = 10n  ; let Cv[19] = 47n  ; let Cv[20] = 22n

  * Collect outputs in a scratch plot
  set curplot = new
  set scratch = $curplot
  setplot prev

  dowhile run <= mc_runs
    alter R1 = Rv[run]
    alter C1 = Cv[run]

    ac dec 50 100 1Meg

    * Copy output magnitude to scratch plot
    set dt = $curplot
    setplot $scratch
    set run_str = $&run
    let vout{$run_str} = mag({$dt}.v(out))
    if run = 0
      let frequency = {$dt}.frequency
    end
    setplot $dt

    let run = run + 1
    reset
  end

  * Write the scratch plot
  setplot $scratch
  write rc_filter_mc.raw
  echo "Wrote rc_filter_mc.raw"
  quit
.endc

.end
