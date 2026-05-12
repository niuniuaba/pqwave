(1) 能否做成独立可插拔模块？

  xschem 没有插件/DLL 系统。核心数据结构 xctx、Raw（在 xschem.h 中定义）和命令分发器
  scheduler.c 都是编译期静态链接的，无法以 .so 形式动态加载。

  但是我们需要加的东西极少，可以维持一个独立的 patch 文件：
  - callback.c：新增一个函数 backannotate_cursor_x(double x)（~50 行，放在已有的
  backannotate_at_cursor_b_pos 旁边）
  - scheduler.c：在命令分发链中加一条 else if 分支（~5 行）
  - xschem.h：声明该函数（1 行）

  如果 patch 不进入上游，每次 git pull 后用 git am 重新应用即可。但更好的解决办法是——

  (2) 向上游提 merge request

  完全可以，而且我发现 xschem 的开发者 Stefan 已经为外部查看器集成预留了多个扩展点：
  - cursor_2_hook Tcl 钩子（callback.c:287）
  - bespice_listen_port TCP server 机制
  - send_to_viewer 对 GAW/BESPICE 的分发

  这说明他欢迎外部查看器集成。我们加的 backannotate_cursor_x() 应该设计为通用功能，而不是
  pqwave 专属的：

  // callback.c
  int backannotate_cursor_x(double cursor_x)
  {
      // 复用 backannotate_at_cursor_b_pos 的核心插值逻辑，
      // 但不依赖 graph 窗口上下文（xRect, Graph_ctx）
      // 外部波形查看器可以用这个命令驱动原理图标注

      if(!xctx->raw || !xctx->raw->values) return 0;
      if(sch_waves_loaded() < 0) return 0;

      // 使用 raw 文件中的 sweep 变量做插值
      // 填充 cursor_b_val[] 和 ngspice::ngspice_data
      // 设置 annot_p, annot_x >= 0
      return 1;
  }

  // scheduler.c，在 xschem 命令分发中：
  else if(!strcmp(argv[1], "annotate_cursor_x")) {
      if(argc > 2) {
          backannotate_cursor_x(atof_spice(argv[2]));
          set_modify(-2);     // 清除 floater 缓存
          draw();              // 重绘原理图
      }
  }

  这个函数：
  - 没有提到 pqwave，任何外部查看器（gaw, bespice, 等等）都能用
  - 语义清晰：xschem annotate_cursor_x 1.234e-3 在光标 X=1.234ms 处做标注
  - 与现有机制互补：xschem set cursor2_x 依赖 graph 窗口，xschem annotate_cursor_x 不依赖
  - 完整性好：更新 ngspice::ngspice_data Tcl 数组、清除 floater
  缓存、触发重绘，全部在一个命令中完成

  Stefan 应该会接受这个
  patch，因为它补齐了外部查看器集成的一个明显缺口（目前外部查看器只能接收来自 xschem
  的命令，无法驱动原理图标注）。

  总结

  ┌──────────────────────────────┬────────────────────────────────────────────────────┐
  │             问题             │                        答案                        │
  ├──────────────────────────────┼────────────────────────────────────────────────────┤
  │ 需要改多少 C 代码？          │ ~55 行，分成 3 处修改                              │
  ├──────────────────────────────┼────────────────────────────────────────────────────┤
  │ 是否需要插件框架？           │ 不需要，patch 极小，<60 行                         │
  ├──────────────────────────────┼────────────────────────────────────────────────────┤
  │ 向上游提 MR？                │ 可以，而且应该提                                   │
  ├──────────────────────────────┼────────────────────────────────────────────────────┤
  │ 代码应该 pqwave              │ 必须通用，不提 pqwave，只提"external viewer        │
  │ 专属还是通用？               │ annotation"                                        │
  ├──────────────────────────────┼────────────────────────────────────────────────────┤
  │ 上游不合并怎么办？           │ 我们维护一个 patch 文件，git pull 后用 git am      │
  │                              │ 重应用                                             │
  └──────────────────────────────┴────────────────────────────────────────────────────┘
