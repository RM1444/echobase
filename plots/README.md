# EchoBase validation plots

High-resolution (300 DPI) figures rendered from the measured artifacts in
`validation/results/`. Regenerate with:

```bash
.venv/bin/python validation/make_plots.py
```

| File | Shows | Source artifact | Key finding |
|---|---|---|---|
| `01_wer_clean_by_profile.png` | Corpus WER + command-recognition rate per recognition profile (clean speech) | `profile_*/wer_clean.md` | Balanced = lowest WER (2.68%); all but Maximum hit the ≥90% command target |
| `02_wer_vs_snr.png` | WER vs SNR (40/50/60 dB) under white & pink noise, one line per profile | `profile_*/wer_vs_snr.md` | Every profile stays far under the 18% noisy target; Balanced is flat and best |
| `03_transcription_latency.png` | Whisper transcribe latency per profile (mean, p95 whisker, log scale) | `latency_decomposition.json` | Fast ~1.5 s; Accurate/Maximum ~20–22 s — only Fast meets the 1.2 s budget offline |
| `04_accuracy_latency_tradeoff.png` | Accuracy–latency Pareto scatter, one point per profile | latency + `wer_clean.md` | Balanced is Pareto-optimal: lowest WER at modest latency |
| `05_routing_per_plugin.png` | Per-plugin precision / recall / F1 (with support) | `routing_per_plugin.json` | macro-F1 0.873, accuracy 95.9%; `files` fails (2 malformed phrases), `media`/`windows`/`window` collide |
| `06_recovery_decisions.png` | Fuzzy-recovery similarity scores vs auto/ask/reject cutoffs | `recovery_audit.json` | Decision bands are consistent with the 0.6/0.85 cutoffs |
| `07_memory_stability.png` | Traced heap over 1000 commands | `stress_memory.json` | 1.6 KB post-warm-up growth (gate <512 KB) → flat, no leak |
| `08_vad_pause_tolerance.png` | Max tolerated mid-utterance pause per pace vs dysarthric target band | `cadence_vad.json` | No pace reaches the 1.5 s lower bound — motivates a "very slow" pace |
| `09_far_field_distance.png` | Wake / transcription / action accuracy at 1–3 m | `far_field_results.md` | 100% wake to 3 m; transcription & action accuracy drop at 3 m |
</content>
