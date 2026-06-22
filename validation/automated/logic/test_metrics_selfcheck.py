"""Self-checks for harness/metrics.py.

These guard the metric primitives themselves (the thesis numbers are only as
trustworthy as the formulas), independent of any EchoBase code.
"""

from __future__ import annotations

import math

from validation.harness import metrics


class TestWER:
    def test_perfect_match_is_zero(self):
        r = metrics.word_error_rate("open firefox now", "open firefox now")
        assert r.wer == 0.0
        assert r.errors == 0

    def test_punctuation_and_case_normalised(self):
        r = metrics.word_error_rate("Open Firefox.", "open firefox")
        assert r.wer == 0.0

    def test_single_substitution(self):
        r = metrics.word_error_rate("open firefox", "open chrome")
        assert (r.substitutions, r.deletions, r.insertions) == (1, 0, 0)
        assert r.ref_words == 2
        assert r.wer == 0.5

    def test_deletion_and_insertion(self):
        # ref has 3 words, hyp drops one -> 1 deletion -> 1/3
        r = metrics.word_error_rate("scroll down please", "scroll please")
        assert r.deletions == 1
        assert math.isclose(r.wer, 1 / 3, rel_tol=1e-9)

    def test_classic_sdi_example(self):
        # ref: a b c d ; hyp: a x c d e -> 1 sub (b->x) + 1 ins (e) = 2/4
        r = metrics.word_error_rate("a b c d", "a x c d e")
        assert r.substitutions == 1
        assert r.insertions == 1
        assert r.wer == 0.5

    def test_empty_reference(self):
        assert metrics.word_error_rate("", "").wer == 0.0
        assert metrics.word_error_rate("", "hello").wer == 1.0


class TestClassification:
    def test_precision_recall_f1(self):
        pairs = [
            ("apps", "apps"),
            ("apps", "apps"),
            ("media", "apps"),  # media misrouted to apps
            ("media", "media"),
            ("system", None),  # unrouted
        ]
        report = metrics.classification_report(pairs)
        assert report.total == 5
        assert report.correct == 3
        assert math.isclose(report.accuracy, 0.6)
        apps = report.per_class["apps"]
        # apps: tp=2, fp=1 (the media->apps), fn=0
        assert (apps.tp, apps.fp, apps.fn) == (2, 1, 0)
        assert math.isclose(apps.precision, 2 / 3)
        assert apps.recall == 1.0
        media = report.per_class["media"]
        assert (media.tp, media.fp, media.fn) == (1, 0, 1)
        system = report.per_class["system"]
        assert (system.tp, system.fp, system.fn) == (0, 0, 1)


class TestSNR:
    def test_snr_db_known_ratio(self):
        # signal power 4, noise power 1 -> 10*log10(4) ~= 6.02 dB
        sig = [2.0, -2.0, 2.0, -2.0]
        noise = [1.0, -1.0, 1.0, -1.0]
        assert math.isclose(metrics.snr_db(sig, noise), 10 * math.log10(4), rel_tol=1e-9)

    def test_noise_gain_round_trips(self):
        sig = [3.0, -3.0, 3.0, -3.0]
        noise = [1.0, -1.0, 1.0, -1.0]
        for target in (40.0, 50.0, 60.0):
            g = metrics.noise_gain_for_snr(sig, noise, target)
            scaled = [n * g for n in noise]
            assert math.isclose(metrics.snr_db(sig, scaled), target, rel_tol=1e-6)


class TestLatencyAndWriters:
    def test_percentile_and_summary(self):
        s = metrics.summarize_latency([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        assert s["n"] == 10
        assert s["ms_p50"] == 50
        assert s["ms_p95"] == 100
        assert s["ms_max"] == 100

    def test_writers_emit_three_files(self, tmp_path):
        rows = [{"command": "open firefox", "f1": 1.0}]
        out = metrics.write_report(
            "selfcheck", rows, {"accuracy": 1.0}, title="Self-check", results_dir=tmp_path
        )
        assert out["csv"].exists() and out["json"].exists() and out["md"].exists()
        assert "open firefox" in out["md"].read_text()
        assert "| command | f1 |" in out["md"].read_text()
