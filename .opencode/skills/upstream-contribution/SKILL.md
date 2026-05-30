---
name: upstream-contribution
description: 将本仓库（canary 分支）中修复的 bug 通过 clean cherry-pick 提交到上游（KIYI671/AhabAssistantLimbusCompany）
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---

## 概述

将已验证的 bugfix 从 canary fork（`Small-tailqwq`）安全 port 到上游（`KIYI671`）。

## 硬性规则（违反则流程失败）

1. **必须创建 todo list**：每个 phase 必须作为独立 todo，完成一个才能进入下一个。
2. **必须用 git worktree**：禁止 `git switch`，worktree 隔离避免文件丢失和工作区污染。
3. **Phase 1 必须执行 canary 代码扫描**：不扫描 ≠ 跳过，扫描失败 = 流程中止。
4. **Phase 4 推送前必须 STOP 等待用户确认**：禁止在同一会话中 push。
5. **不贡献测试文件**：`tests/`、`test/` 下的文件一律排除。
6. **commit 必须纯净**：最后结果 diff 中每一行都必须是 bugfix 本身，不含 canary 特有代码。

## Phase 1: 预检与分析（Pre-Pick Analysis）

> ⚠️ **本阶段不创建任何分支、不做任何 git 操作。仅分析。**

### Step 1.1 — 创建 todo list

加载此 skill 后，**立即**用 `todowrite` 创建以下 todo 列表（不要跳过任何一项）：

```json
[
  {"content": "Phase 1: 拉取 upstream + 审查 commit + Canary 代码扫描", "status": "in_progress", "priority": "high"},
  {"content": "Phase 2: 创建 worktree + Cherry-pick + 净化", "status": "pending", "priority": "high"},
  {"content": "Phase 3: Diff 审计 + 构建/类型检查验证", "status": "pending", "priority": "high"},
  {"content": "Phase 4: 人工审查报告 → STOP → 等待用户确认推送", "status": "pending", "priority": "high"}
]
```

每个 phase 开始时标记为 `in_progress`，完成后立即标记为 `completed`。

### Step 1.2 — 拉取上游最新代码

```ps1
git fetch upstream
```

### Step 1.3 — 审查源 commit 内容

对用户指定的每个 commit hash：

```ps1
git show --stat <commit-hash>
git show <commit-hash>
```

注意：
- 哪些文件是 bugfix 核心文件？
- 哪些文件是附带改动（调试日志、`opencode/` 配置、CHANGELOG 等）？
- 是否包含 `tests/` 或 `test/` 下的测试文件？

输出一个**允许/排除文件清单**，格式：

```
=== commit <hash> 文件清单 ===
✅ 保留（bugfix 核心）:
   - tasks/mirror/in_shop.py
   - ...
❌ 排除（附带改动/测试/canary特有）:
   - tests/test_xxx.py (测试文件)
   - .opencode/xxx (opencode 配置)
   - issues/xxx (issue 归档)
   - CHANGELOG.md (上游有独立 changelog)
```

### Step 1.4 — Canary 特定代码扫描（⚠️ 最关键步骤）

> **并行策略**：以下 4 类扫描（A/B/C/D）互不依赖，使用 `Task` tool 同时派发 4 个 `explore` 子 agent 并行执行。主 agent 只负责收集结果、汇总报告（E）。这显著减少主线程上下文占用，扫描结果也更聚焦。

派发格式（4 个子 agent 并行，一次 tool call 中包含 4 个 Task）：

```
Task 1 — subagent_type: explore, description: "扫描 import 引用"
Task 2 — subagent_type: explore, description: "扫描配置键引用"
Task 3 — subagent_type: explore, description: "扫描 canary-only 函数引用"
Task 4 — subagent_type: explore, description: "扫描文件路径引用"
```

每个子 agent 的 prompt 中使用当前工作区路径和 commit hash，各自独立运行 `git show` + grep。

以下为 4 个子 agent 的独立任务定义：

#### 子 agent A: 新增 import 检查

```
任务：扫描 commit <hash> 的 diff 中所有新增 import 行，验证每个符号在 upstream/main 中是否存在。

步骤：
1. git show <hash> | Select-String "^\+.*(?:^import |^from )" 提取新增 import 行
2. 对每个被导入的符号，用 git grep "<symbol>" upstream/main 验证上游是否存在
3. 汇总返回：每个 import 的符号名、源文件行号、上游是否存在（存在/不存在）
4. 注意标准库（os, datetime, time, PIL 等）无需验证，直接标记为"安全"
```

#### 子 agent B: 配置键引用检查

```
任务：扫描 commit <hash> 的 diff 中所有 cfg.get_value/cfg.set_value/cfg.unsaved_set_value 调用，验证配置键在 upstream 中是否存在。

步骤：
1. git show <hash> | Select-String "cfg\.(get_value|set_value|unsaved_set_value)" 提取配置键引用
2. 对每个键名，用 git grep "\"<key>\"" upstream/main -- "module/config/" "*.yaml" 验证
3. 已知 canary 特有键直接标记（debug_shop, debug_*, lab_screenshot_obs, mirrorchyan_cdk, update_source 等）
4. 汇总返回：每个配置键、行号、上游是否存在
```

#### 子 agent C: Canary-only 函数/类引用检查

```
任务：扫描 commit <hash> 的 diff 中新增的函数/方法定义和调用，检测 canary 特有模式。

步骤：
1. git show <hash> 获取完整 diff
2. 搜索新增函数定义：def _is_*_debug*, def _debug_*, def _shop_debug* 等模式
3. 搜索引用：.opencode/, issues/, canary, dark/ 等 canary 特有路径字符串
4. 对疑似 canary 特有的函数名，用 git grep "<函数名>" upstream/main 验证上游是否存在
5. 汇总返回：可疑符号名、行号、是否为 canary 特有
```

#### 子 agent D: 文件/路径引用检查

```
任务：扫描 commit <hash> 的 diff 中新增的字符串字面量，检测引用 canary 专有路径。

步骤：
1. git show <hash> 获取完整 diff
2. 搜索字符串模式：logs/, .opencode/, issues/, assets/images/dark/, canary
3. 汇总返回：每个可疑路径、行号、风险等级
```

#### 主 agent 汇总（E）

4 个子 agent 完成后，主 agent 汇总输出 canary 代码扫描报告：

```
=== Canary 代码扫描报告 ===
🔴 严重（上游不存在，必须处理）:
   - Line +123: from module.ocr import ocr  → upstream/main 无此模块
   - Line +234: cfg.get_value("debug_shop")  → upstream 无此配置键
   - Line +456: _is_shop_debug_enabled()     → 引用上游不存在的 debug 开关
🟡 警告（需要审查）:
   - Line +789: auto.mouse_action_with_pos() → 确认 upstream 是否有此 API
🟢 安全（上游一定存在）:
   - import os / from datetime / from PIL import Image  → 标准库
   - Shop class 方法内的纯逻辑修改 → 核心 bugfix
```

如果存在 🔴 严重项 → **标记到问题清单，Phase 2 中必须处理**（要么排除该函数 block，要么手动改写为上游兼容版本）。

### Step 1.5 — Phase 1 完成检查

Phase 1 完成后，先向用户报告：
- 文件清单（允许/排除）
- Canary 扫描报告
- 预估需要手动处理的问题数量

**等待用户确认**后再进入 Phase 2。

## Phase 2: Worktree 隔离 + Cherry-pick 净化

### Step 2.1 — 创建 worktree

禁止在 `$ARGUMENTS` 当前工作区执行 `git switch`。始终创建独立 worktree：

```ps1
# 检查 .worktrees 是否存在且被 gitignore 忽略
git check-ignore -q .worktrees 2>$null; if ($LASTEXITCODE -ne 0) {
    Add-Content -Path .gitignore -Value ".worktrees/"
}

# 创建 worktree
git worktree add .worktrees/upstream-fix/<简短英文描述> upstream/main
Set-Location .worktrees/upstream-fix/<简短英文描述>
```

worktree 目录命名规范：`.worktrees/upstream-fix/<简短英文描述>`

### Step 2.2 — 在 worktree 中安装依赖

Worktree 不继承父工作区的 venv。需要确认依赖可用：

```ps1
uv sync --frozen
```

### Step 2.3 — Cherry-pick（净化模式）

**原则：先诊断，再 pick，不要盲 pick。**

根据 Phase 1 的文件清单和 canary 扫描报告，分情况处理：

#### 情况 A：commit 纯净（无 canary 代码混入，无测试文件）

```ps1
git cherry-pick -n <commit-hash>
git diff --cached --name-only    # 确认只有目标文件
# 如有意外文件：
git reset HEAD <意外文件>
git checkout -- <意外文件>
git commit -C <commit-hash>
```

#### 情况 B：commit 包含测试文件但无 canary 代码

```ps1
git cherry-pick -n <commit-hash>
git diff --cached --name-only
git reset HEAD tests/     # 排除测试文件
git checkout -- tests/
git commit -m "<原始提交信息>"
```

#### 情况 C：commit 包含 canary 特有代码（常见）

这是最危险的情况（PR #674 的根源）。**禁止全量 cherry-pick。**

处理策略优先级：

1. **如果 canary 代码在独立函数中**（如 `_is_shop_debug_enabled`, `_shop_debug_save` 等）：
   ```ps1
   git cherry-pick -n <commit-hash>
   git diff --cached          # 检查所有暂存改动
   # 手动撤销 canary-only 函数的添加（用 git checkout -p 或手动编辑）
   # 撤销引用这些函数的调用行
   # 撤销 canary-only import 行
   git diff --cached          # 再次确认暂存区纯净
   git commit -m "<原始提交信息>"
   ```

2. **如果 canary 代码与 bugfix 逻辑交织在同一函数中**：
   - 不要直接 commit。先手动编辑文件，移除 canary 特有代码，保留纯 bugfix
   - 提交时使用自定义 message，注明 "Backport of <original-hash>"

3. **如果无法安全分离**：
   - 报告用户：说明哪些行无法自动分离
   - 等用户提供手动修改方案

**净化后的 commit diff 检查清单：**
- [ ] 没有新增的 canary-only import（如 `from module.ocr import ocr`）
- [ ] 没有引用 canary-only 配置键
- [ ] 没有 debug 开关函数调用
- [ ] 没有 `tests/` 目录下的文件
- [ ] bugfix 核心逻辑完整保留

### Step 2.4 — Phase 2 完成

确认 worktree 中只有一个（或少量）干净 commit。

## Phase 3: 验证（Verification）

### Step 3.1 — Diff 审计

```ps1
git log --oneline upstream/main..HEAD
git diff upstream/main...HEAD --stat
git diff upstream/main...HEAD
```

逐行审查 diff，确保：

- [ ] 没有 canary 品牌相关改动（canary 图片路径、README 金丝雀标题、tagline）
- [ ] 没有 `.opencode/` 下的任何文件
- [ ] 没有 `issues/`、`logs/`、`test/`、`tests/` 本地产物
- [ ] 没有 `CHANGELOG.md` 改动
- [ ] 没有 `version.txt`、`config.example.yaml` 等配置文件的无关改动
- [ ] 新增的 import / 函数调用 / 配置键在上游均存在
- [ ] 文件列表与 Phase 1 清单一致

### Step 3.2 — 构建验证

```ps1
uv run python -m py_compile tasks/mirror/in_shop.py  # 对每个修改文件单独编译
# 如果项目有 type checker：
uv run ruff check <修改的文件路径>
```

> **如果编译/类型检查失败**：回退到 Phase 2，修复代码后重新验证。

### Step 3.3 — Phase 3 完成

输出验证报告：

```
=== 验证通过 ===
- Diff 审计：无 canary 特有代码混入
- 编译检查：所有修改文件通过
- Lint 检查：无新增问题
- 文件完整性：与 Phase 1 清单一致
```

## Phase 4: 人工审查 + 推送

### Step 4.1 — 生成审查报告

向用户输出完整的审查报告，包含：

```
## 上游贡献审查报告

### 基本信息
- 分支: fix/<描述>
- Worktree: .worktrees/upstream-fix/<描述>
- 基点: upstream/main (commit <hash>)
- 包含 commit: <hash-1>, <hash-2>

### 变更摘要
<git diff --stat 输出>

### Canary 扫描结果
<Phase 1 的扫描报告，标注已处理的问题>

### 验证结果
<Phase 3 的验证报告>

### 差异审查
<全量 git diff，或关键片段>

---
⚠️ **审查确认**：以上变更中不包含任何 canary 特定代码、测试文件或无关改动。
请确认后我将推送分支。
```

### Step 4.2 — STOP 并等待用户确认

输出报告后**必须停止**。不要执行 `git push`。

使用 `question` 工具询问用户：

> 以上是完整的审查报告。是否确认推送 `fix/<描述>` 到 `origin`（即 `Small-tailqwq/AhabAssistantLimbusCompany`）？

选项：
- "确认推送" — 执行 `git push origin fix/<描述>`
- "需要修改" — 用户指出需要调整的地方
- "取消" — 清理 worktree 并退出

### Step 4.3 — 推送（仅在用户确认后）

```ps1
git push origin fix/<描述>
```

推送后输出分支名和创建 PR 的 GitHub URL。

### Step 4.4 — 清理

```ps1
# 切回原工作区
Set-Location <原工作区路径>

# 删除 worktree
git worktree remove .worktrees/upstream-fix/<描述>
```

## 仓库信息

- 上游仓库：`KIYI671/AhabAssistantLimbusCompany`，remote 名 `upstream`
- 本仓库：`Small-tailqwq/AhabAssistantLimbusCompany`，remote 名 `origin`
- Worktree 目录：`.worktrees/upstream-fix/<描述>`
- Canary 代码模式速查：见附录

## 已知陷阱

### 陷阱 1：盲 pick 引入下游依赖

PR #674 的典型失败模式。Commit 中包含 `from module.ocr import ocr`、`_is_shop_debug_enabled()` 等 canary 特有代码，cherry-pick 时不做检查直接提交。

**对策**：Phase 1 的 canary 代码扫描（Step 1.4）是硬性要求，不能跳过。

### 陷阱 2：一次会话冲到 push

AI 倾向于在同一个会话中完成所有步骤（pick → commit → push），跳过中间验证。

**对策**：Phase 4 硬性 STOP，必须用 `question` 工具等待用户确认后才能 push。

### 陷阱 3：git switch 丢文件

在原始工作区直接 `git switch` 可能导致未追踪文件丢失或 stash 冲突。

**对策**：Phase 2 使用 `git worktree add`，独立目录完全隔离。

### 陷阱 4：worktree 依赖未初始化

Worktree 不继承父工作区的 venv/node_modules 等，直接运行命令会失败。

**对策**：Step 2.2 执行 `uv sync --frozen`。

### 陷阱 5：暂存区污染

`git status` 中 "Changes to be committed" 会意外带入预暂存文件。

**对策**：每次 `git commit` 前务必 `git diff --cached --stat`。

---

## 附录：Canary 代码模式速查表

以下模式在 diff 中出现时，必须标记为 canary 特有（除非上游也有完全相同的定义）：

| 类别 | 模式示例 | 检测方法 |
|------|---------|---------|
| 调试开关函数 | `_is_*_debug*()`, `_debug_*()`, `_shop_debug*()` | grep `def _` |
| 调试配置键 | `debug_shop`, `debug_*`, `lab_*` | grep `cfg.get_value` |
| Canary-only import | `from module.ocr import ocr` 等上游不存在的模块 | grep `+import` → 验证上游 |
| OBS 功能 | `obs_capture`, `lab_screenshot_obs` | grep 文本 |
| 更新源配置 | `mirrorchyan_cdk`, `update_source` | grep `cfg.get_value` |
| opencode 路径 | `.opencode/`, `issues/` | grep 字符串 |
| 金丝雀资产 | `canary`, `dark/` 主题图片路径 | grep 字符串 |
| 测试文件 | `tests/`, `test/` | git show --stat |
| CHANGELOG | `CHANGELOG.md` | git show --stat |
| 版本/配置 | `version.txt`, `config.example.yaml`, `config.yaml` | git show --stat |

> **关键原则**：宁可多标记、不可漏标记。不确定时标记为 🟡 警告并请求用户审查。
