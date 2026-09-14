"""Whitelisted task-state synchronization from the child AALC to root."""

from __future__ import annotations

import json
from typing import Any

from module.config import cfg
from module.desktop_clone.messages import translate_message

_SCALAR_STATE_TYPES: dict[str, type | tuple[type, ...]] = {
    "last_auto_change": (int, float),
    "hard_mirror_chance": int,
    "hard_mirror": (bool, int),
}
_TEAM_QUEUE_KEY = "teams_active_queue"


def collect_child_state_delta() -> dict[str, Any]:
    """Return only task-owned state that is expected to persist after a run."""
    return {
        _TEAM_QUEUE_KEY: list(cfg.get_value(_TEAM_QUEUE_KEY, []) or []),
        **{
            key: cfg.get_value(key)
            for key in _SCALAR_STATE_TYPES
        },
    }


def serialize_child_state_delta() -> str:
    return json.dumps(
        collect_child_state_delta(),
        ensure_ascii=True,
        separators=(",", ":"),
    )


def apply_child_state_delta(serialized: str) -> None:
    """Validate and persist a child-reported state delta in root configuration."""
    payload = json.loads(serialized)
    if not isinstance(payload, dict) or set(payload) != {
        _TEAM_QUEUE_KEY,
        *_SCALAR_STATE_TYPES,
    }:
        raise ValueError(translate_message("分身状态增量字段不合法"))

    queue = payload[_TEAM_QUEUE_KEY]
    if (
        not isinstance(queue, list)
        or len(queue) > 100
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 1
            for value in queue
        )
    ):
        raise ValueError(translate_message("分身队伍队列不合法"))

    for key, expected_type in _SCALAR_STATE_TYPES.items():
        value = payload[key]
        if key != "hard_mirror" and isinstance(value, bool):
            raise ValueError(
                translate_message("分身状态字段 {0} 类型不合法", key)
            )
        if not isinstance(value, expected_type):
            raise ValueError(
                translate_message("分身状态字段 {0} 类型不合法", key)
            )

    cfg.set_value(_TEAM_QUEUE_KEY, queue)
    cfg.normalize_and_sync_team_state(persist=True)
    for key in _SCALAR_STATE_TYPES:
        cfg.set_value(key, payload[key])
