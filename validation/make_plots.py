#!/usr/bin/env python3
"""Generate thesis-grade plots from the EchoBase validation results.

Reads the measured artifacts under ``validation/results/`` (top-level JSON plus
the per-recognition-profile Markdown tables) and renders high-resolution PNGs
into a sibling ``plots/`` folder at the repo root.

Run with the project interpreter (has matplotlib + numpy):

    .venv/bin/python -m validation.make_plots
    # or
    .venv/bin/python validation/make_plots.py
"""

import csv
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# --- Paths ------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
REPO_ROOT = HERE.parent
PLOTS = REPO_ROOT / "plots"
PLOTS.mkdir(parents=True, exist_ok=True)

# Recognition profiles: (number, display name, results subdir).
PROFILES = [
    (1, "Fast", "profile_1_fast"),
    (2, "Balanced", "profile_2_balanced"),
    (3, "Accurate", "profile_3_accurate"),
    (4, "Maximum", "profile_4_maximum"),
]
# A colour-blind-friendly, print-safe palette (one hue per profile).
PROFILE_COLORS = {
    1: "#0072B2",  # blue
    2: "#009E73",  # green
    3: "#E69F00",  # orange
    4: "#D55E00",  # vermillion
}

# --- Global style -----------------------------------------------------------
plt.rcParams.update(
    {
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 12,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "--",
        "legend.frameon": False,
        "figure.constrained_layout.use": True,
    }
)

ACCENT = "#444444"
TARGET_RED = "#C00000"


# --- Small parsers ----------------------------------------------------------
def load_json(name):
    with open(RESULTS / name) as f:
        return json.load(f)


def parse_md_table(path):
    """Parse the first GitHub-style table in a Markdown file into dicts.

    Numbers are coerced to float where possible; ``True``/``False`` to bool.
    """
    rows, header = [], None
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if rows:  # blank line / heading after data ends the first table
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):  # separator row
            continue
        if header is None:
            header = cells
            continue
        row = {}
        for key, val in zip(header, cells):
            if val in ("True", "False"):
                row[key] = val == "True"
            else:
                try:
                    row[key] = float(val)
                except ValueError:
                    row[key] = val
        rows.append(row)
    return rows


def save(fig, name):
    out = PLOTS / name
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote {out.relative_to(REPO_ROOT)}")


def _bar_labels(ax, bars, fmt="{:.1f}", dy=0.0, fontsize=9, color="black"):
    for bar in bars:
        h = bar.get_height()
        ax.annotate(
            fmt.format(h),
            (bar.get_x() + bar.get_width() / 2, h + dy),
            ha="center",
            va="bottom",
            fontsize=fontsize,
            color=color,
            fontweight="bold",
        )


def _footer(fig, text):
    fig.text(0.005, 0.002, text, fontsize=7.5, color="#888888", style="italic")


# --- 1. WER (clean) + command recognition by profile ------------------------
def plot_wer_clean():
    names, wer, cmd = [], [], []
    for num, name, sub in PROFILES:
        rows = parse_md_table(RESULTS / sub / "wer_clean.md")
        ref = sum(r["ref_words"] for r in rows)
        err = sum(r["errors"] for r in rows)
        ncmd = sum(r["n_commands"] for r in rows)
        rec = sum(r["commands_recognized"] for r in rows)
        names.append(f"{num}\n{name}")
        wer.append(100 * err / ref)
        cmd.append(100 * rec / ncmd)

    x = np.arange(len(names))
    colors = [PROFILE_COLORS[n] for n, _, _ in PROFILES]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.2))

    b1 = ax1.bar(x, wer, color=colors, edgecolor="white", linewidth=1.2)
    ax1.axhline(10, color=TARGET_RED, ls="--", lw=1.5)
    ax1.text(len(names) - 0.5, 10.3, "target ≤ 10%", color=TARGET_RED,
             ha="right", va="bottom", fontsize=9, fontweight="bold")
    _bar_labels(ax1, b1, fmt="{:.2f}%", dy=0.15)
    ax1.set_title("Word Error Rate (clean speech)")
    ax1.set_ylabel("Corpus WER (%)  — lower is better")
    ax1.set_ylim(0, max(wer) * 1.3)

    b2 = ax2.bar(x, cmd, color=colors, edgecolor="white", linewidth=1.2)
    ax2.axhline(90, color=TARGET_RED, ls="--", lw=1.5)
    ax2.text(len(names) - 0.5, 90.4, "target ≥ 90%", color=TARGET_RED,
             ha="right", va="bottom", fontsize=9, fontweight="bold")
    _bar_labels(ax2, b2, fmt="{:.1f}%", dy=0.3)
    ax2.set_title("Command recognition rate (clean speech)")
    ax2.set_ylabel("Commands recognised (%)  — higher is better")
    ax2.set_ylim(0, 105)

    for ax in (ax1, ax2):
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_xlabel("Recognition profile")

    fig.suptitle("Transcription accuracy across recognition profiles",
                 fontsize=16, fontweight="bold")
    _footer(fig, "Source: validation/results/profile_*/wer_clean.md  "
                 "(2 recorded passages, 149 ref words, 17 embedded commands)")
    save(fig, "01_wer_clean_by_profile.png")


# --- 2. WER vs SNR across profiles (white & pink) ---------------------------
def plot_wer_vs_snr():
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), sharey=True)
    noise_axes = {"white": axes[0], "pink": axes[1]}

    for num, name, sub in PROFILES:
        rows = parse_md_table(RESULTS / sub / "wer_vs_snr.md")
        for noise, ax in noise_axes.items():
            pts = sorted(
                [(r["snr_db"], r["corpus_wer_pct"]) for r in rows
                 if r["noise_type"] == noise]
            )
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(xs, ys, marker="o", lw=2.2, ms=7,
                    color=PROFILE_COLORS[num], label=f"{num} {name}")

    for noise, ax in noise_axes.items():
        ax.axhline(18, color=TARGET_RED, ls="--", lw=1.5)
        ax.set_title(f"{noise.capitalize()} noise")
        ax.set_xlabel("SNR (dB)  — higher = cleaner")
        ax.set_xticks([40, 50, 60])
        ax.margins(x=0.12)
    axes[0].set_ylabel("Corpus WER (%)  — lower is better")
    axes[1].text(60, 18.5, "noisy target ≤ 18%", color=TARGET_RED,
                 ha="right", va="bottom", fontsize=9, fontweight="bold")
    axes[0].legend(title="Profile", loc="upper right")

    fig.suptitle("Recognition robustness to additive noise (WER vs SNR)",
                 fontsize=16, fontweight="bold")
    _footer(fig, "Source: validation/results/profile_*/wer_vs_snr.md")
    save(fig, "02_wer_vs_snr.png")


# --- 3. Transcription latency by profile ------------------------------------
def plot_latency():
    data = load_json("latency_decomposition.json")
    by_profile = {}
    for r in data["rows"]:
        if r["stage"] == "transcribe" and r["ms_mean"] != "":
            by_profile[r["profile"]] = (
                float(r["ms_mean"]), float(r["ms_p50"]), float(r["ms_p95"])
            )
    nums = [n for n, _, _ in PROFILES]
    names = [f"{n}\n{nm}" for n, nm, _ in PROFILES]
    means = [by_profile[n][0] for n in nums]
    p95 = [by_profile[n][2] for n in nums]
    err = [max(0, p95[i] - means[i]) for i in range(len(nums))]
    colors = [PROFILE_COLORS[n] for n in nums]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(names, means, color=colors, edgecolor="white", linewidth=1.2,
                  yerr=err, capsize=6, error_kw=dict(ecolor=ACCENT, lw=1.4))
    ax.set_yscale("log")
    ax.set_ylabel("Transcription latency (ms, log scale)  — lower is better")
    ax.set_xlabel("Recognition profile")
    ax.set_title("Whisper transcription latency per recognition profile")

    ax.axhline(1200, color=TARGET_RED, ls="--", lw=1.5)
    ax.text(3.4, 1260, "interactive budget 1200 ms", color=TARGET_RED,
            ha="right", va="bottom", fontsize=9, fontweight="bold")

    for bar, m in zip(bars, means):
        label = f"{m / 1000:.2f} s" if m >= 1000 else f"{m:.0f} ms"
        ax.annotate(label, (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    ha="center", va="bottom", xytext=(0, 8),
                    textcoords="offset points", fontsize=10, fontweight="bold")
    ax.set_ylim(top=max(means) * 2.2)
    _footer(fig, "Source: validation/results/latency_decomposition.json  "
                 "(offline transcribe stage, passage_01; bars=mean, whisker=p95)")
    save(fig, "03_transcription_latency.png")


# --- 4. Accuracy vs latency trade-off (Pareto) ------------------------------
def plot_tradeoff():
    lat = load_json("latency_decomposition.json")
    latency = {r["profile"]: float(r["ms_mean"]) for r in lat["rows"]
               if r["stage"] == "transcribe" and r["ms_mean"] != ""}
    fig, ax = plt.subplots(figsize=(10, 6.5))

    xs, ys = [], []
    for num, name, sub in PROFILES:
        rows = parse_md_table(RESULTS / sub / "wer_clean.md")
        wer = 100 * sum(r["errors"] for r in rows) / sum(r["ref_words"] for r in rows)
        x = latency[num] / 1000.0
        xs.append(x)
        ys.append(wer)
        ax.scatter(x, wer, s=320, color=PROFILE_COLORS[num], zorder=3,
                   edgecolor="white", linewidth=1.5)
        ax.annotate(f"  {num} {name}", (x, wer), fontsize=11, fontweight="bold",
                    va="center", ha="left")

    order = np.argsort(xs)
    ax.plot(np.array(xs)[order], np.array(ys)[order], color=ACCENT, lw=1.2,
            ls=":", zorder=2, alpha=0.7)
    ax.set_xscale("log")
    ax.set_xlabel("Transcription latency (s, log scale)  — lower is better")
    ax.set_ylabel("Corpus WER, clean (%)  — lower is better")
    ax.set_title("Accuracy–latency trade-off across profiles")
    ax.margins(x=0.18, y=0.22)

    ax.annotate("better", xy=(0.06, 0.06), xytext=(0.30, 0.30),
                xycoords="axes fraction", textcoords="axes fraction",
                fontsize=12, fontweight="bold", color="#009E73",
                arrowprops=dict(arrowstyle="-|>", color="#009E73", lw=2))
    _footer(fig, "Source: latency_decomposition.json + profile_*/wer_clean.md")
    save(fig, "04_accuracy_latency_tradeoff.png")


# --- 5. Routing precision / recall / F1 per plugin --------------------------
def plot_routing_per_plugin():
    data = load_json("routing_per_plugin.json")
    rows = sorted(data["rows"], key=lambda r: r["f1"])
    labels = [f'{r["label"]}  (n={int(r["support"])})' for r in rows]
    y = np.arange(len(rows))
    h = 0.26

    fig, ax = plt.subplots(figsize=(11, 8))
    ax.barh(y + h, [r["precision"] for r in rows], h, label="Precision",
            color="#0072B2")
    ax.barh(y, [r["recall"] for r in rows], h, label="Recall", color="#56B4E9")
    ax.barh(y - h, [r["f1"] for r in rows], h, label="F1", color="#E69F00")

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Score (0–1)")
    ax.set_xlim(0, 1.08)
    ax.axvline(0.85, color=TARGET_RED, ls="--", lw=1.3)
    ax.text(0.85, len(rows) - 0.3, "  gate ≥ 0.85", color=TARGET_RED,
            fontsize=9, fontweight="bold", va="top")
    macro = data["summary"]["macro_f1"]
    ax.set_title(f"Command routing per plugin  (macro-F1 = {macro:.3f}, "
                 f"overall accuracy = 95.9%)")
    ax.legend(loc="lower right", ncol=3)
    ax.grid(axis="y", visible=False)
    _footer(fig, "Source: validation/results/routing_per_plugin.json  "
                 "(147 canonical command phrases)")
    save(fig, "05_routing_per_plugin.png")


# --- 6. Fuzzy-recovery decision audit ---------------------------------------
def plot_recovery():
    data = load_json("recovery_audit.json")
    auto_cut = data["summary"]["auto_cutoff"]
    ask_cut = data["summary"]["ask_cutoff"]
    rows = sorted(data["rows"], key=lambda r: r["score"])

    decision_color = {
        "direct": "#1B7837", "auto": "#009E73",
        "ask": "#E69F00", "reject": "#D55E00",
    }
    labels = [r["input"] for r in rows]
    scores = [r["score"] for r in rows]
    colors = [decision_color.get(r["decision"], "#888888") for r in rows]
    y = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(11, 6.5))
    bars = ax.barh(y, scores, color=colors, edgecolor="white", linewidth=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels([f'"{l}"' for l in labels], fontfamily="monospace")
    ax.set_xlabel("difflib similarity to closest known phrase")
    ax.set_xlim(0, 1.05)

    ax.axvline(ask_cut, color="#E69F00", ls="--", lw=1.6)
    ax.axvline(auto_cut, color="#009E73", ls="--", lw=1.6)
    ax.text(ask_cut, len(rows) - 0.2, f" ask ≥ {ask_cut}", color="#B07A00",
            fontsize=9, fontweight="bold", va="top")
    ax.text(auto_cut, len(rows) - 0.2, f" auto ≥ {auto_cut}", color="#1B7837",
            fontsize=9, fontweight="bold", va="top")

    for bar, r in zip(bars, rows):
        ax.annotate(f'{r["score"]:.3f} → {r["decision"]}',
                    (bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(5, 0), textcoords="offset points",
                    va="center", fontsize=9, color=ACCENT)

    legend = [Patch(facecolor=c, label=d) for d, c in decision_color.items()]
    ax.legend(handles=legend, title="Decision", loc="lower right")
    ax.grid(axis="y", visible=False)
    ax.set_title("Fuzzy command-recovery decisions vs profile cutoffs "
                 "(Balanced profile)")
    _footer(fig, "Source: validation/results/recovery_audit.json")
    save(fig, "06_recovery_decisions.png")


# --- 7. Memory stability over 1000 commands ---------------------------------
def plot_memory():
    data = load_json("stress_memory.json")
    s = data["summary"]
    idx = [r["command_index"] for r in data["rows"]]
    kb = [r["traced_kb"] for r in data["rows"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(idx, kb, marker="o", lw=2.4, ms=6, color="#0072B2",
            label="Traced heap (KB)")
    ax.axvline(s["warmup"], color=ACCENT, ls=":", lw=1.4)
    ax.text(s["warmup"] + 8, max(kb) * 0.96, "warm-up ends", color=ACCENT,
            fontsize=9, rotation=90, va="top")

    ax.fill_between(idx, kb, alpha=0.12, color="#0072B2")
    ax.set_xlabel("Commands processed")
    ax.set_ylabel("Traced heap (KB)")
    ax.set_title("Heap stability over 1000 commands")

    txt = (f"post-warm-up growth: {s['post_warmup_growth_kb']} KB\n"
           f"gate: < {s['growth_limit_kb']} KB  →  verdict: {s['verdict'].upper()}")
    ax.text(0.03, 0.97, txt, transform=ax.transAxes, va="top", ha="left",
            fontsize=10, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.5", fc="#EAF4EC", ec="#009E73"))
    ax.legend(loc="lower right")
    _footer(fig, "Source: validation/results/stress_memory.json  "
                 "(tracemalloc, 100-command warm-up)")
    save(fig, "07_memory_stability.png")


# --- 8. VAD pause tolerance by speech pace ----------------------------------
def plot_cadence():
    data = load_json("cadence_vad.json")
    rows = data["rows"]
    lo, hi = data["summary"]["dysarthric_target_s"]
    paces = [r["speech_pace"] for r in rows]
    tol = [r["max_tolerated_pause_s"] for r in rows]
    hang = [r["silence_hang_s"] for r in rows]
    x = np.arange(len(paces))
    w = 0.38

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.axhspan(lo, hi, color="#E69F00", alpha=0.18, zorder=0)
    ax.text(len(paces) - 0.5, hi, f"  dysarthric target {lo}–{hi}s",
            color="#9A6A00", va="top", ha="right", fontsize=9, fontweight="bold")

    b1 = ax.bar(x - w / 2, hang, w, label="Configured silence hang",
                color="#56B4E9", edgecolor="white")
    b2 = ax.bar(x + w / 2, tol, w, label="Max tolerated mid-utterance pause",
                color="#0072B2", edgecolor="white")
    _bar_labels(ax, b1, fmt="{:.2f}s", dy=0.02, fontsize=9)
    _bar_labels(ax, b2, fmt="{:.2f}s", dy=0.02, fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels([p.capitalize() for p in paces])
    ax.set_xlabel("Speech pace setting")
    ax.set_ylabel("Seconds")
    ax.set_ylim(0, hi * 1.15)
    ax.set_title("VAD pause tolerance vs dysarthric pause target")
    ax.legend(loc="upper left")
    _footer(fig, "Source: validation/results/cadence_vad.json  "
                 "(finding: no pace reaches the 1.5 s lower bound)")
    save(fig, "08_vad_pause_tolerance.png")


# --- 9. Far-field accuracy vs distance --------------------------------------
def plot_far_field():
    rows = parse_md_table(RESULTS / "far_field_results.md")
    dist = [f'{int(r["distance_m"])} m' for r in rows]
    woke = [r["woke_pct"] for r in rows]
    trans = [r["transcribed_ok_pct"] for r in rows]
    cmd = [r["command_accuracy_pct"] for r in rows]
    x = np.arange(len(dist))
    w = 0.26

    fig, ax = plt.subplots(figsize=(10, 6))
    b1 = ax.bar(x - w, woke, w, label="Woke", color="#009E73", edgecolor="white")
    b2 = ax.bar(x, trans, w, label="Transcribed OK", color="#0072B2",
                edgecolor="white")
    b3 = ax.bar(x + w, cmd, w, label="Correct action", color="#E69F00",
                edgecolor="white")
    for b in (b1, b2, b3):
        _bar_labels(ax, b, fmt="{:.0f}%", dy=0.5, fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(dist)
    ax.set_xlabel("Distance from microphone (0° frontal)")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 112)
    ax.set_title("Far-field performance vs distance")
    ax.legend(loc="lower left", ncol=3)
    _footer(fig, "Source: validation/results/far_field_results.md  "
                 "(10 calibration commands per distance, single run)")
    save(fig, "09_far_field_distance.png")


def main():
    print(f"Rendering plots into {PLOTS.relative_to(REPO_ROOT)}/ ...")
    plot_wer_clean()
    plot_wer_vs_snr()
    plot_latency()
    plot_tradeoff()
    plot_routing_per_plugin()
    plot_recovery()
    plot_memory()
    plot_cadence()
    plot_far_field()
    print("Done.")


if __name__ == "__main__":
    main()
