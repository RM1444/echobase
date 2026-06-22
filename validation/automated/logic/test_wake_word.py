"""Wake-word detection logic (thesis section 1.3) -- BOTH paths.

EchoBase has two wake mechanisms (verified in ``main._wake_detected``):

1. **openwakeword acoustic classifier** for the built-in names
   (Jarvis/alexa/mycroft/marvin): a per-frame model whose score is thresholded at
   ``WAKE_THRESHOLD`` (0.5).
2. **Whisper substring fallback** for custom names with no pretrained model:
   transcribe a rolling ``LISTEN_WINDOW`` (3 s) buffer and check whether
   ``"hey {name}"`` appears in the transcript.

These tests validate the decision logic of both paths plus the cooldown/window
constants. The end-to-end FPR (<=1/24h) and FNR (<=5%) figures require real audio
and are produced by the wake harness over ``corpora/wake/`` (see realmodel tier
and the protocols), not here.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from EchoBase.core import main as ebmain


def _pcm(n: int = ebmain.WAKE_FRAME) -> bytes:
    """A frame of silence as int16 PCM bytes (content is irrelevant -- the model
    is mocked; only the detector's thresholding logic is under test)."""
    return np.zeros(n, dtype=np.int16).tobytes()


class TestConstants:
    def test_threshold_and_window_constants(self):
        assert ebmain.WAKE_THRESHOLD == 0.5
        assert ebmain.WAKE_COOLDOWN == 3.0
        assert ebmain.LISTEN_WINDOW == 3
        assert ebmain.WAKE_FRAME == 1280  # 80 ms @ 16 kHz

    def test_builtin_names_have_acoustic_models(self):
        for name in ("jarvis", "alexa", "mycroft", "marvin"):
            assert name in ebmain.WAKE_MODELS


class TestOpenWakeWordPath:
    """Path 1: acoustic classifier, score thresholded at WAKE_THRESHOLD."""

    def _core_with_scores(self, fresh_core, score):
        core = fresh_core(name="Jarvis")
        wake = MagicMock()
        wake.predict.return_value = {"hey_jarvis": score}
        core.wakeword = wake
        return core

    def test_fires_at_threshold(self, fresh_core):
        core = self._core_with_scores(fresh_core, ebmain.WAKE_THRESHOLD)
        assert core._wake_detected(_pcm(), []) is True

    def test_fires_above_threshold(self, fresh_core):
        core = self._core_with_scores(fresh_core, 0.9)
        assert core._wake_detected(_pcm(), []) is True

    def test_silent_below_threshold(self, fresh_core):
        core = self._core_with_scores(fresh_core, 0.49)
        assert core._wake_detected(_pcm(), []) is False

    def test_empty_scores_does_not_fire(self, fresh_core):
        core = fresh_core(name="Jarvis")
        wake = MagicMock()
        wake.predict.return_value = {}
        core.wakeword = wake
        assert core._wake_detected(_pcm(), []) is False


class TestWhisperFallbackPath:
    """Path 2: custom name, transcribe a 3 s buffer and substring-match."""

    def _custom_core(self, fresh_core, transcript):
        core = fresh_core(name="Computer")  # not in WAKE_MODELS -> fallback
        core.wakeword = None
        core.transcribe = lambda *a, **k: transcript
        return core

    def test_too_short_buffer_does_not_fire(self, fresh_core):
        core = self._custom_core(fresh_core, "hey computer")
        # One frame is far below the LISTEN_WINDOW worth of frames.
        assert core._wake_detected(_pcm(), [_pcm()]) is False

    def test_fires_when_phrase_present(self, fresh_core):
        core = self._custom_core(fresh_core, "hey computer, open firefox")
        frames_needed = int(ebmain.LISTEN_WINDOW * 16000 / ebmain.WAKE_FRAME)
        buffer = [_pcm() for _ in range(frames_needed)]
        assert core._wake_detected(_pcm(), buffer) is True

    def test_silent_when_phrase_absent(self, fresh_core):
        core = self._custom_core(fresh_core, "what time is it")
        frames_needed = int(ebmain.LISTEN_WINDOW * 16000 / ebmain.WAKE_FRAME)
        buffer = [_pcm() for _ in range(frames_needed)]
        assert core._wake_detected(_pcm(), buffer) is False

    def test_buffer_cleared_after_attempt(self, fresh_core):
        core = self._custom_core(fresh_core, "nope")
        frames_needed = int(ebmain.LISTEN_WINDOW * 16000 / ebmain.WAKE_FRAME)
        buffer = [_pcm() for _ in range(frames_needed)]
        core._wake_detected(_pcm(), buffer)
        assert buffer == []  # cleared so the window slides fresh


def test_wake_phrase_derived_from_name(fresh_core):
    assert fresh_core(name="Computer").wake_phrase == "hey computer"
    assert fresh_core(name="Jarvis").wake_phrase == "hey jarvis"
