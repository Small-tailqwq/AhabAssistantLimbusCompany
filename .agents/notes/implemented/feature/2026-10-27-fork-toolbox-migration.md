# Agent Note: fork 小工具按原生文件边界迁入 AAALC

Status: implemented

## 问题

fork 的工具箱包含汉化、新手提示和截图等独立能力。直接引用旧工具会带入 PySide6、全局配置及 Python 自动化初始化，破坏 AAALC 的独立运行和按需加载。文件工具还需要区分安装目录、当前 Windows 用户存档与自动化证据目录，避免把三者绑定到资源仓库路径。

## 决策

[工具箱](../../../../dotnet/docs/tools.md)使用 C# 与 Avalonia，保留零协汉化、Windows 新手提示和游戏截图三个入口。[MainViewModel.Tools](../../../../dotnet/src/AALC.Desktop/MainViewModel.Tools.cs)复用主窗口的任务互斥、取消与关闭收尾；网络和存档访问由用户操作触发。游戏程序路径单独保存在 AAALC profile 的 `GameExecutablePath`，不导入 Python 配置。

页面的信息层级和结果展示遵循[AAALC 界面设计原则](../architecture/2026-10-27-aaalc-interface-design.md)。

[LlcLocalization](../../../../dotnet/src/AALC.Runtime/Tools/LlcLocalization.cs)查询实际 Release 附件，保留旧版 `.llc_version` 标记，按字符串比较版本。下载及解压在安装目录旁完成，只有完整包通过摘要与路径检查后才提交。更新以完整语言目录替换旧目录，旧目录保留为带时间和随机后缀的备份。这个目录边界使已从上游包移除的文件不继续参与游戏加载，也使安装失败可恢复到同一份旧包。

[TutorialSave](../../../../dotnet/src/AALC.Runtime/Tools/TutorialSave.cs)只处理存档数据模型和 AES 编码；[GameFiles](../../../../dotnet/src/AALC.Platform.Windows/Tools/GameFiles.cs)负责 Windows 注册表密钥读取、当前用户的存档发现与备份替换。关闭提示沿用 fork 的模型范围，保留未知字段与现有教程 ID；恢复提示翻转相应布尔状态，保留公告已读历史。完整恢复以原始加密存档备份为依据。注册表仅用于读取密钥。

截图复用已有 `GameWindow`，遵守游戏窗口所有权和[非 C 盘证据目录](../../../../dotnet/src/AALC.Runtime/EvidencePaths.cs)约定。截图无需初始化模板或 OCR，保存原始客户区尺寸的 PNG。

## 曾考虑的替代方案

直接启动 Python 工具可以复用 Qt 页面，但会让新版产品仍依赖 Python 环境和旧单例，故按 .NET 项目责任重写。

汉化包逐文件覆盖更接近旧版解压行为，但上游删除的文件会残留，取消或解压失败也可能混合两个版本。完整暂存后替换单个语言目录，并保留旧目录，使版本标记、语言文件和恢复来源保持一致；代价是安装时需要容纳下载包、新目录与旧目录。

将驱动管理、资产管理和旧日志复现一并迁移会引入尚未迁入 AAALC 的输入后端、资源编辑和配置切换语义。这些入口保留在旧版，按其各自后端迁移。

## 后果

三个入口可以独立于 Python 使用，文件访问和备份位置可直接从操作记录定位。安装及提示修改要求先退出游戏；网络、解压和槽位遍历支持取消，目录提交和单槽替换完成后再返回。多槽存档修改按文件提交，取消或写入失败时，已提交槽位及其备份保留。

汉化备份和存档备份由用户管理，不自动清理。提示恢复只重新开启提示，完整回退仍需选择对应备份。Windows 存档支持不包含模拟器和 Android。

该决定细化[.NET 重写方案](../../proposed/architecture/2026-10-25-dotnet-rewrite.md)中独立工具的迁移边界，重写方案继续承载其余后端、页面和发布流程。
