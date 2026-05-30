;; pqwave menu additions for lepton-schematic.
;; Loaded via a (load ...) line appended to lepton-eda's menu.scm.
;; This code runs after conf/schematic/menu.scm has populated the
;; built-in menus, but before make-main-menu builds the menu bar.

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

;; Append SPICE to the built-in Netlist menu by manipulating the
;; private menu list.  Must happen before make-main-menu runs.
(let ((menu-list (@@ (schematic menu) %main-menu-list)))
  (let ((netlist-entry (assoc "Netlist" menu-list)))
    (when netlist-entry
      (set-cdr! netlist-entry
        (append (cdr netlist-entry)
                (list (list "SPICE" &spice-netlist #f)))))))

;; Add new top-level menus.
(add-menu "_Simulation" '(("ngspice" &sim-ngspice #f)))
(add-menu "_Wave" '(("pqwave" &wave-pqwave #f)))
