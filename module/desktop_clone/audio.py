"""Prime the redirected playback endpoint inside a Windows Child Session."""

from __future__ import annotations

import struct
import time
import winsound

_SAMPLE_RATE = 48_000
_CHANNEL_COUNT = 2
_SAMPLE_WIDTH_BYTES = 2
_PRIME_DURATION_MS = 200


def _build_silent_wave() -> bytes:
    frame_count = _SAMPLE_RATE * _PRIME_DURATION_MS // 1000
    data_size = frame_count * _CHANNEL_COUNT * _SAMPLE_WIDTH_BYTES
    block_align = _CHANNEL_COUNT * _SAMPLE_WIDTH_BYTES
    byte_rate = _SAMPLE_RATE * block_align
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        _CHANNEL_COUNT,
        _SAMPLE_RATE,
        byte_rate,
        block_align,
        _SAMPLE_WIDTH_BYTES * 8,
        b"data",
        data_size,
    )
    return header + bytes(data_size)


_SILENT_WAVE = _build_silent_wave()


def prime_remote_audio(
    *,
    attempts: int = 3,
    retry_delay: float = 0.2,
) -> tuple[bool, str]:
    """Open the Child Session default playback endpoint before tasks start.

    RDP creates its redirected playback endpoint lazily. A short synchronous
    silent stream forces that initialization to finish before applications such
    as the game perform their own one-shot audio-device discovery.
    """
    last_error = ""
    for attempt in range(1, max(1, attempts) + 1):
        try:
            winsound.PlaySound(
                _SILENT_WAVE,
                winsound.SND_MEMORY
                | winsound.SND_NODEFAULT,
            )
            return True, f"attempt={attempt}"
        except RuntimeError as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(max(0.0, retry_delay))
    return False, f"attempts={max(1, attempts)} error={last_error or 'unknown'}"
