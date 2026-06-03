## 1. Write Monte Carlo User Guide

- [x] 1.1 Write overview and loading data sections — explain what MC analysis is, the three loading modes (stepped, multi-file, pattern-based), and the Open Monte Carlo dialog
- [x] 1.2 Write display modes and control bar section — document spaghetti/envelope/single modes, sigma control, nominal run selection, and run filtering
- [x] 1.3 Write statistical analysis section — document cross-run statistics, yield analysis, worst-case ranking, sensitivity analysis, histogram, and scatter plot features with examples
- [x] 1.4 Write correlation tools section — document the three-step workflow: loading model files, editing correlation matrices, and generating output in all formats (CSV, TSV, ngspice .control, .param)
- [x] 1.5 Write session API / scripting section — document all 17 `mc_*` commands with parameter descriptions, return value shapes, and a complete headless scripting example

## 2. Wire Help Menu Entry

- [x] 2.1 Add "Monte Carlo Guide" action to Help menu in `pqwave/ui/menu_manager.py`
- [x] 2.2 Wire callback in `pqwave/ui/main_window.py` to open `docs/monte_carlo/guide.md` in a QTextBrowser dialog
