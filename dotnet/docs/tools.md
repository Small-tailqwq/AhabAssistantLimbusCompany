# 工具箱

侧栏“工具箱”提供从 fork 迁移的零协汉化、新手提示和游戏截图。实现使用 .NET 与 Avalonia；打开应用和工具页不会请求网络或读取存档。

## 零协汉化

工具共用“设置 → 游戏与资源”中的游戏安装目录，可手动输入或浏览选择。未配置目录时，启动后从 Steam 注册表和库清单自动查找；“搜索”会重新查找并保存，可用于恢复误改的路径。搜索覆盖当前用户、本机的 32/64 位注册表及 Steam 的其他库，只接受同时包含 `LimbusCompany.exe` 和 `LimbusCompany_Data` 的目录。

路径处理保留空格、括号和中文，支持带引号的粘贴路径及环境变量；Steam 库文件中的双反斜杠按 VDF 转义还原。当前 profile 的 `GameExecutablePath` 保存对应程序的完整路径，独立于 Python 配置。

设置目录后检查汉化更新。当前版本读取语言目录中的 `.llc_version`；已有目录但没有标记时显示“未记录版本”，仍可安装。

版本与说明来自[零协 GitHub Release](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/latest)。工具从 Release 的 `assets` 中选择 `LimbusLocalize_<tag>.zip`，使用附件的 `browser_download_url`。检查最多等待 15 秒，安装最多等待 3 分钟；GitHub API 限流会显示错误。汉化文件由零协提供，遵循其 CC BY-NC-SA 4.0 许可。

安装前退出游戏。下载完成后，存在 Release SHA-256 时核验摘要，并检查全部 ZIP 路径。工具只接收 `LimbusCompany_Data/Lang/LLC_zh-CN/` 下的内容，拒绝越界路径和符号链接。文件先解压到语言目录旁的临时目录，完成后写入版本标记。

原 `LLC_zh-CN` 目录重命名为 `LLC_zh-CN.backup-<时间>-<随机后缀>`，再将完整新目录移入；提交失败时恢复原目录。备份路径显示在操作记录中。恢复旧包时退出游戏，将当前语言目录移开，再把对应备份目录改名为 `LLC_zh-CN`。工具不自动删除备份。

启动游戏后，在游戏语言设置中选择 `LLC_zh-CN`。

## 新手提示

退出游戏后，可关闭或恢复本机 Windows 用户的引导、勾选框和对话框提示。存档位于 `%USERPROFILE%/AppData/LocalLow/ProjectMoon/LimbusCompany/save_slot_*.json`；工具从 `HKCU/Software/ProjectMoon/LimbusCompany` 的 `LocalSave.LocalGameOptionData` 项读取 AES 密钥与 IV，只读取注册表。

存档采用 Base64 与 AES-CBC/PKCS7。工具先解密并准备全部槽位，再逐个原子替换有变化的存档；每次替换将原始文件保存在同目录的 `save_slot_*.json.aaalc-backup-<时间>-<随机后缀>`。无变化的槽位不写入。未知模型与其他存档字段保持原值；关闭提示时补充旧版工具已定义的缺失模型，并保留已有的教程 ID。

“恢复提示”重新开启相应布尔状态，保留已读公告列表。恢复某次操作前的完整内容，需要退出游戏后用对应备份覆盖原存档。取消或写入失败时，已完成的槽位及其备份保留，操作记录列出成功写入的文件。

Android 与模拟器存档工具保留在 Python 入口。

## 游戏截图

刷新并选择游戏窗口后截图。采集复用 `GameWindow` 的客户区截图、15 秒等待上限与新旧实例互斥，不发送输入。PNG 使用原始客户区尺寸，画面同时更新到现有预览。

截图位于数据根的 `screenshots/screenshot_<时间>.png`，默认 `D:/AALCData/screenshots/`；`AALC_DATA_ROOT` 可指定其他本地非 C 盘目录。“打开截图目录”打开同一位置。

## 运行与停止

工具操作与日常、镜牢、邮件、场景回放共用运行状态，同一窗口内同时执行一项任务。网络、解压和存档遍历检查取消；停止按钮、窗口内 Esc 与关闭窗口使用现有协作式停止。语言目录提交和单个存档替换完成当前原子操作后返回。

## 实现入口

| 功能 | fork 参考 | AAALC 实现 |
| --- | --- | --- |
| 汉化 | [llc_localization.py](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/tools/llc_localization.py) | [LlcLocalization.cs](../src/AALC.Runtime/Tools/LlcLocalization.cs) |
| 新手提示 | [tutorial_skip.py](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/tools/tutorial_skip.py) | [TutorialSave.cs](../src/AALC.Runtime/Tools/TutorialSave.cs)、[GameFiles.cs](../src/AALC.Platform.Windows/Tools/GameFiles.cs) |
| 截图 | [screenshot_module.py](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/tools/screenshot_module.py) | [MainViewModel.Tools.cs](../src/AALC.Desktop/MainViewModel.Tools.cs)、[GameWindow.cs](../src/AALC.Platform.Windows/GameWindow.cs) |
| 页面与配置 | — | [ToolsView.axaml](../src/AALC.Desktop/ToolsView.axaml)、[DesktopSettings.cs](../src/AALC.Runtime/Configuration/DesktopSettings.cs) |
