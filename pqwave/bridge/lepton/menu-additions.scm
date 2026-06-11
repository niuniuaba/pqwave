;; pqwave menu additions for lepton-schematic.
;; Load via user gschemrc: add (load "/path/to/menu-additions.scm") to
;;   ~/.config/lepton-eda/gschemrc
;; VERSION: 8

(use-modules (srfi srfi-1) (srfi srfi-13) (lepton page) (lepton log)
             (schematic menu) (schematic dialog))

;; Helper: given a full .sch path, return (dir . basename-without-ext).
(define (pqwave-path-parts filename)
  (let* ((idx (or (string-rindex filename #\.) (string-length filename)))
         (base (substring filename 0 idx))
         (slash (string-rindex base #\/))
         (dir (if slash (substring base 0 slash) "."))
         (name (if slash (substring base (+ 1 slash)) base)))
    (cons dir name)))

(define (&spice-netlist)
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((parts (pqwave-path-parts filename))
             (dir (car parts))
             (name (cdr parts))
             (sim-dir (string-append dir "/simulation"))
             (cir (string-append sim-dir "/" name ".cir")))
        (system* "mkdir" "-p" sim-dir)
        (catch #t
          (lambda ()
            (system* "lepton-netlist" "-g" "spice-sdb" "-o" cir filename)
            (schematic-message-dialog
             (string-append "SPICE netlist written:\n" cir)))
          (lambda (key . args)
            (schematic-error-dialog
             (string-append "SPICE netlist failed:\n"
                            (format #f "~A ~A" key args))
             #:secondary-text
             "Check the lepton-schematic log for details.")))))))

(define (&sim-ngspice)
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((parts (pqwave-path-parts filename))
             (dir (car parts))
             (name (cdr parts))
             (sim-dir (string-append dir "/simulation"))
             (cir (string-append sim-dir "/" name ".cir"))
             (raw (string-append sim-dir "/" name ".raw")))
        (system* "mkdir" "-p" sim-dir)
        (system* "lepton-netlist" "-g" "spice-sdb" "-o" cir filename)
        (catch #t
          (lambda ()
            (system* "ngspice" "-b" "-r" raw cir)
            (schematic-message-dialog
             (string-append "Simulation complete:\n" raw)))
          (lambda (key . args)
            (schematic-error-dialog
             (string-append "Simulation failed:\n"
                            (format #f "~A ~A" key args))
             #:secondary-text
             "Check the lepton-schematic log for details.")))))))

(define (&wave-pqwave)
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((parts (pqwave-path-parts filename))
             (dir (car parts))
             (name (cdr parts))
             (sim-dir (string-append dir "/simulation"))
             (raw (string-append sim-dir "/" name ".raw")))
        (system* "sh" "-c"
          (string-append "pqwave \"" raw "\" --connect lepton --sch-path \""
                         filename "\" &"))))))

;; Append SPICE to the built-in Netlist menu.
(let ((menu-list (@@ (schematic menu) %main-menu-list)))
  (let ((netlist-entry (assoc "_Netlist" menu-list)))
    (when netlist-entry
      (set-cdr! netlist-entry
        (append (cdr netlist-entry)
                (list (list "2 SPICE" '&spice-netlist #f)))))))

;; Add Simulation and Wave menus between Netlist and Help.
(let* ((menu-list (@@ (schematic menu) %main-menu-list))
       (names (map car menu-list))
       (netlist-pos (list-index (lambda (n) (string=? n "_Netlist")) names))
       (help-pos (list-index (lambda (n) (string=? n "_Help")) names)))
  (when (and netlist-pos help-pos)
    (let* ((before (list-head menu-list (+ 1 netlist-pos)))
           (after (list-tail menu-list help-pos))
           (sim (list (cons "_Simulation"
                            (list (list "ngspice" '&sim-ngspice #f)))))
           (wave (list (cons "_Wave"
                             (list (list "pqwave" '&wave-pqwave #f)))))
           (new-list (append before sim wave after)))
      (set! (@@ (schematic menu) %main-menu-list) new-list))))
