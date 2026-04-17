#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ThrottledPlotDataItem - PlotDataItem subclass with debounced viewRangeChanged.

During rapid mouse drag (pan/zoom), pyqtgraph's ViewBox fires viewRangeChanged
on every mouse event, triggering full data reprocessing (log mapping,
downsampling, bounds checking) on the entire data array. This is the primary
cause of high CPU usage with large files.

This subclass debounces viewRangeChanged: multiple rapid calls within
DEBOUNCE_MS are coalesced into a single updateItems() call.
"""

import pyqtgraph as pg
from PyQt6.QtCore import QTimer

# Debounce interval in milliseconds. Longer = smoother interaction but more
# lag. 50ms balances responsiveness with meaningful event coalescing
# (typical mouse drag generates 10-20 events per second).
DEBOUNCE_MS = 50


class ThrottledPlotDataItem(pg.PlotDataItem):
    """PlotDataItem with debounced viewRangeChanged for better CPU performance.

    Usage: identical to pg.PlotDataItem. Drop-in replacement.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(DEBOUNCE_MS)
        self._update_timer.timeout.connect(self._do_throttled_update)
        self._update_pending = False

        # Pre-set finite flags for SPICE data (guaranteed finite float32/complex64).
        # This skips the expensive np.isfinite() scan in _getArrayBounds.
        self.xAllFinite: bool | None = True
        self.yAllFinite: bool | None = True

        # Cache data bounds from _updateDataRect() so we don't recompute np.min/max
        # on every viewRangeChanged. The data itself doesn't change, only the view.
        self._dataBoundsCached = False

    def _updateDataRect(self):
        """Override to cache data bounds. SPICE data bounds never change."""
        if not self._dataBoundsCached:
            super()._updateDataRect()
            self._dataBoundsCached = True

    def viewRangeChanged(self, vb=None, ranges=None, changed=None):
        # Replicate parent logic for setting properties and clearing cache,
        # but defer the actual updateItems() call to the debounced timer.

        if changed is None or (len(changed) > 0 and changed[0]):
            self.setProperty('xViewRangeWasChanged', True)
            if self.opts['clipToView'] or self.opts['autoDownsample']:
                self._datasetDisplay = None
        if changed is None or (len(changed) > 1 and changed[1]):
            self.setProperty('yViewRangeWasChanged', True)

        # Schedule a throttled update instead of immediate updateItems()
        if not self._update_pending:
            self._update_pending = True
            self._update_timer.start()
        else:
            # Reset timer — coalesce with the next event
            self._update_timer.start()

    def _do_throttled_update(self):
        """Called after debounce interval expires — actually update the display."""
        self._update_pending = False
        self.updateItems(styleUpdate=False)
