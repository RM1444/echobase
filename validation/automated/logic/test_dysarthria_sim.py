"""Self-checks for the dysarthria timing simulator (section 2.3)."""

from __future__ import annotations

import numpy as np
import pytest

from validation.harness import dysarthria_sim as sim


@pytest.fixture
def speech():
    t = np.arange(16000) / 16000.0
    return (0.5 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)


def test_time_stretch_lengthens(speech):
    out = sim.time_stretch(speech, 1.5)
    assert abs(len(out) - int(len(speech) * 1.5)) <= 1


def test_inject_pauses_adds_silence(speech):
    out = sim.inject_pauses(speech, 16000, n_pauses=2)
    # Two pauses of >=1.5 s each add >=3 s of samples.
    assert len(out) >= len(speech) + int(2 * 1.5 * 16000)


def test_injected_pause_within_target_range(speech):
    out = sim.inject_pauses(speech, 16000, n_pauses=1)
    added = len(out) - len(speech)
    secs = added / 16000.0
    assert sim.PAUSE_RANGE_S[0] <= secs <= sim.PAUSE_RANGE_S[1] + 0.01


def test_simulate_combines_both(speech):
    out = sim.simulate(speech, 16000, n_pauses=2, stretch=1.3)
    # stretched (1.3x) then +2 pauses -> clearly longer than the original.
    assert len(out) > len(speech) * 1.3
