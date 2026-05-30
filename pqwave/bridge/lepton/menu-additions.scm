;; pqwave menu additions for lepton-schematic.
;; Loaded via a (load ...) line appended to lepton-eda's menu.scm.
;; This code runs after conf/schematic/menu.scm has populated the
;; built-in menus, but before make-main-menu builds the menu bar.

(use-modules (srfi srfi-1))

(define (&spice-netlist)
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((idx (or (string-rindex filename #\.) (string-length filename)))
             (base (substring filename 0 idx))
             (cir (string-append base ".cir")))
        (catch #t
          (lambda ()
            (system* "lepton-netlist" "-g" "spice-sdb" "-o" cir filename)
            (log! 'message (string-append "SPICE netlist: " cir)))
          (lambda (key . args)
            (log! 'warning
              (format #f "SPICE netlist failed: ~A ~A" key args))))))))

(define (&sim-ngspice)
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((idx (or (string-rindex filename #\.) (string-length filename)))
             (base (substring filename 0 idx))
             (cir (string-append base ".cir"))
             (raw (string-append base ".raw")))
        (system* "lepton-netlist" "-g" "spice-sdb" "-o" cir filename)
        (catch #t
          (lambda ()
            (system* "ngspice" "-b" "-r" raw cir)
            (log! 'message (string-append "Simulation done: " raw)))
          (lambda (key . args)
            (log! 'warning
              (format #f "Simulation failed: ~A ~A" key args))))))))

(define (&wave-pqwave)
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((idx (or (string-rindex filename #\.) (string-length filename)))
             (base (substring filename 0 idx))
             (raw (string-append base ".raw")))
        (system* "pqwave" raw)))))

;; Merge SPICE into the existing Netlist menu, add Simulation and Wave
;; as new menus between Netlist and Help.
(let* ((menu-list (@@ (schematic menu) %main-menu-list))
       (names (map car menu-list))
       (netlist-pos (list-index (lambda (n) (string=? n "Netlist")) names))
       (help-pos (list-index (lambda (n) (string=? n "Help")) names)))

  ;; Append SPICE to existing Netlist menu items
  (when netlist-pos
    (let ((entry (list-ref menu-list netlist-pos)))
      (set-cdr! entry (append (cdr entry)
                               (list (list "SPICE" &spice-netlist #f))))))

  ;; Insert Simulation and Wave between Netlist and Help
  (when (and netlist-pos help-pos)
    (let* ((before (list-head menu-list (+ 1 netlist-pos)))
           (after  (list-tail menu-list (+ 1 netlist-pos)))
           (sim-entry (cons "_Simulation"
                            (list (list "ngspice" &sim-ngspice #f))))
           (wave-entry (cons "_Wave"
                             (list (list "pqwave" &wave-pqwave #f))))
           (new-list (append before (list sim-entry wave-entry) after)))
      (set! (@@ (schematic menu) %main-menu-list) new-list))))
