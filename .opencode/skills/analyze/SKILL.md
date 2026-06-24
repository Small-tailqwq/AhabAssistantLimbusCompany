---
name: analyze
description: 智能调用日志分析工具对 AALC 本地归档或 GitHub Issue 进行诊断分析，输出复现流程与修复意见
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: debugging
---

## 技能简介

当需要排查 AALC issue 时，本技能指导 agent 自动执行完整的分析流程：获取 issue 上下文 → 读取日志 → 识别异常模式 → 溯源调用链 → 定位根因 → 写出修复方案。

本技能基于本仓库的实际排障实践构建，参考了 issue 2（back_init_menu 无限循环）、issue 3（re_start 齿轮卡死）和 CI triage 的实际运行经验。

## 前置依赖

- `.opencode/tools/log_analyzer.py` — 日志压缩分析工具（纯 stdlib，无需额外依赖）
- `.opencode/tools/match_viewer.py` — Web UI 交互式模板匹配工具
- `debug_tools/verify_matching.py` — CLI 批量模板匹配验证工具（支持 A/B 对照）
- `.opencode/reference/replay_matching.md` — 模板匹配重放的完整管道说明与常见陷阱
- `issues/TEMPLATE.md` — issue 模板

## 分析流程

### 第1步：获取 issue 上下文

**本地归档场景**：读取 issue 目录下的所有文件：

| 文件 | 用途 |
|---|---|
| `metadata.json` | issue id、创建时间、版本号、备注 |
| `meta_info.txt` | 分辨率、截图间隔、AALC 版本等环境信息 |
| `dev_notes.md` | 开发者已有的分析备注 |
| `extracted_config.yaml` | 配置快照，重点关注 `simulator`、`win_input_type`、`background_click` |

**GitHub Issue 场景**：直接从 issue body 和附件日志中提取。

提取以下锚点：
- **AALC 版本**（以日志中**最后一次出现**的版本号为准，开头可能是旧版本覆盖）
- **运行模式**：模拟器/后台点击/前台/Logitech/OBS
- **功能场景**：镜牢/纺锤本/清体力/合成/日常任务
- **用户描述的现象**：卡死/崩溃/误点/不响应
- **配置文件关键项**：截图间隔、鼠标间隔、`skip_enkephalin` 等

### 第2步：读取日志

读日志时按以下策略：
1. 先用 head 读开头 ~50 行，获取配置信息、版本号、运行模式
2. 再用 tail 读末尾 ~200 行，定位异常/崩溃/卡死的位置
3. 版本号**必须取日志中最后一次出现**的匹配
4. 理解问题后按需 grep 关键时间段，不要通读全文

日志较大的话（>5万行），可运行 log_analyzer.py 生成压缩报告：
```powershell
uv run python .opencode/tools/log_analyzer.py <log_path>
```

### 第3步：先排查用户配置

在深入代码分析之前，先检查问题是否由用户配置导致：

- 提取日志头部配置文件中的关键配置项（`skip_enkephalin`、`simulator`、`win_input_type`、`background_click` 等）
- 对比用户描述的现象和配置值：**配置项是否直接解释了现象？**
  - 例：skip_enkephalin=True + 用户反馈"不换体力" → 配置使然，非代码 bug
  - 例：未启用模拟器 + 用户反馈"模拟器没反应" → 配置问题
- **如果配置项直接导致现象**：诊断结论应为"用户设置问题"，修复建议指向 UI 设置项而非改代码。仍可附带代码分析说明机制，但不要创建代码修复方案。

### 第4步：模式识别

从日志中识别以下模式：

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

**4c. 时序分析**
- 截图→点击的间隔反映截图间隔配置
- 点击→下一轮截图的间隔反映游戏渲染时间
- 如果所有操作在 <500ms 内完成 → 循环速度快，截图间隔短

**4d. 崩溃/恢复点**
- `NemuIpc` 断连 + `AttributeError: NoneType has no attribute 'fileno'` → Mumu 模拟器连接断开触发异常
- `check_times()` 超时触发 → `kill_game()` + `restart_game()` 被执行
- 异常后的流程（restart_game → retry → 继续任务）反映自动恢复能力

**4e. 开始执行/结束执行 瞬时返回**
- `开始执行 X` 和 `结束执行 X` 时间戳差 ≤1ms → 函数体未执行任何实际操作
- 通常是因为前置条件（skip/skip_enkephalin 等配置）导致函数直接 return
- 需与用户配置交叉验证：查日志头部 cfg 或 grep 对应配置项

### 第4.5步：模板匹配重放验证

如果用户提供了卡死界面的截图，必须对截图进行完整的模板匹配重放，验证日志中的相似度是否符合预期。

**使用 `verify_matching.py` 快速验证：**

```powershell
# 单截图 + 关键资产
uv run python debug_tools/verify_matching.py <screenshot.png> --minimal --models clam aggressive

# A/B 对照（问题截图 vs 正常截图）
uv run python debug_tools/verify_matching.py <问题截图> --compare <正常截图> --minimal

# 完整资产列表
uv run python debug_tools/verify_matching.py <screenshot.png>

# 指定区域像素分析
uv run python debug_tools/verify_matching.py <screenshot.png> --pixel X Y W H
```

**A/B 对照是判断资产过期/UI 变化的最有效手段**：
- 两张截图分辨率相同但匹配值差异悬殊 → UI 差异（字体/HDR/主题/汉化补丁修改）
- 两张截图匹配值都低 → 资产已过期，需要更新
- 同一张截图 `identify_assets.png` 高（>0.9）但按钮匹配低 → 弹窗/覆盖层遮挡按钮

**手动重放管道**遵循 `.opencode/reference/replay_matching.md`：
1. 以截图实际高度除以 1440 计算 scale（不用 `cfg.set_win_size`）
2. `_assets.png` 后缀资产必须先 `get_bbox()` + `crop()` 再匹配
3. 使用 `ImageUtils.match_template()`，不能直接用 `cv2.matchTemplate()`
4. `model=clam` 在 bbox 附近搜索，`model=aggressive` 全屏搜索

**像素分析辅助判定**：当匹配值异常时，用 `--pixel` 参数提取按钮区域像素统计。对比模板按钮区域的亮暗像素分布可判断：
- 按钮是否被禁用（灰色/暗化）
- 文字/图标亮度是否与模板匹配
- 是否有半透明覆盖层

### 第5步：溯源调用链

从日志中的文件路径追溯调用链：

- 日志行 `..\..\tasks\mirror\mirror.py:946` → 读取 `mirror.py` 对应行的源码
- 日志行 `..\..\tasks\base\back_init_menu.py:83` → 读取对应行的源码
- 调用栈（ERROR 级别后的 Traceback）→ 完整调用链

工作原理：
1. 从日志的热力图找**最高频文件** — 卡死所在模块
2. 从重复模式找**最高频行** — 卡死所在函数
3. 从 `grep def <function> <file>` 找函数定义
4. 读取该函数源码 → 分析 `while/if/continue/break` 结构
5. 查找该函数的所有调用者 → `grep <function> *.py`

### 第6步：关联分析

如果新 issue 与历史 issue 行为相似（同为齿轮误匹配、同为 back_init_menu 循环、同为 Mumu 断连恢复），在诊断中标注关联关系和新旧差异。

如果用户日志版本与当前主线代码明显不一致：
- 确认用户版本，必要时切到对应 tag 复核旧逻辑
- 若当前主线已修复，用 `gh release list --repo <owner>/<repo>` 检查修复是否已进入 release
- **如果问题在新版 release 中已修复**：在修复建议中明确"此问题已在 vX.X.X 中修复，请升级到最新版"
- 如果修复未发版：建议等待 next release

如果用户反馈的问题在当前版本的代码中已经不存在（代码已被重写或修复）：
- 检查用户版本和当前 latest release 版本
- 如果用户版本远低于 latest → 明确建议升级
- 例如：用户 V1.4.5 反馈的问题在 V1.4.9 已修复 → "请升级到 V1.4.9+"

### 第7步：形成诊断

输出以下结构。引用代码时使用 GitHub blob 行号链接：

## 问题概要

## 环境
- AALC 版本:
- 分辨率:
- 运行模式:
- 功能场景:

## 关键证据

<details><summary>点击展开</summary>

- 日志片段...
- 配置关键项...
- 代码依据...

</details>

## 根因分析

### 异常位置
### 画面推断（如有）
### 调用链

## 修复建议

> [!TIP]
> 如果问题已在较新版本中修复，优先建议用户升级。

## 置信度
- 高 / 中 / 低
- 还缺什么证据

## 常见模式速查

以下是在 AALC 实际排障中积累的常见模式，供分析时参考：

| 模式 | 典型日志特征 | 常见根因 |
|------|-------------|---------|
| 寻路无限循环 | 同一文件/图片匹配反复出现，`continue` 始终命中 | ONNX 模型问题 → 降级到兜底寻路 → back_init_menu 卡住 |
| 齿轮误匹配 | `re_start` 高频出现，齿轮资产匹配度高但不该在画面上 | 资产图片过于通用，非齿轮界面也被匹配 |
| Mumu 断连崩溃 | `NemuIpc` 断连 + `AttributeError` Traceback | 模拟器连接不稳定或异常断开 |
| 跳过换体/日常 | `开始执行 体力换饼` 和 `结束执行` 时间戳相同 | `skip_enkephalin=True` 配置导致函数直接 return |
| 战斗完不前进 | 战斗胜利后 stuck，路线识别/奖励确认资产匹配失败 | 分辨率不匹配、主题包资产缺失 |
| 截图超时恢复 | `check_times()` 触发 → `kill_game()` + `restart_game()` | 游戏进程卡死/窗口失去焦点导致截图一直超时 |
| UI 修改导致匹配失败 | `identify_assets.png` 高匹配但操作按钮低匹配，同屏幕不同截图匹配值差异巨大 | 用户修改了汉化字体/主题，或开启了 HDR/夜间模式等影响画面渲染的选项 |

## 注意事项

- **绝不改动日志文件本身** — 只读不写
- **绝不删除日志文件** — 即使压缩报告已生成也不删源文件
- **确认文件存在** — 每一步操作前先检查文件是否存在，不存在则跳过并说明
- **`log_analyzer.py` 输出 UTF-8 编码的报告文件** — 用 Read tool 读取，不要在终端直接打印
- **代码分析优先用 Read tool** — 精准读取相关行，避免大段加载
- **复现步骤必须可执行** — 不能写"未知"，至少写"在 X 环境下运行 Y 功能时卡死"
- **修复建议优先用最小改动方案**
- **引用代码时用 GitHub blob 行号链接**，例如 `<https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/<commit>/path/to/file.py#L123-L130>`**
- **用户提供截图时必须执行模板匹配重放** — 优先使用 `verify_matching.py --compare` 做 A/B 对照，可快速区分资产过期 vs UI 修改 vs 弹窗遮挡
- **如果匹配值能复现但不合理** — 检查用户是否修改了汉化补丁字体、是否开启了 HDR/夜间模式/主题包覆盖等会改变画面渲染的系统选项
- **`chaim_to_battle_assets.png` 等全屏截图式资产** — 这类资产是 2560×1440 的完整截图而非按钮裁剪，bbox 超出截图可用区域时匹配值会被压低，需确认截图分辨率 ≥ 模板 bbox 覆盖范围
