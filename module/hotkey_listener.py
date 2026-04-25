from __future__ import annotations

from collections.abc import Callable
from time import time

from pynput import keyboard

_MODIFIER_KEYS = {
    keyboard.Key.alt,
    keyboard.Key.alt_gr,
    keyboard.Key.cmd,
    keyboard.Key.ctrl,
    keyboard.Key.shift,
}

# 修饰键和弦超时（秒）。当修饰键被按下后超过此时间仍没有对应的非修饰键
# 被按下，认为该修饰键可能因 Alt+Tab 等系统操作导致 key-up 丢失而残留。
# 正常热键操作（如 Ctrl+Q）在 1 秒内完成，此阈值覆盖所有合理手速。
_HOTKEY_CHORD_TIMEOUT = 5.0


class _ExactHotKey:
    def __init__(self, keys: list[keyboard.Key | keyboard.KeyCode], on_activate: Callable[[], None]):
        self._keys = set(keys)
        self._state: set[keyboard.Key | keyboard.KeyCode] = set()
        self._required_modifiers = {key for key in self._keys if key in _MODIFIER_KEYS}
        self._is_active = False
        self._on_activate = on_activate

    def press(
        self,
        key: keyboard.Key | keyboard.KeyCode,
        pressed_modifiers: set[keyboard.Key],
    ) -> None:
        if key in self._keys:
            self._state.add(key)

        should_activate = self._state == self._keys and pressed_modifiers == self._required_modifiers
        if should_activate and not self._is_active:
            self._is_active = True
            self._on_activate()
        elif not should_activate:
            self._is_active = False

    def release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        self._state.discard(key)
        self._is_active = False


class ExactGlobalHotKeys(keyboard.Listener):
    def __init__(self, hotkeys: dict[str, Callable[[], None]], *args, **kwargs):
        self._pressed_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        self._modifier_timestamps: dict[keyboard.Key | keyboard.KeyCode, float] = {}
        self._hotkeys = [
            _ExactHotKey(keyboard.HotKey.parse(hotkey), callback)
            for hotkey, callback in hotkeys.items()
        ]
        super().__init__(
            on_press=self._on_press,
            on_release=self._on_release,
            *args,
            **kwargs,
        )
        self.daemon = True

    def _on_press(self, key, injected=False):
        if injected:
            return

        canonical_key = self.canonical(key)
        self._pressed_keys.add(canonical_key)
        now = time()

        # 非修饰键按下时，检查是否有修饰键已"按住"过久（key-up 可能已被系统吞掉）
        if canonical_key not in _MODIFIER_KEYS:
            stale = [
                k for k in list(self._pressed_keys)
                if k in _MODIFIER_KEYS
                and now - self._modifier_timestamps.get(k, now) > _HOTKEY_CHORD_TIMEOUT
            ]
            for k in stale:
                self._pressed_keys.discard(k)
                for hotkey in self._hotkeys:
                    hotkey.release(k)
        else:
            self._modifier_timestamps[canonical_key] = now

        pressed_modifiers = {key for key in self._pressed_keys if key in _MODIFIER_KEYS}
        for hotkey in self._hotkeys:
            hotkey.press(canonical_key, pressed_modifiers)

    def _on_release(self, key, injected=False):
        if injected:
            return

        canonical_key = self.canonical(key)
        for hotkey in self._hotkeys:
            hotkey.release(canonical_key)
        self._pressed_keys.discard(canonical_key)
        self._modifier_timestamps.pop(canonical_key, None)
