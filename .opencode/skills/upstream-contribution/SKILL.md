---
name: upstream-contribution
description: 将本仓库（canary 分支）中修复的 bug 通过 clean cherry-pick 提交到上游（KIYI671/AhabAssistantLimbusCompany）
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---

## 我的职责

当你确认某个 fix commit 已经在本仓库验证通过、可以贡献回上游时，我会执行以下流程：

### 关键原则

**commit 必须纯净**：待贡献的 commit 中每一行改动都必须是该 bugfix 的一部分。混入无关文件（如预暂存的工作区改动、其他分支的调试日志）会导致 cherry-pick 污染上游历史。

### 前置条件

- 你明确告诉我**需要贡献的 commit hash**（一个或多个）
- 当前 `main` 分支上这些 commit 是已验证的 bugfix
- 工作区 clean（无未提交改动）—— 如有未提交改动，先 `git stash` 再继续

### 第 0 步（新增）— 审查 commit 内容是否纯净（非常重要）

```ps1
git show --stat <commit-hash>                      # 确认改了哪些文件
git show <commit-hash>                             # 逐行审查全部变更
```

逐一检查每个 commit：
- **是否包含非此 bugfix 的文件？** 如果混入了其他预暂存或不相关的改动（如调试日志、`opencode/` 技能文件等），必须先拆分 commit：
  ```ps1
  git reset --soft HEAD~1                           # 拆包
  git reset HEAD <无关文件>                          # 排除无关文件
  git commit -m "原提交信息"                         # 只提交 bugfix 文件
  git add <无关文件> && git commit -m "chore: ..."   # 无关文件单独提交
  ```
- 是否只包含 bugfix 代码？没有金丝雀专属改动（canary 品牌、金丝雀版本号、README 金丝雀标识、`opencode/` 配置等）？
- 是否引入了上游没有的新依赖或配置？
- 修改的文件是否上游存在且逻辑一致？

> **💡 经验教训**：如果 commit 是通过 `git commit` 带入了已暂存但无关的文件（常见于先 `git add` 了调试代码），就必须在第 0 步拆分干净，不能带着脏数据 cherry-pick。

### 第 2 步 — 从上游拉取最新代码，创建 fix 分支

```ps1
git fetch upstream
git switch -c fix/<简短英文描述> upstream/main
```

分支基点永远是最新的 `upstream/main`，不是本地的 `main`。

### 第 3 步 — Cherry-pick 修复 commit

优先使用 `cherry-pick -n`（`--no-commit`）分阶段处理，方便排除意外混入的文件：

```ps1
git cherry-pick -n <commit-hash-1> [<commit-hash-2> ...]
# 检查暂存区是否引入了不应有的文件
git diff --cached --name-only
# 如果包含无关文件，排除它：
git reset HEAD <无关文件>
git checkout -- <无关文件>       # 还原为上游版本
```

确认暂存区只有目标文件后：

```ps1
git commit -C <commit-hash>     # 使用原始提交信息
```

**如果 cherry-pick 遇到冲突**：
1. `git diff --name-only --diff-filter=U` 查看冲突文件
2. 对属于**无关文件**的冲突 → `git checkout --theirs <file>` + `git add <file>`（取上游版本，丢弃我们的改动）
3. 对属于**目标 bugfix** 的冲突 → 手动解决后 `git add <file>`
4. 全部解决后 `git cherry-pick --continue`，绝不 `--skip` 或暴力合并

> **💡 经验教训**：`-n` 模式是防止脏数据混入的安全网。即使第 0 步已经拆分，cherry-pick 的自动合并仍可能把不应有的文件带入暂存区。养成 `git diff --cached --name-only` 检查的习惯。

### 第 4 步 — 严格审查分支纯度（最重要步骤）

```ps1
git log --oneline upstream/main..HEAD              # 确认只有目标 commit
git diff upstream/main...HEAD --stat               # 文件级总览
git diff upstream/main...HEAD                      # 逐行审查全部变更
```

检查清单：
- ❌ 没有 `config.yaml` 的改动（用户配置文件，上游不追踪）
- ❌ 没有金丝雀品牌相关改动（`canary` 图片、README 金丝雀标题、tagline 等）
- ❌ 没有 `.opencode/` 下的任何文件
- ❌ 没有 `issues/`、`logs/`、`test/` 本地产物
- ❌ 没有 `CHANGELOG.md` 改动（上游有自己的 changelog）
- ❌ 没有 `version.txt`、`config.example.yaml` 等配置文件的无关改动
- ❌ 没有在 cherry-pick 中用 `--theirs` 排除过的无关文件残留
- ✅ 文件列表与第 0 步确认的目标文件完全一致
- ✅ 只包含 bugfix 的逻辑代码修改

### 第 5 步 — 推送分支（不创建 PR）

```ps1
git push origin fix/<简短英文描述>
```

推送完成后我会告诉你分支名称，你可以在 GitHub 上手动创建 PR。

## 何时使用我

- 金丝雀版本中修复了某个 bug，需要回馈上游项目
- 修复已在本仓库验证通过，commit 记录干净

## 注意事项

- 上游仓库：`KIYI671/AhabAssistantLimbusCompany`，remote 名 `upstream`
- 本仓库：`Small-tailqwq/AhabAssistantLimbusCompany`，remote 名 `origin`
- **绝不**推送金丝雀专属功能或改动到上游
- 提交信息保持原始内容，**不要加** "Canary"、"金丝雀" 等标记
- 如有多个 commit 是同一 bug 的拆分修复，优先 squash 后再 cherry-pick
- 推送后如需补充修改，**不 rebase 已推送的分支**，用额外 commit 叠加

## 已知陷阱 & 常见问题

### 陷阱 1：预暂存文件污染 commit

`git status` 中 "Changes to be committed" 的文件会在下一次 `git commit` 时一并打入，即使你没有 `git add` 它。

**症状**：cherry-pick 后发现 fix 分支多了一个无关文件。
**预防**：提交前务必 `git diff --cached --stat` 确认暂存区。
**修复**：用第 0 步的拆分流程，或者用 `cherry-pick -n` + `git reset HEAD <文件>` 排除。

### 陷阱 2：cherry-pick 自动合入无关文件

有时 cherry-pick 的自动合并会将本不应包含的文件带入暂存区（尤其是当源 commit 和被 cherry-pick 的 commit 有相似上下文时）。

**对策**：始终使用 `git cherry-pick -n`，然后 `git diff --cached --name-only` 检查暂存区文件列表是否纯净。

### 陷阱 3：冲突解决时误保留无关文件的改动

冲突文件中，如果某文件不属于此 bugfix，应当用 `--theirs` 接受上游版本，而不是手动合并。

**判断原则**：文件是否出现在第 0 步确认的目标文件列表中？不在列表中 → `--theirs`。
