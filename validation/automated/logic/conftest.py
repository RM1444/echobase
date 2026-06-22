"""Logic-tier fixtures: stub the heavy native stack, then build a real core.

These tests validate routing / recovery / wake / cadence *logic* and must run
fast and offline with no models. We stub the heavy/optional native imports
(mirroring the pattern in the project's own ``tests/``) BEFORE any test imports
``EchoBase.core.main``. This stubbing is confined to the ``logic/`` subpackage
so it never leaks into ``realmodel/``, which needs the real stack.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# Stub heavy / optional native deps at import time (before EchoBase is imported).
# numpy is intentionally left real (the core uses it for buffer math).
_STUBBED = [
    "pyaudio",
    "openwakeword",
    "openwakeword.model",
    "openwakeword.vad",
    "faster_whisper",
    "cv2",
    "mediapipe",
]
for _name in _STUBBED:
    sys.modules.setdefault(_name, MagicMock())


@pytest.fixture(scope="session")
def core():
    """A real EchoBase with all 17 plugins loaded and I/O neutralised (shared,
    read-mostly -- use for routing where no per-test mutation happens)."""
    from validation.harness.echobase_factory import build_core

    return build_core(name="Jarvis")


@pytest.fixture
def fresh_core():
    """Function-scoped factory for a fresh, I/O-neutralised EchoBase, for tests
    that monkeypatch core methods (wake / recovery / cadence)."""
    from validation.harness.echobase_factory import build_core

    def _make(name: str = "Jarvis"):
        return build_core(name=name)

    return _make
