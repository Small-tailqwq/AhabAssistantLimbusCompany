# 开发指南

[首页](../../../README.md) · [构建](build_guide.md) · [翻译](translateGuide.md) · [图片识别](image_recognition.md)

本 fork 以 100% vibe coding 方式迭代。开发说明记录当前入口与约定；AI 输出需要结合源码、调用方、日志和实际画面判断，不能用生成的解释替代验证。

## 环境与启动

当前项目面向 Windows，Python 要求以 [pyproject.toml](../../../pyproject.toml) 的 `requires-python = ">=3.12"` 为准。使用 uv 和锁文件安装依赖：

```powershell
git clone https://github.com/Small-tailqwq/AhabAssistantLimbusCompany.git
cd AhabAssistantLimbusCompany
uv sync --frozen
uv run python .\main.py
```

`main.py` 是源码启动入口，继承当前终端权限；发行包的 `AALC.exe` 会请求管理员权限。使用源码运行桌面分身等需要管理员权限的功能时，请先打开管理员终端。开发入口提供自动重启与手动重载：

```powershell
uv run python .\main_dev.py
uv run python .\main_dev.py --no-reload
```

`--no-reload` 关闭文件变化触发的自动重启，仍保留 `Ctrl+R` 手动重载；`Ctrl+C` 退出开发启动器。`main_dev.py` 同样继承当前终端权限。重载会重启进程，调试真实任务时先停止任务再改代码。

## 从哪里读起

| 范围 | 入口 |
| --- | --- |
| 窗口与任务控制 | `app/my_app.py`、`app/farming_interface.py` |
| 任务编排与协作停止 | `tasks/base/script_task_scheme.py` |
| 输入和截图 | `module/automation/`、`module/game_and_screen/` |
| 图像与 OCR | `utils/image_utils.py`、`module/ocr/` |
| 配置与默认值 | `module/config/`、`assets/config/config.example.yaml` |
| 桌面分身 | `module/desktop_clone/`、`native/desktop_clone_host/` |
| 打包与更新 | `scripts/build.py`、`module/update/`、`updater.py` |

具体协作规则见 [AGENTS.md](../../../AGENTS.md)。历史设计与实验记录从 [文档索引](../../../docs/README.md) 查阅。

## 改动与验证

保留用户配置、日志和未提交工作。每次改动说明预期行为、实际证据和仍未覆盖的环境。验证按受影响范围选择：

```powershell
uv run python -m py_compile path\to\changed_file.py
uv run ruff check path\to\changed_file.py
uv run python -m unittest tests.test_relevant_module -v
```

上面路径和测试模块是占位符，需要替换为实际目标。`tests/` 存放回归检查；`test/` 含依赖游戏、设备或 OBS 的手动脚本，不能当作无副作用的单元测试批量执行。

UI、截图、输入与自动化变更需分别报告静态检查和实机证据。纯文档修改检查内容、链接与 diff 即可。临时截图与重放产物写入已忽略的 `logs/<feature>_debug/`，不要提交账号信息、凭据或用户配置。

## 提交反馈与贡献

问题与 PR 提交到 [本 fork](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany)，不要默认投递到上游。范围明确、可复现、有实际验证记录的改动更便于处理；提交不代表一定合并或同步上游。
