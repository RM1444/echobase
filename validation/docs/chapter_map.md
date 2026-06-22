# Thesis chapter ↔ validation artifact map

Each report section maps 1:1 to an automated test/harness and the artifact(s) it
writes to `validation/results/`. Drop the Markdown table straight into the chapter;
the CSV/JSON back it for archival and recompute.

| Report § | Topic | Test / harness | Result artifact(s) |
|---|---|---|---|
| 1.1 | WER (clean) | `realmodel/test_wer`, `harness/wer` | `wer_clean.{md,csv,json}` |
| 1.2 | Command-routing accuracy | `logic/test_command_routing`, `harness/routing_eval` | `routing_accuracy.*`, `routing_per_plugin.*` |
| 1.3 | Wake word (both paths) | `logic/test_wake_word` + wake harness | (logic asserts) + wake FPR/FNR table |
| 1.4 | Noise / SNR | `realmodel/test_noise_snr`, `harness/snr_mixer` | `wer_vs_snr.*` |
| 2.1 | Zero-touch recovery + meta | `logic/test_error_recovery` | `recovery_audit.*` |
| 2.2 | Far-field (manual) | `protocols/far_field.md` | data sheet → `far_field_results.csv` |
| 2.3 | Cadence / VAD | `logic/test_cadence_vad`, `harness/dysarthria_sim` | `cadence_vad.*` |
| 2.4 | Multimodal TTS feedback (manual) | `protocols/multimodal_feedback.md` | feedback audit sheet |
| 3.1 | E2E latency | `realmodel/test_latency`, `harness/latency_probe` | `latency_decomposition.*` |
| 3.2 | No-network / privacy | `logic/test_offline_no_network` | (asserts) + source-seam audit |
| 3.3 | Stress / memory | `logic/test_stress_memory`, `harness/stress_runner` | `stress_memory.*`, `stress_runtime.*` |
| 4.1 | Backend integration + degradation | `logic/test_integration` | `integration_degradation.*` |
| 4.2 | Biometric speaker verification | — | Out of scope (documented) |
| 5.1 | Critical zero-touch recovery (manual) | `protocols/uat_scenarios.md` | UAT sheet |
| 5.2 | Routine workflow (manual) | `protocols/uat_scenarios.md` | UAT sheet |
| 6 | Test-case tables | `protocols/test_case_template.md` | filled TC tables |

Metric primitives (WER, P/R/F1, SNR, latency, writers) live in
`harness/metrics.py` and are self-checked by `logic/test_metrics_selfcheck.py`.
