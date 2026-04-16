## TODO.md
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
