# EchoBase Validation Methodology

This document defines the validation methodology for **EchoBase**, a fully-local,
Wayland-native, English-only voice assistant for Linux/GNOME aimed at users with
locomotor disabilities and dysarthria. It adapts a generic academic test plan to
what the EchoBase codebase **actually** does (verified by code inspection), and
preserves the academic formalism (WER, Precision/Recall/F1, SNR, end-to-end
latency decomposition, formal test-case tables).

The suite is split into:

* **Automated tests** (`validation/automated/`): a fast *logic* tier (mocked) and
  a heavy *realmodel* tier (real faster-whisper on recorded audio).
* **Measurement harness** (`validation/harness/`): reusable scripts that compute
  the metrics and emit thesis-ready artifacts to `validation/results/`.
* **Human-run protocols** (`validation/protocols/`): far-field, multimodal
  feedback, UAT scenarios, and the formal test-case template.

It is kept entirely separate from the existing `tests/` suite (704 tests), which
remains untouched.

## What EchoBase actually is (key reconciliations)

| Assumption in the generic plan | Reality in EchoBase (code) |
|---|---|
| Wake word = Whisper transcribes 3 s windows + string match | **openwakeword acoustic classifier** (`WAKE_THRESHOLD=0.5`) for built-in names; the Whisper 3 s substring path (`LISTEN_WINDOW=3`) is only the *fallback* for custom names (`main._wake_detected`). Both validated. |
| NLU intent/slot extraction | **None.** Exact/substring match in each plugin's `handle` + difflib fuzzy recovery (`_closest_phrase`/`_recover`, cutoffs 0.85/0.6). Reframed to *command-routing accuracy*. |
| Confirmation before destructive actions | **Absent.** `listen_yes_no` is used only by fuzzy recovery and OOBE; lock/suspend/close/delete run immediately. Documented as a limitation. |
| Cloud→edge failover | EchoBase is already fully local. Reframed to a **no-network privacy verification**; the single outbound seam is the Piper voice download in `config.py`. |
| Biometric speaker verification | Not a feature. Out of scope. |

The canonical command vocabulary contains exactly **187 phrases** across 17
plugins (computed from `EchoBase._collect_phrases`).

## Metric definitions and formulas

### Word Error Rate (section 1.1)

WER is the word-level Levenshtein edit distance, normalised by reference length:

```
WER = (S + D + I) / N
```

where *S*, *D*, *I* are substitutions, deletions and insertions in the optimal
reference→hypothesis alignment and *N* is the number of reference words. Text is
normalised (lower-cased, punctuation stripped, whitespace collapsed) before
scoring. Implemented in `harness/metrics.word_error_rate` (full DP backtrace so
S/D/I are reported separately).

**Targets:** WER ≤ 10 % clean, ≤ 18 % noisy. Reported alongside **command
recognition rate** (fraction of embedded command phrases surviving transcription)
— for a command system this matters more than raw WER.

### Command-routing accuracy: Precision / Recall / F1 (section 1.2)

For each command (class *c*):

```
Precision_c = TP_c / (TP_c + FP_c)
Recall_c    = TP_c / (TP_c + FN_c)
F1_c        = 2 · P_c · R_c / (P_c + R_c)
```

A phrase routed to its owning plugin is a TP; routed elsewhere contributes a FP to
the wrong plugin and a FN to the owner; unrouted is a FN. Macro-F1 averages over
classes; micro-F1 pools TP/FP/FN. Implemented in
`harness/metrics.classification_report`.

The **fuzzy-recovery decision** is audited against the profile cutoffs: a near
miss is *auto-run* (score ≥ auto_cutoff), *asked* (ask_cutoff ≤ score <
auto_cutoff) or *rejected* (below ask_cutoff).

### Wake word: FPR / FNR (section 1.3)

* **False Positive Rate** — false activations per 24 h of passive audio; target
  ≤ 1 / 24 h.
* **False Negative Rate** — missed genuine wakes / total genuine wakes; target
  ≤ 5 %.

Account for `WAKE_COOLDOWN = 3.0 s` and, on the fallback path, the 3 s window.

### Signal-to-Noise Ratio (section 1.4)

```
SNR_dB = 10 · log10(P_signal / P_noise)
```

Noise is mixed to a target SNR by scaling it with gain
`g = sqrt( P_signal / (10^(SNR/10) · P_noise) )` (`harness/snr_mixer`). Conditions:
white / pink / babble at 40 / 50 / 60 dB.

### End-to-end latency decomposition (section 3.1)

Total latency is the sum of stage latencies:

```
L_total = L_record/VAD + L_transcribe + L_route+recovery + L_plugin + L_TTS
```

reported **per recognition profile** (Fast / Balanced / Accurate / Maximum).
Budget: < 1200 ms (< 800 ms ideal) — realistic only for the smaller profiles, so
each profile is reported honestly. `transcribe` and `route` are measured offline
(`harness/latency_probe`); `record/VAD`, `plugin`, `TTS` are measured live via the
`ECHOBASE_TRACK_PERF` instrumentation under the latency protocol.

## Recognition profiles

| # | Name | Model | Beam | Bias | auto/ask cutoff |
|---|------|-------|------|------|-----------------|
| 1 | Fast | base.en | 1 | command | 0.85 / 0.60 |
| 2 | Balanced (default) | small.en | 5 | command | 0.85 / 0.60 |
| 3 | Accurate | medium.en | 8 | phrases | 0.80 / 0.55 |
| 4 | Maximum | distil-large-v3 | 8 | phrases-strong | 0.72 / 0.50 |

## Speech-pace endpointing (section 2.3)

`config.PACE_TIMING` maps `speech_pace` → (silence-hang, max-utterance):
normal (0.6 s, 8 s), relaxed (1.0 s, 11 s), slow (1.4 s, 14 s). A pause shorter
than the hang does not end the utterance.

## Findings surfaced by the suite

These are reproducible outputs of the automated suite (see `validation/results/`),
suitable for the thesis "limitations / discussion" chapters:

1. **Substring-precedence routing collisions** — `media` matches the bare words
   "next"/"previous", shadowing `next/previous workspace` and `next/previous
   window` (per-plugin F1 in `routing_per_plugin`).
2. **Registry hygiene** — two descriptive continuation lines from `files.py`'s
   `COMMANDS` ("Folders: documents, …") leak into the 187-phrase fuzzy-recovery
   vocabulary as non-command strings.
3. **No destructive-action confirmation** — routing any command never triggers a
   yes/no gate; lock/suspend/close run immediately.
4. **Cadence gap for dysarthria** — even the slowest pace tolerates only ~1.4 s of
   mid-utterance pause, below the 1.5–3.5 s typical of moderate dysarthria
   (`cadence_vad`). Recommendation: add a "very slow" pace (≥ 1.8 s hang).
5. **False confirmations on failure** — `media` and `system` speak success
   ("Playing.", "Volume up.") without checking the backend result; a downed
   extension is otherwise silent (`integration_degradation`).

## Reproducibility

* Logic tier runs offline with no models and pins recognition profile 2 for
  deterministic cutoffs.
* Noise, pink-noise and dysarthria simulations are seeded.
* Every metric run writes CSV (raw), JSON (summary) and Markdown (table) into
  `validation/results/` for 1:1 inclusion in the report (see `chapter_map.md`).
