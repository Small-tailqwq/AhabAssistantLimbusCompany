# 图片识别与坐标

[首页](../../../README.md) · [开发指南](develop_guide.md) · [翻译与资源](translateGuide.md)

## 当前管线

模板匹配使用 OpenCV，文字识别使用 RapidOCR / ONNX Runtime。主要入口是 `module/automation/automation.py`、`utils/image_utils.py` 和 `utils/path_manager.py`。诊断时同时看原始截图、模板、裁剪区域及调用参数。

## 坐标与截图时机

- 匹配基于游戏客户区截图；普通图像匹配返回当前截图中的目标位置。交给现有点击封装时不要再无条件按 2560×1440 缩放一次。
- 硬编码基准坐标、OCR 裁剪框和匹配返回位置不是同一种数据。基准坐标需按调用点所用约定换算，裁剪框需落在实际截图内。
- `find_element` / `click_element` 的 `take_screenshot` 默认是 `False`，会使用已有截图。切页后需要确认新页面时，应明确获取新画面，不能用过渡前的帧判断结果。
- OCR、特征、多目标与普通模板查找的返回结构不完全相同，新增调用前检查对应实现。

## 资源和匹配范围

通过 `ImageUtils.load_image(相对 key)` 加载模板，例如 `home/window_assets.png`。主题和语言候选由 `PathManager` 管理，源文件位于 `assets/images/default/{en,zh_cn,share}/` 与 `assets/images/dark/`。

现有资源使用两类形式：带黑色背景掩膜的完整画面模板，以及裁剪后的元素模板。带 `assets.png` 后缀的模板通常会依据非黑区域计算 bbox；实际搜索区域还取决于匹配模式和调用参数，不是固定全屏。

`find_element` 默认阈值为 0.8。模式名包括 `clam`、`normal` 和 `aggressive`，具体裁剪和扩展逻辑以实现为准；提高范围或降低阈值可能改变误匹配率。

## 制作与排查

1. 保存目标页面的原始截图，记录游戏语言、分辨率、主题、窗口状态和截图方式。
2. 对照现有模板的基准尺寸与目标区域。项目完整画面模板通常以 2560×1440 为基准；保留掩膜及目标位置关系。
3. 检查空裁剪、模板大于搜索区域、缩放和字体差异，再判断是否需要更新模板。
4. 使用 `debug_tools/verify_matching.py` 等仓库工具重放生产匹配管线；参数以工具当前帮助为准。
5. 报告实际结果、阈值与坐标含义，保存证据到 `logs/<feature>_debug/`。模板重放成功后，页面进入和退出逻辑仍需单独验证。

C24 对空裁剪和过小截图增加了未匹配返回，这能避免部分 OpenCV 异常，但不能自动修复错误的模板或截图来源。
