# Mirror Team Queue Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mirror team system's multi-source state with a single queue-based source of truth while preserving current UI behavior and config compatibility.

**Architecture:** Add `teams_active_queue` as the only authoritative representation of enabled mirror teams and execution order. Centralize migration, normalization, queue rotation, and legacy field projection in `module/config/config.py`, then update UI and mirror execution flows to call these helpers instead of mutating `teams_order`, `teams_be_select`, and `teams_be_select_num` directly.

**Tech Stack:** Python 3.12+, Pydantic, PySide6, ruamel.yaml, existing AALC config and UI framework

---

### Task 1: Add Queue Field To Config Model

**Files:**
- Modify: `module/config/config_typing.py`

- [ ] **Step 1: Add the new config field**

Update `module/config/config_typing.py` so `ConfigModel` includes the new queue field next to the existing mirror team legacy fields:

```python
    teams_be_select_num: int = 0
    """被选中的队伍数量"""

    teams_be_select: List[bool] = [False]
    """被选中的队伍"""

    teams_order: List[int] = [0]
    """队伍的顺序"""

    teams_active_queue: List[int] = []
    """镜牢启用队伍的执行队列（单一事实源）"""
```

- [ ] **Step 2: Run syntax verification**

Run: `uv run python -m py_compile module/config/config_typing.py`

Expected: command exits successfully with no output.

- [ ] **Step 3: Commit**

```bash
git add module/config/config_typing.py
git commit -m "feat: 为镜牢编队新增执行队列字段"
```

---

### Task 2: Implement Queue Migration And Normalization Helpers

**Files:**
- Modify: `module/config/config.py`

- [ ] **Step 1: Add helper methods to the Config class**

Insert the following methods into `module/config/config.py` inside `class Config`, after `__getattr__` and before `class Theme_pack_list`:

```python
    def get_team_numbers(self) -> list[int]:
        """Return existing mirror team slot numbers in ascending order."""
        teams = self.get_value("teams", config_obj=self.config) or {}
        return sorted(int(key) for key in teams.keys())

    def migrate_legacy_team_queue(self) -> list[int]:
        """Build queue from legacy fields when teams_active_queue is absent or invalid."""
        team_numbers = self.get_team_numbers()
        if not team_numbers:
            return []

        team_set = set(team_numbers)
        teams_order = list(self.get_value("teams_order", []) or [])
        queue_from_order: list[tuple[int, int]] = []
        seen_orders = set()
        can_use_order = True
        for team_num in team_numbers:
            idx = team_num - 1
            if idx >= len(teams_order):
                continue
            order = teams_order[idx]
            if order <= 0:
                continue
            if order in seen_orders:
                can_use_order = False
                break
            seen_orders.add(order)
            queue_from_order.append((order, team_num))

        if can_use_order and queue_from_order:
            queue = [team_num for order, team_num in sorted(queue_from_order)]
            if all(team_num in team_set for team_num in queue):
                return queue

        teams_be_select = list(self.get_value("teams_be_select", []) or [])
        queue = []
        for team_num in team_numbers:
            idx = team_num - 1
            if idx < len(teams_be_select) and teams_be_select[idx]:
                queue.append(team_num)
        return queue

    def normalize_and_sync_team_state(self) -> None:
        """Normalize mirror team queue and project legacy fields from it."""
        team_numbers = self.get_team_numbers()
        team_set = set(team_numbers)

        raw_queue = list(self.get_value("teams_active_queue", []) or [])
        if not raw_queue:
            raw_queue = self.migrate_legacy_team_queue()

        queue = []
        seen = set()
        for team_num in raw_queue:
            if team_num not in team_set or team_num in seen:
                continue
            seen.add(team_num)
            queue.append(team_num)

        team_count = len(team_numbers)
        teams_be_select = [False] * team_count
        teams_order = [0] * team_count
        for order, team_num in enumerate(queue, start=1):
            teams_be_select[team_num - 1] = True
            teams_order[team_num - 1] = order

        self.unsaved_set_value("teams_active_queue", queue)
        self.unsaved_set_value("teams_be_select", teams_be_select)
        self.unsaved_set_value("teams_order", teams_order)
        self.unsaved_set_value("teams_be_select_num", len(queue))

    def reindex_team_queue(self, old_to_new: dict[int, int]) -> None:
        """Rewrite the queue after teams dict keys are compacted."""
        queue = list(self.get_value("teams_active_queue", []) or [])
        new_queue = [old_to_new[team_num] for team_num in queue if team_num in old_to_new]
        self.unsaved_set_value("teams_active_queue", new_queue)
        self.normalize_and_sync_team_state()

    def rotate_team_queue(self) -> None:
        """Move the current active mirror team to the end of the queue."""
        queue = list(self.get_value("teams_active_queue", []) or [])
        if len(queue) > 1:
            queue.append(queue.pop(0))
        self.unsaved_set_value("teams_active_queue", queue)
        self.normalize_and_sync_team_state()
        self.save()

    def remove_team_from_queue(self, team_num: int) -> None:
        """Remove one team from the active queue."""
        queue = [value for value in list(self.get_value("teams_active_queue", []) or []) if value != team_num]
        self.unsaved_set_value("teams_active_queue", queue)
        self.normalize_and_sync_team_state()

    def set_team_enabled(self, team_num: int, enabled: bool) -> None:
        """Toggle one mirror team in the active queue and sync legacy fields."""
        queue = list(self.get_value("teams_active_queue", []) or [])
        queue = [value for value in queue if value != team_num]
        if enabled:
            queue.append(team_num)
        self.unsaved_set_value("teams_active_queue", queue)
        self.normalize_and_sync_team_state()
        self.save()
```

- [ ] **Step 2: Normalize immediately after config load**

Update `_load_config()` in `module/config/config.py` so the loaded config is normalized before backup/save logic proceeds:

```python
                # 使用更新后的配置初始化 Config 对象
                self.config = ConfigModel(**loaded_config)
                self.normalize_and_sync_team_state()
                # 成功加载后保存当前文件为备份
                shutil.copy(path, path.with_suffix(".yaml.backup"))
```

- [ ] **Step 3: Normalize after old-version upgrades that construct team data**

No additional migration branch is needed in `_old_version_cfg_upgrade()`. Keep that method unchanged and rely on `_load_config()` to normalize after `self.config = ConfigModel(**loaded_config)`.

- [ ] **Step 4: Run syntax verification**

Run: `uv run python -m py_compile module/config/config.py`

Expected: command exits successfully with no output.

- [ ] **Step 5: Manual spot-check in REPL-style command**

Run:

```bash
uv run python -c "from module.config import cfg; print(cfg.teams_active_queue, cfg.teams_order, cfg.teams_be_select, cfg.teams_be_select_num)"
```

Expected: command prints four normalized values and exits without traceback.

- [ ] **Step 6: Commit**

```bash
git add module/config/config.py
git commit -m "feat: 集中镜牢编队队列迁移与归一化逻辑"
```

---

### Task 3: Move Team Checkbox Toggling To Queue Helpers

**Files:**
- Modify: `app/base_tools.py`

- [ ] **Step 1: Replace direct legacy-field mutation in BaseCheckBox**

Update the `elif self.config_name.startswith("the_team_"):` branch in `BaseCheckBox.on_toggle()` in `app/base_tools.py` to this implementation:

```python
        elif self.config_name.startswith("the_team_"):
            team_num = int(self.config_name.split("_")[-1])
            cfg.set_team_enabled(team_num, checked)
            mediator.refresh_teams_order.emit()
```

This step deletes the current block that manually appends to `teams_be_select`, mutates `teams_order`, and increments/decrements `teams_be_select_num`.

- [ ] **Step 2: Run syntax verification**

Run: `uv run python -m py_compile app/base_tools.py`

Expected: command exits successfully with no output.

- [ ] **Step 3: Commit**

```bash
git add app/base_tools.py
git commit -m "refactor: 编队勾选改为统一操作执行队列"
```

---

### Task 4: Normalize Before UI Build And Remove Manual Grow Logic

**Files:**
- Modify: `app/page_card.py`

- [ ] **Step 1: Normalize before building PageMirror team widgets**

At the start of `PageMirror.get_setting()` in `app/page_card.py`, add normalization before clearing/rebuilding child widgets:

```python
    def get_setting(self):
        cfg.normalize_and_sync_team_state()
        team_toggle_button_group.clear()
        self.page_general.setUpdatesEnabled(False)
        try:
            for i in range(1, 21):
                if self.findChild(MirrorTeamCombination, f"team_{i}") is not None:
                    self.remove_team_card(f"team_{i}")
                if cfg.config.teams.get(f"{i}", None) is not None:
                    self.vbox_general.insertWidget(
                        self.vbox_general.count() - 1,
                        MirrorTeamCombination(i, f"the_team_{i}", f"编队{i}", None, f"team{i}_setting"),
                    )
        finally:
            self.page_general.setUpdatesEnabled(True)

        QT_TRANSLATE_NOOP("MirrorTeamCombination", "编队")
        self.refresh()
```

- [ ] **Step 2: Delete the old manual grow block**

Remove this block entirely from `PageMirror.get_setting()`:

```python
        n = len(cfg.config.teams)
        while len(cfg.config.teams_be_select) < n:
            cfg.config.teams_be_select.append(False)
        while len(cfg.config.teams_order) < n:
            cfg.config.teams_order.append(0)
```

- [ ] **Step 3: Update new_team to stop appending legacy fields**

Replace the config update section in `PageMirror.new_team()` with:

```python
            if cfg.config.teams.get(f"{number}", None) is None:
                cfg.config.teams[f"{number}"] = TeamSetting()
                cfg.normalize_and_sync_team_state()
                theme_list.create_team_weight_config(number)
                cfg.save()
```

- [ ] **Step 4: Run syntax verification**

Run: `uv run python -m py_compile app/page_card.py`

Expected: command exits successfully with no output.

- [ ] **Step 5: Commit**

```bash
git add app/page_card.py
git commit -m "refactor: 在镜牢编队界面构建前统一归一化状态"
```

---

### Task 5: Rework Team Deletion, Reindex, And Widget Rebuild

**Files:**
- Modify: `app/page_card.py`

- [ ] **Step 1: Add helper logic to rebuild teams dict keys and mapping**

Replace `refresh_team_setting_card()` in `app/page_card.py` with this implementation:

```python
    def refresh_team_setting_card(self):
        old_keys = sorted((int(key) for key in cfg.config.teams.copy().keys()))
        old_to_new = {}
        new_teams = {}

        for new_index, old_index in enumerate(old_keys, start=1):
            old_to_new[old_index] = new_index
            new_teams[f"{new_index}"] = cfg.config.teams[f"{old_index}"]
            if new_index != old_index:
                theme_list.set_team_weight_config_from_team(new_index, old_index)
                theme_list.delete_team_weight_config(old_index)

        cfg.config.teams = new_teams
        cfg.reindex_team_queue(old_to_new)
        cfg.save()
        self.get_setting()
```

- [ ] **Step 2: Update delete_team to remove from queue, compact config, and rebuild UI**

Replace `delete_team()` in `app/page_card.py` with:

```python
    def delete_team(self, target: str):
        try:
            team = self.findChild(MirrorTeamCombination, target)
            if team is not None:
                team_order_box = team.findChild(BaseCheckBox, f"the_team_{team.team_number}")
                if team_order_box is not None:
                    team_order_box.set_check_false()

            number = int(target.split("_")[-1])
            cfg.remove_team_from_queue(number)
            self.remove_team_card(target)
            cfg.config.teams.pop(f"{number}", None)
            theme_list.delete_team_weight_config(number)
            self.refresh_team_setting_card()
        except Exception as e:
            log.error(f"delete_team 出错：{e}")
```

This preserves the checkbox side effect for UI consistency, but the authoritative removal happens through `cfg.remove_team_from_queue(number)`.

- [ ] **Step 3: Confirm that delete flow rebuilds widgets instead of retranslating**

Ensure `delete_team()` no longer ends with:

```python
            self.retranslateUi()
```

The only rebuild at the end of the deletion path should be `self.get_setting()` from `refresh_team_setting_card()`.

- [ ] **Step 4: Run syntax verification**

Run: `uv run python -m py_compile app/page_card.py`

Expected: command exits successfully with no output.

- [ ] **Step 5: Commit**

```bash
git add app/page_card.py
git commit -m "fix: 删除镜牢编队后同步重排队列与界面"
```

---

### Task 6: Switch Mirror Execution To Queue Rotation

**Files:**
- Modify: `tasks/base/script_task_scheme.py`

- [ ] **Step 1: Read the current active team from queue head**

In `Mirror_task()` in `tasks/base/script_task_scheme.py`, replace:

```python
        teams_order = cfg.teams_order  # 复制一份队伍顺序
        team_num = teams_order.index(1)  # 获取序号1的队伍在队伍顺序中的位置
        team_setting = cfg.config.teams[f"{team_num + 1}"]  # 获取序号1的队伍的配置
```

with:

```python
        cfg.normalize_and_sync_team_state()
        queue = list(cfg.teams_active_queue)
        if not queue:
            break
        team_num = queue[0]
        team_setting = cfg.config.teams[f"{team_num}"]
```

- [ ] **Step 2: Replace skip-path manual teams_order writes with queue rotation**

Replace the fixed-team-use skip block:

```python
                for index, value in enumerate(teams_order):
                    if value == 0:
                        continue
                    if teams_order[index] == 1:
                        teams_order[index] = cfg.teams_be_select_num
                    elif teams_order[index] != 0:
                        teams_order[index] -= 1
                cfg.set_value("teams_order", teams_order)
                continue
```

with:

```python
                cfg.rotate_team_queue()
                continue
```

- [ ] **Step 3: Replace success-path manual teams_order writes with queue rotation**

Replace the success block:

```python
            for index, value in enumerate(teams_order):
                if value == 0:
                    continue
                if teams_order[index] == 1:
                    teams_order[index] = cfg.teams_be_select_num
                elif teams_order[index] != 0:
                    teams_order[index] -= 1
            cfg.set_value("teams_order", teams_order)
```

with:

```python
            cfg.rotate_team_queue()
```

- [ ] **Step 4: Run syntax verification**

Run: `uv run python -m py_compile tasks/base/script_task_scheme.py`

Expected: command exits successfully with no output.

- [ ] **Step 5: Commit**

```bash
git add tasks/base/script_task_scheme.py
git commit -m "refactor: 镜牢执行顺序改为轮转编队队列"
```

---

### Task 7: Replace Startup Self-Heal With Central Normalize Call

**Files:**
- Modify: `app/farming_interface.py`

- [ ] **Step 1: Replace legacy self-heal block in check_setting**

In `check_setting()` in `app/farming_interface.py`, replace:

```python
            teams_be_select = sum(1 for team in cfg.teams_be_select if team)
            if teams_be_select != cfg.teams_be_select_num:
                cfg.set_value("teams_be_select_num", teams_be_select)
                from utils.utils import check_teams_order

                teams_order = check_teams_order(cfg.teams_order)
                cfg.set_value("teams_order", teams_order)
                cfg.flush()
```

with:

```python
            cfg.normalize_and_sync_team_state()
            cfg.flush()
```

- [ ] **Step 2: Keep downstream validation code unchanged**

Do not change the later checks that iterate over `teams_be_select`; after normalization they still work as-is:

```python
            if cfg.teams_be_select_num == 0:
                ...

            teams_be_select = cfg.get_value("teams_be_select")
            for index in (i for i, t in enumerate(teams_be_select) if t is True):
                ...
```

- [ ] **Step 3: Run syntax verification**

Run: `uv run python -m py_compile app/farming_interface.py`

Expected: command exits successfully with no output.

- [ ] **Step 4: Commit**

```bash
git add app/farming_interface.py
git commit -m "refactor: 启动镜牢前统一归一化编队状态"
```

---

### Task 8: Verify Existing Defensive Read Still Covers Deleted Teams

**Files:**
- Modify: none expected
- Verify: `app/team_setting_card.py`

- [ ] **Step 1: Confirm StarlightCard still uses defensive `.get()` read**

Verify that `StarlightCard.__init__` in `app/team_setting_card.py` still contains:

```python
        self.level = 0
        if team_config := cfg.config.teams.get(str(team_num)):
            self.level = team_config.opening_bonus_level[self.team_num - 1]
```

No code change is required if this code is still present.

- [ ] **Step 2: No-op commit step**

If no file changed in this verification task, skip commit and continue.

---

### Task 9: Run End-To-End Verification Commands

**Files:**
- Verify: `module/config/config.py`
- Verify: `app/base_tools.py`
- Verify: `app/page_card.py`
- Verify: `tasks/base/script_task_scheme.py`
- Verify: `app/farming_interface.py`

- [ ] **Step 1: Run syntax checks for all changed modules**

Run:

```bash
uv run python -m py_compile module/config/config_typing.py module/config/config.py app/base_tools.py app/page_card.py tasks/base/script_task_scheme.py app/farming_interface.py app/team_setting_card.py
```

Expected: command exits successfully with no output.

- [ ] **Step 2: Run lint on the touched files**

Run:

```bash
uv run ruff check module/config/config_typing.py module/config/config.py app/base_tools.py app/page_card.py tasks/base/script_task_scheme.py app/farming_interface.py app/team_setting_card.py
```

Expected: all files pass, or only unrelated pre-existing issues remain outside the changed lines.

- [ ] **Step 3: Manual verification checklist**

Perform these manual checks in the running app:

1. Start with at least 6 mirror teams, enable `2`, `4`, `6`, then delete `3`.
Expected: UI rebuilds to `1..5`, active numbers become continuous, and the queue meaning remains `2 -> 5 -> 3`.

2. Add new teams beyond the original config count, enable them, then reopen the mirror page.
Expected: no log error, no index error, and active numbers remain `1..N`.

3. Use a config without `teams_active_queue` and start the app.
Expected: legacy fields are migrated automatically and mirror page opens without mismatch.

4. Run one mirror cycle with multiple active teams.
Expected: after one run, the previous active `1` moves to the end and all displayed active numbers rotate correctly.

- [ ] **Step 4: Commit final verification-safe state**

```bash
git add module/config/config_typing.py module/config/config.py app/base_tools.py app/page_card.py tasks/base/script_task_scheme.py app/farming_interface.py
git commit -m "fix: 重构镜牢编队顺序为单一队列状态"
```

---

### Task 10: Update Design/Plan Artifacts If Needed

**Files:**
- Verify: `docs/superpowers/specs/2026-05-03-mirror-team-queue-normalization-design.md`
- Verify: `docs/superpowers/plans/2026-05-03-mirror-team-queue-normalization.md`

- [ ] **Step 1: Re-read spec and confirm implementation matches it**

Check these points against the code after Task 9:

- `teams_active_queue` is the only business-written source of truth
- `delete_team()` rebuilds widgets through `get_setting()`
- `normalize_and_sync_team_state()` runs before mirror page widget construction
- mirror execution rotates queue instead of writing `teams_order`
- startup self-heal is centralized

- [ ] **Step 2: If implementation required any spec correction, update the spec file**

If the shipped code differs from the approved design in a necessary way, edit the corresponding section in:

```text
docs/superpowers/specs/2026-05-03-mirror-team-queue-normalization-design.md
```

Otherwise leave the spec unchanged.

- [ ] **Step 3: Commit docs only if a docs change was required**

```bash
git add docs/superpowers/specs/2026-05-03-mirror-team-queue-normalization-design.md docs/superpowers/plans/2026-05-03-mirror-team-queue-normalization.md
git commit -m "docs: 同步镜牢编队队列重构设计与实施计划"
```

Skip this commit if no docs changed.
