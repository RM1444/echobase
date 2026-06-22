"""Mix clean speech with calibrated noise at a target SNR (thesis section 1.4).

Produces the noisy conditions for the WER-vs-SNR experiment: white, pink and
babble noise mixed into a clean recording at a chosen SNR in dB. The mix gain is
computed from the measured signal/noise powers (see ``metrics.noise_gain_for_snr``)
so the realised SNR matches the target.

CLI:
    python -m validation.harness.snr_mixer in.wav out.wav --noise pink --snr 50
    python -m validation.harness.snr_mixer in.wav out.wav --noise babble \\
        --babble corpora/noise/babble.wav --snr 40
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

from validation.harness import metrics

TARGET_SNRS_DB = (40.0, 50.0, 60.0)  # the plan's noise conditions
NOISE_TYPES = ("white", "pink", "babble")
SAMPLE_RATE = 16000  # EchoBase records mono 16 kHz


# --------------------------------------------------------------------------- #
# WAV I/O (mono 16-bit PCM, the format EchoBase uses)
# --------------------------------------------------------------------------- #


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a mono 16-bit PCM wav into float32 samples in [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return data, sr


def write_wav(path: str | Path, samples: np.ndarray, sr: int = SAMPLE_RATE) -> Path:
    """Write float32 samples in [-1, 1] as mono 16-bit PCM."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    target = Path(path)
    with wave.open(str(target), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return target


# --------------------------------------------------------------------------- #
# Noise generators
# --------------------------------------------------------------------------- #


def white_noise(n: int, seed: int = 1234) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n).astype(np.float32)


def pink_noise(n: int, seed: int = 1234) -> np.ndarray:
    """1/f (pink) noise via spectral shaping of white noise. Deterministic for a
    given seed so noisy corpora are reproducible."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n)
    scaling = np.ones_like(freqs)
    nonzero = freqs > 0
    scaling[nonzero] = 1.0 / np.sqrt(freqs[nonzero])
    shaped = np.fft.irfft(spectrum * scaling, n=n)
    shaped = shaped / (np.max(np.abs(shaped)) or 1.0)
    return shaped.astype(np.float32)


def _fit_length(noise: np.ndarray, n: int) -> np.ndarray:
    """Tile or trim *noise* to exactly *n* samples."""
    if len(noise) == 0:
        return np.zeros(n, dtype=np.float32)
    if len(noise) < n:
        reps = int(np.ceil(n / len(noise)))
        noise = np.tile(noise, reps)
    return noise[:n].astype(np.float32)


def make_noise(kind: str, n: int, babble: np.ndarray | None = None, seed: int = 1234) -> np.ndarray:
    if kind == "white":
        return white_noise(n, seed)
    if kind == "pink":
        return pink_noise(n, seed)
    if kind == "babble":
        if babble is None:
            raise ValueError("babble noise requires a babble track (--babble)")
        return _fit_length(babble, n)
    raise ValueError(f"unknown noise type {kind!r}; choose from {NOISE_TYPES}")


# --------------------------------------------------------------------------- #
# Mixing
# --------------------------------------------------------------------------- #


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, target_snr_db: float) -> np.ndarray:
    """Return speech + noise scaled so the realised SNR == ``target_snr_db``."""
    noise = _fit_length(noise, len(speech))
    gain = metrics.noise_gain_for_snr(speech.tolist(), noise.tolist(), target_snr_db)
    return (speech + gain * noise).astype(np.float32)


def realised_snr_db(speech: np.ndarray, mixed: np.ndarray) -> float:
    """Measure the SNR of a mixed signal given the original clean speech."""
    noise = mixed - speech
    return metrics.snr_db(speech.tolist(), noise.tolist())


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mix clean speech with noise at a target SNR.")
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--noise", choices=NOISE_TYPES, default="pink")
    ap.add_argument("--snr", type=float, default=50.0)
    ap.add_argument("--babble", help="babble noise wav (required for --noise babble)")
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args(argv)

    speech, sr = read_wav(args.infile)
    babble = read_wav(args.babble)[0] if args.babble else None
    noise = make_noise(args.noise, len(speech), babble=babble, seed=args.seed)
    mixed = mix_at_snr(speech, noise, args.snr)
    write_wav(args.outfile, mixed, sr)
    print(f"wrote {args.outfile}: {args.noise} @ {args.snr} dB "
          f"(realised {realised_snr_db(speech, mixed):.1f} dB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
