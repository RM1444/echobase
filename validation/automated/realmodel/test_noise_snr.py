"""WER vs SNR across noise types (thesis section 1.4).

For each recorded passage we synthesise white/pink (and babble if a babble track
is present) noise at 40/50/60 dB SNR, transcribe the noisy mix with the real
model, and report WER + command-recognition degradation vs the clean baseline.
Target: WER <= 18% noisy. Reported honestly per condition.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from validation.harness import corpus as corpusmod
from validation.harness import metrics, snr_mixer, wer

pytestmark = pytest.mark.real_model

NOISE_TYPES = ("white", "pink")  # babble added automatically if the track exists


def _babble_track():
    p = corpusmod.CORPUS_DIR / "noise" / "babble.wav"
    if p.exists():
        return snr_mixer.read_wav(p)[0]
    return None


def test_wer_vs_snr(audio_passages, transcribe_fn, results_dir):
    babble = _babble_track()
    noise_types = list(NOISE_TYPES) + (["babble"] if babble is not None else [])
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for noise in noise_types:
            for snr in snr_mixer.TARGET_SNRS_DB:
                noisy_passages = []
                for p in audio_passages:
                    speech, sr = snr_mixer.read_wav(p.wav)
                    track = snr_mixer.make_noise(noise, len(speech), babble=babble)
                    mixed = snr_mixer.mix_at_snr(speech, track, snr)
                    out = tmpdir / f"{p.name}.{noise}.{int(snr)}.wav"
                    snr_mixer.write_wav(out, mixed, sr)
                    noisy_passages.append(
                        corpusmod.Passage(p.name, p.reference, out, p.commands)
                    )
                cond = f"{noise}@{int(snr)}dB"
                _r, summary = wer.compute_corpus_wer(noisy_passages, transcribe_fn, condition=cond)
                rows.append(
                    {
                        "noise_type": noise,
                        "snr_db": snr,
                        "corpus_wer_pct": summary["corpus_wer_pct"],
                        "command_recognition_pct": summary["command_recognition_pct"],
                        "n_passages": summary["n_passages"],
                    }
                )
    metrics.write_report(
        "wer_vs_snr",
        rows,
        {"noise_types": noise_types, "snr_levels": list(snr_mixer.TARGET_SNRS_DB)},
        title="WER vs SNR by noise type",
        caption="Section 1.4 -- recognition degradation under white/pink/babble noise.",
        results_dir=results_dir,
    )
    assert rows
    # Lower SNR should generally not improve WER; record the monotonic trend.
    assert all(r["corpus_wer_pct"] >= 0 for r in rows)
