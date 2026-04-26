---
name: canary-release
description: 发布金丝雀（canary）预览版本，包含版本号 bump、tag、CI 触发及 GitHub Release 管理
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---

## 我的职责

当需要发布一个新的金丝雀预览版时，我会执行以下完整流程：

1. **更新版本号** — 修改 `assets/config/version.txt`，格式 `X.Y.Z-canary.N`
2. **更新 CHANGELOG** — 在 `CHANGELOG.md` 的 `[Unreleased] — Canary` 节下记录本次变更
3. **提交并推送** — `git add && git commit && git push origin main`
4. **创建 Tag** — `git tag -a "vX.Y.Z-canary.N" -m "..." && git push origin vX.Y.Z-canary.N`
5. **等待 CI 构建** — 约 3-4 分钟，`Release` workflow 完成自动上传 `AALC_*.7z`
6. **更新 Release 属性** — CI 自动创建的 Release 只有 tag name 作为标题且缺少说明。需要用 GitHub API PATCH 补充：
   - `name`: 设为 `"vX.Y.Z-canary.N — 金丝雀预览版"`
   - `body`: 写入变更说明 Markdown
   - `prerelease`: 设为 `true`
   - 通过 `requests.patch(url, headers=BearerToken, json=payload)` 完成

## 何时使用我

当项目需要向测试用户分发预览版本时使用。典型场景：
- 累积了足够的功能/修复改动，需要测试验证
- 修复了上一个 canary 版本的关键问题，需要重新发布

## 注意事项

- 金丝雀版本号始终包含 `-canary` 后缀（例如 `1.5.0-canary.2`）
- 版本号含 `-canary` 时，应用会自动切换到金丝雀更新通道（检查本仓库而非上游）
- CI 提交后需等待 `Release` workflow 完成（约 3-4 分钟），然后检查 Release 是否已标记为 prerelease
- 如果 `prerelease` 未自动设为 `true`，需要通过 GitHub API PATCH 更新
