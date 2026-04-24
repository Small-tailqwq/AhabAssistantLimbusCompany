# AhabAssistantLimbusCompany - Agent Guidance

## Quick Start

```ps1
uv sync --frozen
uv run python .\main.py
uv run python .\main_dev.py
uv run python .\main_dev.py --no-reload
uv run ruff check .
uv run python -m py_compile path\to\touched_file.py
uv run python .\scripts\build.py --version dev
```

## Reality Check

- Windows-only desktop automation project, Python 3.12, `uv` managed.
- GUI behavior depends on real game state, window handles, simulator state, and sometimes OBS.
- There is no maintained automated test suite. Files like `test_bionic*.py` are ad-hoc local scripts, not reliable regression coverage.
- Runtime verification often requires a foreground game window, simulator, or OBS session.
- `ruff` is configured, but legacy modules still contain pre-existing warnings such as wildcard imports and bare `except`. Do not do unrelated lint cleanup during feature work.

## Architecture

- Entry points: `main.py` (prod) and `main_dev.py` (dev).
- UI: `app/`.
- Task orchestration: `tasks/base/script_task_scheme.py`.
- Shared services and singletons live under `module/`.
- Key singletons: `cfg`, `auto`, `ocr`, `screen`, `game_process`.
- OBS screenshot backend: `module/automation/obs_capture.py`.
- Mirror Dungeon logic: `tasks/mirror/`.
- Translations: `i18n/*.ts` and compiled `.qm` files.

## Core Conventions

- Use `cfg.set_value()` for persistent config writes.
- Use `cfg.unsaved_set_value()` for temporary UI-side config updates.
- Never re-instantiate `cfg`, `auto`, `ocr`, `screen`, or `game_process`.
- Use `ImageUtils.load_image()` with relative keys such as `mirror/road_in_mir/enter_assets.png`.
- Image lookup is language-aware through `utils.pic_path`; preserve relative asset keys.
- `main.py` resets the working directory to the executable location, so relative paths must stay portable.
- Prefer existing `mediator` signals over introducing direct cross-widget coupling.
- For hierarchical debug settings, turning off the parent debug-mode switch must also reset every child debug toggle to `False`.
- Commit messages should use Chinese whenever possible (提交说明尽可能使用中文).

## Script Lifecycle

- Main script thread class: `my_script_task` in `tasks/base/script_task_scheme.py`.
- Start/stop UI is owned by `app/farming_interface.py`.
- Graceful stop is cooperative, not forceful:
  - `my_script_task.stop()` calls `auto.request_stop()`.
  - Long-running code must call `auto.ensure_not_stopped()` or input-handler `check_stop_requested()`.
  - Stop propagates as `userStopError`.
  - `my_script_task.run()` clears stop state, disconnects OBS, then emits `mediator.script_finished`.
  - `FarmingInterfaceLeft.handle_script_finished()` restores the UI and cleans simulator connections.
- Do not reintroduce `QThread.terminate()` for normal stopping.

## Startup And Stop Safety

- Startup can block on game launch, window handle discovery, emulator connection, or simulator boot.
- If you touch `init_game()`, `screen.init_handle()`, `MumuControl`, or `SimulatorControl`, preserve stop checks inside blocking waits.
- `app/my_app.py::closeEvent()` waits up to 5 seconds for graceful shutdown. Avoid creating unbounded waits in the stop path.
- Post-stop cleanup retries are intentionally bounded to avoid freezing the UI thread.

## OBS Capture Notes

- OBS capture is enabled through `cfg.lab_screenshot_obs`.
- `script_task()` performs a preflight check with `get_obs_capture().validate_capture_ready()` before running tasks.
- That preflight intentionally clears failed connection cooldown so users can retry immediately after fixing OBS.
- Always tear down OBS from thread cleanup via `disconnect_obs_capture()`.

## Mirror Dungeon Notes

- `MirrorMap` caches route data per floor.
- Prefer cache reuse or targeted retries before adding more broad `take_screenshot=True` polling.
- Keyboard route flow can often reuse cached directions; mouse-based movement may need bus-position recalculation.
- Input mode branches matter: foreground, background, Logitech, OBS, and simulator flows do not behave identically.

## Verification

- Fast syntax check for touched files:

```ps1
uv run python -m py_compile path\to\file.py path\to\other.py
```

- Lint:

```ps1
uv run ruff check .
```

- Build:

```ps1
uv run python .\scripts\build.py --version dev
```

- Manual runtime validation is usually required. For stop-flow changes, verify at least:
  - start then stop from the UI button
  - `Ctrl+Q` stop during normal task execution
  - stop during startup or emulator waiting
  - OBS enabled startup preflight
  - UI returns to `Link Start!` after thread completion

## Local Artifacts

- Do not commit local screenshots, build outputs, `__pycache__`, temporary configs, or personal backup files unless the task explicitly requires them.
- Treat files such as `config.yaml`, screenshots under `test/`, and local debug scripts as environment-specific unless the user asks otherwise.

## References

- `README.md`
- `assets/doc/zh/develop_guide.md`
- `assets/doc/zh/build_guide.md`
- `assets/doc/zh/translateGuide.md`
- `assets/doc/zh/image_recognition.md`
- `assets/doc/zh/FAQ.md`
- `assets/doc/zh/How_to_use.md`
- `assets/doc/zh/Custom_setting.md`
