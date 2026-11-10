# Agent 与 MCP

`AALC.Mcp` 是当前用户的 stdio MCP 服务，连接正在运行的 AAALC 桌面端。任务、截图和配置操作由桌面端执行。桌面端和 MCP 均可使用普通用户权限运行，无需安装服务或开放网络端口。桌面分身仍遵循其 Windows 权限要求。

## 连接

构建 `AAALC.slnx` 后，将下面的服务配置添加到 Agent 的 MCP 配置中，替换绝对路径：

```json
{
  "mcpServers": {
    "aaalc": {
      "command": "C:\\path\\AAALC.Mcp.exe",
      "args": ["--desktop", "C:\\path\\AAALC.exe"]
    }
  }
}
```

源码构建的服务为 `src/AALC.Mcp/bin/Release/net10.0-windows/AAALC.Mcp.exe`；发布包中为 `mcp/AAALC.Mcp.exe`。发布包的服务自动查找上一级的 `AAALC.exe`，可以省略 `--desktop`。源码运行可使用 `dotnet run --no-build --project src/AALC.Mcp -c Release -- [参数]`，先完成构建，保持 stdout 只包含 MCP 消息。

Codex CLI 可以直接注册发布包中的服务：

```powershell
codex mcp add aaalc -- "C:\path\AAALC\mcp\AAALC.Mcp.exe"
```

默认 profile 与桌面端相同，位于数据根下的 `profile/`。使用独立配置时给 MCP 传 `--profile <绝对目录>`；`aalc_open` 会以此 profile 启动桌面端。连接已有实例时，两端须使用相同 profile、Windows 用户与权限级别。每个 profile 只有一个 Agent 接口实例；第二个桌面实例会显示接口启动错误。日志写入 stderr。

## 工具

| 工具 | 行为 |
|---|---|
| `aalc_open` | 连接或启动 AAALC，不启动游戏 |
| `aalc_launch_game` | 启动游戏；已有窗口时复用 |
| `aalc_close_game` | 空闲时请求关闭游戏，30 秒未退出则结束进程 |
| `aalc_game_action` | 空闲时用最新截图的一次性 `actionToken` 发送点击或按键，处理已核对的弹窗 |
| `aalc_get_status` | 返回任务编号、状态、结果、事件时间、帧龄、录制目录和游戏窗口 |
| `aalc_start_task` | `kind=launch/daily/harvest/mirror`，使用启动时的配置快照 |
| `aalc_stop_task` | 协作取消；可指定 `taskId` 防止停止另一个任务 |
| `aalc_get_screenshot` | 返回 PNG 图片和非 C 盘证据路径；运行时复用最近观察帧 |
| `aalc_get_events` | `after` 游标分页，返回 `nextCursor`；每次最多 200 条，保留当前任务最近 1000 条 |
| `aalc_get_config` | 返回当前界面配置、profile 和 `revision` |
| `aalc_update_config` | 空闲时按 `revision` 验证并保存 JSON `patch`，同步界面 |

启动和关闭游戏、启动任务均立即返回。随后轮询 `aalc_get_status`，检查 `isRunning`、`taskId` 和 `result.outcome`。停止后等到 `isRunning=false` 再修改配置、关闭游戏或启动下一项；正在运行时拒绝重复任务与配置更新。

`taskId` 标识一次启动操作；事件中的 `RunId` 属于对应的日常或镜牢录制会话。一键计划各步骤的 `run.recording` 事件分别给出该步骤的录制目录。

配置 patch 的字段区分大小写，未知字段和不合法选项会报错；对象递归合并，数组整体替换。例如先读取配置，再使用返回的 revision 提交：

```json
{
  "revision": "从 aalc_get_config 读取的 revision",
  "patch": {
    "Launch": { "Daily": false, "Harvest": false, "Mirror": true },
    "Mirror": { "Runs": 1 }
  }
}
```

配置版本同时反映界面草稿和磁盘配置；任一发生变化都需重新读取。运行任务持有自己的快照。任务失败或取消不会自动重跑已完成内容；先核对当前画面和录制，再决定恢复方式。

## 监督与诊断

运行期间的截图来自生产观察器，不创建第二个 `GameWindow`；`ageMilliseconds` 表示帧龄，`source=observation` 表示最近观察帧，`source=clone-preview` 表示经过缩小和压缩的分身预览。启动游戏尚无观察帧时会提示稍后重试；空闲时截图使用生产截图入口并占用任务槽。

用 `lastEvent.At` 与帧龄判断是否仍在观察，`lastProgress` 提供最近的业务事件。状态响应省略底层观察详情，业务详情最多 512 字符；通过 `aalc_get_events` 读取完整事件。事件游标早于 `oldestSequence` 时，从 `recordingDirectory/events.jsonl` 读取完整记录。`run.recording` 在加载模型和连接游戏前公布证据目录，失败时仍可定位 `options.json` 和已产生的事件。

截图写入数据根的 `screenshots/`，遵循 `EvidencePaths` 的非 C 盘与目录链接检查。游戏输入仍经 `GameSession` / `GameWindow` 的窗口所有权、帧时效、坐标和取消检查。

空闲截图会短暂持有生产窗口并返回 `actionToken`。令牌最多有效五秒，只能发送一次恢复动作；超时、新截图或开始任务都会使它失效并释放窗口。`aalc_game_action` 的 `action=click` 使用截图原始像素坐标 `x/y`，`action=key` 使用 `GameKey` 名称。运行中截图不提供操作令牌；恢复动作不自动重试，完成后需重新截图确认页面变化。

SDK 使用官方 [MCP C# SDK](https://github.com/modelcontextprotocol/csharp-sdk)。
