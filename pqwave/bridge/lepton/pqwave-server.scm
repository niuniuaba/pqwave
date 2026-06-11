;; pqwave-server.scm — cross-probe and back-annotation TCP server for lepton-schematic
;; Load via user gafrc: add (load "/path/to/pqwave-server.scm") to
;;   ~/.config/lepton-eda/gafrc
;; Menu additions are in menu-additions.scm (loaded separately).
;; This file contains the TCP server, cross-probe logic, and back-annotation.
;; VERSION: 13

(use-modules (srfi srfi-1) (srfi srfi-13) (ice-9 rdelim) (ice-9 regex) (ice-9 threads) (ice-9 hash-table))
(use-modules (lepton attrib) (lepton object) (lepton object foreign) (lepton page) (lepton log))
(use-modules (schematic hook) (schematic selection))
(use-modules (schematic window) (system foreign))

(define pqwave-port 9424)
(define pqwave-server-socket #f)
(define pqwave-client #f)
;; Label tracking for Xa cursor back-annotation: netname → text-object
(define pqwave-label-map (make-hash-table))
;; Label tracking for DC operating-point annotation: netname → text-object
(define pqwave-dc-label-map (make-hash-table))

(define (pqwave-log-status! text)
  "Log connection status to stderr (visible in the terminal that
  launched lepton-schematic).  lepton's GTK status bar is transient
  and gets reset on every user action — terminal logging is reliable."
  (format (current-error-port) "pqwave: ~A\n" text))

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
                  ;; Handshake: send the current schematic path so pqwave
                  ;; knows which .sch is open on the editor side.
                  (let ((page (active-page)))
                    (when page
                      (let ((filename (page-filename page)))
                        (when filename
                          (catch #t
                            (lambda ()
                              (write-line (string-append "$SCHEMATIC:" filename)
                                          (car client-conn))
                              (force-output (car client-conn)))
                            (lambda _ #f))))))
                  (pqwave-log-status! "connected")
                  (pqwave-handle-client (car client-conn))
                  (set! pqwave-client #f)
                  (pqwave-log-status! "disconnected")
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
    (pqwave-clear-dc-stamps))
   ((string-prefix? "$CLEAR:STALE" cmd)
    (pqwave-remove-stale-labels-from-cmd cmd))
   ((string-prefix? "$REMOVE:LABEL" cmd)
    (pqwave-remove-label-from-cmd cmd))))

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
    ;; Clear any previous cross-probe selection before highlighting the new net.
    (pqwave-clear-selection)
    ;; Select the net and leave it selected so the user can see it.
    (for-each (lambda (net)
                (catch #t (lambda () (select-object! net)) (lambda _ #f)))
              nets)
    ;; Zoom to the first matched net.
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
  ;; Format: $ANNOTATE:DC|<netname>|<voltage>
  ;; Creates floating text near the net (free text, no netname prefix).
  ;; Uses a separate pqwave-dc-label-map so DC labels are distinct from
  ;; Xa cursor back-annotation labels.
  ;; Text format matches Xa cursor: "96.19V" (just value + unit).
  (let* ((parts (string-split cmd #\|))
         (netname (if (> (length parts) 1) (list-ref parts 1) ""))
         (voltage (if (> (length parts) 2) (list-ref parts 2) "0.0"))
         (text (string-append voltage "V")))
    (let ((page (active-page)))
      (when page
        (let ((existing (hash-ref pqwave-dc-label-map netname)))
          (if existing
              ;; Update existing DC label text in-place.
              (set-text-string! existing text)
              ;; Create new DC label. Auto-position near net.
              (let* ((nets (pqwave-find-nets-by-name page netname))
                     (pos (if (pair? nets)
                              (let ((b (object-bounds (car nets))))
                                ;; bounds: ((left . top) right . bottom)
                                (if b
                                    (cons (caar b) (+ (cddr b) 50))
                                    (cons 0 0)))
                              (cons 0 0)))
                     (txt (make-text pos 'lower-left 0 text 8 #t 'both 2)))
                (page-append! page txt)
                (hash-set! pqwave-dc-label-map netname txt))))))))

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
        (let ((existing (hash-ref pqwave-label-map netname)))
          (if existing
              ;; Update existing — preserves user position/rotation
              (set-text-string! existing text)
              ;; Create new label.  Auto-position near net if (0,0).
              (let* ((pos (if (and (= x 0) (= y 0))
                            (let ((nets (pqwave-find-nets-by-name page netname)))
                              (if (pair? nets)
                                  (let ((b (object-bounds (car nets))))
                                    ;; bounds: ((left . top) right . bottom)
                                    (if b
                                        (cons (caar b) (+ (cddr b) 50))
                                        (cons 0 0)))
                                  (cons 0 0)))
                            (cons x y)))
                     (txt (make-text pos 'lower-left 0 text 8 #t 'both 2)))
                (page-append! page txt)
                (hash-set! pqwave-label-map netname txt))))))))

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

(define (pqwave-remove-stale-labels-from-cmd cmd)
  "Parse $CLEAR:STALE|net1|net2|... and remove labels for nets not in the list."
  (let* ((parts (string-split cmd #\|))
         (active-nets (if (> (length parts) 1) (cdr parts) '())))
    (pqwave-remove-stale-labels active-nets)))

(define (pqwave-remove-label-from-cmd cmd)
  "Parse $REMOVE:LABEL|netname and remove the label for that net."
  (let* ((parts (string-split cmd #\|))
         (netname (if (> (length parts) 1) (list-ref parts 1) "")))
    (let ((page (active-page)))
      (when (and page (not (string-null? netname)))
        (let ((txt (hash-ref pqwave-label-map netname)))
          (when txt
            (catch #t (lambda () (page-remove! page txt)) (lambda _ #f))
            (hash-remove! pqwave-label-map netname)))))))

(define (pqwave-clear-dc-stamps)
  ;; Remove DC floating-text labels and clear the DC label map.
  (let ((page (active-page)))
    (when page
      (hash-for-each
       (lambda (netname txt)
         (catch #t (lambda () (page-remove! page txt)) (lambda _ #f)))
       pqwave-dc-label-map)
      (set! pqwave-dc-label-map (make-hash-table)))))

;; ---- Reverse Cross-Probe (schematic → pqwave) ----

(add-hook! select-objects-hook
  (lambda (obj-or-list)
    ;; Reverse cross-probe: send net name to pqwave.
    (when pqwave-client
      (let ((objs (if (list? obj-or-list) obj-or-list (list obj-or-list))))
        (for-each
         (lambda (obj)
           (let ((netname (find (lambda (a) (string=? "netname" (attrib-name a)))
                                (object-attribs obj))))
             (when netname
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

;; Start the server.
(pqwave-start-server pqwave-port)
(pqwave-log-status! "listening")
