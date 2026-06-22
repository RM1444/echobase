"""Real-model tier fixtures.

These tests load the REAL faster-whisper models and run on recorded audio, so
they are heavy and environment-dependent. They run ONLY when:

* ``ECHOBASE_VALIDATION_REAL=1`` is set, AND
* faster-whisper is importable, AND
* the relevant corpus audio is present.

Otherwise each test SKIPS with a clear reason. Crucially this subpackage does NOT
stub the native stack (unlike automated/logic/), so it must be run in its own
pytest session -- never mixed with the logic tier (whose import-time stubs would
poison the real model). The realmodel/logic split keeps that guarantee.
"""

from __future__ import annotations

import os

import pytest

REAL = os.environ.get("ECHOBASE_VALIDATION_REAL") == "1"
PROFILE = int(os.environ.get("ECHOBASE_VALIDATION_PROFILE", "2"))


def _guard_against_stubbed_stack():
    """Fail loudly if the logic tier's stubs leaked into this process."""
    import sys
    from unittest.mock import MagicMock

    fw = sys.modules.get("faster_whisper")
    if isinstance(fw, MagicMock):
        pytest.exit(
            "faster_whisper is stubbed -- run realmodel/ in its own pytest session, "
            "not together with automated/logic/.",
            returncode=3,
        )


@pytest.fixture(scope="session", autouse=True)
def require_real():
    if not REAL:
        pytest.skip("set ECHOBASE_VALIDATION_REAL=1 to run real-model tests")
    try:
        import faster_whisper  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"faster-whisper not importable: {exc}")
    _guard_against_stubbed_stack()


@pytest.fixture(scope="session")
def profile() -> int:
    return PROFILE


@pytest.fixture(scope="session")
def transcribe_fn(require_real, profile):
    from validation.harness.whisper_runner import make_transcribe_fn

    return make_transcribe_fn(profile=profile)


@pytest.fixture(scope="session")
def audio_passages():
    from validation.harness import corpus

    passages = corpus.passages_with_audio()
    if not passages:
        pytest.skip("no recorded passages in corpora/reading_passages/*.clean.wav")
    return passages
