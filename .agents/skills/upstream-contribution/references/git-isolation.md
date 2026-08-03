# Git 隔离与分支拓扑

创建或改动贡献 worktree 前使用本文件。

## 预检

不改变原工作区地检查：

```powershell
git status --short
git remote -v
git branch --show-current
git worktree list --porcelain
git fetch upstream
git rev-parse upstream/main
```

确认预期拓扑，而不是假设 remote 名：

- 下游 fork 通常经 `origin` 推送；
- 贡献目标通常是 `upstream/main`；
- PR head 分支必须存在于上游接受 PR 的某个 remote 上。

remote 与拓扑不符时报告实际 URL，并在添加或改写 remote 前询问。

## 创建 worktree

选择唯一 slug。一条命令同时创建分支与 worktree：

```powershell
$branch = "upstream-contrib/<slug>"
$worktree = ".worktrees/upstream-contribution/<slug>"
git worktree add -b $branch $worktree upstream/main
```

贡献工作绝不使用这种形式：

```powershell
git worktree add <path> upstream/main
```

它会把 remote 跟踪提交检出为游离 `HEAD`，不留下可推送的命名分支。

在 worktree 内验证结果：

```powershell
git -C $worktree branch --show-current
git -C $worktree rev-parse HEAD
git -C $worktree merge-base --is-ancestor upstream/main HEAD
git -C $worktree status --short
```

## base 更新

PR 存在前，优先从最新上游 base 重建未改动的贡献分支。已有提交后，rebase 前先 fetch 并检查分歧。Rebase 或 force-push 会改写远端历史；取得当前任务要求的授权，绝不隐藏改写。

不要把下游 `main` 合并进贡献分支。贡献分支必须只含上游 base 历史加上游兼容的贡献提交。

## 冲突处理

cherry-pick、rebase 或合并冲突时：

1. 停下并列出冲突路径；
2. 读 base、upstream 与预期行为；
3. 按行为契约与上游代码形态逐冲突解决；
4. 像手写改动一样运行同样的审阅与检查；
5. 绝不用全部 `ours` 或全部 `theirs` 走捷径。

必要时只中止进行中的操作；不要 reset 或 clean 用户的原工作区。

## 清理

worktree 清理可选，且只在分支不再需要后进行。展示精确 worktree 路径，确认其中没有唯一的未推送工作再移除。不要因为 PR 已合并就删除被忽略的 worktree。
