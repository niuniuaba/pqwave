## TODO.md
###   v0.2.5 enhance analysis capability
- ✅ 18.1 measurement (.meas / .measure)✅ **已完成** 
  - 在 vector combo, func combo那一行插入一个Measure comb，里面封装好spice中的.meas命令的函数（上升/下降时间、过冲、下冲、周期、频率、占空比、RMS、THD、SINAD、等），具体函数请参考./meas.md；Measure combo的行为类似Func combo的行为：按函数名alphabet排列，提供显示函数描述的tip messages，Ctrl+left click多选，Shit+left click连续选择，等。
  - 在Add Trace那一行的下方插入一个 Measurement expr，行为类似Add Trace expr，当用户从Measure combo选择后把被选择函数填入Measurement expr，同时用户可以在其中进行表达式编辑。注意
  - run a .meas script
  - built-in meas functions (上升/下降时间、过冲/下冲、周期、频率、占空比、RMS、THD、SINAD 等)
- 18.2 Compute the average or RMS of a trace.
  - integrate a trace to obtain the average and RMS value over the displayed region
  - First zoom the waveform to the region of interest, then move the mouse to the label of the trace, hold down the control key and left mouse click 
  - RMS average is reported only if the physical units of the integrated quantity is volts or amps to avoid confusing people that need the average when power is integrated.
- 18.3 FFT
- 18.4 功率分析（瞬态、平均）
- 18.5 power supply - specific analysis 
- 18.6 multiple plot panel
- 18.7 数字波形（时序图风格）

###   v0.2.4 feature add 
17. add some features
- ✅ 17.1 save only data of current traces to a raw file.✅ **已完成**
  - only save the data of current traces. the result is a subset of original raw which is useful to save interested data after exploration of a large dataset.
  - support qspiec .qraw, ltspice .raw, ngspice .raw
  - a "File - Save as" item and a toolbar entry.
- ✅ 17.2 a command line to do the same as 17.1✅ **已完成** 
  - something like `pqwave --extract <inputfile> <expr1[,expr2[,...]]> -ngspice|-ltspice|-qspice <outputfile>`  
- ✅ 17.3 a command line to convert raw files.✅ **已完成** 
  - don't extract subset of data but just convert raw type.
  - `pqwave --convert <inputfile> -ngspice|-ltspice|-qspice <outputfile>`
  - the same feature is already available in 'File - Convert Raw Data'.  
- ✅ 17.4 add a 'select trace' mechanism ✅ **已完成**
  - left click on legend: select trace (deselect others)
  - ctrl+left click: toggle multi-select
  - clicking the sole selected trace toggles its visibility (LTspice-like)
  - selected traces shown with bold legend text
  - selection state persisted in per-file state JSON
- ✅ 17.5 fix save-as_raw_data keybinding warning ✅ **已完成**
  - Added Ctrl+Shift+S keybinding for Save As Raw Data action
  - Fixed "WARNING: Unknown action 'save-as_raw_data'" on startup

###   v0.2.4 enhance functions and expressions
- ✅ 16.1 support more functions and binary operators✅ **已完成**
  - to support functions and binary operators listed in ./expr.md 
- ✅ 16.2 Add a Functions combo and help doc✅ **已完成**
  - Add a Functions combo to list up supported functions and binary operators
  - similar to Vectors combo, when clicked add the function / operator into Add Trace expr, waiting for user edition
  - when a function or binary operator is selected (or mouse approximat that item) show a tip of description (what it is)
  - Add a Help - Functions menu item to show function and operator description.
  - 如果添加的是一个需要变量的函数，当其被加到Add Trace expr之后，光标停留在该函数的()内，等待用户编辑，此时如果用户从Vectors combo内选择一个向量，则把该向量添加到前述函数的()内，因为以一个向量作为一个函数的变量是正常的操作逻辑。

###  ✅ v0.2.3 keybindings ✅ **已完成**
15.  keybindings ✅ **已完成**  
- 提供一套快捷键系统，目前需要实现的keybindings记录在./keybindings.md，今后可继续扩展
- 提供一个用户可以设定keybindings的方法
- 提供Help - Keybindings菜单项，为用户提示默认的keybindings列表以及定制化设定的方法

###   v0.2.3   
14.  ✅ attach states to plot✅ **已完成**  
- 提供一个机制，将当前state与当前的plot绑定，这样当用户下次打开同一个raw时自动加载绑定的state，这样用户不用重复去调整各种参数设置。
- 默认将状态json文件保存到与打开的raw文件相同的目录下，文件名与raw文件名相同。比如打开name.raw文件，则保存name.json文件。
- 当前窗口关闭时自动保存状态json文件，同时增加一个File - Save Current State菜单项，用户可以在任意时候保存状态。
- 状态文件不要保存x_data，对于大的raw文件来说数据量太庞大了。
- 不再保存stat.json到$HOME/.pqwave，也不要再从该位置读取stat.json，防止冲突。

###  ✅ v0.2.3 independent vertical (x) and horizon (y) cursors✅ **已完成**  
13. independent horizon (y) and vertical (x) cursors ✅ **已完成**  
- 与cross-hair cursor分离，可以独立使用
- 支持两个x cursors，两个y cursor
- 用户可以使用一个x/y cursor，也可以使用两个
- 当使用两个x cursor时，在status bar显示delta x 的值
- 当使用两个y cursor时，在status bar显示 delta y1和delta y2的值
- 与cross-hair的区别：cross-hair用于在trace上打点并获取该点的数值，x/y cursor用于拖动，显示delta值，并为后续的back-anotate做准备（TODO No. 12）。

###  ✅ v0.2.3 introduce new feature : back-anotate from pqwave to xschem✅ **已完成**   
12. back-anotate to xschem schematic✅ **已完成**  
- 当用户使用cross-hair cursor扫过某个或多个trace时，将数据点发送给xschem，xschem在电路图上这些trace对应的node处显示接收到的数值。
- live backannotation: You can place / move a (vertical) cursor in the  and see voltages and currents annotated in the schematic.
- 可能需要参考xschem的graph的实现方法。./xschem_graph.md; ../xschem.git/src

### ✅ v0.2.3 introduce new feature : communicate with external eda tools. ✅ **已完成**   
11. communicate with xschem ✅ **已完成**
- open pqwave as external wave viewer from xschem 
  - **实现**: 在 xschemrc 中添加 pqwave 到 `sim(spicewave)` 数组，支持 GAW 式 TCP 套接字通信，无需修改 xschem 源代码
- receive node_name signal from xschem schematic then plot the trace.
  - **实现**: `pqwave/communication/xschem_server.py` TCP 服务器（默认端口 2026），解析 `table_set filename.raw` 和 `copyvar v(node) sel #color` 命令
  - **实现**: `pqwave/communication/command_handler.py` 命令处理器，将 TCP 命令转换为 Qt 信号
  - **实现**: `pqwave/communication/window_registry.py` 窗口注册表，管理多窗口和客户端映射
  - **实现**: 单实例服务器模式，后续 pqwave 实例将命令转发到已有服务器
  - **配置**: 文档 `docs/xschem_integration.md` 提供详细配置说明
- back-anotate data points from pqwave to xschem schematic
  - **实现**: JSON 扩展协议支持 `get_data_point` 命令查询特定 X 坐标的数据点
  - **实现**: 复数数据处理（幅度/相位、实部/虚部格式）
  - **示例**: xschemrc 中提供 Tcl 过程示例，用于查询和显示波形数据
  - **测试**: `pqwave/tests/test_xschem_server.py` 7 项测试全部通过

### ✅ v0.2.2 further performance improvement ✅ **已完成**
10. reduce high cpu use for large files
- simple benchmark from top information (read raw, add trace, move, span, zoom, etc)
  - tests/rc_100M.raw : CPU ~10% / xschem, 120-140 % pqwave → **now ~5-10%**
- **Optimizations applied**:
  - (a) **PlotDataItem → PlotCurveItem**: Pre-downsample to 1600pts at trace creation (peak method). Eliminates per-paint autoDownsample, updateItems, dataBounds nanmin/nanmax. **18x faster**
  - (b) **_StaticCurveItem**: Subclass that permanently caches boundingRect and skips viewTransformChanged invalidation. **22% faster**
  - (c) **Segmented line mode**: `setSegmentedLineMode('on')` uses drawLines instead of drawPath. Reduces QPainter overhead
  - (d) **ThrottledPlotDataItem**: Debounced viewRangeChanged at 50ms (already existed, kept)
  - (e) **ViewBox translateBy/scaleBy throttle**: Coalesce rapid pan/zoom calls into single paint every 30ms. **2.6x fewer paints** during real mouse drag
  - (f) **Remove debug logging**: Strip logger.debug from _on_mouse_moved, LogAxisItem.tickStrings/setLogMode
  - (g) **BoundingRectViewportUpdate**: Reduce repaint region size
- **Results** (22 traces, 636K pts each, 200 translateBy events):
  - Before: 0.703s (3.5ms/event, ~700ms total for 200 events)
  - After: 0.009s (0.045ms/event, **78x faster** in tight loop)
  - Realistic timing (100 events over 2s): 38 paints vs 100 → **15.9 Hz vs 50 Hz**

### ✅ v0.2.2.2 float32 migration and memory optimization ✅ **已完成**
9. further performance improvement
- still heavy memory use for large file and potential memory leak.
- **根本原因**: 三处内存浪费 — (1) spicelib 解析后保留完整数据副本 (2) Dataset.Variable 通过 get_variable_data() 为每个变量创建第三份数组 (3) 所有数据用 float64 存储，内存翻倍
- **修复 (1)**: parse() 结束后设置 `self.raw_data = None`，释放 spicelib 内部缓存 (~2.4 GB for rc_ltspice.raw)
- **修复 (2)**: Variable 直接引用 memmap/column_stack 矩阵的列 (numpy view, zero-copy)，所有 Variable 共享同一底层内存
- **修复 (3)**: 所有实数数据从 float64 → float32，复数数据从 complex128 → complex64。LTspice 文件本就 float32 存储；xschem 也提供 float 选项
- **LRU 缓存**: get_variable_data() 增加 (dataset_idx, var_name) 缓存，重复调用返回同一 view 对象
- **效果** (rc_100M.raw, 20 vars, 1.3M pts): RSS 从理论 ~7.2 GB → ~1.2 GB (~6× 减少)。rc_500M.raw: 2.15x 文件比。cdg_16M.raw (AC): 7.06x 文件比 (小文件受 Python/Qt 固定开销影响)
- **更新**: profiling 脚本适配优化后的 pipeline (`memory_profile.py`, `memory_profile_light.py`, `cpu_profile.py`)

### ✅ v0.2.2.1 add themes setting of viewbox ✅ **已完成**
8. 增加一个设定绘图区(viewbox)颜色theme的功能。
- 仅提供dark和light两种theme，确保作为示波器显示供能的显示效果，并避免分散用户的注意力
- Dark mode: background设为纯黑色(#000000)，foreground设为#E0E0E0，同时title和label字体颜色也设为foreground颜色
- Light mode：background设为白色(#FFFFFF)，foreground设为黑色(#000000)，同时title和label字体颜色也设为foreground颜色
- 取消目前viewbox / tilte / label 颜色跟随系统theme的方法
- 用户通过plot setting widget来使用此功能

### ✅ v0.2.2.1 add raw data conversion ✅ **已完成**
7. 将当前打开的raw data转换为其他格式，支持spice, qspice, ltspice之间相互转换，在File菜单添加一个Conver Raw Data项来触发，触发后让用户可以保存到文件。
- **实现**: `pqwave/models/raw_converter.py` 新增 write_raw_file()，处理三种格式的编码/数据类型/Command: header 差异
- **修复**: 源格式检测从文件扩展名改为 spicelib 的 `raw_data.dialect` 属性，解决 ngspice .raw 被误判为 LTspice 的问题
- **已知限制**: QSPICE AC 文件转换时，spicelib 始终将第一个变量视为频率轴（float64），若第一个变量非频率轴则数据可能不正确
- **测试**: `pqwave/tests/test_raw_converter.py` 7 项测试全部通过

### ✅ v0.2.2.1 further performance improvement ✅ **已完成**
6. 通过改进数据处理方式进一步提升性能
- **根本原因**: spicelib 的 `get_trace()` 在 NormalAccess 模式下是懒加载——每次调用都从二进制文件重新读取整个数据段（120 MB），33 次循环 = 33×120 MB = ~3.9 GB 中间缓冲区，且 78% CPU 时间花在重复 `read()` 上
- **修复**: 在 `RawFile.parse()` 中，循环前调用 `read_trace_data(all_spicelib_names)` 一次性读取并缓存全部变量，后续 `get_trace()` 全部命中缓存
- **效果** (SMPS.qraw, 36 变量, 479K 点): RSS 从 ~4.4 GB → ~689 MB (6.4× 减少), parse CPU 从 1.9s → 0.5s (3.8× 加速)
- **新增**: `pqwave/tests/memory_profile.py` (tracemalloc + RSS 逐阶段分析), `pqwave/tests/cpu_profile.py` (per-stage timing + cProfile)


### ✅ v0.2.2.1 add a cross-hair cursor ✅ **已完成**
5. a cross-hair to enhance data accuracy by allowing precice mouse tracking
  - 在cross-hair cursor ON的状态下，当用户移动鼠标时，保持当前在status bar中显示坐标的实现，小数位保持.6g格式
  - 此时，如果用户按下鼠标左键，则在绘图区该位置绘制一个十字mark，表明用户在此位置mark了
  - 提供 "Delete Last" 按钮删除最后一条mark（替代undo，简单实现）
  - 对于每一个鼠标左键mark的动作，除了在status bar上继续显示位置坐标之外，提供一个数据展示面板，显示坐标值
  - 这个面板可以独立于主窗口移动，以免挡住绘图区的位置
  - 当用户再次按下鼠标左键时，在绘图区增加另一个mark，同时在数据面板上添加新的坐标数据
  - 如此反复，直到用户将cross-hair cursor OFF掉
  - 数据面板上的数值可以export到plain text, csv格式，用户也可以选择数据并copy到clipboard
  - cross-hair OFF时，清除所有mark并关闭数据面板，每次ON都是全新开始
4. a tool bar icon to ON/OFF the cursor (toggle行为)
3. a menu item under View menu to ON/OFF the cursor (toggle行为)

### ✅ v0.2.2.1 add command line args. ✅ **已完成**
2. add command line args. --test, --debug, --verbose for pqwave.py ✅ **已完成**
   - --test: run test suites in ./tests directory (test scripts already copied to ./pqwave/tests)
   - --debug: enable debug-level logging (shows detailed debugging information like log_axis.py outputs)
   - --verbose: enable info-level logging (shows user feedback and informational messages)
   - Default behavior: only warnings and errors are shown, keeping the interface clean
1. replace debug codes with logging system ✅ **已完成**
   - replace all debug print() statements with Python standard logging module
   - convert log_axis.py debug prints to logger.debug() (only shown with --debug)
   - convert error/warning prints to logger.warning()/logger.error() (always shown)
   - convert user feedback prints to logger.info() (shown with --verbose)
   - keep if __name__ == "__main__": test blocks unchanged as they only affect script execution

### ✅ v0.2.2.0 new architecture ✅ **已完成**
1. restructure the project from monolithic to modular✅ **已完成**
2. add tips for trace_expr.当鼠标移动到"Add Trace:" label上方，或者trace_expr上方，或者"X"/"Y1"/"Y2"按钮上方时，显示一个tip,提醒用户包含运算符的表达式必须用""或者''围起来。✅ **已完成**
3. implement trace property editor✅  **已完成** 
4. implement Settings widget, with respect to the requirements in settings_widget.md ✅ **已完成**

### ✅ v0.2.1.2 add features ✅ **已完成** 
1. Add a menu item "View" ✅ **已完成**
  - to toggle the ON/OFF of tool bar and status bar
  - to toggle the ON/OF of X/Y grids（pyqtgraph的context menu已有X-grid ON/OFF, Y-grid ON/OFF功能，直接使用其方法，不要增加新的方法）
  - to zoom in / zoom out / zoom full (zoom to fit) / zoom box / auto range x-axis / auto range Y1&Y2 axis  
    （同理，优先使用已经有的方法。除非没有现有方法，或者现有方法实现不了，才引入新的方法）
  - to turn grid ON/OFF （同理，优先使用已有方法）
2. Add a tool bar to realize these functions ✅ **已完成**
  -  Open File
  -  Open New Window
  -  zoom in
  -  zoom out
  -  zoom full (zoom to fit)
  - auto range X-axis 
  - auto range Y1&Y2-axis
  -  zoom box
  -  turn grid ON/OFF
3. Add a status bar to show these information ✅ **已完成**
  - 当鼠标在绘图区中时，显示鼠标当前坐标
  - 当前的activate dataset（为后续支持multiple dataset时显示activate dataset做准备）


###  v0.2.1.1 完善v0.2.1的UX并增加一些小功能 ✅ **已完成**

### ✅ 1. 通过改变legend的表示提示该trace是在使用Y1轴还是Y2轴 
- 当前没有区分trace在使用哪个Y轴的机制，用户无法容易识别
- 将legend显示方式从"--trace_name"改成"trace_name @ Yx"的方式，x为1或2，提示该trace是在使用哪个Y轴

### ✅ 2. File menu改善
- 现在的次级菜单Open重命名为Open Raw File，
- 增加一个次级菜单项Open New Window，用以打开另一个窗口
  - 打开的新窗口应该是init的状态，即没有数据载入，也不继承当前窗口的属性

### ✅ 3. Edit menu改善
- Edit menu中，次级菜单Settings用以设定全局参数，保持其现有功能不变，不做任何改动
- 将现有次级菜单Edit Trace Aliases升级为Edit Trace Properties，用以设定trace的特性。实现方式不变，但在现有的Alias:输入框下增加以下component：
  - Color: combo，用以选择trace颜色
  - Line width: combo, 用以选择trace的线宽
  - 以上属性是针对哪条trace的编辑，是由上方的trace list中的选定决定的
