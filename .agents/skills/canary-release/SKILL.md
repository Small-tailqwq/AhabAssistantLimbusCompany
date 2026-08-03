---
name: canary-release
description: 准备、发布、验证、修复或回滚 AALC 金丝雀预发布版本，包括隔离发布工作区、版本与更新日志更新、构建与更新协议检查、tag、GitHub Actions、发布说明、产物清单、通道行为与发布后报告。任何 canary 发布操作都使用本技能。
---

# AALC Canary 发布

把 canary 当作有状态的发布事务。仅有 tag 或已上传的压缩包不算完成；发布必须能通过既定通道被消费，且产物与说明必须匹配打 tag 的源码。

## 权限与安全

- 改动 git 状态前先检查原工作区；保留无关改动。
- 工作区脏或发布准备超过单文件编辑时，优先在隔离 worktree 中建命名发布分支。
- 绝不打印或提交 token。使用已认证的 `gh` 或凭据助手。
- push、打 tag、编辑 Release、删除产物/tag、重跑远端工作流都属于外部写入，只执行已授权的范围。
- 在第一步不可逆或外部可见操作之前，展示精确的分支、提交、tag、remote 与发布变更。

## 预检

1. 确认目标版本、上一个发布 tag、目标提交与发布通道。
2. 检查 `git status --short`、remotes、已有 tag，以及同版本是否已有 Release。
3. 确认用户可见变更与已知风险。
4. 从仓库工作流与构建脚本确认当前发布策略，不要凭记忆。
5. 除非更新协议兼容性确实变化，否则保持当前 `bootstrap_version`。
6. 协议 sidecar 通过构建脚本生成，绝不手改。

常见发布源文件是 `assets/config/version.txt` 与 `CHANGELOG.md`。不要修改用户 `config.yaml`。

## 准备与审阅

只更新发布范围内的文件。若代码或工作流需要发布阻断性修复，把该改动单独留作可审阅项。

检查精确的发布 diff，然后按触及区域选择检查：

```powershell
uv run python -m py_compile scripts\build.py
uv run python .\scripts\build.py --version dev
uv run python .\scripts\check_i18n.py --update
```

若 `scripts/build.py` 有改动，其控制台输出必须保持 ASCII 以兼容 Windows cp1252 CI。提交前对发布代码或工作流改动运行 `code-review`。

## 提交与打 tag 关口

push 之前：

- 展示版本与上一个 tag；
- 展示 `git diff --stat` 及版本/更新日志 diff；
- 展示计划的中文提交信息与附注 tag；
- 确认目标 remote 与源提交；
- 取得尚未授予的外部写入确认。

只在已验证的发布提交上创建附注 tag。push 前用 `git rev-parse <tag>^{commit}` 验证。不带 force 地推送分支与 tag。

## 跟进 CI 到匹配的 SHA

监控目标 tag 触发的工作流，确认它构建的是预期提交。一次成功的无关运行不算数。

失败时检查失败任务与日志，判断原因是源码、环境、凭据还是发布状态；通过已审阅的提交与新的有意 tag 状态修复源码，并重跑本地检查与匹配的远端工作流。不要静默重定向已发布的 tag。

## 验证 GitHub Release

一个可消费的 canary 必须满足：

- release tag 与目标提交匹配；
- release 标记为 prerelease；
- 恰好存在一个 `AALC_<version>.7z`；
- 恰好存在一个 `AALC.update_manifest.json`；
- 稳定专属的校验和策略在适用处仍然满足；
- 没有重复、过期或错误版本的产物；
- manifest 与压缩包来自匹配的工作流运行；
- canary 通道能发现该 prerelease，同时 stable 过滤保持不变。

这些检查全部通过前不要对外宣布。

## 发布说明与最终报告

GitHub Release body 是用户可见的事实来源，必须与 `CHANGELOG.md` 一致。用 notes 文件配合 `gh release edit`，避免 shell 转义错误。

读 [references/release-notes.md](references/release-notes.md) 了解要求的标题、正文格式与最终报告结构。

## 恢复

产物、tag、manifest 或通道状态异常时，先读 [references/recovery.md](references/recovery.md) 再进行任何删除或 tag 变更。
