"""Simulate atypical / dysarthric speech timing from clean recordings (section 2.3).

Real dysarthric corpora (TORGO / UASpeech-style) are the gold standard and the
suite supports dropping them into ``corpora/dysarthric/external/`` (see the
corpora README). For reproducible, always-available coverage we ALSO synthesise
two timing characteristics of dysarthric speech from a clean recording:

* **mid-utterance pauses** -- insert 1.5-3.5 s silences at low-energy boundaries,
  to exercise the VAD endpointing / speech_pace tolerance (the dysarthria-critical
  path);
* **time-stretch** -- slow the speech by a factor (naive linear resample; this
  shifts pitch and is documented as a *timing* approximation, not an acoustic
  model of dysarthria).

This simulates timing only -- it does not model articulation. Results derived
from it must be labelled "simulated" in the thesis; real-sample results override.

CLI:
    python -m validation.harness.dysarthria_sim clean.wav out.wav --pauses 3 --stretch 1.3
"""

from __future__ import annotations

import numpy as np

from validation.harness import snr_mixer

PAUSE_RANGE_S = (1.5, 3.5)  # the dysarthric mid-utterance pause target


def inject_pauses(
    samples: np.ndarray,
    sr: int,
    n_pauses: int = 3,
    pause_range_s: tuple[float, float] = PAUSE_RANGE_S,
    seed: int = 7,
) -> np.ndarray:
    """Insert *n_pauses* silences (lengths sampled from pause_range_s) at the
    lowest-energy interior points, simulating halting speech."""
    if n_pauses <= 0 or len(samples) == 0:
        return samples.astype(np.float32)
    rng = np.random.default_rng(seed)

    # Short-time energy on ~20 ms frames; choose the quietest interior boundaries.
    frame = max(1, int(0.02 * sr))
    n_frames = len(samples) // frame
    if n_frames < n_pauses + 2:
        # Too short to place pauses sensibly: just prepend/append silence.
        pad = np.zeros(int(pause_range_s[0] * sr), dtype=np.float32)
        return np.concatenate([pad, samples.astype(np.float32), pad])
    energies = np.array(
        [float(np.sum(samples[i * frame:(i + 1) * frame] ** 2)) for i in range(n_frames)]
    )
    interior = np.argsort(energies[1:-1])[:n_pauses] + 1  # quietest interior frames
    cut_points = sorted(int(idx * frame) for idx in interior)

    pieces = []
    prev = 0
    for cut in cut_points:
        pieces.append(samples[prev:cut])
        dur = rng.uniform(*pause_range_s)
        pieces.append(np.zeros(int(dur * sr), dtype=np.float32))
        prev = cut
    pieces.append(samples[prev:])
    return np.concatenate([p.astype(np.float32) for p in pieces])


def time_stretch(samples: np.ndarray, factor: float) -> np.ndarray:
    """Slow (factor>1) or speed (factor<1) via linear resample. Naive: shifts
    pitch. Documented as a timing approximation for simulation only."""
    if factor <= 0 or len(samples) == 0:
        return samples.astype(np.float32)
    n_out = int(len(samples) * factor)
    xp = np.linspace(0, len(samples) - 1, num=n_out)
    return np.interp(xp, np.arange(len(samples)), samples).astype(np.float32)


def simulate(
    samples: np.ndarray,
    sr: int,
    n_pauses: int = 3,
    stretch: float = 1.3,
    seed: int = 7,
) -> np.ndarray:
    stretched = time_stretch(samples, stretch)
    return inject_pauses(stretched, sr, n_pauses=n_pauses, seed=seed)


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Simulate dysarthric timing from clean audio.")
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--pauses", type=int, default=3)
    ap.add_argument("--stretch", type=float, default=1.3)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    samples, sr = snr_mixer.read_wav(args.infile)
    out = simulate(samples, sr, n_pauses=args.pauses, stretch=args.stretch, seed=args.seed)
    snr_mixer.write_wav(args.outfile, out, sr)
    print(f"wrote {args.outfile}: {len(out) / sr:.1f}s "
          f"(from {len(samples) / sr:.1f}s, +{args.pauses} pauses, x{args.stretch} stretch)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
