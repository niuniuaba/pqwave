# PRD: Mixed-Signal Waveform Viewer

## Status: Draft
## Target: pqwave v0.3.0

---

## 1. Problem Statement

混合信号仿真已成为 SPICE 生态的主流范式。ngspice 内置 XSPICE 数字引擎和 d_cosim（Verilog/VHDL 协同仿真），QSPICE 原生支持 C++/Verilog 数字块。但**开源工具链中没有一个波形查看器能在一个窗口中同步显示模拟波形和数字时序图**：

- **ngspice** 将 analog 写入 `.raw`，digital 写入 `.vcd`（两个文件、两个工具）
- **QSPICE** 用统一 `.qraw` 格式，但 QUX 查看器将所有信号渲染为模拟曲线，无数字时序图
- **xschem graph** 只读 `.raw`，通过逻辑阈值判定渲染数字信号，但不支持 `.vcd`
- **GTKWave** 只读 `.vcd`/`.fst`，不读 SPICE `.raw`

**用户痛点**：调试混合信号电路时，需要打开两个查看器（如 Gwave + GTKWave），手动对齐时间轴，无法同步缩放和平移。这在调试 SAR-ADC、PLL、DC-DC 数字控制环路等电路时极其低效。

## 2. User Personas

| Persona | 典型场景 |
|---------|---------|
| **模拟 IC 设计师** | 用 ngspice + XSPICE 仿真 SAR-ADC，需要同时看模拟 ramp 和数字比较器输出 |
| **电源工程师** | 用 QSPICE 仿真数字控制 DC-DC，需要同时看功率级 V/I 波形和数字 PWM 控制信号 |
| **FPGA/数字工程师** | 用 d_cosim（Verilator）做混合信号协同仿真，需要在一个窗口中看模拟节点和 Verilog 信号 |
| **教育/学生** | 学习混合信号电路，需要直观看到模拟和数字波形的交互 |

## 3. Scope

### 3.1 In Scope（v0.3.0）

**P0 — 核心渲染能力**
- **P0.1** 数字波形时序图风格渲染：基于逻辑阈值将信号渲染为 0/1 阶梯状时序图
- **P0.2** 数字波形的 analog 显示模式：一键在时序图与模拟曲线之间切换
- **P0.3** 总线信号（Bus Signal）显示：将多个 digital trace 打包为 bus，显示 hex/bin/dec 值

**P1 — 数据格式支持**
- **P1.1** `.raw` 文件中的数字信号（dac_bridge 工作流）：用户可标记任意 trace 为 "digital"
- **P1.2** `.vcd` 文件导入：VCD parser，实现 raw + VCD 同窗同步叠加
- **P1.3** `.qraw` 文件中的数字信号识别：自动或半自动识别数字 trace

**P2 — 高级分析**
- **P2.1** Eye Diagram：从数字波形生成眼图，支持颜色强度/persistence 渲染
- **P2.2** Bus slicing/concatenation：Verilog 风格总线切片（`bus[7:4]`）、拼接（`{a,b}`），复用现有中缀表达式系统进行 bus 值算术

### 3.2 Out of Scope（v0.3.0）
- `.fst`/`.lxt2` 格式支持（GTKWave 专用格式，需求较低）
- 协议解码（I2C、SPI、UART 等 — 可留给 v0.4.0）
- Verilog/VHDL 源码直接导入
- 混合信号仿真启动（pqwave 是查看器，不是仿真器）

## 4. Functional Requirements

### FR-1: Signal Type System

每个 trace 具有类型属性：

| Type | 描述 | 数据来源 |
|------|------|---------|
| `analog` | 连续模拟信号 | `.raw` / `.qraw` 默认类型 |
| `digital` | 数字逻辑信号 | 用户标记，或 VCD 导入 |
| `bus` | 总线信号（digital trace 的集合） | 用户分组 |

状态转换：
```
analog ──[Mark as Digital]──▶ digital ──[Group into Bus]──▶ bus
digital ──[Unmark]──────────▶ analog
bus ──[Ungroup]─────────────▶ digital (xN)
```

### FR-2: Digital Trace Rendering

**FR-2.1 逻辑阈值判定**
- 默认：V_high = 80% * V_range, V_low = 20% * V_range
- 用户可覆盖为自定义电压阈值（如 TTL: 0.8V/2.0V, CMOS: 0.3*Vdd/0.7*Vdd）
- 0→1 和 1→0 的 transition 渲染为斜线（斜率基于实际数据 slew rate）
- Unknown（Z/X）状态：渲染为阴影区域或中间色

**FR-2.2 时序图样式**
- 阶梯状逻辑电平线，不渲染模拟采样点间的连续波形
- 高电平颜色可配置（默认亮绿/亮蓝）
- 低电平颜色可配置（默认深灰）
- 信号标签在 Y 轴左侧，紧凑排列（类 GTKWave / 逻辑分析仪风格）

**FR-2.3 Analog 与 Digital 切换**
- 通过 trace context menu 或 toolbar toggle 切换
- 切换即时生效（只改变渲染方式，不改变底层数据）
- 可在同一 ViewBox 中混合显示 analog 和 digital 渲染的 trace

### FR-3: Bus Signal

**FR-3.1 Bus 创建**
- 用户选择多个 digital trace → right-click → "Group as Bus"
- 自动推断 bit 顺序（从 trace name 中的数字后缀，如 `d[0]`, `d[1]`, ...）
- 用户可手动调整 bit 顺序和 MSB/LSB 方向

**FR-3.2 Bus 显示**
- 默认显示 hex 值（如 `A3`, `7F`）
- 可选 bin / dec / oct / ASCII 格式
- Bus 值标签在波形旁边或 Y 轴区域
- 当 bus 值变化时，渲染 transition marker

**FR-3.3 Bus 展开/折叠**
- 可展开 bus 查看所有 member signal 的时序图
- 折叠时只显示 bus 值行
- toggle 行为，保持 UI 紧凑

### FR-4: VCD Import

**FR-4.1 VCD Parser**
- 解析 IEEE 1364-2001 VCD 格式（纯文本）
- 支持 `$var`, `$scope`, `$upscope`, `$enddefinitions`, `$dumpvars`
- 处理 multi-bit wire/reg 声明
- 支持 `$comment` 和 `$date` / `$version`

**FR-4.2 Raw + VCD 同步叠加**
- 用户打开 `.raw` 文件后，可通过菜单加载关联的 `.vcd` 文件
- VCD 信号与 raw 信号共享同一时间轴
- 同步缩放、平移作用于所有信号（analog + digital）
- 时间对齐：以 raw 的 time vector 为主轴，VCD 时间点映射到最近的 raw 采样点

**FR-4.3 VCD-Only 模式**
- 用户可单独打开 VCD 文件（无需 raw）
- 此时时间轴完全由 VCD 的时间戳定义

### FR-5: Eye Diagram

**FR-5.1 生成**
- 用户选择一个 digital trace → right-click → "Eye Diagram"
- 参数：bit period（自动检测或手动设置）、samples per bit
- 使用 numpy 将长波形折叠为重叠的 UI（Unit Interval）段

**FR-5.2 渲染模式**
- Mode 1（Overlay）：所有 UI 段叠加为细线（示波器无限余晖风格）
- Mode 2（Color Persistence）：2D histogram + colormap（数字示波器余晖风格）
- pyqtgraph `ImageItem` 用于 color persistence 模式

**FR-5.3 测量叠加**
- Eye height / Eye width 标注
- Optimal sampling point 标记

### FR-6: UI/UX

**FR-6.1 Plot Pane 组织**
- 保持现有 multi-panel 架构
- Analog trace 和 digital trace 可在同一 pane 中混合，也可分离到不同 pane
- 推荐默认布局：analog pane（上）+ digital pane（下），共享 X 轴

**FR-6.2 图例**
- Digital trace 在图例中显示 `■ signal_name [D]` 标识
- Bus trace 显示 `■ bus_name [BUS:8]`（位宽）
- 颜色/样式与渲染一致

**FR-6.3 Context Menu**
- Analog trace："Mark as Digital..."、"Eye Diagram..."
- Digital trace："Show as Analog"、"Threshold Settings..."、"Add to Bus..."、"Eye Diagram..."
- Bus trace："Expand/Collapse"、"Display Format →"、"Ungroup"

**FR-6.4 逻辑阈值设置对话框**
- Per-trace 或 global 阈值设定
- 预设：TTL (0.8V/2.0V)、CMOS-3.3V、CMOS-5V、Auto (20%/80%)
- 实时预览阈值线

## 5. Non-Functional Requirements

### NFR-1: Performance
- 数字信号渲染不得比现有 analog 渲染慢
- VCD 解析：支持 1M+ 事件的 VCD 文件，解析时间 < 2s
- Eye diagram 生成：100K 样本折叠 < 500ms
- Bus 显示：16-bit bus 渲染不得引入明显延迟

### NFR-2: Compatibility
- 不影响现有 analog-only 工作流
- 现有 `.json` state 文件格式兼容（新增 trace type 和 digital metadata 字段）
- 支持所有已有 raw 格式：ngspice `.raw`、LTspice `.raw`、QSPICE `.qraw`

### NFR-3: Usability
- 纯 analog 用户感知不到数字功能的存在（除非主动使用）
- 数字功能的入口清晰但不侵扰

## 6. Data Format Support Matrix

| 场景 | 数据源 | Analog | Digital | Bus | 优先级 |
|------|--------|:------:|:-------:|:---:|:------:|
| QSPICE mixed-signal | `.qraw` x1 | 现有 | 标记 | 标记 | P1 |
| ngspice dac_bridge | `.raw` x1 | 现有 | 标记 | 标记 | P1 |
| ngspice XSPICE only | `.raw` + `.vcd` | 现有 | VCD import | VCD import | P1 |
| ngspice d_cosim | `.raw` + `.vcd` | 现有 | VCD import | VCD import | P1 |
| QSPICE C++/Verilog block | `.qraw` x1 | 现有 | 标记 | 标记 | P1 |
| VCD only（e.g. Icarus） | `.vcd` x1 | N/A | VCD import | VCD import | P2 |

## 7. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    pqwave UI Layer                   │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Analog   │  │ Digital      │  │ Bus Signal    │  │
│  │ Renderer │  │ Renderer     │  │ Renderer      │  │
│  │(existing)│  │(timing diag) │  │(hex/bin/dec)  │  │
│  └────┬─────┘  └──────┬───────┘  └───────┬───────┘  │
│       │               │                   │          │
│  ┌────┴───────────────┴───────────────────┴───────┐  │
│  │              Trace Type System                  │  │
│  │   (analog | digital | bus) + threshold config  │  │
│  └────────────────────┬───────────────────────────┘  │
│                       │                               │
│  ┌────────────────────┴───────────────────────────┐  │
│  │              Data Provider Layer                │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │  │
│  │  │ Raw      │  │ VCD      │  │ QRAW         │  │  │
│  │  │ Parser   │  │ Parser   │  │ Parser       │  │  │
│  │  │(existing)│  │   (new)  │  │(spicelib)    │  │  │
│  │  └──────────┘  └──────────┘  └──────────────┘  │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| VCD 大文件（>100M events）解析慢 | 用户体验差 | 增量加载 + FST 格式作为快速路径 |
| raw/VCD 时间轴不同步 | 数据显示错误 | 统一插值到 raw 时间轴；用户可见的 offset 调整 |
| 数字渲染性能不达标 | 大量 digital trace 时卡顿 | 预渲染 + 缓存；downsampling 策略 |
| 破坏现有 analog-only 工作流 | 回归 bug | 充分测试；trace type 默认 `analog`；零行为变更 |

## 9. Success Metrics

- 用户可在打开 `.raw` 文件后，通过一次操作将 trace 切换为数字时序图显示
- 用户可加载 `.vcd` 文件并与 `.raw` 信号在同一窗口同步显示
- Eye diagram 生成时间 < 500ms（100K 样本）
- 16-bit bus 显示帧率不下降
- 现有 analog-only 测试套件全部通过（零回归）

## 10. References

- TODO.md #18.7
- ngspice Manual Ch.12: XSPICE Mixed-Mode Simulation
- xschem graph documentation: `http://repo.hu/projects/xschem/releases/doc-3.4.6/xschem_man/graphs.html`
- IEEE 1364-2001: Verilog VCD format
- `eyediagram` Python library（Warren Weckesser）
- GTKWave LXT2 format（Tony Bybell）
- ngspice `tmp-gtkwave-1` branch（Jim Holmes, Efabless）
