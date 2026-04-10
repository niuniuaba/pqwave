
## TODO.md

### 🔧   v0.2.2 重要功能增强
-
-
-

### ✅ v0.2.1.2 add features ✅ **已完成** 
- Add a menu item "View"
  - to toggle the ON/OFF of tool bar and status bar
  - to toggle the ON/OF of X/Y grids（pyqtgraph的context menu已有X-grid ON/OFF, Y-grid ON/OFF功能，直接使用其方法，不要增加新的方法）
  - to zoom in / zoom out / zoom full (zoom to fit) / zoom box / auto range x-axis / auto range Y1&Y2 axis  
    （同理，优先使用已经有的方法。除非没有现有方法，或者现有方法实现不了，才引入新的方法）
  - to turn grid ON/OFF （同理，优先使用已有方法）
- Add a tool bar to realize these functions
  -  Open File
  -  Open New Window
  -  zoom in
  -  zoom out
  -  zoom full (zoom to fit)
  - auto range X-axis 
  - auto range Y1&Y2-axis
  -  zoom box
  -  turn grid ON/OFF
- Add a status bar to show these information
  - 当鼠标在绘图区中时，显示鼠标当前坐标
  - 当前的activate dataset（为后续支持multiple dataset时显示activate dataset做准备）


### 🔧 v0.2.1.1 完善v0.2.1的UX并增加一些小功能 ✅ **已完成**

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
 
## 🔧   v0.2.2 重要功能增强
