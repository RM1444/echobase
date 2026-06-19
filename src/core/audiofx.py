"""Audio preprocessing front-end for speech-to-text.

Cheap / laptop microphones hand Whisper a signal it was never trained on:
quiet, DC-biased, hissy, and full of low-frequency rumble. Whisper was trained
mostly on clean, level-normalised speech, so a weak signal lands far outside its
comfort zone and accuracy collapses. This module normalises *every* microphone
to roughly the same clean baseline before transcription.

The pipeline is deliberately pure ``numpy`` / ``scipy`` (both already pulled in
as transitive deps) so there is no black box: each stage is small and
inspectable, which also makes it easy to ablate when measuring its effect.

    int16 bytes
      -> float32 [-1, 1]
      -> DC-offset removal            (kills the constant bias of cheap ADCs)
      -> high-pass @ 80 Hz            (removes mains hum / rumble / handling)
      -> spectral-gate denoise        (subtracts the estimated stationary noise)
      -> AGC / RMS normalisation      (brings quiet mics up to Whisper's level)
      -> int16 bytes

Every stage degrades gracefully: on silence or pathologically short input the
original audio is returned unchanged rather than amplifying noise into speech.
"""

import numpy as np
from scipy import ndimage, signal

# Target loudness handed to Whisper. -20 dBFS RMS is a comfortable speech level
# that leaves headroom before the 0 dBFS clipping point.
_TARGET_RMS_DBFS = -20.0
_TARGET_RMS = 10.0 ** (_TARGET_RMS_DBFS / 20.0)
_MAX_GAIN = 8.0  # +18 dB ceiling, so we never blow pure noise up to "speech"
_PEAK_LIMIT = 0.97  # leave a sliver of headroom to avoid int16 clipping

# Below this RMS the buffer is treated as silence and passed straight through;
# normalising near-silence just manufactures loud hiss.
_SILENCE_RMS = 1e-4

# STFT geometry for the denoiser. 512 samples @ 16 kHz = 32 ms window, 8 ms hop
# — standard speech-analysis resolution.
_NPERSEG = 512
_NOVERLAP = 384

# How aggressively to attenuate bins judged to be noise. 0.85 -> noise floor is
# pulled down to 15 %, gentle enough to avoid "musical noise" artefacts.
_PROP_DECREASE = 0.85
_NOISE_STD_THRESH = 1.5  # a bin counts as speech if mag > mean + 1.5*std of noise


def _highpass(x, rate, cutoff=80.0):
    """4th-order Butterworth high-pass — removes DC residue, mains hum and the
    low-frequency rumble cheap mics pick up from desks/handling."""
    sos = signal.butter(4, cutoff, btype="highpass", fs=rate, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def _denoise(x, rate):
    """Stationary spectral-gate denoise.

    The noise profile is estimated from the quietest frames of *this* clip (no
    assumption about *where* the silence is), then bins that don't clearly rise
    above that profile are attenuated. The gain mask is smoothed in time and
    frequency to suppress musical noise.
    """
    f, t, Z = signal.stft(x, fs=rate, nperseg=_NPERSEG, noverlap=_NOVERLAP)
    if Z.shape[1] < 4:  # too few frames to estimate anything reliable
        return x

    mag = np.abs(Z)

    # Pick the quietest ~25 % of frames as the noise sample.
    frame_energy = mag.mean(axis=0)
    quiet_cut = np.percentile(frame_energy, 25)
    quiet = frame_energy <= quiet_cut
    if quiet.sum() < 2:
        return x

    noise_mean = mag[:, quiet].mean(axis=1, keepdims=True)
    noise_std = mag[:, quiet].std(axis=1, keepdims=True)
    thresh = noise_mean + _NOISE_STD_THRESH * noise_std

    # Soft gain: full pass for speech bins, attenuated floor for noise bins.
    gain = np.where(mag >= thresh, 1.0, 1.0 - _PROP_DECREASE)
    # Smooth the mask (freq x time) so we don't carve isolated bins into bleeps.
    gain = ndimage.uniform_filter(gain, size=(4, 4))

    _, x_clean = signal.istft(
        Z * gain, fs=rate, nperseg=_NPERSEG, noverlap=_NOVERLAP
    )
    return x_clean.astype(np.float32)


def _normalise(x):
    """Automatic gain control: scale RMS to the target speech level, capped so
    quiet noise isn't amplified into a roar, then peak-limit to avoid clipping."""
    rms = float(np.sqrt(np.mean(x ** 2)))
    if rms < _SILENCE_RMS:
        return x  # silence — leave it alone
    gain = min(_TARGET_RMS / rms, _MAX_GAIN)
    x = x * gain
    peak = float(np.max(np.abs(x)))
    if peak > _PEAK_LIMIT:
        x = x * (_PEAK_LIMIT / peak)
    return x


def preprocess(audio_bytes, rate=16000, denoise=True):
    """Clean and level a raw 16-bit mono PCM buffer for Whisper.

    Returns processed ``int16`` bytes ready to be written to a WAV. On empty,
    silent, or too-short input the original bytes are returned unchanged.
    """
    if not audio_bytes or len(audio_bytes) % 2:
        # Empty, or not whole 16-bit samples (truncated/malformed read) — leave
        # it to Whisper rather than risk corrupting the buffer.
        return audio_bytes

    x = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if x.size < rate // 20:  # < 50 ms, nothing worth processing
        return audio_bytes

    rms = float(np.sqrt(np.mean(x ** 2)))
    if rms < _SILENCE_RMS:  # pure silence — don't manufacture hiss
        return audio_bytes

    x = x - np.mean(x)  # DC-offset removal
    x = _highpass(x, rate)
    if denoise:
        x = _denoise(x, rate)
    x = _normalise(x)

    x = np.clip(x, -1.0, 1.0)
    return (x * 32767.0).astype(np.int16).tobytes()
