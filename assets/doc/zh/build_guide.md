# 构建指南

[首页](../../../README.md) · [开发指南](develop_guide.md) · [English](../en/build_guide_EN.md)

## 环境与命令

在 Windows x64 上构建，需要 uv、项目支持的 Python、PATH 中的 `7z`，以及 .NET Framework C# 编译器 `csc.exe`。宿主构建器会查找 PATH 和 Windows Framework / Framework64 目录。

在仓库根目录执行：

```powershell
uv sync --frozen
uv run python .\scripts\build.py --version dev
```

构建脚本会清理并重建输出目录；不要把用户数据放在 `dist/`。它会编译桌面分身原生宿主、打包主程序与更新器、处理资源和翻译、写入版本与更新清单，最后压缩并生成 SHA-256。

## 产物

| 路径 | 内容 |
| --- | --- |
| `dist/AALC/` | 可运行的完整程序目录 |
| `dist/AALC/AALC.exe` | 主程序 |
| `dist/AALC/AALC Updater.exe` | 更新器 |
| `dist/AALC/_internal/desktop_clone/AALC.DesktopCloneHost.exe` | 桌面分身原生宿主 |
| `dist/AALC_dev.7z` | 平铺发行包 |
| `dist/AALC_dev.7z.sha256` | 压缩包摘要 |
| `dist/AALC.update_manifest.json` | 对外发布的更新清单 |

包内清单名为 `update_manifest.json`，受管理文件名单为 `managed_files.txt`。`dev` 用于本地构建；发行版本应传入与标签一致的完整版本号。

## 发布约定

目前 Canary 使用平铺包和 bootstrap 协议版本 2。发布源码维护 `assets/config/version.txt` 与 `CHANGELOG.md`；GitHub Release 正文是用户在更新时看到的说明，应与更新日志一致。

标签触发的流程见 [release.yaml](../../../.github/workflows/release.yaml) 与 [reusable-build.yml](../../../.github/workflows/reusable-build.yml)。发布后还需核验对应 SHA、Pre-release 标记、唯一压缩包、更新清单、摘要和包内版本，构建成功本身不足以确认可更新。

不要手工修改生成的 manifest，也不要将历史桥接包选项 `--bridge-updater` 用于普通 Canary。直接运行 PyInstaller spec 不会完成原生宿主准备、资源整理和完整更新元数据生成。

构建脚本的控制台输出保持 ASCII，避免 Windows CI 的 cp1252 编码失败。
