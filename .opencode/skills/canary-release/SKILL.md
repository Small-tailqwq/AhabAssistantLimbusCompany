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
   - `prerelease`: **不设置**（保留为 `false`，避免部分更新渠道无法读取版本）

### 通过 GitHub API 更新 Release 的完整流程

**Step 1: 获取 Release ID**
```powershell
$token = powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Ko_teiru\bin\github-mcp-server\read-credential.ps1"
$headers = @{"Authorization" = "token $token"}
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}" -Headers $headers
$releaseId = $release.id
```

**Step 2: 更新 Release 名称和内容**

> ⚠️ **不要使用 `Invoke-RestMethod` + `ConvertTo-Json` + here-string** —— 该组合会因 Markdown 特殊字符（`` ` ``、`"`、`@`）导致 `ConvertTo-Json` 生成畸形 JSON，表现为 `Invoke-RestMethod` 报 "response ended prematurely" 或 body 为空。

使用 `Invoke-WebRequest -UseBasicParsing` + 手写单引号 JSON（`\r\n` 换行）：

```powershell
$token = powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Ko_teiru\bin\github-mcp-server\read-credential.ps1"
$headers = @{
    "Authorization" = "token $token"
    "Accept" = "application/vnd.github.v3+json"
}

# 手写 JSON 字符串（单引号，\r\n 换行），避免 ConvertTo-Json 转义 Markdown 特殊字符
$body = '{"name":"vX.Y.Z-canary.N — 金丝雀预览版","body":"# 金丝雀预览版 vX.Y.Z-canary.N\r\n\r\n### 分类标题\r\n\r\n- feat: 新功能描述\r\n- fix: 修复描述\r\n\r\n[查看完整变更](https://github.com/{owner}/{repo}/compare/v{prev}...v{new})"}'

Invoke-WebRequest -Uri "https://api.github.com/repos/{owner}/{repo}/releases/$releaseId" `
    -Headers $headers `
    -Method Patch `
    -Body $body `
    -ContentType "application/json; charset=utf-8" `
    -UseBasicParsing
```

**为什么不用 `Invoke-RestMethod`：**
- `Invoke-RestMethod` 会解析响应体，当 PATCH 返回的 JSON 意外或空时抛出 "response ended prematurely"
- `Invoke-WebRequest -UseBasicParsing` 不做自动解析，只要 HTTP 200 就表示成功

**关键点：**
- Token 从 Windows Credential Manager 读取（`read-credential.ps1`），不要硬编码
- JSON body 使用**单引号字符串** + 手动 `\r\n` 换行，**禁止** `ConvertTo-Json`（会错误转义 Markdown）
- 必须指定 `charset=utf-8` 否则中文会乱码
- Release ID 比 tag name 更可靠（避免 tag 格式问题）
- Validate：执行后 `Invoke-RestMethod -Uri "...releases/tags/v..."` 检查 `name` 和 `body` 是否更新

## 何时使用我

当项目需要向测试用户分发预览版本时使用。典型场景：
- 累积了足够的功能/修复改动，需要测试验证
- 修复了上一个 canary 版本的关键问题，需要重新发布

## 注意事项

- 金丝雀版本号始终包含 `-canary` 后缀（例如 `1.5.0-canary.2`）
- 版本号含 `-canary` 时，应用会自动切换到金丝雀更新通道（检查本仓库而非上游）
- CI 提交后需等待 `Release` workflow 完成（约 3-4 分钟），然后检查 Release 是否已标记为 prerelease
- 如果 `prerelease` 未自动设为 `true`，需要通过 GitHub API PATCH 更新
- **Windows CI 编码陷阱**：`scripts/build.py` 中的 `print()` 不能包含非 ASCII 字符（中文、`→`、`✓` 等），否则会触发 `UnicodeEncodeError` 导致构建失败。所有输出必须使用纯 ASCII

### 版本兼容性

`X.Y.Z-canary.N` 不是 [PEP 440](https://peps.python.org/pep-0440/) 合法的预发布后缀，`packaging.version.parse()` 会抛出 `InvalidVersion`。`module/update/check_update.py` 中的 `_normalize_version()` 在调用 `parse()` 前将 `-canary.` 替换为 `dev`（`1.5.0-canary.8` → `1.5.0dev8`）。**对外格式不变**：`version.txt`、git tag、GitHub Release 仍使用 `X.Y.Z-canary.N`，仅在内部比较时归一化。`devN < release`，符合 canary pre-release 语义。

### Mirror酱 已移除

本分支（金丝雀版）已移除全部 Mirror酱（MirrorChyan）代码：`check_update.py` 仅保留 GitHub 源，`setting_interface.py` 中的更新源选择器和 CDK 输入卡已删除，`config_typing.py` 中对应的 `update_source` 和 `mirrorchyan_cdk` 字段已清理。

## 常见问题

### CI 构建失败：UnicodeEncodeError
- **症状**：`build & bundle` 步骤失败，日志显示 `'charmap' codec can't encode character '\u2192'`
- **原因**：GitHub Actions Windows runner 使用 cp1252 编码，无法处理 Unicode 字符
- **修复**：将 `build.py` 中的 `→` 替换为 `->`，中文替换为英文
- **预防**：提交前运行 `python -c "检查 scripts/build.py 中 print 的非 ASCII 字符"`

### Release Body 为空或 PATCH 失败
- **症状**：API PATCH 返回成功但 `name`/`body` 未变，或 `Invoke-RestMethod` 报 "response ended prematurely"
- **原因**：`ConvertTo-Json` 对 Markdown 特殊字符（反引号 `` ` ``、双引号 `"`、`@`）进行了错误的 JSON 转义，HTTP 层面虽返回 200 但 GitHub 服务端解析 JSON body 失败
- **修复**：改用 `Invoke-WebRequest -UseBasicParsing` + 手写单引号 JSON 字符串（`\r\n` 换行），参考 Step 2 示例代码
- **预防**：PATCH 后务必用 `Invoke-RestMethod -Uri "...releases/tags/v..."` 验证 `name` 和 `body` 字段已更新

### GitHub MCP 认证失败 (401)
- **症状**：MCP 工具返回 `Bad credentials`
- **原因**：Token 过期或未正确配置
- **修复**：使用 `store-credential.ps1` 重新存储 token 到 Windows Credential Manager

### 检查 CI 构建状态
GitHub MCP 不支持 Actions API，需要直接调用 GitHub API：
```powershell
$token = powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Ko_teiru\bin\github-mcp-server\read-credential.ps1"
$headers = @{"Authorization" = "token $token"}

# 获取 workflow run 状态
$run = Invoke-RestMethod -Uri "https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}" -Headers $headers
Write-Host "Status: $($run.status) | Conclusion: $($run.conclusion)"

# 获取失败的 job 详情
$jobs = Invoke-RestMethod -Uri "https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs" -Headers $headers
foreach ($j in $jobs.jobs) {
    Write-Host "Job: $($j.name) | Conclusion: $($j.conclusion)"
    foreach ($s in $j.steps) {
        if ($s.conclusion -eq "failure") {
            Write-Host "  FAILED: $($s.name)"
        }
    }
}
```
