关键发现：@spice_get_voltage 需要 C 层支持

  xschem 原理图上的标注文本（如 lab_pin.sym 中的 @spice_get_voltage）在 token.c:4772-4813
  中被处理，核心逻辑是：

  if(live_cursor2_backannotate && sch_waves_loaded()>=0 && xctx->raw->annot_p>=0) {
      idx = get_raw_index(fqnet, NULL);
      if(idx >= 0) {
          val = xctx->raw->cursor_b_val[idx];  // 从 C 层 raw 数据读取
      }
  }

  它读的是 raw->cursor_b_val[]，这是由 C 函数 backannotate_at_cursor_b_pos() 在
  callback.c:285 中填充的。仅仅通过 Tcl 命令设置 ngspice::ngspice_data(varname)
  是不够的，因为存量电路图和符号都使用 @spice_get_voltage(net) 格式，它直接读 C 层的
  raw->cursor_b_val。

  有两条路

  路线 A：Tcl-only（不需要改 xschem C 代码）

  原理图上放 floater 文本格式为 tcleval($ngspice::ngspice_data(v(r2)))，而不是使用标准
  @spice_get_voltage 符号。这样我们可以通过 xschem_listen_port 设置 Tcl 变量来驱动标注。

  缺点：不能复用现有的 lab_pin.sym 等符号。用户需要手动修改原理图或创建新的标注符号。

  路线 B：最简 xschem C 修改（推荐，改动极小）

  在 xschem 的 scheduler.c 中新增一个 Tcl 命令 xschem annotate_cursor_x
  <xvalue>，其核心逻辑是从已加载的 raw 文件中做插值、填充 cursor_b_val[] 和
  ngspice::ngspice_data、清除 floater 缓存并触发重绘。本质上是把
  backannotate_at_cursor_b_pos 中不依赖于 graph 上下文的核心逻辑提取出来。

  优点：
  - 存量 @spice_get_voltage 符号自动生效
  - 与 xschem 内置 graph 行为完全一致
  - 改动极小（~50 行 C 代码）
  - pqwave 只需要发 xschem annotate_cursor_x <x> 一条命令

  缺点是需要修改 xschem C 源码并重新编译。
