# Translation and game resources

[Home](README_EN.md) · [简体中文](../zh/translateGuide.md)

## Application translation

The UI currently supports Simplified Chinese and English, registered in `app/language_manager.py`. English strings live in `i18n/myapp_en.ts` and compile into a `.qm` file.

From the repository root:

```powershell
uv run python .\scripts\translation_files_build.py
# Edit i18n/myapp_en.ts
uv run python .\scripts\translation_files_compile.py
```

Use a text editor or Qt Linguist. Preserve placeholders, HTML tags and newline semantics. Do not rename another language's output to the English filename; adding a language also requires registration, loading and UI validation.

Translation checking lives in `scripts/check_i18n.py`, with supporting scripts in `debug_tools/`. Dynamic UI translation follows the `LanguageManager` registration and `retranslateUi` conventions.

## Game text and templates

Application language and game language are separate settings. Current resource roots are:

- `assets/images/default/{en,zh_cn,share}/`
- `assets/images/dark/`

Load templates by relative key so the resource loader can handle language and theme. Check reference resolution, black masks, crop bounds and naming when replacing assets. The old `assets/images/zh_cn` path is not the current layout.

See [image matching and coordinates (Chinese)](../zh/image_recognition.md). Validate against real game screenshots and report language, resolution, UI state, thresholds and results; a plausible-looking template alone is insufficient.

## Documentation

Keep the Chinese and English READMEs, usage, FAQ and configuration pages consistent in project identity and important limitations. Download, issue and contribution links should target this fork; upstream links are for attribution or explicitly upstream information.
