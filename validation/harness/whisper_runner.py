"""Real faster-whisper transcription, faithful to EchoBase's own settings.

Mirrors ``EchoBase._whisper_text``: int8 compute, the profile's model + beam,
``vad_filter=True`` and the profile's initial-prompt biasing (command vs
phrases/phrases-strong). Used by the realmodel WER / noise / latency tests.

faster-whisper is imported lazily so this module can be imported without the
heavy stack present (tests gate on ECHOBASE_VALIDATION_REAL before calling in).
"""

from __future__ import annotations

import time

from EchoBase.core import config as ebconfig
from EchoBase.core import main as ebmain


def _initial_prompt(settings, known_phrases) -> str:
    """Reproduce EchoBase._command_prompt for the given settings."""
    vocab = known_phrases or []
    if settings.bias == "command" or not vocab:
        return ebmain.COMMAND_PROMPT
    joined = ", ".join(vocab)
    if settings.bias == "phrases-strong":
        return f"{joined}. {ebmain.COMMAND_PROMPT}"
    return f"{ebmain.COMMAND_PROMPT}, {joined}"


def make_transcribe_fn(profile: int = 2, known_phrases=None):
    """Load the real model for *profile* and return ``transcribe_fn(wav)->str``.

    If *known_phrases* is None, the canonical vocabulary is loaded from a real
    core so phrases-biased profiles use the same prompt EchoBase would.
    """
    from faster_whisper import WhisperModel

    settings = ebconfig.recognition_settings({"recognition_profile": profile})
    if known_phrases is None:
        from validation.harness.echobase_factory import build_core

        known_phrases = build_core(recognition_profile=profile).known_phrases
    prompt = _initial_prompt(settings, known_phrases)
    model = WhisperModel(settings.model, compute_type="int8")

    def transcribe_fn(wav_path: str) -> str:
        segments, _info = model.transcribe(
            wav_path,
            beam_size=settings.beam,
            vad_filter=True,
            initial_prompt=prompt,
        )
        return " ".join(seg.text for seg in segments).strip()

    return transcribe_fn


def timed_transcribe_fn(profile: int = 2, known_phrases=None):
    """Like make_transcribe_fn but returns ``fn(wav)->(text, seconds)``."""
    inner = make_transcribe_fn(profile=profile, known_phrases=known_phrases)

    def fn(wav_path: str):
        t0 = time.perf_counter()
        text = inner(wav_path)
        return text, time.perf_counter() - t0

    return fn
