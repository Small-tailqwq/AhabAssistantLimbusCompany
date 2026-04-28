---
name: analyze
description: 智能调用日志分析工具对本地归档的 issue 进行诊断分析，输出复现流程与修复意见
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: debugging
---

## 技能简介

当需要排查本地已归档的 issue 时，本技能指导 agent 自动执行完整的分析流程：读取 issue 元数据 → 压缩日志 → 识别死循环/异常模式 → 溯源调用链 → 定位根因 → 写出修复方案。

本技能基于本仓库的实际排障实践构建，参考了 issue 2（back_init_menu 无限循环）和 issue 3（re_start 齿轮卡死）的完整分析过程。

## 前置依赖

- `.opencode/tools/log_analyzer.py` — 日志压缩分析工具（运行时需要 `uv run python`）
- `issues/TEMPLATE.md` — issue 模板

## 分析流程

### 第1步：读取 issue 上下文

读取 issue 目录下的所有文件：

| 文件 | 用途 |
|---|---|
| `metadata.json` | issue id、创建时间、版本号、备注 |
| `meta_info.txt` | 分辨率、截图间隔、AALC 版本等环境信息 |
| `dev_notes.md` | 开发者已有的分析备注（可能为空或仅为初步印象） |
| `extracted_config.yaml` | 配置文件快照，重点关注 `simulator`、`win_input_type`、`background_click` |

输出：issue 基本画像（运行模式、分辨率、版本、已知现象）

### 第2步：压缩日志

对 issue 目录下所有 `.log` 文件运行日志压缩工具：

```powershell
uv run python .opencode/tools/log_analyzer.py issues/<issue_id>/<filename>.log
```

输出在 `<filename>.report.txt` 中。产出关键指标：
- **总行数 + 时间跨度** — 卡死时长
- **全局重复模式**（行频率统计）— 识别无限循环
- **阶段切分** — 按模块变化自动分组
- **关键事件**（WARNING / ERROR / INFO）— 异常与调用栈
- **文件热力图** — 哪些模块被日志引用最多
- **每分钟密度** — 密集程度变化

如果有多份日志文件（如 debugLog1~4 + original），**全部压缩**后再对比分析。

### 第3步：模式识别

从压缩报告中识别以下模式：

**3a. 无限循环检测**
- 单行频率极高（千次以上）+ 同文件多行等频 → 说明在某函数内轮询
- `continue` 路径先于 `break` 路径被命中 → 代码中的逃生路径被前置条件拦截
- 示例：`setting_assets.png` 匹配度 0.85 始终先于 `towindow&forfeit_confirm`（0.13）命中

**3b. 画面状态推断**
- 多张图片在同一时刻被检查 → 它们共享同一帧截图
- 匹配度高低直接反映按钮是否在画面上：
  - 高（>0.7）= 按钮在画面上 ✅
  - 中（0.3~0.7）= 可能部分匹配，需结合画面上下文
  - 低（<0.3）= 按钮不在画面上 ❌

**3c. 时序分析**
- 截图→点击的间隔反映截图间隔配置
- 点击→下一轮截图的间隔反映游戏渲染时间
- 如果所有操作在 <500ms 内完成→循环速度快，截图间隔短

**3d. 崩溃/恢复点**
- `NemuIpc` 断连 + `AttributeError: NoneType has no attribute 'fileno'` → Mumu 模拟器连接断开触发异常
- `check_times()` 超时触发 → `kill_game()` + `restart_game()` 被执行
- 异常后的流程（restart_game → retry → 继续任务）反映自动恢复能力

### 第4步：溯源调用链

从日志中的文件路径追溯调用链。关键模式：

- 日志行 `..\..\tasks\mirror\mirror.py:946` → 读取 `mirror.py` 对应行的源码
- 日志行 `..\..\tasks\base\back_init_menu.py:83` → 读取对应行的源码
- 调用栈（ERROR 级别后的 Traceback）→ 完整调用链

工作原理：
1. 从日志的热力图找**最高频文件** — 卡死所在模块
2. 从重复模式找**最高频行** — 卡死所在函数
3. 从 `grep def <function> <file>` 找函数定义
4. 读取该函数源码 → 分析 `while/if/continue/break` 结构
5. 查找该函数的所有调用者 → `grep <function> \` *.py`

### 第5步：形成诊断并写入

更新 `dev_notes.md`，包含以下结构：

```markdown
# Issue N — 标题

## 问题现象
<!-- 用户反馈的现象 -->

## 环境
- 版本: xxx
- 分辨率: xxx
- 运行模式: 模拟器/后台点击

## 分析时间线
<!-- 多份日志的按时间顺序排列 -->

## 根因分析
### 卡死位置
<!-- 代码片段 + 说明 -->

### 画面推断
<!-- 基于各图片匹配度推断当前画面状态 -->

### 调用链
<!-- onnx寻路→降级→back_init_menu→... 或 战斗失败→re_start→... -->

## 修复建议
<!-- 具体修改方案 -->

## 已解决的
<!-- 已应用的修复 -->

## 未解决的
<!-- 已知但未修复的问题 -->
```

### 第6步：关联分析

如果新 issue 与历史 issue 行为相似（同为齿轮误匹配、同为 back_init_menu 循环、同为 Mumu 断连恢复），在诊断中标注关联关系和新旧差异。

## 注意事项

- **绝不改动日志文件本身** — 只读不写
- **绝不删除日志文件** — 即使压缩报告已生成也不删源文件
- **确认文件存在** — 每一步操作前先检查文件是否存在（`Read tool` 或 `ls` 或 `Test-Path`），不存在则跳过并说明
- **`log_analyzer.py` 输出 UTF-8 编码的报告文件** — 用 `Read tool` 读取，不要在终端直接打印
- **代码分析优先用 `Read tool`** — 精准读取相关行，避免大段加载
- **复现步骤必须可执行** — 不能写"未知"，至少写"在 X 环境下运行 Y 功能时卡死"
- **修复建议优先用最小改动方案**
