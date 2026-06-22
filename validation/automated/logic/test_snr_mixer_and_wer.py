"""Self-checks for the SNR mixer and the corpus WER harness (no models needed).

Validates the noise calibration math and the WER/command-recognition scoring
against a stub transcriber, so these harness pieces are trustworthy before any
real-model run.
"""

from __future__ import annotations

import numpy as np
import pytest

from validation.harness import corpus as corpusmod
from validation.harness import snr_mixer, wer


@pytest.fixture
def speech():
    # 1 s of a 220 Hz tone at 16 kHz -- a deterministic non-trivial "signal".
    t = np.arange(16000) / 16000.0
    return (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class TestSNRMixer:
    @pytest.mark.parametrize("snr", list(snr_mixer.TARGET_SNRS_DB))
    @pytest.mark.parametrize("kind", ["white", "pink"])
    def test_realised_snr_matches_target(self, speech, kind, snr):
        noise = snr_mixer.make_noise(kind, len(speech))
        mixed = snr_mixer.mix_at_snr(speech, noise, snr)
        assert abs(snr_mixer.realised_snr_db(speech, mixed) - snr) < 0.5

    def test_noise_fitted_to_length(self, speech):
        short = snr_mixer.make_noise("white", 1000)
        fitted = snr_mixer._fit_length(short, len(speech))
        assert len(fitted) == len(speech)

    def test_wav_round_trip(self, speech, tmp_path):
        path = tmp_path / "tone.wav"
        snr_mixer.write_wav(path, speech, snr_mixer.SAMPLE_RATE)
        back, sr = snr_mixer.read_wav(path)
        assert sr == snr_mixer.SAMPLE_RATE
        assert len(back) == len(speech)
        assert np.max(np.abs(back - speech)) < 1e-3  # 16-bit quantisation only

    def test_babble_requires_track(self, speech):
        with pytest.raises(ValueError):
            snr_mixer.make_noise("babble", len(speech), babble=None)


class TestWERHarness:
    def test_score_passage_wer_and_commands(self):
        p = corpusmod.Passage(
            name="p1",
            reference="please open firefox and then scroll down",
            wav=None,
            commands=[
                corpusmod.Command("open firefox", "apps"),
                corpusmod.Command("scroll down", "scroll"),
            ],
        )
        # Hypothesis drops "then" (1 deletion) and mishears one command.
        hyp = "please open firefox and scroll up"
        s = wer.score_passage(p, hyp)
        assert s.ref_words == 7
        assert s.errors >= 1
        # "open firefox" recognised, "scroll down" not (heard "scroll up").
        assert s.commands_recognized == 1
        assert s.n_commands == 2

    def test_compute_corpus_wer_with_stub(self, tmp_path):
        # A passage with a real (silent) wav so has_audio is True.
        wavp = tmp_path / "p.clean.wav"
        snr_mixer.write_wav(wavp, np.zeros(1600, dtype=np.float32))
        p = corpusmod.Passage("p", "open firefox", wavp, [corpusmod.Command("open firefox", "apps")])
        rows, summary = wer.compute_corpus_wer([p], transcribe_fn=lambda _w: "open firefox")
        assert summary["n_passages"] == 1
        assert summary["corpus_wer_pct"] == 0.0
        assert summary["command_recognition_pct"] == 100.0
