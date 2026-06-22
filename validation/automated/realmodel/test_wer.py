"""WER + command recognition over the recorded corpus (thesis section 1.1).

Real faster-whisper transcribes each recorded passage; we report corpus WER and
command recognition. Targets: WER <= 10% clean. The test asserts the report is
produced and (when audio is present) records the headline figure; it does not
hard-fail on the target so an honest number reaches the thesis even if a profile
misses it -- except it flags a gross failure (> 40% WER) as a likely setup error.
"""

from __future__ import annotations

import pytest

from validation.harness import metrics, wer

pytestmark = pytest.mark.real_model


def test_clean_wer(audio_passages, transcribe_fn, profile, results_dir):
    rows, summary = wer.compute_corpus_wer(audio_passages, transcribe_fn, condition="clean")
    summary["profile"] = profile
    metrics.write_report(
        "wer_clean",
        rows,
        summary,
        title="Word Error Rate -- clean condition",
        caption="Section 1.1 -- WER and command recognition over recorded passages.",
        results_dir=results_dir,
    )
    assert rows, "no passages scored"
    # Sanity gate: a WER above 40% almost certainly means a broken setup
    # (wrong sample rate, empty audio), not a real recognition result.
    assert summary["corpus_wer_pct"] < 40.0, (
        f"corpus WER {summary['corpus_wer_pct']}% implausibly high -- check audio/model"
    )
