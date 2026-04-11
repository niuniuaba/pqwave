## TODO.md

###  v0.2.2.3 add horizon/vertical line cursors
1. 
2. 
3. 
4.

###  v0.2.2.2 add a cross-hair cursor
1. a cross-hair to enhance data accuracy by allowing precice mouse tracking
2. a tool bar icon to ON/OFF the cursor
3. a menu item under View menu to ON/OFF the cursor
4. show the coordinate in status bar in the form of X: 0.000, Y1: 0.000, Y2: 0.000

###  v0.2.2.1 add command line args.
1. add command line arg. --test for pqwave.py
   - copy test scripts in ./tests directory to ./pqwave/tests
   - ./venv/bin/python --test to run test suits in ./tests directory
2. remove debug codes
   - there are many debug codes in the current code tree which print too many debug information to stdout. remove them to test suits or add a --debug arg.

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
