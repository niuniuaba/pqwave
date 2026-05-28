;; pqwave-server.scm — cross-probe and back-annotation server for lepton-schematic
;; Deployed to ~/.config/lepton-eda/scheme/autoload/ on first bridge use.
;; Loaded automatically by lepton-schematic at startup via system-gafrc.

(use-modules (srfi srfi-1)
             (ice-9 rdelim)
             (ice-9 threads)
             (lepton attrib)
             (lepton object)
             (lepton page)
             (schematic hook)
             (schematic selection)
             (schematic window)
             (schematic menu)
             (schematic builtins))

(define pqwave-port 9424)
(define pqwave-server-socket #f)
(define pqwave-client #f)
(define pqwave-label-objects '())

;; ---- TCP Server ----

(define (pqwave-start-server port)
  (set! pqwave-port port)
  (catch #t
    (lambda ()
      (let ((sock (socket PF_INET SOCK_STREAM 0)))
        (setsockopt sock SOL_SOCKET SO_REUSEADDR 1)
        (bind sock AF_INET INADDR_LOOPBACK port)
        (listen sock 5)
        (set! pqwave-server-socket sock)
        (call-with-new-thread
          (lambda ()
            (let loop ()
              (let ((client-conn (accept sock)))
                (set! pqwave-client (cdr client-conn))
                (pqwave-handle-client (cdr client-conn))
                (set! pqwave-client #f)
                (loop)))))))
    (lambda (key . args)
      (format (current-error-port) "pqwave-server: TCP error ~A ~A\n" key args))))

(define (pqwave-handle-client client)
  (catch #t
    (lambda ()
      (let loop ()
        (let ((line (read-line client)))
          (if (eof-object? line)
              (close-port client)
              (begin
                (pqwave-dispatch (string-trim-both line))
                (loop))))))
    (lambda (key . args)
      (format (current-error-port) "pqwave-server: client error ~A ~A\n" key args))))

;; ---- Command Dispatch ----

(define (pqwave-dispatch cmd)
  (cond
   ((string-prefix? "$NET:" cmd)
    (pqwave-probe-net (pqwave-strip-quotes (string-trim-both (string-drop cmd 5)))))
   ((string-prefix? "$PART:" cmd)
    (pqwave-probe-part (pqwave-strip-quotes (string-trim-both (string-drop cmd 6)))))
   ((string=? "$CLEAR" cmd)
    (pqwave-clear-selection))
   ((string-prefix? "$ANNOTATE:DC" cmd)
    (pqwave-annotate-dc cmd))
   ((string-prefix? "$ANNOTATE:LABEL" cmd)
    (pqwave-annotate-label cmd))
   ((string=? "$CLEAR:ANNOTATIONS" cmd)
    (pqwave-clear-labels))
   ((string=? "$CLEAR:DC" cmd)
    (pqwave-clear-dc-stamps))))

(define (pqwave-strip-quotes s)
  (string-trim-both s #\"))

;; ---- Net/Part Lookups ----

(define (pqwave-find-nets-by-name page name)
  (filter (lambda (o)
            (and (eq? (object-type o) 'net)
                 (any (lambda (a)
                        (and (string=? "netname" (attrib-name a))
                             (string=? name (attrib-value a))))
                      (object-attribs o))))
          (page-contents page)))

(define (pqwave-find-part-by-refdes page ref)
  (find (lambda (o)
          (any (lambda (a)
                 (and (string=? "refdes" (attrib-name a))
                      (string=? ref (attrib-value a))))
               (object-attribs o)))
        (page-contents page)))

;; ---- Cross-Probe Handlers ----

(define (pqwave-probe-net name)
  (let* ((page (active-page))
         (nets (if page (pqwave-find-nets-by-name page name) '())))
    (for-each (lambda (net)
                (catch #t
                  (lambda () (select-object! net))
                  (lambda _ #f)))
              nets)
    (when (and page (pair? nets))
      (catch #t
        (lambda ()
          (let* ((*canvas (schematic_window_get_current_canvas
                           (window->pointer (current-window)))))
            (unless (null-pointer? *canvas)
              (schematic_canvas_zoom_object *canvas (object->pointer (car nets))))))
        (lambda _ #f)))))

(define (pqwave-probe-part ref)
  (let* ((page (active-page))
         (part (if page (pqwave-find-part-by-refdes page ref) #f)))
    (when part
      (catch #t (lambda () (select-object! part)) (lambda _ #f))
      (catch #t
        (lambda ()
          (let* ((*canvas (schematic_window_get_current_canvas
                           (window->pointer (current-window)))))
            (unless (null-pointer? *canvas)
              (schematic_canvas_zoom_object *canvas (object->pointer part)))))
        (lambda _ #f)))))

(define (pqwave-clear-selection)
  (let ((page (active-page)))
    (when page
      (for-each (lambda (obj)
                  (catch #t (lambda () (deselect-object! obj)) (lambda _ #f)))
                (page-selection page)))))

;; ---- Back-Annotation Handlers ----

(define (pqwave-annotate-dc cmd)
  (let* ((parts (string-split cmd #\space))
         (netname (if (> (length parts) 1) (list-ref parts 1) ""))
         (voltage (if (> (length parts) 2) (list-ref parts 2) "0.0")))
    (let ((page (active-page)))
      (when page
        (for-each
         (lambda (net)
           (let ((na (find (lambda (a) (string=? "netname" (attrib-name a)))
                           (object-attribs net))))
             (when na
               (set-attrib-value! na
                 (string-append netname " [DC:" voltage " V]")))))
         (pqwave-find-nets-by-name page netname))))))

(define (pqwave-annotate-label cmd)
  ;; Format: $ANNOTATE:LABEL|<netname>|<text>|<x>|<y>
  (let* ((parts (string-split cmd #\|))
         (netname (if (> (length parts) 1) (list-ref parts 1) ""))
         (text (if (> (length parts) 2) (list-ref parts 2) "?"))
         (x-str (if (> (length parts) 3) (list-ref parts 3) "0"))
         (y-str (if (> (length parts) 4) (list-ref parts 4) "0"))
         (x (string->number x-str))
         (y (string->number y-str)))
    (let ((page (active-page)))
      (when (and page x y)
        (let ((txt (make-text (cons x y) 'lower-left 0 text 8 #t 'both 2)))
          (page-append! page txt)
          (set! pqwave-label-objects (cons txt pqwave-label-objects)))))))

(define (pqwave-clear-labels)
  (let ((page (active-page)))
    (when page
      (for-each (lambda (lbl)
                  (catch #t (lambda () (page-remove! page lbl)) (lambda _ #f)))
                pqwave-label-objects)
      (set! pqwave-label-objects '()))))

(define (pqwave-clear-dc-stamps)
  (let ((page (active-page)))
    (when page
      (for-each
       (lambda (obj)
         (let ((na (find (lambda (a) (string=? "netname" (attrib-name a)))
                         (object-attribs obj))))
           (when na
             (let* ((val (attrib-value na))
                    (bracket-idx (string-index val #\[)))
               (when bracket-idx
                 (set-attrib-value! na (string-trim-right (substring val 0 bracket-idx))))))))
       (page-contents page)))))

;; ---- Reverse Cross-Probe (schematic → pqwave) ----

(add-hook! select-objects-hook
  (lambda (obj-or-list)
    (when pqwave-client
      (let ((objs (if (list? obj-or-list) obj-or-list (list obj-or-list))))
        (for-each
         (lambda (obj)
           (let ((netname (find (lambda (a) (string=? "netname" (attrib-name a)))
                                (object-attribs obj))))
             (when netname
               (catch #t
                 (lambda ()
                   (write-line (string-append "$SELECTED:net "
                                              (attrib-value netname))
                               pqwave-client)
                   (force-output pqwave-client))
                 (lambda _ #f)))))
         objs)))))

;; ---- In-Schematic Menus ----

(define-action-public (&spice-netlist #:label "SPICE" #:icon "gtk-execute")
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((idx (or (string-rindex filename #\.) (string-length filename)))
             (base (substring filename 0 idx))
             (cir-file (string-append base ".cir")))
        (catch #t
          (lambda ()
            (system* "lepton-netlist" "-g" "spice-sdb" "-o" cir-file filename)
            (log! 'message (string-append "SPICE netlist written: " cir-file)))
          (lambda (key . args)
            (log! 'warning (format #f "SPICE netlist export failed: ~A ~A" key args))))))))

(define-action-public (&sim-ngspice #:label "ngspice" #:icon "gtk-execute")
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((idx (or (string-rindex filename #\.) (string-length filename)))
             (base (substring filename 0 idx))
             (cir-file (string-append base ".cir"))
             (raw-file (string-append base ".raw")))
        (system* "lepton-netlist" "-g" "spice-sdb" "-o" cir-file filename)
        (catch #t
          (lambda ()
            (system* "ngspice" "-b" "-r" raw-file cir-file)
            (log! 'message (string-append "Simulation complete: " raw-file)))
          (lambda (key . args)
            (log! 'warning (format #f "Simulation failed: ~A ~A" key args))))))))

(define-action-public (&wave-pqwave #:label "pqwave" #:icon "gtk-execute")
  (let* ((page (active-page))
         (filename (if page (page-filename page) #f)))
    (when filename
      (let* ((idx (or (string-rindex filename #\.) (string-length filename)))
             (base (substring filename 0 idx))
             (raw-file (string-append base ".raw")))
        (system* "pqwave" raw-file)))))

;; Register menus — gafrc runs before make-main-menu, so these appear on startup
(add-menu "Netlist" '(("SPICE" &spice-netlist "gtk-execute")))
(add-menu "_Simulation" '(("ngspice" &sim-ngspice "gtk-execute")))
(add-menu "_Wave View" '(("pqwave" &wave-pqwave "gtk-execute")))

;; Start the server
(pqwave-start-server pqwave-port)
