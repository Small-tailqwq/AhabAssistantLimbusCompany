# Lifecycle, UI, and Configuration

## Contents

1. Cooperative stopping
2. Blocking operations
3. UI communication and retranslation
4. Theme and debug switches
5. Configuration synchronization

## 1. Cooperative stopping

The global task-thread owner is `tasks/base/script_task_scheme.py::my_script_task`.

- `stop()` requests stopping rather than terminating the thread.
- Long tasks call `auto.ensure_not_stopped()`; input handlers use their established stop checks.
- `userStopError` propagates to centralized cleanup.
- `my_script_task.run()` clears stop state, disconnects OBS, and emits `mediator.script_finished` during teardown.
- `FarmingInterfaceLeft.handle_script_finished()` restores UI and cleans emulator connections.

Do not require every child method named `run()` to repeat global teardown. Do not use `QThread.terminate()` for normal stopping.

## 2. Blocking operations

Inspect waits individually when changing:

- game startup;
- `screen.init_handle()` window discovery;
- `MumuControl` or `SimulatorControl` startup and reconnect;
- stop cleanup and retry paths.

Waits need cooperative checks and bounded retries. `closeEvent()` has at most five seconds for graceful exit, so the UI thread must not enter an unbounded stop path.

## 3. UI communication and retranslation

- Communicate across pages and threads through `mediator` signals instead of directly owning another page instance.
- Components that respond to language changes register with `LanguageManager()` and implement `retranslateUi`.
- Follow current unregister patterns when dynamically registered components are destroyed.
- Use `cfg.set_value()` for persisted config and `cfg.unsaved_set_value()` for current temporary UI state.

## 4. Theme and debug switches

- Independent QWidget tools under `tasks/tools/` connect to `qconfig.themeChanged`.
- `_apply_theme_style()` applies both window theme and status-label styling when that is the established widget pattern.
- Child `debug_*` behavior is gated by both `debug_mode` and its own switch.
- Turning off `debug_mode` resets child switches and their UI state.
- Read `.opencode/tools/debug_model_constitution.md` before adding a debug switch; do not duplicate its template here.

## 5. Configuration synchronization

For a new config field, inspect at least:

- `module/config/config_typing.py`;
- `assets/config/config.example.yaml`;
- the corresponding UI card and read/write sites.

Never update defaults by modifying or replacing user `config.yaml`. Keep debug descriptions semantically accurate for log-plus-screenshot, screenshot-only, and log-only behavior.
