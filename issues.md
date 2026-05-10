## issues
### ✅ 1. init state ✅ **fixed**
- what is: 
  - there are two guessed variables show up in trace_expr
- how to reproduce:
  - open gui by ./venv/bin/python pqwave.py
  - open tests/bridge.raw from File menu or Toolbar
  - the variable "time" is guessed as and set to X axis
  - there are two "time" show up in add_trace expr 
- what expected:
  - when a variable or variables or expressions are "Add" the trace_expr should be cleared for next input

### ✅ 2. mouse tracking ✅ fixed
- what is:
  - mouse tracking doesn't function
- how to produce:
  - open gui by ./venv/bin/python pqwave.py 
  - move mouse in plotwidget
  - the status bar shows X: nan, Y1: nan, Y2: nan
- What expected
  - the status bar should show the current position of mouse in form of X: 0.000, Y1: 0.000, Y2: 0.000

### ✅ 3. zoom in / zoom out / zoom box ✅ **fixed**
- what is:
  - zoom in / zoom out / zoom box not implemented
- how to reproduce
  - click zoom in / zoom out / zoom box icons and a pop up message says they are not implemented yet.
- what expected
  - zoom in / zoom out / zoom box functions.

### ✅ 4. cross-hair cursor feature ✅ **fixed (v0.2.2.1)**
- what is:
  - 需要实现 cross-hair cursor 功能，包括 ON/OFF toggle、mark 标注、数据面板
- what expected
  - View 菜单和工具栏有 Toggle Cross-hair 项（toggle 行为）
  - cursor ON 时显示十字线跟随鼠标，左键点击放置 mark
  - 弹出独立 Mark Data 面板显示 (Index, X, Y1, Y2)
  - 支持 Delete Last、Copy Selected、Export (CSV/TXT)
  - cursor OFF 时清除所有 mark 和面板，每次 ON 都是全新开始
- files changed:
  - `pqwave/ui/mark_panel.py` (新增) — QDialog 数据面板
  - `pqwave/ui/plot_widget.py` — 新增 mark_clicked 信号、_on_mouse_clicked、mark 渲染
  - `pqwave/ui/main_window.py` — 新增 toggle_cross_hair、mark 面板生命周期管理
  - `pqwave/ui/menu_manager.py` — 新增 View 菜单项和工具栏按钮

### ✅ 5. log mode 下坐标数值和 mark 位置错误 ✅ **fixed (v0.2.2.1)**
- what is:
  - 当轴设为对数模式时，status bar 和 mark 面板显示的坐标值是 log10 指数（如 3.0），而非实际线性值（如 1000.0）
  - 对数模式下 mark 的位置不对（mark 渲染到了错误位置）
  - 根本原因：pyqtgraph 在 log mode 下把数据做了 np.log10 变换，viewbox 的 mapSceneToView 返回的是 log 空间坐标（指数值），不是线性值
- how to reproduce:
  - 打开 tests/bridge.raw，add v(r1) 到 Y1
  - 将 Y1 设为 log mode，将 X 设为 log mode
  - 移动鼠标查看 status bar 坐标值（显示指数而非实际值）
  - 在 cross-hair 模式下点击放置 mark（mark 位置偏移）
- what expected:
  - status bar 和 Mark Data 面板始终显示线性空间值（如 1000.0 而非 3.0）
  - mark 在绘图区的视觉位置必须正确对应点击位置
- root cause:
  - pyqtgraph 的 mapSceneToView 在 log mode 下返回的是 log10 指数值，不是线性值
  - PlotWidget._on_axis_log_mode_changed 回调只发射信号，没有更新本地 _x_log_mode 等标志，导致 log mode 切换时标志不同步
  - mark 渲染用到了 plotItem.addItem(ScatterPlotItem)，plotItem 内部是 viewbox 坐标系。如果传入线性值而非 viewbox 坐标，mark 就会偏移到画面外
- fix:
  - plot_widget.py: _on_axis_log_mode_changed 中根据 orientation 更新 _x_log_mode/_y1_log_mode/_y2_log_mode 标志
  - plot_widget.py: _on_mouse_moved 中用 viewbox 坐标设置 cross-hair，用 10^x 转换后的线性值发射 mouse_moved 信号
  - plot_widget.py: _on_mouse_clicked 中用 viewbox 坐标添加到 mark 渲染，用转换后的线性值发射 mark_clicked 信号
  - mark_clicked 信号发射 5 个参数: (x_vb, y1_vb, x_linear, y1_linear, y2_linear)，viewbox 坐标用于 plot 内渲染，线性值用于面板显示
  - main_window.py: _on_mark_clicked 用 viewbox 坐标调用 add_mark_at_position，用线性值调用 mark_panel.add_mark
- element analysis (元素坐标系统排查):

| 元素 | 添加到 | 坐标系 | 状态 |
|------|--------|--------|------|
| title | plotItem.titleLabel | 像素坐标（独立） | OK |
| axis labels | AxisItem | 文本（独立） | OK |
| ticks | AxisItem 自动生成 | 跟随 axis log mode | OK |
| grid | AxisItem 自动生成 | 跟随 axis log mode | OK |
| traces (PlotCurveItem) | viewbox | pyqtgraph 内部做 np.log10 变换 | OK |
| cross-hair vline/hline (InfiniteLine) | plotItem | **必须用 viewbox 坐标** | 已修复 |
| mark (ScatterPlotItem) | plotItem | **必须用 viewbox 坐标** | 已修复 |
| cursor_x/y1/y2_line (InfiniteLine) | plotItem/y2_viewbox | **必须用 viewbox 坐标** | 未改动（非 cross-hair 功能） |
| auto-range (setXRange/setYRange) | viewbox | **必须用 log 空间值** | OK（axis_manager 内部已做 np.log10 转换） |

- 关键原则：凡是添加到 viewbox/plotItem 的可视化元素（InfiniteLine、ScatterPlotItem、PlotCurveItem），必须使用 viewbox 坐标系；凡是显示给用户的数值（status bar、数据面板），必须使用线性空间值

### ✅ 6. mark hover tooltip 显示 index ✅ **fixed (v0.2.2.1)**
- what is:
  - 需要给绘图区的 mark 添加 index 标签（#1, #2...），使其与 Mark Data 面板的 index 一一对应
  - 需求：鼠标移动到 mark 附近时才显示，不干扰波形观察
- what expected:
  - 鼠标靠近 mark 时显示 index 提示文本（如 #1）
  - 鼠标移开后自动隐藏
  - 与 mark 同时生成、同时消亡
- root cause (v1 TypeError):
  - 最初使用 ScatterPlotItem.sigHovered 信号，但 pyqtgraph 0.14.0 的 sigHovered 发射的是 ScatterPlotItem 对象本身，不是 SpotItem 列表
  - 代码中尝试 points[0] 导致 TypeError: 'ScatterPlotItem' object is not subscriptable
  - 此外，v1 使用 viewbox 坐标距离（5% of range）做 hit detection，在 log mode 下完全失真
- fix (v2):
  - 移除 sigHovered 方案，改用 _on_mouse_moved 路径中已有的 viewbox 坐标
  - 在 _check_mark_hover 中使用 mapViewToScene 将 viewbox 坐标转换为 scene（像素）坐标
  - 用 20px 像素半径做距离判断，在任意 zoom level 和 log mode 下均准确
  - 用 pg.TextItem 显示 index 标签，锚点在 mark 左下方，半透明灰色背景
  - 鼠标离开 viewbox 或清除 mark 时同时隐藏/移除 label
- files changed:
  - pqwave/ui/plot_widget.py — 新增 _mark_label, _check_mark_hover, _show_mark_label, _hide_mark_label

### ✅ 7. performance improvement (v0.2.2.1) ✅ **fixed (v0.2.2.1)**)
- apply rules 功能实现规则 in README.md to improvement

### ✅ 8. 改善cross-hair模式下的行为 ✅ **fixed (v0.2.2.2)**
- what is : 在cross-hair cursor模式下，当Mark Data widget 被关闭后，继续mark时，Mark Data widget不再被弹出
- how to reproduce: 启动pqwave，打开pqware/tests/bridge.raw，添加v(r1)到Y1，触发cross-hair至ON状态，在绘图区mark一个点，关闭mark dat widget, 接着mark一个点，mark data widget 不再出现。
- what expected : 当cross-hair保持在ON的状态下时，关闭data widget只是让它不再显示，但不是杀死它。当继续mark时，mark data widget应该弹出，且保留有关闭前的数据，并且把新mark点的坐标数据追加上去。也就是说只有cross-hair被turn off时才能结束一个周期，消除其数据和状态。
- root cause: MarkPanel 没有重写 closeEvent，用户点击窗口关闭按钮时 QDialog 默认行为是 hide()，但 `_open_mark_panel()` 中在 cross-hair ON 时调用 `clear_all_marks()` 清除了所有数据，且 `_on_mark_clicked()` 没有重新显示已隐藏的 panel
- fix:
  - mark_panel.py: 重写 `closeEvent()` 调用 `event.ignore()` 并发射 `window_closed` 信号，只隐藏不销毁
  - main_window.py: `_on_mark_clicked()` 中在添加 mark 前先调用 `mark_panel.show()` 重新显示 panel
  - main_window.py: 新增 `_connect_mark_panel()` 和 `_on_mark_panel_closed()` 处理信号
- files changed:
  - `pqwave/ui/mark_panel.py` — 新增 closeEvent 重写、window_closed 信号
  - `pqwave/ui/main_window.py` — _on_mark_clicked 增加 show()，_connect_mark_panel, _on_mark_panel_closed

### ✅ 9. 改善对字符编码的支持 ✅ **fixed (v0.2.2.1)**
- what is: 某些字符无法正确显示（显示为乱码）
- how to reproduce：启动pqwave，打开tests/SMPS.qraw, 在变量列表（X comb，Y comb）中有些变量的名称中的字符无法识别，如V(?1#inn), I(B2??1), 等。
- what expected ：正确显示字符
- root cause: QSPICE 使用 Latin-1/CP1252 编码写入特殊字符（希腊字母 α β γ 等）。spicelib 自动检测 UTF-8 后逐字节读取 header，多字节 UTF-8 序列被破坏为 U+FFFD 替换字符
- fix:
  - rawfile.py: 新增 `_SPECIAL_CHAR_MAP` 将 QSPICE 原始字节映射到正确的 Unicode 字符
  - rawfile.py: 新增 `_decode_header_bytes()` 先尝试 UTF-8 严格模式，回退 Latin-1 + 特殊字符映射
  - rawfile.py: 新增 `_parse_header_variables()` 直接从原始字节解析变量名，绕过 spicelib 的逐字节 header 读取
  - rawfile.py: `RawFile.parse()` 直接从字节解析变量名，用 spicelib 仅读取二进制数据；建立位置映射正确查找 trace 数据
  - rawfile.py: `get_variable_data()` 使用名称映射查找 spicelib 内部的 trace
- files changed:
  - `pqwave/models/rawfile.py` — _SPECIAL_CHAR_MAP, _decode_header_bytes, _parse_header_variables, preprocess_raw_file, RawFile 重构

### ✅ 10. auto-range doesn't work✅ **fixed** 
- what is: 打开一个raw文件，再打开另一个文件后auto-range不起作用
- how to reproduce: 打开 tests/cdg.raw, 添加"-imag(ac_data)/2/pi/250000*1E12"到Y1，然后Y1设置为log，到这里为止显示是正常的。然后点File --> Open Raw Data，打开tests/bridge.raw, 添加v(r1)到Y1，context menu --> plot option取消log Y的勾选，无论是menu bar 还是 context menu的auto range X，auto range Y1, view all (autorange x/y1/y2) 都不起作用了。但是menu --> Edit --> Setting中的autorange X和autorange Y1有用。
- log 文件 为 ./log.1
- 补充信息：cdg.raw包含的ac_data为复数向量，bridge.raw仅包含实数向量。先打开cdg.raw, 再打开bridge.raw会发生此issue, 但是先打开bridge.raw再打开cdg.raw则不会。因此怀疑是处理了复数向量数据之后转到实数向量时发生。

### ✅ 11. back-annotation not work (v0.2.3)✅ **已完成** 
- what is : back-annotation from pqwave to xschem doesn't work
- how to reproduce
  - cd ~/Apps/pqwave.git/tests/bridge && xschem bridge.sch
  - launch pqwave from xschem menu bar Waves -> External viewer
  - select node "r2" in xschem schematic, send add trace command to pqwave by pressing ALT+G keybind
  - toggle cross-hair cursor in pqwave, drag X cursor, nothing shown in xschem schematic
- what expected : r2 voltage (v(r2)) should be shown somewhere in xschem schematic when drag X cursor in pqwave.

### ✅ 13. X cursor out-of-range shows misleading floater values ✅ **fixed**
- what is: When X cursors are positioned outside the dataset range, floaters in xschem still show interpolated numbers, which can mislead users into thinking data exists at that X value.
- what expected: Show "-" (dash) instead of interpolated values when cursor is outside data range.
- root cause: The sign-change detection in backannotate_cursor_x only triggers when cursor_x is between two data points. When cursor_x is before the first or after the last data point, no sign change occurs, the loop falls through to found:, and the nearest edge point's value is shown.
- fix: Added `cursor_in_range` flag, set to 1 only on sign change or exact match. At `found:`, if flag is 0, all ngspice::ngspice_data values are set to "-" instead of interpolating.
- files changed:
  - `/home/wing/Apps/xschem.git/src/callback.c` — cursor_in_range flag + out-of-range dash logic

###  ✅ 12. bugs found after implementation of back-annotation (v0.2.3) ✅ **fixed**
- xschem complained about undefined Tcl variables (backannotate_sync_draw, backannotate_min_delta, backannotate_last_x)
- all objects other than text such as components, wires, etc. dismiss (not rendered) when doing back-annotation.
- Xa / Xb cursor break autorange. when toggle Xa or Xb cursor before adding any trace to plot widget, autorange doesn't work. Y cursors doesn't cause this problem. And if traces are plot prior to trigger x cursors on there is no this problem either.  
- root causes and fixes:
  1. xschem complained: tclgetboolvar/tclgetdoublevar call dbg(0) when Tcl var doesn't exist. Fixed by adding defaults via `info exists` before first access.
  2. components disappear: backannotate_redraw used draw_single_layer=-2 (text-only). Fixed by removing -2 mode — backannotate_redraw now calls draw() directly (full redraw).
  3. Xa/Xb break autorange: autoRange includes InfiniteLine cursors in bounding calculation, extending range to cursor's default position (0.5). Fixed by filtering out pg.InfiniteLine items from autoRange calculation in auto_range_axis().

### ✅ 13. change X variable doesn't affect in current session ✅ **fixed**
- What is : when change X to another variable, the trace doesn't redraw against new x variable in current session.
- How to reproduce : open tests/bridge.raw, add v(r1) to Y1. change X variable to v(r2), toggle autorange, the trace still in shape of v(r1) vs. time, not v(r1) vs. v(r2). close the window and open tests/bridge.raw again, now the trace is in shape of v(r1) vs. v(r2) which is correct.
- root cause: `_on_add_trace_to_axis()` in main_window.py only updated `state.current_x_var`, the axis label, and auto-ranged X when the user set a new X variable. It never re-evaluated or redrew existing traces with the new X data. Traces retained their original `x_data` copied at creation time. Close-and-reopen worked because `_load_per_file_state()` re-creates all traces from scratch with the current `current_x_var`.
- fix:
  - trace_manager.py: Added `update_x_variable()` method that reads new X data from the raw file, updates each state trace's `x_data`, then redraws all plot items via `setData()` with proper log-transform and downsampling
  - main_window.py: `_on_add_trace_to_axis()` calls `self.trace_manager.update_x_variable(x_var)` after setting the new X variable
- files changed:
  - `pqwave/ui/trace_manager.py` — new `update_x_variable()` method
  - `pqwave/ui/main_window.py` — calls `update_x_variable()` in X variable change handler

### ✅ 14. cannot add trace with name in a form of expressions✅ **fixed**
- what is : when a vector's name is in form of expressions, it cannot be plot by add trace.
- how to reproduce : 1)pqwave --extract tests/bridge.raw "v(ac_p)-v(ac_n)","v(r2)" -ngspice tests/bridge_extract.raw; 2) pqwave tests/bridge_extract.raw --debug; 3) select "v(ac_p)-v(ac_n)" from vector combo; 4) quote v(ac_p)-v(ac_n) inside ""; 5) press Y1 button. a pop up message says failed to add trace as expression "v(ac_p)-v(ac_n)"
- reference tests/bridge_extract.log.

### ✅ 15. `--extract` from AC files stored real data as complex, making traces unplottable ✅ **fixed**
- what is : `--extract` from AC files stored real-valued expressions as complex128 (all imag=0), causing "Can not plot complex data types" when loading and plotting.
- root cause (3 layers):
  1. `raw_converter.py:extract_traces_to_raw()`: when `is_ac=True`, ALL Y data stored as complex128 regardless of actual dtype
  2. `trace_manager.py:add_trace()` and `update_x_variable()`: x_data fetched via `raw_file.get_variable_data()` directly, bypassing the zero-imag fix in `ExprEvaluator.evaluate()`
  3. `PlotCurveItem.setData()` rejects complex data outright
- fix:
  1. `raw_converter.py`: check if any trace actually has non-zero imaginary data; only output complex if truly needed, otherwise store as float
  2. `expression.py`: `evaluate()` already had zero-imag check at line 209-210 (from prior session)
  3. `trace_manager.py`: added `np.iscomplexobj(x_data) and np.all(x_data.imag == 0)` check in both `add_trace()` and `update_x_variable()`
- files changed:
  - `pqwave/models/raw_converter.py` — detect real-only data in AC extraction path
  - `pqwave/ui/trace_manager.py` — zero-imag check for x_data in add_trace() and update_x_variable()
  - `pqwave/models/expression.py` — zero-imag check in evaluate() (prior session)

### ✅ 16. only Y vectors are extracted✅ **fixed** 
- what is : when `--extract` from raw file, only Y vectors are extracted, making ploting a trace vs. un-default x impossible
- how to reproduce : pqwave tests/cdg.raw (default x is "yes"), select "real(ac_data)" and press X button to set X to real(ac_data); add trace "-imag(ac_data)/2/pi/250000*1E12" to Y1; File - Save As to save to tests/cdg_extract.raw. Now pqwave tests/cdg_extract.raw and "real(ac_data)" is not in vectors combo so it's impossible to plot "-imag(ac_data)/2/pi/250000*1E12" vs. "real(ac_data)"
- root cause: `extract_traces_to_raw()` had no way to specify a custom X variable separately from traces metadata; `_run_extract()` always used `variables[0]['name']`; `save_as_raw_data()` didn't pass `state.current_x_var`. Additionally, `RawFile.get_variable_data()` treated variable names like `real(ac_data)` as the `real()` function call on `ac_data` instead of a literal variable lookup.
- fix:
  - `raw_converter.py`: `extract_traces_to_raw()` — added optional `x_var_name` and `x_var_data` params. When provided, use them for X column instead of first trace's x_data.
  - `main.py`: `_run_extract()` — added `-x <varname>` CLI flag parsing. When provided, evaluates custom X expression and passes it to `extract_traces_to_raw()`.
  - `main_window.py`: `save_as_raw_data()` — reads `state.current_x_var` and its data, passes both to `extract_traces_to_raw()`.
  - `rawfile.py`: `get_variable_data()` — exact variable name match before function-name interception (so `real(ac_data)` is found as a literal variable).

### ✅ 17. too small Vector combo width ✅ **fixed**
- what is : the width of Vector combo is too small so vectors with names in form of long expressions is unreadable.
- fix: Increased `vector_combo` width constraints in `control_panel.py` — minimum 250px, maximum 500px (was 200px max), and added `AdjustToContents` size adjust policy for the dropdown popup.
- files changed:
  - `pqwave/ui/control_panel.py` — setMinimumWidth(250), setMaximumWidth(500), setSizeAdjustPolicy(AdjustToContents)

### ✅ 18. `pqwave --help` doesn't show information of `--extract` and `--convert` option ✅ **fixed**

### ✅ 19. cannot add plotted vectors to measurement expr✅ **fixed** 
- what is : when a vector is plotted it cannot be added to measurement expr
- how to reproduce : pqwave ./tests/bridge.raw; nothing happens when click v(r1) in vectors combo

### ✅ 20. meas functions doesn't take expression of vectors as variable✅ **fixed** 
- what is : functions doesn't take expression of vectors as variable
- how to reproduce : pqwave ./tests/bridge.raw, add "avg(v(ac_p)-v(ac_n))" and press RUN, an error message says vector not found : 'v(ac_p)-v(ac_n)'
- what expected : meas functions accept expressions. this is true in Func functions. for example mean(v(ac_p)-v(ac_n)) plot the trace correctly.

### ✅ 21. tip message doesn't show up for last items in Func combo and Measure combo✅ **fixed** 
- how to reproduce : scroll mouse to bottom of the list item in Func combo and Measure combo, there is no tip message showing up.

### ✅ 22. cannot run user-written meas command✅ **fixed** 
- how to reproduce : qpwave ./tests/bridge.raw; write ".meas tran when v(r1)=96" in measurement expr, press RUN button, an error message says "invalid measure expression : '.meas tran when v(r1)=96'"

### ✅ 23. 'From Script' changes backgroud of measurement expr which makes text unreadable.✅ **fixed** 
- how to reproduce : pqwave tests/bridge.raw, then press 'From Script' button, select tests/bridge.meas file, the measurement expr background changes to white and make text unreadable.

### ✅ 24. measurement expr cannot be clear after running from a Script✅ **fixed** 
- how to reproduce : pqwave tests/bridge.raw, then press 'From Script' button, select tests/bridge.meas file, press 'RUN' button, then the text in measurement expr cannot be clear (cannot be deleted)

### ✅ 25. cannot add plotted vectors to Add Trace expr ✅ **fixed**
- what is : when a vector is plotted it cannot be added to Add Trace expr
- how to reproduce : pqwave ./tests/bridge.raw; add v(r1) to Y1, select mean(x) from Func combo, v(r1) cannot be put to Add Trace expr to coine mean(v(r1)). 
- similiar to #19 but happens to Add Trace expr.

###  ✅ 26. meas script runs into error when script file path is provided by key-in✅ **fixed** 
- what is : when user key-in a meas script path and press 'RUN' button it leads to a invalid expression error.
- how to reproduce : key-in '/home/wing/Apps/pqwave.git/tests/bridge.meas' in measurement expr then press 'RUN' button leads to error : Invalid expression : '/home/wing/Apps/pqwave.git/tests/bridge.meas'  
- what expected: user can run a meas script by select it from a file selector, or by key-in its path. further more, user can edit the path freely before press 'RUN' no matter it is selected from file selector or by key-in. 

###  ✅ 27. improve tooltip message for measurement expr✅ **fixed**  
- what is : measurement tooltip message says 'Enter a measurement expression ...'
- what expected : measurement tooltip message says 'Enter a measurement expression..., or a script path ....'

###  ✅ 28. fft() failed to add trace for expression ✅ **fixed**  
- how to reproduce : pqwave tests/bridge.raw; click fft(x) from func combo; click v(ac_p) from vectors combo to coine fft(v(ac_p)); press Y1, an error pop up says Failed to add trace for expression: fft(v(ac_p))
- log file in ./tests/bridge.log

### ✅  29. unexpected panel resize behavior in second split ✅ **fixed**    
- in second split, no matter horizon or vertical, the as-split panels are compressed to near single line and the left unsplit panel claims all the space. 
- how to reproduce : ctrl+shift+e to split to 2x1 layout, click the upper one to set it activated, ctrl+shift+o to split it, now the upper two panels are compressed to near a single line height and the left-unsplit lower panel resizes to almost all the space- what expected: expect a 1x2 + 1x1 stack, with equal height.

### ✅   30. runtime error when split panel after a panel was closed ✅ **fixed**     
- close a panel following by a split panel action leads to runtime error. 
- how to reproduce : ctrl+shift+e to split to 2 panels, ctrl+shift+w to close one panel, ctrl+shift+e or ctrl+shift+o to split panel agaain leads to a RuntimeError: wrapped C/C++ object of type PlotWidget has been deleted.
- refer to log file : ./tests/bridge.log

### ✅31. Y tick number doesn't indicate 'db' in db presentation✅ **fixed**     
- what is : in db presentation, Y tick number doesn't have a 'db' sufix which make it hard to distinct which presentation (linear or db) is in used. 
- what expected : in db presentation Y tick numbers have a 'db' suffix which coine the tick numbers in form of something like -10db, 0db, 10db, 20db, .......(number here is for example purpose)

### ✅32. tick number is wrong when X axis is in log mode in a fft() plot ✅ **fixed**     
- what is : in a fft() plot when set X asis (frequency) to log mode the tick number is wrong (not transfered correctly)
- how to reproduce : pqwave tests/bridge.raw; plot fft(v(ac_p)) and the X axis (in linear mode) shows a range of around 0~4000000Hz; set X axis to log mode and now the tick range shows 10^0 ~ 10^4000000 which suggests the exponents are taken directly from the linear numbers. Now autorange X axis and the range turns to about 10^-6 to 10^-1. 

### ✅33. pqwave stop response when set X axis to log mode in a fft() plot ✅ **fixed**     
    
- what is : setting X asis (frequency) to log mode in a fft() plot causes pqwave stoping response 
- how to reproduce : pqwave tests/bridge.raw; select fft(x) from func combo, select v(ac_p) from vectors combo to coine fft(v(ac_p)) and press 'Y1' button; ctrl+shift+x to set x axis to log mode, then a message widget pop up says 'python not response, you can wait or force quit'. in the meanwhile btop shows pqwave uses 4G memory and 100% cpu. 
### ✅34. overflow warning when open some raw file✅ **DON'T need a fix**   
- what is : pqwave tests/bridge.raw invokes overflow warning but pqwave tests/cdg.raw doesn't.
- log in ./tests/bridge.log

### 35. pqwave doesn't take system theme from time to time 
- what is : sometimes when launch pqwave it doesn't take system theme.
- how to re-produce : rm tests/bridge.json && pqwave tests/bridgge.raw, the window title bar background is white, and there are no minimize, maximize and close buttons.

### ✅36. frequency data is not saved when save fft plot to a raw file. ✅ **fixed**
- what is : in a fft plot when save trace data from File - Save As menu, the x variable (frequency) is not included in result raw file.
- how to reproduce : pqwave tests/bridge.raw, plot fft(v(ac_p)) to Y1, File - Save As to bridge_fft.raw. check bridge_fft.raw in ngspice the raw file include fft(v(ac_p)) and time but not frequency.
- fix : In `save_as_raw_data()`, detect FFT traces and set x_var to "frequency" with no x_var_data, so `extract_traces_to_raw` uses the trace's frequency bins as the X variable instead of the original file's time vector.

### ✅37. set log Y in fft plot should do nothing. ✅ **fixed**
- what is : set Y axis to log mode (e.g. by ctrl+shift+y) leads to Y axis tick number change. the tick numbers cluster together make them unreadable.
- what expected : do nothing when user set Y to log mode in fft plot. pop up a message would be metter. (in fft plot Y is already in log (dB)).
- fix : In `_toggle_log_axis()`, detect FFT traces on the target Y axis and prevent enabling log mode, showing an informational message that FFT is already in dB.

### ✅38. tick numbers clusters in fft plot when set x axis to log mode✅ **fixed** 
- what is : when set X axes to log mode in a fft plot the tick number cluster and make them unreadable.
- how to re-produce : rm tests/bridge.json && pqwave tests/bridgge.raw, plot fft(v(ac_p)), ctrl+shit+x to set x axis to log mode. the x tick numbers cluster at near x=0.

### ✅39. formatted message not rendered correctly in Help - Keybindings menu✅ **fixed** 
- what is : formatted message is rendered in plain text in Help - Keybindings menu : To customise, edit the file: <code> .....Keybindings.json</code> Format: &#123;

### ✅40. There is no default keybindings.json in place.✅ **fixed**  
- what is : there is no default keybindings.json in current codebase
- what expected : user can customise keybindings by editing ~/.pqwave/keybindings.json. in case of problem, they may want to fallback to default settings, there should be a default keybindings.json file for reference or just copy from.

### ✅41. Improve FFT Settings options and UI layout✅ **fixed**  
- what is :
  - there is no 'Reset' option in FFT settings
  - 'DC Removal' is not set as default 
  - there is room for UI layout improvement
- what expected : 
  - there is a 'Reset' option to reset to default values.
  - 'DC Removal' is default value (box checked by default)
  - UI layout as below:     
      Window: combo    FFT Size: combo      
      X range: combo   Representation: combo    
      Binomial Smooth: combo   DC Removal  Reset button     
                       
### ✅42. not all FFT options reset to default values at a single reset action✅ **fixed**  
- what is : when press 'Reset' button only one option is reset so user have to press Reset button multiple times to reset all options.
- what expected : a single press reset them all.

###✅43. keybindings and Edit > Settings of setting log mode doesn't synchronize✅ **fixed**  
- what is : when trigger log mode by keybindings ctrl+shift+X/Y/Z, the check boxes in Edit > Settings > Axes Settings are not checked / unchecked accordingly
- what expected : these two trigger methods synchronize to identical status.

### ✅44. no way to tell which plot widget is the active one in multiple plot widget mode.✅ **fixed**  
- what is : in multiple plot widget mode, a plot widget is set to active by click it. but when it is clicked there is no indicate to tell that so it's difficult for the user to know which one is active.

### ~~45. cannot trigger statistic analysis context menu by right click~~  

### ✅46. trace statistics analysis result needs improvement✅ **fixed**  
- what is : trace statistics analysis result dialog covers the plot view and cannot move independently from main window.
- what expect : can move result dialog (or widget, whatever) from the plot view region so user can check the numbers and the waveforms accordingly.

### ✅47. trace statistics analysis result needs improvement for multiple traces analysis.✅ **fixed**   
- what is : when select multiple traces (ctrl+click) and Analyze > Compute Trace Statistics, the result dialogs overlap and user has to close the most-front one to see the next underneath.
- wht expected : user can see results of all selected traces at the same time.

### ✅48. no x axis range infomation in power analysis result.✅ **fixed**   
- what is : there is no x axis range information in power analysis result
- what expect : provide x axis range of current zoom in power analysis result, like what it does in trace statistics analysis result.

### ✅49. font color in mean row make text hard to reads✅ **fixed**    
- what is : in power analysis result, the bottom row (mean numbers) of per-cycle breakdown has a font color in blue, makes it hard to read in dark mode.
- what expected : easy to read font colors for both light and dark mode. (maybe green?)

### ✅50. inconvenient data export in power analysis✅ **fixed**   
- what is : in power analysis result user has to click copy tsv to copy data and paste it in some kind of spreadsheet applications.
- what expected : export data to a csv directly by a single click. just like what it does in mark data widget.

### ✅51. there is no keybind to trigger trace statistic analysis✅ **fixed**  
- what is : currently Analyze > Trace Statistics menu item is the only way to execute a trace statistic analysis.
- what expected : provide a keybind Ctrl+Shift+S to execute trace statistic analysis. register the keybind to default keybindings.json and Help > Keybindings menu item. 

### ✅52. there is no keybind to trigger power analysis✅ **fixed**   
- what is : currently Analyze > Power Analysis menu item is the only way to execute a trace statistic analysis.
- what expected : provide a keybind Ctrl+Shift+P to execute power analysis. register the keybind to default keybindings.json and Help > Keybindings menu item.

### ✅53. cannot open vcd file✅ **fixed**   
- what is : File > Open VCD File doesn't open a vcd file
- how to re-produce : launch pqwave, File > Open VCD File, select tests/dump.vcd, there is no data load, and terminal output error message.
- error message see ./tests/dump.log

### ✅54. vcd variables are not list up in vectors combo✅ **fixed**  
- what is : when open a standalone vcd file (without any raw in prior), vcd variables are not list up in vectors combo.
- how to re-produce : launch pqwave, File > Open VCD File, select tests/dump.vcd, it sas vcd variables are loaded. but the vectors combo is empty.

### ✅55. failed to add vcd trace in vcd-alone mode✅ **fixed**  
- what is : pqwave failed to plot a vcd trace in vcd-alone mode.
- how to re-produce : launch pqwave, open tests/dump.vcd, select 'adc_core_digital_tb.conv_finished_osr_out' then press 'Y1' button, an error message pop up and says failed to add trace for expression : adc_core_digital_tb.conv_finished_osr_out.
- terminal output : 'DEBUG: add_trace called: expression=adc_core_digital_tb.conv_finished_osr_out, x_var_name=time, y_axis=AxisAssignment.Y1
WARNING: No raw file opened'

### ✅56. ValueError when plot vcd trace in vcd-alone mode✅ **fixed**  
- what is : when plot a vcd trace in vcd-alone mode, trace_manager raises a ValueError.
- how to re-produce : see ./tests/ValueError.log

### ✅57. Attribute Error when plot vcd trace in vcd-alone mode✅ **fixed**  
- what is : when plot a vcd trace in vcd-alone mode, AttributeError raise.
- how to re-produce : see ./tests/AttributeError.log

### ✅58. failed to plot vcd traces in vcd-alone mode✅ **fixed**   
- what is : pqwave complains failed to add trace for expression.
- see ./tests/vcd_signal_not_found.log

### ✅59. incorrect digital wave rendering✅ **fixed**  
- what is : digital traces are not rendered in compact stack (gtkwave-like) fashion
- how to re-produce : (1)launch pqwave by venv/bin/pqwave; (2)File > Open VCD File and select tests/mixed_signa.vcd; (3)select '[VCD] dig_clk' from Vectors combo; (4)press 'Y1' button. '[VCD] dig_clk' trace is not rendering visibly in plot widget.
- what expected : the trace should poses a couple of 0->1 cycles in the time range from 0 to 8*10^-6 s.

### ✅60. X axis (time) not alligned in mixed_signal simulation data✅ **fixed**  
- what is : X axis (time) not alligned correctly in digital and analog panel in a mixed signal simulation dataset.
- how to reproduce : (1)pqwave tests/mixed_signal.raw; (2)File > Load VCD then select tests/mixed_signal.vcd;(3)Ctrl+Shift+E to split plot panel; (4) plot vcd variables in upper panel, analog variables in lower panel, the X axis (time) is not alligned correctly. see tests/mixed_signal_time_alignment.png
- some findings / thoughts : (1) digital and analog plot doesn't share a time range (0-16 us in digital and 0- 10 in analog), autorange X axis or autorange all (zoom to fit) doesn't change this. (2) analog plot shows left and right ticks but digital plot doesn't. even they share a time range how to arrange X axes in pixel precision? Maybe a column intentation in both left and right tick positions in digital plot?   

### ✅61. not using established vcd parser✅ **fixed** 
- what is : pqwave is using a self-written vcd parser
- what expected : use an established and maintained parser - vcdvcd 

### ✅62. Y2 in digital plot confuse user✅ **fixed**  
- what is : Y2 is enabled by default in all plot panels. but if digital traces are plot against multiple Y axes it confuse user.
- what expected : digital traces represent time-series events and they should use single Y axis.

### ✅63. Y tick values in digital plot confuse user✅ **fixed**  
- what is : Y tick values (-1, 0, 1, 2, ..., n) in digital plot confuse user. it's hard to tell what does these number mean.
- what expected : digital traces represent time-series events and they don't have a physical dimension unit. digital plot should not show Y tick values unless in analog view of trace.

### ✅64. X label shown as 'X' in pure vcd plot✅ **fixed**  
- what is : in pure vcd plot X axis label is named 'X'
- what expected : in vcd plot X axis should be named 'time' by default which is the case in a mixed vcd plot.

### ✅65. cannot add multiple vcd traces at a time in pure vcd plots✅ **fixed**  
- what is : in pure vcd plots adding multiple vcd traces to Add Trace expr then pressing 'Y1' button raises an error : Failed to add trace to expression.
- what expected : can add multiple tarces in a time which is the case in both analog plots and mixed vcd plots.

### ✅66. Ctrl+D doesn't work in vcd plot✅ **fixed**   
- what is : Ctrl+D doesn't trigger analog representation of digital tarce.
- how to re-produce : (1) launch pqwave; (2) File > Open VCD File and open tests/mixed_singal.vcd; (3) select 'dig_clk' from Vectors combo then press 'Y1' button; (4) left click dig_clk legend to select trace (turns to bold); (5) Ctrl+D but nothing happens
- what expected : Ctrl+D triggers 'dig_clk' to its analog representation.

### ✅67. Ctrl+Shift+E is broken✅ **fixed**   
- what is : when pres Ctrl+Shift+E an error raises says QAction::event: Ambiguous shortcut overload: Ctrl+Shift+E
- what expected : Ctrl+Shift+E should split plot panel vertically

### ✅68. inconsistent analog representation of same vcd trace in pure vcd plot and mixed vcd plot✅ **fixed**  
- what is : analog representation of vcd trace in a pure vcd plot shows a visible slop of transition from minimum to maximum voltage of the trace but no visible slop in mixed vcd plot. in mixed vcd plot the analog representation of a trace looks like a step transition.

### ✅69. cannot edit property of bus trace✅ **fixed**   
- what is : when edit property of a bus trace an AttributeError raises.
- how to re-produce : (1) launch pqwave; (2) File > Open VCD File to open tests/mixed_signal.vcd; (3) Add traces q1~q4; (4) Ctrl+click to multi-select q1~q4; (5) Ctrl+B to group q1~q4 as a bus where it is named to bus5 automatically; (6) Edit > Edit Trace Properties, when edit properties of bus5 an error raises :Traceback (most recent call last):
  File "/home/wing/Apps/pqwave.git/pqwave/ui/main_window.py", line 1363, in <lambda>
    apply_btn.clicked.connect(lambda: self._apply_trace_properties(list_widget.currentRow(), list_widget))
                                      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wing/Apps/pqwave.git/pqwave/ui/main_window.py", line 1453, in _apply_trace_properties
    plot_item.setPen(new_pen)
    ^^^^^^^^^^^^^^^^
AttributeError: 'DigitalStepCurveItem' object has no attribute 'setPen'. Did you mean: 'setPos'?

### ✅70. bus trace invisible ✅ **fixed**  
- what is : bus trace in digital plot is solid-filled with color and invisible. see tests/bus_invisible.png

### ✅71. property edition only applys to one line of bus trace✅ **fixed**   
- what is : when setting properties (color, line width) for a bus trace it only applys to one line of the trace.
- what expected : bus trace is represented by two lines and properties should apply to both lines.

### ✅72. pqwave stop response when open ltspice raw file✅ **fixed**   
- what is : when open ltspice raw file through command line or File > Open Raw File pqwave stop response. btop shows pqwave uses 100% CPU and 250Mb memory.
- how to re-produce : pqwave tests/bridge_ltspice.raw --debug

### ✅73. pqwave doesn't save state when close window in pure vcd case.✅ **fixed** 
- what is : when close pqwave window of a pure vcd case it doesn't save state (no .json state file generated). user has to save current state through File > Save Current State.
- what expected : save state of pure vcd case too when close window.

### ✅74. pqwave doesn't recover stored state of a pure vcd.✅ **fixed** 
- what is : when open a vcd file, the stored state is not recovered
- how to reproduce : (1)pqwave tests/mixed_signal.vcd; (2)choose dig_clk from vectors combo then press "Y1"; (3) File > Save Current State; (4) close pqwave window; (5) pqwave tests/mixed_signal.vcd, the plot widget is empty, X / Y1 scale shows initial state.

### ✅75. X/Y data is saved to state json for vcd plot.✅ **fixed**  
- what is : when save state of a pure vcd or mixed vcd case the X/Y data of vcd (vcd_time / vcd_value) is also saved. when the plot consists of many digital traces it makes state json bulky.
- what expected : save trace name (trace entry) only like what is done in raw case.

### ✅76. selected vectors by checkbox are not emitted ✅ **fixed**  
- what is : when selecting vectors by checking checkbox, then close popup, the selected items are not emitted to Add Trace expr. (for reference : double click works.)

### ✅77. Ctrl+click and Shift+click vector names doesn't make vectors selected✅ **fixed**   
- what is : selecting vectors only works through checkbox which makes Ctrl+click and Shift+click vector names doesn't select vectors.
- what expected : Ctrl+click names and Shift+click names make them checked.

### ✅78. need help doc for vector selection✅ **fixed**  
- what is : there is no help doc for vector selection
- what expected : a Help > Select Vectors item to document how the select vectors widget works.

### ✅79. AttributeError raises when launch pqwave✅ **fixed**  
- what is : when launch pqwave from command line AttributeError raises. Error message : 
Traceback (most recent call last):
  File "/home/wing/.local/bin/pqwave", line 8, in <module>                              sys.exit(main())
             ~~~~^^
  File "/home/wing/Apps/pqwave.git/pqwave/main.py", line 441, in main
    window = MainWindow(xschem_ba_port=args.xschem_ba_port)
  File "/home/wing/Apps/pqwave.git/pqwave/ui/main_window.py", line 119, in __init__
    self._setup_ui()
    ~~~~~~~~~~~~~~^^
  File "/home/wing/Apps/pqwave.git/pqwave/ui/main_window.py", line 154, in _setup_ui
    callbacks = self._create_menu_callbacks()
  File "/home/wing/Apps/pqwave.git/pqwave/ui/main_window.py", line 206, in _create_menu_callbacks                                                                           'compute_trace_stats': self._compute_trace_stats,                                                          ^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'MainWindow' object has no attribute '_compute_trace_stats'

### ✅80. autorange when trigger analog view or vise versa✅ **fixed**   
- what is : when transfer a trace from digital to analog representation or vise versa the trace is out of plot widget
- what expected : autorange when trigger digital/analog representation of trace to keep it fit to plot widget.

### ✅81. Save As Raw Data is not disable in multifile session✅ **fixed**   
- what is : in multifile session when user trys to Save As Raw Data pqwave doesn't stop it.
- what expected : Disabled when len(source_files) > 1. Tooltip: "Save as data file is only available for single-file sessions."

### ✅82. No Save As VCD Data option for pure vcd case✅ **fixed**     
- what is : there is no option to save as vcd file in pure vcd case
- what expected : 
  - change File > Save As Raw to File > Save As Data File
  - add VCD to target format list
  - in pure vcd case set vcd as default target format

### ✅83. 'Open File' toolbar item tip message improvement✅ **fixed**  
- what is : the message says 'Open .raw or .vcd file'
- what expected : the message says 'Open data (.raw/.qraw/.vcd) or project (.json) file'

### ✅84. File > Save Project and File > Save Project As improvement✅ **fixed**  
- what is : in save file widget the show file type combo only indicate 'Project Files' but 'project' or 'project file' is not a common concept in the field of spice wave viewing and users may not be aware that a json file is to be saved.
- what expected : the show file type combo indicate 'Project Files (.json)' and/or file name input field includes .json automatically.

### ✅ 85. add vcd support to pqwave --extract ✅ **fixed**
- what is : `pqwave --extract` command line doesn't support vcd
- what expected : `pqwave --extract` supports vcd input, vcd or ngspice raw output 

### ✅ 86. render bus signal as-is ✅ **fixed**
- what is : bus signal is rendered as a single digital trace with multiple pulse height 
- how to re-produce : qpwave tests/dump.vcd; select adc_core_digital_tb.result_out[15:0] from vector combo then press Y1 button.
- what expected : render bus signal as-is (a bus trace)

### ✅ 87. can't read a vector name when it extend beyond vector combo width ✅ **fixed**
- what is : can't read a long vector name when it extends beyond vector combo widht which leads to difficulty in vector section.
- how to re-produce : pqwave tests/dump.vcd, then expand vector comb, can't tell which vector is which because their names are too long and compressed.
- what expected: a vector full-name tip on mouse hover.

### ✅ 88. tcp port conflict when launch second pqwave session from terminal ✅ **fixed**
- what is : when run a second pqwave session from terminal an error raises and syas ERROR:Failed to start Xschem server on port 2026: [Errno 98] Address already in use.
- what expected : warn the user and ask if launch without tcp

### ✅ 89. missed time vector when extract vcd trace to raw file from command line ✅ **fixed**
- what is : when extract trace from vcd to raw file from command line, time is not included in the output raw file.
- what expected : when extract trace from vcd to raw file from command line include time in the output raw file.

### ✅ 90. pqwave doesn't render vcd trace correctly ✅ **fixed**
- what is : pqwave doesn't read vcd data correctly
- how to reproduce : (1) pqwave tests/dump.vcd, (2) plot 'adc_core_digital_tb.result_out[15:0]', it shows time range is [0, 2600 us] and the trace consists of 4 events
- what expected : time range should be [0, 2810 us], the trace consists of 5 events among which the last event has a value of 3cc0 within time range [2600us, 2810us].

### ✅ 91. only one line of bus trace is hidden ✅ **fixed**
- what is : when trigger the visibility of a bus trace by clicking its legend only one of the two lines is hidden.
- what expected : hide the whole trace

### ✅ 92. cannot split plot panel in vcd case ✅ **fixed**
- what is : Ctrl+Shift+E/Ctrl+Shift+O doesn't split plot panel in vcd case
- how to re-produce : tests/split_vcd.log

###  ✅ 93. vcd trace render improvement✅ **fixed** 
- what is : when plot too few or too many vcd traces the render looks awful - trace height is too large or too small.
- what expected : fix trace height to proper value with respect to pixel? plus : user can set trace height to x1, x2 through Edit > Edit Trace Properties

### ✅ 94. vcd trace doesn't scale ✅ **fixed** 
- what is : when set vcd trace height to x2.0 it doesn't stretch but translate to a x2.0 Y position
- what expected : set trace height to x2.0 should hold its position, stretch to double height and keep its width.

### ✅ 95. moveable edit trace properties widget ✅ **fixed**
- wht is : edit trace properties dialog attach to main window and cover the visible plot widget
- what expected : a moveable edit trace properties widget which can be moved independently to the main window.

### ✅ 96. range is broken when split plot panel ✅ **fixed**
- what is : when split plot panel the range of old panel is broken.
- how to reproduce : pqwave tests/bridge.raw, plot v(r1), when split plot panel through Ctrl+Shift+E the x axis (time) of the old panel (which contains v(r1) trace) is stretched to 0~1000 (x0.001)
- what expected : keep the old panel range as-is when split panel.

