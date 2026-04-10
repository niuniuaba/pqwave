# pqwave 开发总结

## 项目概述
pqwave（原名wave_viewer）是一个用于SPICE仿真数据的波形查看器，使用spicelib和PyQtGraph构建。

## 项目迁移历史
- **原始项目**: wave_viewer (位于xschem.git/wave_viewer)
- **新项目**: pqwave (独立git项目，计划发布到https://github.com/niuniuaba/pqwave)
- **迁移日期**: 2026-04-10

## 已完成的主要功能

### v0.2.1.1 (当前版本)
1. **Legend显示格式改进**
   - 格式从"--trace_name"改为"trace_name @ Yx"
   - 明确显示trace使用的是Y1轴还是Y2轴
   - 移除了复杂的CustomLegendItem实现，使用标准的pyqtgraph LegendItem

2. **File菜单改进**
   - "Open"重命名为"Open Raw File"
   - 新增"Open New Window"菜单项，可以打开新的独立窗口

3. **Edit菜单改进**
   - "Edit Trace Aliases"升级为"Edit Trace Properties"
   - 新增Color组合框（10种预定义颜色 + "Default (auto)"选项）
   - 新增Line width组合框（1-5像素选项）
   - 保持原有的Alias编辑功能

4. **Bug修复**
   - 修复了log mode下的auto range计算问题
   - 修复了从log mode切换到linear mode时trace消失的问题
   - 修复了update_traces_for_log_mode方法中的AttributeError

### v0.2.1
- 添加X/Y数据长度一致性检查
- 添加命令行参数支持
- 改进log轴刻度显示（10^指数格式，带superscript指数）
- 为log轴模式禁用autoSIPrefix
- UI布局重新设计（合并X和Y组合框为单个Vector组合框）
- 两行布局：Dataset/Vector组合框 + 带X/Y1/Y2按钮的Add Trace
- 修复X轴变量设置和数据范围问题
- 增强trace表达式处理，支持引号

### v0.2.0
- 修复Y1/Y2轴刻度显示一致性
- 改进log scale的非正值处理

### v0.1.0
- 多格式SPICE RAW文件支持
- 中缀表达式求值
- 自动和手动范围调整
- 对数Y轴
- 科学计数法显示

## 技术架构

### 主要组件
1. **LogAxisItem**: 自定义对数轴显示类
2. **RawFile**: SPICE RAW文件解析器
3. **WaveViewer**: 主应用程序类

### 关键技术
- **PyQt6**: GUI框架
- **pyqtgraph**: 绘图库
- **spicelib**: SPICE文件解析
- **numpy**: 数值计算

## 项目结构
```
pqwave.git/
├── pqwave.py              # 主应用程序文件
├── requirements.txt       # 依赖项
├── setup.py              # 安装脚本
├── pyproject.toml        # 现代Python项目配置
├── MANIFEST.in           # 打包清单
├── Makefile              # 开发任务自动化
├── LICENSE               # MIT许可证
├── README.md             # 项目文档
├── CHANGELOG.md          # 版本历史
├── TODO.md               # 待办事项
├── DEVELOPMENT_SUMMARY.md # 开发总结（本文件）
├── tests/                # 测试文件
│   ├── test_basic.py    # 基本测试
│   └── *.raw, *.log     # 测试数据
└── archieves/           # 历史版本存档
```

## 开发工作流

### 安装开发环境
```bash
# 克隆项目
git clone https://github.com/niuniuaba/pqwave.git
cd pqwave

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -e ".[dev]"
```

### 常用命令
```bash
make install      # 安装生产依赖
make dev-install  # 安装开发依赖
make test         # 运行测试
make lint         # 运行代码检查
make format       # 格式化代码
make clean        # 清理构建产物
make build        # 构建包
make run          # 运行应用程序
```

## 待办事项
参见[TODO.md](TODO.md)文件，其中v0.2.1.1的所有任务已完成并标记为✅。

## 后续开发建议

### 短期目标 (v0.2.1.2)
1. 修复向Y2添加trace时使用重复颜色的问题
2. 添加光标坐标显示功能

### 中期目标 (v0.2.2)
1. 重要功能增强
2. 性能优化
3. 用户体验改进

### 长期目标
1. 插件系统
2. 更多文件格式支持
3. 高级分析功能

## 重要决策记录

### 1. 项目重命名
- **原因**: 创建独立的git项目，便于维护和分发
- **新名称**: pqwave (PyQt Wave Viewer的缩写)
- **仓库**: https://github.com/niuniuaba/pqwave

### 2. Legend显示格式
- **初始方案**: (Yx)--trace_name
- **修改方案**: (Yx) trace_name
- **最终方案**: trace_name @ Yx
- **决策原因**: 保持简单，使用标准pyqtgraph行为，只在文本中添加Y轴信息

### 3. 技术栈选择
- **GUI框架**: PyQt6 (成熟、功能丰富)
- **绘图库**: pyqtgraph (高性能、适合科学计算)
- **文件解析**: spicelib (专门用于SPICE文件)

## 测试策略
- 单元测试: 测试核心功能
- 集成测试: 测试GUI组件交互
- 功能测试: 测试完整工作流程
- 性能测试: 测试大数据集处理能力

## 发布流程
1. 更新版本号
2. 更新CHANGELOG.md
3. 运行测试套件
4. 构建包: `make build`
5. 发布到PyPI: `make publish`
6. 创建GitHub release

## 联系方式
- **GitHub**: https://github.com/niuniuaba/pqwave
- **Issues**: https://github.com/niuniuaba/pqwave/issues
- **作者**: niuniuaba