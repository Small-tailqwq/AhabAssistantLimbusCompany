---
name: code-style
description: 通过自动化工具分析代码风格，评估 LLM 可读性，并提供修复建议以提升代码质量和 LLM 理解效率
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---

## 我的职责

分析代码库的代码风格，评估 LLM 可读性，按 ROI 排序输出修复建议，并执行安全修复。

## 触发条件

用户提及以下任一关键词时自动激活：
- 代码风格、代码规范、风格化、格式化
- ruff、lint、flake8
- LLM 阅读、LLM 可读性、上下文污染
- 通配符导入、裸 except、调试 print
- 询问"我的代码好不好读"类问题

## 工具

本技能依赖 `scripts/code_style_check.py`，通过六个维度评估代码对 LLM 的可读性：

| 维度 | 扣分权重 | 检测方式 |
|------|---------|---------|
| 通配符导入 | 15/处 | ruff F403/F405 |
| 超大文件 (>500行) | 10/文件 | 行数统计 |
| 裸 except | 8/处 | 静态分析 |
| 导入不在顶部 | 6/处 | ruff E402 |
| 调试 print | 5/处 | 字符串匹配 |
| 未使用导入 | 4/处 | ruff F401 |
| 未排序导入 | 3/处 | ruff I001 |
| 模糊变量名/未使用变量 | 2/处 | ruff E741/F841 |
| 超长行 | 1/处 | 字符串匹配 |

## 工作流

### 第 1 步 — 全量扫描

```ps1
uv run python scripts/code_style_check.py
```

输出包含：
1. 问题统计摘要
2. 修复建议（按 ROI 排序）
3. LLM 可读性最差 Top 10 文件
4. 通配符导入链源头列表

如需限定范围：
```ps1
uv run python scripts/code_style_check.py --path app/
uv run python scripts/code_style_check.py --path tasks/
```

### 第 2 步 — 分类处理

按优先级从高到低处理，但**绝不做无关清理**（参见 AGENTS.md）。

#### [CRITICAL] 通配符导入

最影响 LLM 理解的因素。`from X import *` 污染符号表，使 LLM 无法追踪变量来源。

**修复方式**：将 wildcard 替换为显式具名导入。

```ps1
# 1. 先确认被通配符导入的模块提供了哪些符号
rg "from app import" --include "*.py"

# 2. 手动替换为显式导入（不可自动化，需判断符号来源）
```

**何时修**：开发涉及这些文件时顺手修。不要创建独立 PR 只为清理导入。

#### [HIGH] 导入排序 & 未使用导入（可自动修复）

```ps1
uv run ruff check --select I,F401 --fix .
```

这 2 条规则在 ruff 中可安全自动修复，不会改变逻辑。

#### [MEDIUM] 裸 except

将 `except:` 改为 `except Exception:`。**只在编辑涉及该代码段时顺手改**，不要全量批量替换（部分裸 except 可能是故意的）。

```ps1
# 只查看，不自动修复
uv run ruff check --select E722 .
```

#### [LOW] 调试 print

将业务代码中的 `print()` 替换为 `log.debug()` / `log.info()`。scripts/ 和 test/ 目录下的 print 属于 CLI 正常输出，无需处理。

### 第 3 步 — 验证

```ps1
uv run python scripts/code_style_check.py --verify
```

## 设计原则

1. **只修改涉及的文件**：不做全量清理，不为风格创建独立 PR
2. **不改遗留警告**：ruff 预存的 E722/E501 不在此技能范围内强行修复
3. **安全优先**：只有 I001/F401/F541/F841 可自动修复
4. **LLM 视角**：评分权重以 LLM 阅读体验为准，不是严格的 PEP 8 合规性

## 评分解读

- **总分 < 20**：LLM 友好，符号清晰，噪音低
- **总分 20-50**：可接受，有改进空间
- **总分 50-100**：注意，存在较多噪音来源
- **总分 > 100**：需要关注，LLM 理解成本显著增高

## 注意事项

- 工具自身的 `scripts/code_style_check.py` 也会出现在报告中（吃自己狗粮）
- 通配符导入链分析目前不支持模块间传递（如 `app → base_tools → base_combination`），只检测直接 wildcard 声明
- E501（行长度）被 project 级忽略，不在扫描范围
