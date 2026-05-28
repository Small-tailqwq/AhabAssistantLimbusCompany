from collections.abc import Mapping

KeyCode = int | str

_LETTER_KEYS = tuple(chr(code) for code in range(ord("a"), ord("z") + 1))
_DIGIT_KEYS = tuple(str(number) for number in range(10))

CANONICAL_KEYS = frozenset(
    (
        *_LETTER_KEYS,
        *_DIGIT_KEYS,
        "enter",
        "esc",
        "space",
        "tab",
        "shift",
        "ctrl",
        "alt",
        "up",
        "down",
        "left",
        "right",
        "backspace",
        "delete",
        "pageup",
        "pagedown",
        "home",
        "end",
        "insert",
        "lwindows",
        "rwindows",
    )
)

KEY_ALIASES = {
    "return": "enter",
    "escape": "esc",
    "control": "ctrl",
    "ctl": "ctrl",
    "option": "alt",
    "arrow_up": "up",
    "arrow_down": "down",
    "arrow_left": "left",
    "arrow_right": "right",
    "up_arrow": "up",
    "down_arrow": "down",
    "left_arrow": "left",
    "right_arrow": "right",
    "back_space": "backspace",
    "del": "delete",
    "page_up": "pageup",
    "pgup": "pageup",
    "page_down": "pagedown",
    "pgdn": "pagedown",
    "lwin": "lwindows",
    "left_windows": "lwindows",
    "left_win": "lwindows",
    "rwin": "rwindows",
    "right_windows": "rwindows",
    "right_win": "rwindows",
}


class UnsupportedKeyError(KeyError):
    def __init__(self, key: object, backend: str | None = None):
        self.key = key
        self.backend = backend
        if backend:
            message = f"Unsupported key for {backend}: {key!r}"
        else:
            message = f"Unsupported key: {key!r}"
        super().__init__(message)

    def __str__(self) -> str:
        return str(self.args[0])


def normalize_key(key: str) -> str:
    normalized = str(key).strip().lower()
    if normalized.startswith("<") and normalized.endswith(">"):
        normalized = normalized[1:-1]
    normalized = normalized.replace("-", "_").replace(" ", "_")
    normalized = KEY_ALIASES.get(normalized, normalized)
    if normalized not in CANONICAL_KEYS:
        raise UnsupportedKeyError(key)
    return normalized


def resolve_backend_key(key: str, backend_map: Mapping[str, KeyCode], backend: str) -> KeyCode:
    canonical_key = normalize_key(key)
    try:
        return backend_map[canonical_key]
    except KeyError as e:
        raise UnsupportedKeyError(canonical_key, backend=backend) from e
