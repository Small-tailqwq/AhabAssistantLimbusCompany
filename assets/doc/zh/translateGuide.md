# 翻译与游戏资源

[首页](../../../README.md) · [开发指南](develop_guide.md) · [English](../en/translateGuide.md)

## 界面翻译

当前 UI 支持简体中文和英文，语言注册位于 `app/language_manager.py`。英文词条维护在 `i18n/myapp_en.ts`，编译结果为 `.qm`。

在仓库根目录执行：

```powershell
uv run python .\scripts\translation_files_build.py
# 编辑 i18n/myapp_en.ts
uv run python .\scripts\translation_files_compile.py
```

可以用文本编辑器或 Qt Linguist 编辑词条。保持占位符、HTML 标记和换行语义；不要把其他语言文件重命名为英文文件来冒充语言支持。新增语言还需要注册语言代码、加载路径及验证相应界面。

翻译检查脚本位于 `scripts/check_i18n.py`，辅助工具位于 `debug_tools/`。UI 组件的动态翻译遵循 `LanguageManager` 注册与 `retranslateUi` 约定。

## 游戏文字和模板

程序界面语言与游戏语言是独立设置。游戏图片位于：

- `assets/images/default/{en,zh_cn,share}/`
- `assets/images/dark/`

模板采用相对 key，由资源加载器处理主题与语言。新增或替换资源时核对基准分辨率、黑色掩膜、裁剪区域和文件名；不要直接套用旧的 `assets/images/zh_cn` 路径。

制作方法和坐标约定见 [图片识别](image_recognition.md)。应使用对应语言的真实游戏截图验证，说明分辨率、UI 状态、阈值和匹配结果；单独生成一张看似正确的模板不代表生产流程能识别。

## 文档翻译

中英文 README、使用指南、FAQ 和配置说明需保持定位及关键限制一致。翻译本 fork 的当前内容，下载、Issues 和贡献入口指向本仓库；上游链接只用于来源或明确的上游说明。
