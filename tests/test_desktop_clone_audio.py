from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from module.desktop_clone.audio import prime_remote_audio


class DesktopCloneAudioTests(unittest.TestCase):
    @patch("module.desktop_clone.audio.winsound.PlaySound")
    def test_prime_plays_one_silent_pcm_wave(self, play_sound):
        primed, detail = prime_remote_audio()

        self.assertTrue(primed)
        self.assertEqual(detail, "attempt=1")
        play_sound.assert_called_once()
        wave_data, flags = play_sound.call_args.args
        self.assertEqual(wave_data[:4], b"RIFF")
        self.assertEqual(wave_data[8:12], b"WAVE")
        self.assertTrue(all(sample == 0 for sample in wave_data[44:]))
        self.assertNotEqual(flags, 0)

    @patch("module.desktop_clone.audio.time.sleep")
    @patch(
        "module.desktop_clone.audio.winsound.PlaySound",
        side_effect=[RuntimeError("not ready"), None],
    )
    def test_prime_retries_a_temporarily_unavailable_endpoint(
        self,
        play_sound,
        sleep,
    ):
        primed, detail = prime_remote_audio(attempts=3, retry_delay=0.1)

        self.assertTrue(primed)
        self.assertEqual(detail, "attempt=2")
        self.assertEqual(play_sound.call_count, 2)
        sleep.assert_called_once_with(0.1)

    @patch("module.desktop_clone.audio.time.sleep")
    @patch(
        "module.desktop_clone.audio.winsound.PlaySound",
        side_effect=RuntimeError("not ready"),
    )
    def test_prime_failure_is_bounded(self, play_sound, sleep):
        primed, detail = prime_remote_audio(attempts=3, retry_delay=0.1)

        self.assertFalse(primed)
        self.assertEqual(detail, "attempts=3 error=not ready")
        self.assertEqual(play_sound.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch(
        "module.desktop_clone.client.get_instance_context",
        return_value=SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=17,
        ),
    )
    def test_client_primes_audio_before_reporting_ready(self, _context):
        from module.desktop_clone.client import DesktopCloneClient

        events = []
        client = DesktopCloneClient()

        def stop_after_read(_handle):
            events.append(("read",))
            client._stop_event.set()

        with (
            patch(
                "module.desktop_clone.client.connect_pipe",
                return_value=object(),
            ),
            patch(
                "module.desktop_clone.client.prime_remote_audio",
                side_effect=lambda: (
                    events.append(("prime",)) or (True, "attempt=1")
                ),
            ),
            patch.object(
                client,
                "_send",
                side_effect=lambda *parts: events.append(parts),
            ),
            patch.object(client, "_read_commands", side_effect=stop_after_read),
            patch.object(client, "_close_handle"),
        ):
            client.run()

        self.assertEqual(
            events[:5],
            [
                ("hello", "child-session", "1"),
                ("prime",),
                ("audio-prime", "ready", "YXR0ZW1wdD0x"),
                ("ready", "17"),
                ("read",),
            ],
        )
