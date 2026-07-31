"""Small line protocol shared by root, child AALC, and the RDP host."""

from __future__ import annotations

import base64

PROTOCOL_VERSION = "1"
MAX_MESSAGE_BYTES = 64 * 1024

ROLE_RDP_HOST = "rdp-host"
ROLE_CHILD_SESSION = "child-session"


def encode_text(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_text(value: str) -> str:
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except Exception:
        from module.desktop_clone.messages import translate_message

        return translate_message("无法解码远端错误信息")


def serialize_message(parts: list[str] | tuple[str, ...]) -> bytes:
    if not parts or any("\t" in part or "\r" in part or "\n" in part for part in parts):
        raise ValueError("桌面分身 IPC 消息包含非法字段")
    payload = ("\t".join(parts) + "\n").encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("桌面分身 IPC 消息超过长度上限")
    return payload


def parse_message(payload: bytes) -> list[str]:
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("桌面分身 IPC 消息超过长度上限")
    line = payload.decode("utf-8", errors="strict").rstrip("\r\n")
    if not line:
        raise ValueError("桌面分身 IPC 消息为空")
    return line.split("\t")

