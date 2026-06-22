"""Variable cadence / VAD endpointing (thesis section 2.3) -- dysarthria-critical.

EchoBase ends an utterance when trailing silence reaches ``vad_silence_hang``
seconds (``record_until_silence``), where the hang comes from the speaker's
configured ``speech_pace`` via ``config.PACE_TIMING``:

    normal  -> (0.6 s hang, 8 s cap)
    relaxed -> (1.0 s hang, 11 s cap)
    slow    -> (1.4 s hang, 14 s cap)

Each VAD frame is ``VAD_FRAME / 16000 = 0.08 s``. These tests drive
``record_until_silence`` deterministically (scripted speech/silence, no real
audio) to measure the longest mid-utterance pause tolerated at each pace and
verify the utterance is not cut early.

FINDING surfaced and reported: even the slowest pace tolerates only ~1.4 s of
pause, below the 1.5-3.5 s mid-utterance pauses typical of moderate dysarthria.
The suite reports this gap rather than asserting a target the code cannot meet.
"""

from __future__ import annotations

import math

import pytest

from EchoBase.core import config as ebconfig
from EchoBase.core import main as ebmain
from validation.harness import metrics

FRAME_SEC = ebmain.VAD_FRAME / 16000.0  # 0.08 s
DYSARTHRIC_PAUSE_RANGE = (1.5, 3.5)  # target the plan asks us to tolerate


def _run_record(core, speech_then_silence_script):
    """Drive record_until_silence with a scripted _is_speech sequence.

    *speech_then_silence_script* is a list of bools (True=speech frame). Once it
    is exhausted, frames are treated as silence forever. Returns the number of
    frames captured before endpointing fired.
    """
    seq = iter(speech_then_silence_script)
    state = {"reads": 0}

    def fake_read(*_a, **_k):
        state["reads"] += 1
        return b"\x00\x00"

    core.stream.read = fake_read
    core._get_vad = lambda: object()
    # record_until_silence calls self._is_speech(vad, chunk); a plain 2-arg
    # callable on the instance shadows the bound method correctly.
    core._is_speech = lambda _vad, _chunk: next(seq, False)
    ebmain.EchoBase.record_until_silence(core)
    return state["reads"]


class TestPaceTimingTable:
    @pytest.mark.parametrize(
        "pace,hang,cap",
        [("normal", 0.6, 8.0), ("relaxed", 1.0, 11.0), ("slow", 1.4, 14.0)],
    )
    def test_pace_timing_values(self, pace, hang, cap):
        assert ebconfig.PACE_TIMING[pace] == (hang, cap)

    def test_pace_timing_applied_to_core(self, fresh_core):
        for pace, (hang, cap) in ebconfig.PACE_TIMING.items():
            core = fresh_core()
            core.config["speech_pace"] = pace
            core.vad_silence_hang, core.vad_max_seconds = ebconfig.pace_timing(core.config)
            assert (core.vad_silence_hang, core.vad_max_seconds) == (hang, cap)


class TestEndpointing:
    @pytest.mark.parametrize("pace", ["normal", "relaxed", "slow"])
    def test_endpoints_after_hang_silence(self, fresh_core, pace):
        """Recording stops only after ~hang seconds of continuous trailing silence."""
        core = fresh_core()
        hang, cap = ebconfig.PACE_TIMING[pace]
        core.vad_silence_hang, core.vad_max_seconds = hang, cap
        speech_frames = 10  # ~0.8 s of speech
        reads = _run_record(core, [True] * speech_frames)
        # silence frames needed to reach the hang threshold
        silence_frames = math.ceil(hang / FRAME_SEC)
        assert reads == speech_frames + silence_frames

    @pytest.mark.parametrize("pace", ["normal", "relaxed", "slow"])
    def test_short_pause_does_not_cut_utterance(self, fresh_core, pace):
        """A pause shorter than the hang must NOT end the utterance: speech after
        the pause is still captured."""
        core = fresh_core()
        hang, cap = ebconfig.PACE_TIMING[pace]
        core.vad_silence_hang, core.vad_max_seconds = hang, cap
        # pause = just under the hang, then speech resumes, then a full hang.
        pause_frames = max(1, math.ceil(hang / FRAME_SEC) - 1)
        script = [True] * 5 + [False] * pause_frames + [True] * 5
        reads = _run_record(core, script)
        # It must not have stopped during the mid-pause; it captured the resumed
        # speech and then the final hang of silence.
        assert reads > 5 + pause_frames + 5


def test_report_tolerated_pause_vs_dysarthric_target(fresh_core, results_dir):
    """Measure the max tolerated mid-utterance pause per pace and compare to the
    1.5-3.5 s dysarthric target. Emits a thesis table + an honest gap verdict."""
    rows = []
    for pace, (hang, cap) in ebconfig.PACE_TIMING.items():
        # The longest fully-tolerated pause is just under the hang (one frame of
        # silence below threshold keeps the utterance open).
        tolerated = (math.ceil(hang / FRAME_SEC) - 1) * FRAME_SEC
        rows.append(
            {
                "speech_pace": pace,
                "silence_hang_s": hang,
                "max_utterance_s": cap,
                "max_tolerated_pause_s": round(tolerated, 2),
                "meets_1.5s_min": tolerated >= DYSARTHRIC_PAUSE_RANGE[0],
            }
        )
    meets_any = any(r["meets_1.5s_min"] for r in rows)
    metrics.write_report(
        "cadence_vad",
        rows,
        {
            "dysarthric_target_s": list(DYSARTHRIC_PAUSE_RANGE),
            "any_pace_meets_min": meets_any,
            "finding": (
                "No pace tolerates the 1.5 s lower bound of the dysarthric pause "
                "target; the slow pace caps at ~1.4 s. Recommend a 'very slow' "
                "pace (>=1.8 s hang) for moderate dysarthria."
            ),
        },
        title="VAD endpointing tolerance per speech pace",
        caption="Section 2.3 -- tolerated mid-utterance pause vs 1.5-3.5 s dysarthric target.",
        results_dir=results_dir,
    )
    # This is a measurement+documentation test, not a pass/fail gate on the app:
    # we assert the artifact exists and the verdict is recorded honestly.
    assert (results_dir / "cadence_vad.md").exists()
    assert meets_any is False  # documents the gap; update if a slower pace is added
