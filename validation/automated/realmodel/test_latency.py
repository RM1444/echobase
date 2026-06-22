"""Per-profile latency decomposition (thesis section 3.1).

Measures the offline-measurable stages (Whisper transcribe + routing/recovery)
per recognition profile over a sample recording, and emits the decomposition with
the live-only stages (record/VAD, plugin, TTS) explicitly marked for the manual
perf protocol. Reports each profile honestly against the <1200 ms (<800 ideal)
budget rather than forcing a single pass.
"""

from __future__ import annotations

import pytest

from validation.harness import latency_probe, metrics

pytestmark = pytest.mark.real_model

PROFILES = (1, 2, 3, 4)


def test_latency_decomposition(audio_passages, results_dir):
    sample = str(audio_passages[0].wav)
    summaries = [latency_probe.probe_profile(sample, p, repeats=2) for p in PROFILES]
    rows = latency_probe.to_rows(summaries)
    metrics.write_report(
        "latency_decomposition",
        rows,
        {
            "profiles": list(PROFILES),
            "sample": audio_passages[0].name,
            "offline_budget_note": "transcribe+route only; live stages via perf protocol",
        },
        title="End-to-end latency decomposition per recognition profile",
        caption="Section 3.1 -- offline-measurable stages; live stages via ECHOBASE_TRACK_PERF.",
        results_dir=results_dir,
    )
    # Routing must be a small fraction of the budget on every profile.
    route_rows = [r for r in rows if r["stage"] == "route"]
    assert route_rows and all(r["ms_mean"] < 200 for r in route_rows), (
        "routing+recovery latency unexpectedly high"
    )
