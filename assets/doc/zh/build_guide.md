# 构建指南

## 推荐构建方式

项目当前推荐使用 `uv` 和仓库内置构建脚本：

```ps1
uv sync --frozen
uv run python .\scripts\build.py --version dev
```

构建完成后会生成：

- `dist\AALC\AALC.exe`
- `dist\AALC\AALC Updater.exe`
- `dist\AALC_dev.7z`

如果要打正式版本，把 `dev` 换成你的版本号即可，例如：

```ps1
uv run python .\scripts\build.py --version 1.4.0
```

## 手动 / 兼容方式

如果只想手动执行 PyInstaller，可使用：

```ps1
pyinstaller .\main.spec
pyinstaller .\updater.spec
```

这种方式只会生成基础打包结果，不会自动整理附属文件、生成翻译文件、写入版本号或打 7z 包。
