"""End-to-end latency decomposition per recognition profile (thesis section 3.1).

The pipeline stages are: record/VAD -> Whisper transcribe -> routing+recovery ->
plugin execution (D-Bus/AT-SPI/keyboard) -> TTS. Two of these are measurable
offline and deterministically here:

* **transcribe** -- real faster-whisper over a sample recording, per profile;
* **route** -- routing + fuzzy recovery over the transcript.

The remaining stages (**record/VAD**, **plugin**, **TTS**) depend on a live mic,
a running GNOME Shell extension and the Piper/ffplay audio chain, so they are
captured by the live ``ECHOBASE_TRACK_PERF`` instrumentation under the manual
latency protocol. This module reports the offline-measurable budget per profile
and clearly marks the live-only stages, so the thesis reports each profile
honestly rather than forcing a single pass/fail.

CLI:
    ECHOBASE_VALIDATION_REAL=1 python -m validation.harness.latency_probe sample.wav
"""

from __future__ import annotations

import contextlib
import io
import time

from validation.harness import metrics

# Stages we can measure offline vs those requiring the live desktop.
OFFLINE_STAGES = ("transcribe", "route")
LIVE_ONLY_STAGES = ("record_vad", "plugin", "tts")
PROFILES = (1, 2, 3, 4)
PROFILE_NAMES = {1: "Fast", 2: "Balanced", 3: "Accurate", 4: "Maximum"}


def probe_profile(wav_path: str, profile: int, repeats: int = 3) -> dict:
    """Measure transcribe + route latency for one profile over *repeats* runs.
    Returns a summary dict with mean/p50/p95 per offline stage (ms)."""
    from validation.harness.echobase_factory import build_core, predict_with_recovery
    from validation.harness.whisper_runner import timed_transcribe_fn

    core = build_core(recognition_profile=profile)
    transcribe = timed_transcribe_fn(profile=profile, known_phrases=core.known_phrases)

    transcribe_ms, route_ms = [], []
    for _ in range(repeats):
        text, secs = transcribe(wav_path)
        transcribe_ms.append(secs * 1000.0)
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            predict_with_recovery(core, text)
        route_ms.append((time.perf_counter() - t0) * 1000.0)

    return {
        "profile": profile,
        "profile_name": PROFILE_NAMES.get(profile, str(profile)),
        "transcribe": metrics.summarize_latency(transcribe_ms),
        "route": metrics.summarize_latency(route_ms),
    }


def to_rows(summaries) -> list[dict]:
    """Flatten per-profile summaries into one row per (profile, offline stage)."""
    rows = []
    for s in summaries:
        for stage in OFFLINE_STAGES:
            st = s[stage]
            rows.append(
                {
                    "profile": s["profile"],
                    "profile_name": s["profile_name"],
                    "stage": stage,
                    "measured": "offline",
                    "ms_mean": st["ms_mean"],
                    "ms_p50": st["ms_p50"],
                    "ms_p95": st["ms_p95"],
                }
            )
        for stage in LIVE_ONLY_STAGES:
            rows.append(
                {
                    "profile": s["profile"],
                    "profile_name": s["profile_name"],
                    "stage": stage,
                    "measured": "live-only (ECHOBASE_TRACK_PERF protocol)",
                    "ms_mean": "",
                    "ms_p50": "",
                    "ms_p95": "",
                }
            )
    return rows


def _main(argv=None) -> int:
    import argparse
    import os

    ap = argparse.ArgumentParser(description="Per-profile latency decomposition.")
    ap.add_argument("wav", help="a sample command recording")
    ap.add_argument("--profiles", default="1,2,3,4")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args(argv)

    if os.environ.get("ECHOBASE_VALIDATION_REAL") != "1":
        print("Set ECHOBASE_VALIDATION_REAL=1 to run real-model latency probing.")
        return 2

    profiles = [int(p) for p in args.profiles.split(",")]
    summaries = [probe_profile(args.wav, p, repeats=args.repeats) for p in profiles]
    rows = to_rows(summaries)
    out = metrics.write_report(
        "latency_decomposition",
        rows,
        {"profiles": profiles, "repeats": args.repeats, "offline_budget_ms": "transcribe+route"},
        title="End-to-end latency decomposition per recognition profile",
        caption="Section 3.1 -- offline-measurable stages; live stages via the perf protocol.",
    )
    print(f"latency report: {out['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
