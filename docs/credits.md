# 来源、许可与致谢

[首页](../README.md) · [文档索引](README.md)

## 项目来源 / Project lineage

本 fork 基于 [KIYI671/AhabAssistantLimbusCompany](https://github.com/KIYI671/AhabAssistantLimbusCompany)。感谢上游及本仓库所有贡献者。100% vibe coding 是本分支的开发定位，历史代码、设计和素材的来源仍然保留。

This fork builds on AALC. Its 100% vibe coding identity describes development of this fork, not authorship of all inherited code or assets.

代码许可见 [GNU AGPL v3](../LICENSE)，项目元数据标记为 `AGPL-3.0-or-later`。第三方组件和素材按其各自许可使用；本项目与 Project Moon、Steam 或下列项目没有官方隶属关系。

## 当前技术组成 / Current components

当前 .NET 依赖以 [src/](../src/) 下各项目的 `.csproj` 为准，主要包括 Avalonia、SukiUI、CommunityToolkit.Mvvm、OpenCvSharp 与 ONNX Runtime。桌面分身使用独立的 .NET Framework 4.8 RDP 宿主。

## 历史参考 / Earlier references

保留原项目的来源致谢；这份列表不表示所有项目仍是当前运行依赖。

- [LixAssistantLimbusCompany](https://github.com/HSLix/LixAssistantLimbusCompany)：早期自动化实现参考。
- [PaddleOCR-json](https://github.com/hiroi-sora/PaddleOCR-json)：历史 OCR 方案；当前 .NET OCR 使用 PP-OCRv4 模型与 ONNX Runtime。
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)：界面组件。
- [March7thAssistant](https://github.com/moesnow/March7thAssistant)：助手项目参考。
- [blue_archive_auto_script](https://github.com/pur1fying/blue_archive_auto_script)：模拟器实现参考。

## 字体与素材 / Fonts and assets

- [ChineseFont.ttf](../assets/app/fonts/ChineseFont.ttf) 来源于 [更纱黑体 / Sarasa Gothic](https://github.com/be5invis/Sarasa-Gothic)，保留 SIL Open Font License 许可说明。
- 部分图片与音频素材来源于 [边狱巴士中文 WIKI](https://limbuscompany.huijiwiki.com/wiki/) 和 [月海伦娜](https://yuehailunna.lofter.com/)。
- 原文档注明部分图标素材来自网络；这些素材不因随仓库分发而自动适用代码的 AGPL 许可。
- 游戏画面、名称与相关素材的权利归各自权利人；汉化等外部下载内容保留其原项目许可与署名。

素材来源或署名有误时，请通过[本仓库 Issues](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/issues) 提供具体文件与依据。
