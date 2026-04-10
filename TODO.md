
## TODO.md

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
 
### 🔧  v0.2.1.2 修复以下bug

### 1. 当向Y2添加trace时使用了重复的颜色 
- 当只向Y1
- 

### 2. 
- 
- 
- 

### 3. 
- 
- 
- 
- 
- 

### 4. 
- 
- 
- 
- 
- 
- 



## v0.2.2 重要功能增强

### 1. 当光标处于绘图区内时，显示当前光标坐标 
- 可快速查看波形中某点的值
- prompts can land in the shell instead of the coding agent
- "session exists" does not mean "session is ready"

### 2. Truth is split across layers
- tmux state
- clawhip event stream
- git/worktree state
- test state
- gateway/plugin/MCP runtime state

### 3. Events are too log-shaped
- claws currently infer too much from noisy text
- important states are not normalized into machine-readable events

### 4. Recovery loops are too manual
- restart worker
- accept trust prompt
- re-inject prompt
- detect stale branch
- retry failed startup
- classify infra vs code failures manually

### 5. Branch freshness is not enforced enough
- side branches can miss already-landed main fixes
- broad test failures can be stale-branch noise instead of real regressions

### 6. Plugin/MCP failures are under-classified
- startup failures, handshake failures, config errors, partial startup, and degraded mode are not exposed cleanly enough

### 7. Human UX still leaks into claw workflows
- too much depends on terminal/TUI behavior instead of explicit agent state transitions and control APIs
