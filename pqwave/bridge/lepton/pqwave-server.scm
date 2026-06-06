;; pqwave-server.scm — cross-probe and back-annotation TCP server for lepton-schematic
;; Load via user gafrc: add (load "/path/to/pqwave-server.scm") to
;;   ~/.config/lepton-eda/gafrc
;; Menu additions are in menu-additions.scm (loaded separately).
;; This file contains the TCP server, cross-probe logic, and back-annotation.
;; VERSION: 8

(use-modules (srfi srfi-1) (srfi srfi-13) (ice-9 rdelim) (ice-9 regex) (ice-9 threads) (ice-9 hash-table))
(use-modules (lepton attrib) (lepton object) (lepton page) (lepton log))
(use-modules (schematic hook) (schematic selection))
(use-modules (schematic window) (system foreign))

(define pqwave-port 9424)
(define pqwave-server-socket #f)
(define pqwave-client #f)
;; Label tracking: netname → text-object for in-place updates
(define pqwave-label-map (make-hash-table))

;; ---- TCP Server ----

(define (pqwave-start-server port)
  (set! pqwave-port port)
  ;; Close any previously-bound socket to avoid "Address already in use"
  ;; when lepton-schematic is restarted quickly.
  (when pqwave-server-socket
    (catch #t
      (lambda () (close-port pqwave-server-socket))
      (lambda _ #f))
    (set! pqwave-server-socket #f))
  ;; Retry bind a few times — the OS may need a moment to release the port.
  (let retry ((attempts 5))
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
                  ;; Guile 3.0: accept returns (client-sock . addr-vector)
                  (set! pqwave-client (car client-conn))
                  (pqwave-handle-client (car client-conn))
                  (set! pqwave-client #f)
                  (loop)))))))
      (lambda (key . args)
        (if (> attempts 1)
            (begin
              (sleep 1)
              (retry (- attempts 1)))
            (format (current-error-port)
                    "pqwave-server: TCP error ~A ~A\n" key args))))))

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
  (format (current-error-port) "pqwave DEBUG: dispatch cmd=~A\n" cmd)
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
                             (let ((val (attrib-value a)))
                               (and (string? val)
                               ;; Match exact name, or name with annotation suffix
                               ;; (old [DC:...] format or new "R1 96.7417V" format).
                               (or (string=? name val)
                                   (and (string-prefix? name val)
                                        (< (string-length name) (string-length val))
                                        (let ((c (string-ref val (string-length name))))
                                          (or (char=? c #\[)   ; old [DC:...] format
                                              (char=? c #\ ))) ; new "R1 96.7417V" format
                                        ))))))
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
    ;; Briefly select each net for visual highlighting, then zoom.
    (for-each (lambda (net)
                (catch #t (lambda () (select-object! net)) (lambda _ #f)))
              nets)
    (when (and page (pair? nets))
      (catch #t
        (lambda ()
          (let* ((*canvas (schematic_window_get_current_canvas
                           (window->pointer (current-window)))))
            (unless (null-pointer? *canvas)
              (schematic_canvas_zoom_object *canvas (object->pointer (car nets))))))
        (lambda _ #f))
      ;; Immediately deselect so the cross-probed net cannot be
      ;; accidentally deleted, moved, or copied by the user.
      (for-each (lambda (net)
                  (catch #t (lambda () (deselect-object! net)) (lambda _ #f)))
                nets))))

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
  ;; Format: $ANNOTATE:DC|netname|voltage  (pipe-delimited to allow
  ;; net names containing spaces).
  ;; Strips any existing [DC:...V], [DC:... V], or trailing number+V
  ;; annotation before writing the new value, so the netname does not
  ;; accumulate stale annotations across cursor moves.
  (let* ((parts (string-split cmd #\|))
         (netname (if (> (length parts) 1) (list-ref parts 1) ""))
         (voltage (if (> (length parts) 2) (list-ref parts 2) "0.0")))
    (let ((page (active-page)))
      (when page
        (for-each
         (lambda (net)
           (let ((na (find (lambda (a) (string=? "netname" (attrib-name a)))
                           (object-attribs net))))
             (when na
               ;; Strip any prior annotation suffix: [DC:...], trailing
               ;; number+V, or number V pattern left by a previous stamp.
               (let* ((cur (attrib-value na))
                      (clean (regexp-substitute/global
                              #f
                              "(\\[[^]]*\\][[:space:]]*|[[:space:]]*[+-]?[0-9.]+[eE]?[+-]?[0-9]*[[:space:]]*V)$"
                              cur 'pre)))
                 (set-attrib-value! na
                   (string-append clean " " voltage "V"))))))
         (pqwave-find-nets-by-name page netname))))))

(define (pqwave-annotate-label cmd)
  ;; Format: $ANNOTATE:LABEL|<netname>|<text>|<x>|<y>
  ;; When x=0 and y=0, auto-positions the label near the net.
  (format (current-error-port) "pqwave DEBUG: annotate-label cmd=~A\n" cmd)
  (let* ((parts (string-split cmd #\|))
         (netname (if (> (length parts) 1) (list-ref parts 1) ""))
         (text (if (> (length parts) 2) (list-ref parts 2) "?"))
         (x-str (if (> (length parts) 3) (list-ref parts 3) "0"))
         (y-str (if (> (length parts) 4) (list-ref parts 4) "0"))
         (x (string->number x-str))
         (y (string->number y-str)))
    (let ((page (active-page)))
      (when (and page x y)
        (let ((existing (hash-ref pqwave-label-map netname)))
          (if existing
              ;; Update existing — preserves user position/rotation
              (begin
                (format (current-error-port)
                        "pqwave DEBUG: updating existing label for ~A\n" netname)
                (set-text-string! existing text))
              ;; Create new label.  Auto-position near net if (0,0).
              (begin
                (format (current-error-port)
                        "pqwave DEBUG: creating new label netname=~A pos=(~A,~A)\n"
                        netname x y)
                (let* ((pos (if (and (= x 0) (= y 0))
                              (let ((nets (pqwave-find-nets-by-name page netname)))
                                (format (current-error-port)
                                        "pqwave DEBUG: auto-pos found ~A nets\n"
                                        (length nets))
                                (if (pair? nets)
                                    (let ((b (object-bounds (car nets))))
                                      (format (current-error-port)
                                              "pqwave DEBUG: bounds=~A\n" b)
                                      (if b
                                          ;; bounds: ((left . top) right . bottom)
                                          (cons (caar b)
                                                (+ (cddr b) 50))
                                          (cons 0 0)))
                                    (cons 0 0)))
                              (cons x y)))
                       (txt (make-text pos 'lower-left 0 text 8 #t 'both 0)))  ; 0 = standalone, not an attribute
                  (format (current-error-port) "pqwave DEBUG: text created at ~A\n" pos)
                  (page-append! page txt)
                  (hash-set! pqwave-label-map netname txt)))))))))

(define (pqwave-clear-labels)
  (let ((page (active-page)))
    (when page
      (hash-for-each
       (lambda (netname txt)
         (catch #t (lambda () (page-remove! page txt)) (lambda _ #f)))
       pqwave-label-map)
      (set! pqwave-label-map (make-hash-table)))))

(define (pqwave-remove-stale-labels active-nets)
  "Remove tracked labels for nets not in ACTIVE-NETS (list of netname strings)."
  (let ((page (active-page)))
    (when page
      (let ((to-remove '()))
        (hash-for-each
         (lambda (netname txt)
           (unless (member netname active-nets)
             (catch #t (lambda () (page-remove! page txt)) (lambda _ #f))
             (set! to-remove (cons netname to-remove))))
         pqwave-label-map)
        (for-each (lambda (n) (hash-remove! pqwave-label-map n)) to-remove)))))

(define (pqwave-clear-dc-stamps)
  ;; Strip any back-annotation suffix from netname attributes.
  ;; Handles both old format (R1 [DC:96.7417 V]) and new (R1 96.7417V).
  (let ((page (active-page)))
    (when page
      (for-each
       (lambda (obj)
         (let ((na (find (lambda (a) (string=? "netname" (attrib-name a)))
                         (object-attribs obj))))
           (when na
             (let* ((cur (attrib-value na))
                    (clean (regexp-substitute/global
                            #f
                            "(\\[[^]]*\\][[:space:]]*|[[:space:]]*[+-]?[0-9.]+[eE]?[+-]?[0-9]*[[:space:]]*V)$"
                            cur 'pre)))
               (unless (string=? clean cur)
                 (set-attrib-value! na (string-trim-right clean)))))))
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
               ;; Strip any [DC:...] suffix left by back-annotation.
               (let* ((raw-val (attrib-value netname))
                      (bracket-idx (string-index raw-val #\[))
                      (clean-name (if bracket-idx
                                      (string-trim-right
                                       (substring raw-val 0 bracket-idx))
                                      raw-val)))
                 (catch #t
                   (lambda ()
                     (write-line (string-append "$SELECTED:net " clean-name)
                                 pqwave-client)
                     (force-output pqwave-client))
                   (lambda _ #f))))))
         objs)))))

;; Start the server
(pqwave-start-server pqwave-port)
