"""Core metric primitives for the EchoBase validation suite.

This module is intentionally dependency-free (standard library only) so it can be
imported by both the automated pytest tests and the standalone harness scripts,
with or without the heavy runtime stack installed.

It provides the academic metrics the thesis methodology relies on:

* Word Error Rate (WER) -- token-level Levenshtein distance.
* Precision / Recall / F1 -- per-class and macro/micro averaged.
* Signal-to-Noise Ratio (SNR) in decibels, plus the gain needed to mix a noise
  track to a target SNR.
* Latency aggregation (mean / p50 / p95) for the end-to-end decomposition.

It also provides writers that emit every result set as CSV (raw rows), JSON
(machine summary) and Markdown (a thesis-ready table) into ``validation/results``.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

# --------------------------------------------------------------------------- #
# Text normalisation
# --------------------------------------------------------------------------- #

_PUNCT_RE = re.compile(r"[^\w\s']")
_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lower-case, drop punctuation (keeping intra-word apostrophes) and collapse
    whitespace. This is the canonical normalisation applied before scoring WER so
    that "Open Firefox." and "open firefox" are not counted as an error."""
    text = (text or "").lower()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def tokenize(text: str) -> list[str]:
    """Normalise then split into word tokens."""
    norm = normalize_text(text)
    return norm.split() if norm else []


# --------------------------------------------------------------------------- #
# Word Error Rate
# --------------------------------------------------------------------------- #


@dataclass
class WERResult:
    """Breakdown of a single WER computation.

    WER = (S + D + I) / N, where S/D/I are substitutions, deletions and
    insertions from the reference->hypothesis alignment and N is the number of
    reference words.
    """

    substitutions: int
    deletions: int
    insertions: int
    ref_words: int

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def wer(self) -> float:
        if self.ref_words == 0:
            return 0.0 if self.errors == 0 else 1.0
        return self.errors / self.ref_words

    @property
    def wer_pct(self) -> float:
        return round(self.wer * 100.0, 2)

    def as_dict(self) -> dict:
        return {
            "substitutions": self.substitutions,
            "deletions": self.deletions,
            "insertions": self.insertions,
            "ref_words": self.ref_words,
            "errors": self.errors,
            "wer_pct": self.wer_pct,
        }


def word_error_rate(reference: str, hypothesis: str) -> WERResult:
    """Compute WER between *reference* and *hypothesis* via a word-level
    Levenshtein edit distance with backtrace, so S/D/I are reported separately."""
    ref = tokenize(reference)
    hyp = tokenize(hypothesis)
    n, m = len(ref), len(hyp)

    # dp[i][j] = edit distance between ref[:i] and hyp[:j]. op[i][j] records the
    # operation taken to reach (i, j): 'M' match, 'S' sub, 'D' del, 'I' ins.
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    op = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
        op[i][0] = "D"
    for j in range(1, m + 1):
        dp[0][j] = j
        op[0][j] = "I"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                op[i][j] = "M"
                continue
            sub = dp[i - 1][j - 1] + 1
            dele = dp[i - 1][j] + 1
            ins = dp[i][j - 1] + 1
            best = min(sub, dele, ins)
            dp[i][j] = best
            op[i][j] = "S" if best == sub else ("D" if best == dele else "I")

    s = d = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        o = op[i][j]
        if o == "M":
            i, j = i - 1, j - 1
        elif o == "S":
            s += 1
            i, j = i - 1, j - 1
        elif o == "D":
            d += 1
            i -= 1
        else:  # "I"
            ins += 1
            j -= 1
    return WERResult(substitutions=s, deletions=d, insertions=ins, ref_words=n)


# --------------------------------------------------------------------------- #
# Precision / Recall / F1 (multi-class, for command routing)
# --------------------------------------------------------------------------- #


@dataclass
class ClassScore:
    label: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def support(self) -> int:
        return self.tp + self.fn

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "support": self.support,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


@dataclass
class ClassificationReport:
    per_class: dict[str, ClassScore] = field(default_factory=dict)
    total: int = 0
    correct: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def macro_f1(self) -> float:
        if not self.per_class:
            return 0.0
        return sum(c.f1 for c in self.per_class.values()) / len(self.per_class)

    @property
    def micro_f1(self) -> float:
        tp = sum(c.tp for c in self.per_class.values())
        fp = sum(c.fp for c in self.per_class.values())
        fn = sum(c.fn for c in self.per_class.values())
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def rows(self) -> list[dict]:
        return [c.as_dict() for c in sorted(self.per_class.values(), key=lambda c: c.label)]


def classification_report(
    pairs: Iterable[tuple[str, str | None]],
) -> ClassificationReport:
    """Build a per-class P/R/F1 report from (expected, predicted) label pairs.

    A ``predicted`` of None counts as a false negative for the expected class
    (the command was not routed anywhere). This is exactly the command-routing
    confusion structure: did transcribed text reach the correct plugin/command?
    """
    report = ClassificationReport()
    labels: set[str] = set()
    materialised = list(pairs)
    for expected, predicted in materialised:
        labels.add(expected)
        if predicted is not None:
            labels.add(predicted)
    for label in labels:
        report.per_class.setdefault(label, ClassScore(label=label))

    for expected, predicted in materialised:
        report.total += 1
        if predicted == expected:
            report.correct += 1
            report.per_class[expected].tp += 1
        else:
            report.per_class[expected].fn += 1
            if predicted is not None:
                report.per_class[predicted].fp += 1
    return report


# --------------------------------------------------------------------------- #
# Signal-to-Noise Ratio
# --------------------------------------------------------------------------- #


def _power(samples: Sequence[float]) -> float:
    if len(samples) == 0:
        return 0.0
    return sum(float(s) * float(s) for s in samples) / len(samples)


def snr_db(signal: Sequence[float], noise: Sequence[float]) -> float:
    """SNR in dB = 10 * log10(P_signal / P_noise)."""
    ps, pn = _power(signal), _power(noise)
    if pn == 0:
        return float("inf")
    if ps == 0:
        return float("-inf")
    return 10.0 * math.log10(ps / pn)


def noise_gain_for_snr(
    signal: Sequence[float], noise: Sequence[float], target_snr_db: float
) -> float:
    """Return the linear scale factor to apply to *noise* so that mixing it with
    *signal* yields ``target_snr_db``. Used by ``snr_mixer.py``."""
    ps, pn = _power(signal), _power(noise)
    if pn == 0 or ps == 0:
        return 0.0
    target_pn = ps / (10.0 ** (target_snr_db / 10.0))
    return math.sqrt(target_pn / pn)


# --------------------------------------------------------------------------- #
# Latency aggregation
# --------------------------------------------------------------------------- #


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile (pct in [0, 100]). Returns 0.0 for empty input."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 100:
        return ordered[-1]
    rank = math.ceil(pct / 100.0 * len(ordered))
    return ordered[min(rank, len(ordered)) - 1]


def summarize_latency(samples_ms: Sequence[float]) -> dict:
    """Mean / p50 / p95 / max in milliseconds for a list of stage timings."""
    if not samples_ms:
        return {"n": 0, "ms_mean": 0.0, "ms_p50": 0.0, "ms_p95": 0.0, "ms_max": 0.0}
    return {
        "n": len(samples_ms),
        "ms_mean": round(sum(samples_ms) / len(samples_ms), 2),
        "ms_p50": round(percentile(samples_ms, 50), 2),
        "ms_p95": round(percentile(samples_ms, 95), 2),
        "ms_max": round(max(samples_ms), 2),
    }


# --------------------------------------------------------------------------- #
# Result writers (CSV + JSON + Markdown) -> validation/results/
# --------------------------------------------------------------------------- #


def _ensure_results_dir(results_dir: Path | None = None) -> Path:
    target = Path(results_dir) if results_dir else RESULTS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_csv(name: str, rows: Sequence[Mapping], results_dir: Path | None = None) -> Path:
    """Write *rows* (list of dicts) to ``<results>/<name>.csv``."""
    target = _ensure_results_dir(results_dir) / f"{name}.csv"
    if not rows:
        target.write_text("", encoding="utf-8")
        return target
    fieldnames = list(rows[0].keys())
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return target


def write_json(name: str, payload, results_dir: Path | None = None) -> Path:
    """Write *payload* to ``<results>/<name>.json``."""
    target = _ensure_results_dir(results_dir) / f"{name}.json"
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return target


def write_markdown_table(
    name: str,
    rows: Sequence[Mapping],
    *,
    title: str = "",
    caption: str = "",
    results_dir: Path | None = None,
) -> Path:
    """Write *rows* as a GitHub-flavoured Markdown table, ready to paste into the
    thesis. An optional *title* (H2) and *caption* (italic line) bracket it."""
    target = _ensure_results_dir(results_dir) / f"{name}.md"
    lines: list[str] = []
    if title:
        lines.append(f"## {title}\n")
    if rows:
        headers = list(rows[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    else:
        lines.append("_(no rows)_")
    if caption:
        lines.append(f"\n*{caption}*")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def write_report(
    name: str,
    rows: Sequence[Mapping],
    summary: Mapping,
    *,
    title: str = "",
    caption: str = "",
    results_dir: Path | None = None,
) -> dict[str, Path]:
    """Convenience: emit CSV (rows) + JSON (rows+summary) + Markdown (rows) at once.
    Returns the three paths keyed by extension."""
    return {
        "csv": write_csv(name, rows, results_dir),
        "json": write_json(name, {"summary": dict(summary), "rows": list(rows)}, results_dir),
        "md": write_markdown_table(
            name, rows, title=title, caption=caption, results_dir=results_dir
        ),
    }
