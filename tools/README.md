# 诊断工具

在仓库根目录调用 `tools/diagnostics/` 下的脚本，派生结果写入明确指定的目录，保留原始证据。

| 工具 | 用途 |
|---|---|
| `dotnet_run_metrics.py` | 汇总原生 .NET 录制的事件、阶段与输入 |
| `mirror_phase_timing.py` | 镜牢录制的阶段耗时 |
| `map_learning.py` | 从录制收集待人工标注的地图样本 |
| `diagnose_dotnet_map_nodes.py` | 对已有截图检查 ONNX 地图预测 |
| `evaluate_map_models.py`、`train_map_model.py` | 对明确标注的样本评估、训练模型 |

事件汇总与样本收集使用 Python 标准库；图像工具需要 OpenCV、NumPy、ONNX Runtime，训练工具另需 PyTorch/Ultralytics，按脚本 import 与 `--help` 准备环境。它们不属于 .NET 应用运行依赖。

```powershell
python tools/diagnostics/dotnet_run_metrics.py --help
python tools/diagnostics/mirror_phase_timing.py --help
```
