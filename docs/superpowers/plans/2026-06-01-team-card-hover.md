# Team Card Hover Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the team-setting sinner card hover regression so cards always return to their base size on mouse leave and never accumulate size during rapid switching.

**Architecture:** Keep the current `SinnerSelect` animation behavior, but preserve the cached base geometry while the geometry animation is running. Add a focused regression test that simulates the animation-time resize path which currently clears the cache and causes the bad leave target.

**Tech Stack:** Python 3.12+, PySide6, unittest, uv

---

### Task 1: Lock the regression with tests

**Files:**
- Create: `tests/test_team_card_hover.py`
- Modify: `app/base_combination.py:719-778`

- [ ] **Step 1: Write the failing test**

```python
class TestTeamCardHover(unittest.TestCase):
    def test_resize_during_running_hover_animation_keeps_base_geometry(self):
        ...

    def test_leave_after_running_hover_resize_targets_original_geometry(self):
        ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_team_card_hover -v`
Expected: FAIL because `resizeEvent()` clears `raw_geom` while the hover animation is running.

- [ ] **Step 3: Write minimal implementation**

```python
def resizeEvent(self, event):
    ...
    if self.ani.state() != QAbstractAnimation.State.Running:
        self.raw_geom = None
        self._end_geom = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_team_card_hover -v`
Expected: PASS

- [ ] **Step 5: Run one nearby regression check**

Run: `uv run python -m unittest tests.test_daily_task_preview -v`
Expected: PASS
