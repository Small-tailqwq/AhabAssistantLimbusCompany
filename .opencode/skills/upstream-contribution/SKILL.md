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

### 前置条件

- 你明确告诉我**需要贡献的 commit hash**（一个或多个）
- 当前 `main` 分支上这些 commit 是已验证的 bugfix
- 工作区 clean（无未提交改动）

### 第 1 步 — 审查待贡献的 commit

```ps1
git log --oneline <commit-hash> -1                 # 确认提交信息
git show --stat <commit-hash>                      # 确认改了哪些文件
```

逐一检查每个 commit：
- 是否只包含 bugfix 代码？没有金丝雀专属改动（canary 品牌、金丝雀版本号、README 金丝雀标识、`opencode/` 配置等）？
- 是否引入了上游没有的新依赖或配置？
- 修改的文件是否上游存在且逻辑一致？

### 第 2 步 — 从上游拉取最新代码，创建 fix 分支

```ps1
git fetch upstream
git switch -c fix/<简短英文描述> upstream/main
```

分支基点永远是最新的 `upstream/main`，不是本地的 `main`。

### 第 3 步 — Cherry-pick 修复 commit

```ps1
git cherry-pick <commit-hash-1> [<commit-hash-2> ...]
```

如遇冲突，解决后 `git cherry-pick --continue`，绝不 `--skip` 或暴力合并。

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
