# Startup Main Menu Wait Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“启动后等待主界面”从 `back_init_menu()` 的运行时兜底逻辑中拆分出来，避免冷启动、自动重启、自动拉起游戏时提前耗尽 30 次预算并误杀游戏，同时提供 PC / 模拟器可配置的启动等待超时。

**Architecture:** 新增一个独立的启动等待函数，专门处理标题页、清缓存页、连接页、等待页等冷启动状态；`back_init_menu()` 继续保留原本的运行时兜底职责。`script_task()`、`restart_game()`、`ensure_simulator_game_started()` 触发的新启动流程统一切到这条新路径，并使用按模式区分的秒数预算，而不是共享 `retry()` 的 90 秒超时和 `back_init_menu()` 的 30 次预算。

**Tech Stack:** Python 3.12+, unittest, PySide6, uv, Windows-only 桌面自动化

## Global Constraints

- 所有等待循环必须保留 `auto.ensure_not_stopped()` 或等价停止检查。
- 不重新实例化 `cfg`、`auto`、`screen`、`game_process`。
- 持久配置写入使用 `cfg.set_value()`。
- 新增配置同步到 `module/config/config_typing.py`、`assets/config/config.example.yaml`、对应设置界面。
- 不覆盖用户现有 `config.yaml`。
- 不修改与本问题无关的识图、任务逻辑或遗留 warning。
- 不提交 git commit，除非用户后续明确要求。

---

## File Structure

- Modify: `tasks/base/back_init_menu.py`
  - 增加启动等待函数、模式超时读取、冷启动共享判定逻辑。
- Modify: `tasks/base/retry.py`
  - `restart_game()` 与 `retry()` / `ensure_simulator_game_started()` 的调用链切换到启动等待路径。
- Modify: `tasks/base/script_task_scheme.py`
  - `init_game()` 之后显式调用启动等待函数。
- Modify: `module/config/config_typing.py`
  - 新增 `startup_wait_timeout_pc`、`startup_wait_timeout_simulator` 配置字段。
- Modify: `assets/config/config.example.yaml`
  - 新增两项默认配置与注释。
- Modify: `app/setting_interface.py`
  - 增加两个超时设置卡片并挂到现有分组。
- Modify: `tests/test_simulator_recovery.py`
  - 覆盖 `retry()` / `restart_game()` 切换到启动等待路径。
- Modify: `tests/test_team_queue_normalization.py`
  - 覆盖 `script_task()` 在 `init_game()` 后调用启动等待函数。
- Create: `tests/test_startup_main_menu_wait.py`
  - 覆盖新启动等待函数的超时选择、标题页处理和秒数预算行为。

## Interfaces

- Produces: `tasks.base.back_init_menu.wait_until_main_menu_after_launch(*, allow_restart: bool = True) -> bool`
  - 调用方只关心是否成功等到主界面。
- Produces: `tasks.base.back_init_menu.get_startup_wait_timeout_seconds() -> int`
  - 根据 `cfg.simulator` 读取 `startup_wait_timeout_pc` / `startup_wait_timeout_simulator`。
- Produces: `tasks.base.back_init_menu.handle_launch_state_once() -> bool | None`
  - 返回 `True` 表示已完成一次启动态处理并应继续等待；`None` 表示未命中冷启动页，调用方继续判定别的状态。
- Consumes: `tasks.base.retry.click_title_screen_safely()`
- Consumes: `tasks.base.retry.ensure_simulator_game_started()`
- Consumes: `tasks.base.retry.kill_game()` / `tasks.base.retry.restart_game()`

### Task 1: 写启动等待函数的失败测试

**Files:**
- Create: `tests/test_startup_main_menu_wait.py`
- Modify: `tasks/base/back_init_menu.py`

**Interfaces:**
- Produces: `wait_until_main_menu_after_launch(*, allow_restart: bool = True) -> bool`
- Produces: `get_startup_wait_timeout_seconds() -> int`
- Produces: `handle_launch_state_once() -> bool | None`

- [ ] **Step 1: 写超时选择失败测试**

```python
import unittest
from unittest.mock import patch

import tasks.base.back_init_menu as back_init_menu_module


class TestStartupMainMenuWait(unittest.TestCase):
    def test_get_startup_wait_timeout_seconds_uses_simulator_value(self):
        cfg_stub = type(
            "CfgStub",
            (),
            {"simulator": True, "get_value": lambda self, key, default=None: {"startup_wait_timeout_simulator": 180}.get(key, default)},
        )()

        with patch.object(back_init_menu_module, "cfg", cfg_stub):
            self.assertEqual(back_init_menu_module.get_startup_wait_timeout_seconds(), 180)

    def test_get_startup_wait_timeout_seconds_uses_pc_value(self):
        cfg_stub = type(
            "CfgStub",
            (),
            {"simulator": False, "get_value": lambda self, key, default=None: {"startup_wait_timeout_pc": 120}.get(key, default)},
        )()

        with patch.object(back_init_menu_module, "cfg", cfg_stub):
            self.assertEqual(back_init_menu_module.get_startup_wait_timeout_seconds(), 120)
```

- [ ] **Step 2: 运行测试，确认因函数不存在而失败**

Run: `uv run python -m unittest tests.test_startup_main_menu_wait.TestStartupMainMenuWait.test_get_startup_wait_timeout_seconds_uses_simulator_value -v`

Expected: `AttributeError` 或 `ImportError`，指出 `get_startup_wait_timeout_seconds` 尚不存在。

- [ ] **Step 3: 写标题页与秒数预算失败测试**

```python
    def test_handle_launch_state_once_uses_safe_title_click_for_cache_prompt(self):
        calls = []

        class AutoStub:
            def find_element(self, target, *_, **__):
                return target == "base/clear_all_caches_assets.png"

            def click_element(self, target, *_, **__):
                calls.append(("click_element", target))
                return False

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "click_title_screen_safely", lambda: calls.append(("safe_click",))),
        ):
            result = back_init_menu_module.handle_launch_state_once()

        self.assertTrue(result)
        self.assertIn(("safe_click",), calls)

    def test_wait_until_main_menu_after_launch_uses_deadline_not_loop_count(self):
        calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

            def click_element(self, *args, **kwargs):
                return False

            def find_element(self, *args, **kwargs):
                return False

        time_values = iter([0.0, 0.0, 1.0, 2.0, 3.1])

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=True),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=3),
            patch.object(back_init_menu_module, "sleep", lambda *_: None),
            patch.object(back_init_menu_module, "time", type("TimeStub", (), {"time": staticmethod(lambda: next(time_values))})()),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertFalse(result)
        self.assertGreaterEqual(len(calls), 3)
```

- [ ] **Step 4: 运行测试，确认因启动等待函数不存在而失败**

Run: `uv run python -m unittest tests.test_startup_main_menu_wait -v`

Expected: 失败，提示 `handle_launch_state_once` / `wait_until_main_menu_after_launch` 尚不存在。

- [ ] **Step 5: 实现最小生产代码让测试通过**

在 `tasks/base/back_init_menu.py` 中新增最小实现：

```python
import time


def get_startup_wait_timeout_seconds() -> int:
    key = "startup_wait_timeout_simulator" if cfg.simulator else "startup_wait_timeout_pc"
    return int(cfg.get_value(key, 180 if cfg.simulator else 120))


def handle_launch_state_once() -> bool | None:
    if auto.find_element("base/clear_all_caches_assets.png", model="clam"):
        if auto.click_element("base/update_confirm_assets.png"):
            return True
        click_title_screen_safely()
        return True
    if auto.find_element("base/connecting_assets.png"):
        return True
    if auto.find_element("base/waiting_assets.png"):
        return True
    if auto.find_element("base/waiting_2_assets.png"):
        return True
    if auto.click_element("base/only_option_assets.png", model="clam"):
        return True
    return None


def wait_until_main_menu_after_launch(*, allow_restart: bool = True) -> bool:
    deadline = time.time() + get_startup_wait_timeout_seconds()
    while time.time() <= deadline:
        auto.ensure_not_stopped()
        if ensure_simulator_game_started():
            continue
        if handle_launch_state_once():
            continue
        if auto.click_element("home/window_assets.png") and auto.find_element("home/mail_assets.png", model="normal"):
            return True
        sleep(0.5)
    if not allow_restart:
        return False
    from tasks.base.retry import kill_game, restart_game

    log.error("启动后等待主界面超时，尝试重启游戏")
    kill_game()
    restart_game()
    return False
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `uv run python -m unittest tests.test_startup_main_menu_wait -v`

Expected: 4 个测试全部 `ok`。

### Task 2: 让 script_task 和 restart_game 走启动等待路径

**Files:**
- Modify: `tasks/base/script_task_scheme.py`
- Modify: `tasks/base/retry.py`
- Modify: `tests/test_team_queue_normalization.py`
- Modify: `tests/test_simulator_recovery.py`

**Interfaces:**
- Consumes: `wait_until_main_menu_after_launch(*, allow_restart: bool = True) -> bool`
- Produces: `script_task()` 在 `init_game()` 后显式等待主界面
- Produces: `restart_game()` 在 `init_game()` 后显式等待主界面

- [ ] **Step 1: 写 `script_task()` 调用启动等待的失败测试**

在 `tests/test_team_queue_normalization.py` 中追加：

```python
    def test_script_task_waits_for_main_menu_after_init_game(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, *args, **kwargs):
                return False

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": False,
            },
        )()
        path_manager_stub = type("PathManagerStub", (), {"initialize_paths": lambda self: None, "pic_path": []})()

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(script_task_scheme, "wait_until_main_menu_after_launch", lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)), create=True),
        ):
            script_task_scheme.script_task()

        self.assertIn(("init_game",), calls)
        self.assertIn(("wait_main_menu", True), calls)
```

- [ ] **Step 2: 写 `restart_game()` 调用启动等待的失败测试**

在 `tests/test_simulator_recovery.py` 中追加：

```python
    def test_restart_game_waits_for_main_menu_after_init_game(self):
        calls = []

        with (
            patch("tasks.base.script_task_scheme.init_game", lambda: calls.append(("init_game",))),
            patch("tasks.base.back_init_menu.wait_until_main_menu_after_launch", lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart))),
            patch.object(retry_module, "sleep", lambda *_: None),
        ):
            retry_module.restart_game()

        self.assertEqual(calls, [("init_game",), ("wait_main_menu", True)])
```

- [ ] **Step 3: 运行新增测试，确认失败**

Run: `uv run python -m unittest tests.test_team_queue_normalization.TestTeamQueueNormalization.test_script_task_waits_for_main_menu_after_init_game tests.test_simulator_recovery.TestSimulatorRecovery.test_restart_game_waits_for_main_menu_after_init_game -v`

Expected: `AttributeError` 或断言失败，表明两个调用点尚未切换。

- [ ] **Step 4: 写最小实现**

在 `tasks/base/script_task_scheme.py` 中：

```python
from tasks.base.back_init_menu import back_init_menu, wait_until_main_menu_after_launch


def script_task() -> None | int:
    start_time = time()
    init_game()
    wait_until_main_menu_after_launch()
    ...
```

在 `tasks/base/retry.py` 中：

```python
def restart_game():
    from tasks.base.back_init_menu import wait_until_main_menu_after_launch
    from tasks.base.script_task_scheme import init_game

    init_game()
    sleep(3)
    wait_until_main_menu_after_launch()
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `uv run python -m unittest tests.test_team_queue_normalization.TestTeamQueueNormalization.test_script_task_waits_for_main_menu_after_init_game tests.test_simulator_recovery.TestSimulatorRecovery.test_restart_game_waits_for_main_menu_after_init_game -v`

Expected: 两个测试都 `ok`。

### Task 3: 让 back_init_menu 和 retry 在自动拉起游戏后切到启动等待路径

**Files:**
- Modify: `tasks/base/back_init_menu.py`
- Modify: `tasks/base/retry.py`
- Modify: `tests/test_simulator_recovery.py`

**Interfaces:**
- Consumes: `ensure_simulator_game_started() -> bool`
- Consumes: `wait_until_main_menu_after_launch(*, allow_restart: bool = True) -> bool`
- Produces: 自动拉起游戏后不再继续消耗 30 次预算或落入 `check_times(90)`

- [ ] **Step 1: 写 `retry()` 切换路径的失败测试**

在 `tests/test_simulator_recovery.py` 中追加：

```python
    def test_retry_waits_for_main_menu_after_auto_start_game(self):
        calls = []

        class AutoStub:
            def get_restore_time(self):
                return None

        cfg_stub = type("CfgStub", (), {"config": type("ConfigStub", (), {"simulator": True})()})()

        with (
            patch.object(retry_module, "cfg", cfg_stub),
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "ensure_simulator_game_started", side_effect=[True]),
            patch.object(retry_module, "wait_until_main_menu_after_launch", lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)), create=True),
        ):
            retry_module.retry()

        self.assertEqual(calls, [("wait_main_menu", True)])
```

- [ ] **Step 2: 写 `back_init_menu()` 切换路径的失败测试**

在 `tests/test_simulator_recovery.py` 中追加：

```python
    def test_back_init_menu_waits_for_main_menu_after_auto_start_game(self):
        calls = []

        class AutoStub:
            model = "clam"

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        with (
            patch("tasks.base.back_init_menu.auto", AutoStub()),
            patch("tasks.base.back_init_menu.ensure_simulator_game_started", side_effect=[True]),
            patch("tasks.base.back_init_menu.wait_until_main_menu_after_launch", lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)) or True),
        ):
            result = __import__("tasks.base.back_init_menu", fromlist=["back_init_menu"]).back_init_menu(allow_restart=False)

        self.assertTrue(result)
        self.assertIn(("wait_main_menu", False), calls)
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `uv run python -m unittest tests.test_simulator_recovery.TestSimulatorRecovery.test_retry_waits_for_main_menu_after_auto_start_game tests.test_simulator_recovery.TestSimulatorRecovery.test_back_init_menu_waits_for_main_menu_after_auto_start_game -v`

Expected: 失败，说明两个函数尚未切换调用链。

- [ ] **Step 4: 写最小实现**

在 `tasks/base/retry.py` 顶部导入：

```python
from tasks.base.back_init_menu import wait_until_main_menu_after_launch
```

修改 `retry()`：

```python
def retry():
    ...
    while True:
        if ensure_simulator_game_started():
            if not wait_until_main_menu_after_launch():
                return False
            return True
        ...
```

修改 `back_init_menu()`：

```python
def back_init_menu(*, allow_restart: bool = True):
    ...
    while True:
        auto.ensure_not_stopped()
        loop_count -= 1
        ...
        if ensure_simulator_game_started():
            return wait_until_main_menu_after_launch(allow_restart=allow_restart)
        if retry() is False:
            return False
        ...
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `uv run python -m unittest tests.test_simulator_recovery -v`

Expected: 新增测试和原有恢复测试全部 `ok`。

### Task 4: 增加配置模型、示例配置和设置界面

**Files:**
- Modify: `module/config/config_typing.py`
- Modify: `assets/config/config.example.yaml`
- Modify: `app/setting_interface.py`

**Interfaces:**
- Produces: `startup_wait_timeout_pc: int`
- Produces: `startup_wait_timeout_simulator: int`

- [ ] **Step 1: 写配置默认值失败测试**

在 `tests/test_startup_main_menu_wait.py` 中追加：

```python
import module.config.config_typing as config_typing_module


    def test_config_model_exposes_startup_wait_timeouts(self):
        model = config_typing_module.ConfigModel()
        self.assertEqual(model.startup_wait_timeout_pc, 120)
        self.assertEqual(model.startup_wait_timeout_simulator, 180)
```

- [ ] **Step 2: 运行测试，确认因字段不存在而失败**

Run: `uv run python -m unittest tests.test_startup_main_menu_wait.TestStartupMainMenuWait.test_config_model_exposes_startup_wait_timeouts -v`

Expected: `AttributeError`，表明两个字段尚不存在。

- [ ] **Step 3: 写最小实现**

在 `module/config/config_typing.py` 中新增：

```python
    startup_wait_timeout_pc: int = 120
    """PC 启动游戏后等待主界面的超时时间（秒）"""

    startup_wait_timeout_simulator: int = 180
    """模拟器启动游戏后等待主界面的超时时间（秒）"""
```

在 `assets/config/config.example.yaml` 中新增：

```yaml
startup_wait_timeout_simulator: 180 # 模拟器启动游戏后等待主界面的超时时间(秒)
startup_wait_timeout_pc: 120 # PC启动游戏后等待主界面的超时时间(秒)
```

在 `app/setting_interface.py` 中新增两个 `PushSettingCardChance`：

```python
        self.startup_wait_timeout_simulator_card = PushSettingCardChance(
            QT_TRANSLATE_NOOP("PushSettingCardChance", "修改"),
            FIF.CLOCK,
            QT_TRANSLATE_NOOP("PushSettingCardChance", "模拟器启动后等待主界面超时时间(秒)"),
            config_name="startup_wait_timeout_simulator",
            max_value=3600,
            content="",
            parent=self.simulator_setting_group,
        )

        self.startup_wait_timeout_pc_card = PushSettingCardChance(
            QT_TRANSLATE_NOOP("PushSettingCardChance", "修改"),
            FIF.CLOCK,
            QT_TRANSLATE_NOOP("PushSettingCardChance", "PC启动后等待主界面超时时间(秒)"),
            config_name="startup_wait_timeout_pc",
            max_value=3600,
            content="",
            parent=self.game_path_group,
        )
```

并在 `__initLayout()` 对应分组中加入这两张卡。

- [ ] **Step 4: 运行测试，确认配置测试通过**

Run: `uv run python -m unittest tests.test_startup_main_menu_wait.TestStartupMainMenuWait.test_config_model_exposes_startup_wait_timeouts -v`

Expected: `ok`。

- [ ] **Step 5: 做语法检查**

Run: `uv run python -m py_compile tasks/base/back_init_menu.py tasks/base/retry.py tasks/base/script_task_scheme.py module/config/config_typing.py app/setting_interface.py`

Expected: 无输出。

### Task 5: 运行完整验证

**Files:**
- Test: `tests/test_startup_main_menu_wait.py`
- Test: `tests/test_simulator_recovery.py`
- Test: `tests/test_team_queue_normalization.py`

**Interfaces:**
- 验证启动等待路径、自动拉起路径、配置默认值、脚本入口接线均正常

- [ ] **Step 1: 运行新增专项测试**

Run: `uv run python -m unittest tests.test_startup_main_menu_wait tests.test_simulator_recovery -v`

Expected: 全部 `ok`。

- [ ] **Step 2: 运行相关入口回归测试**

Run: `uv run python -m unittest tests.test_team_queue_normalization -v`

Expected: 全部 `ok`。

- [ ] **Step 3: 运行 ruff 最小范围检查**

Run: `uv run ruff check tasks/base/back_init_menu.py tasks/base/retry.py tasks/base/script_task_scheme.py module/config/config_typing.py app/setting_interface.py tests/test_startup_main_menu_wait.py tests/test_simulator_recovery.py tests/test_team_queue_normalization.py`

Expected: `All checks passed!` 或无新增问题。

## Self-Review

- Spec coverage: 已覆盖职责拆分、3 个调用点、标题页处理、`retry()` 90 秒边界、PC/模拟器双配置、UI 设置与测试。
- Placeholder scan: 计划内无 `TODO`、`TBD`、`适当处理` 之类占位描述。
- Type consistency: 计划统一使用 `wait_until_main_menu_after_launch(*, allow_restart: bool = True) -> bool` 与 `get_startup_wait_timeout_seconds() -> int`。
