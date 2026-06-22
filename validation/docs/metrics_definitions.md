# Metrics: definitions, thresholds, pass/fail criteria

Precise, citable definitions for every metric the suite produces. Formulas are in
`methodology.md`; this file is the quick-reference table of what each number means,
its target, and how the suite decides pass/fail.

| Metric | Definition | Source | Target | Automated gate |
|---|---|---|---|---|
| **WER (clean)** | (S+D+I)/N over recorded passages | `harness/wer` + real model | ≤ 10 % | Reported; gross-failure guard at > 40 % (setup error) |
| **WER (noisy)** | WER under white/pink/babble @ 40/50/60 dB | `realmodel/test_noise_snr` | ≤ 18 % | Reported per condition |
| **Command recognition rate** | embedded command phrases surviving transcription / total | `harness/wer` | ≥ 90 % | Reported |
| **Routing accuracy** | canonical phrases routed to owning plugin / total | `logic/test_command_routing` | ≥ 85 % | **Hard gate** ≥ 85 % (currently 95.9 %) |
| **Routing P/R/F1** | per-plugin precision/recall/F1 | same | — | Reported; collisions documented |
| **Recovery decision** | auto / ask / reject vs profile cutoffs | `logic/test_error_recovery` | consistent w/ cutoffs | **Hard gate** on band↔score consistency |
| **Wake decision** | acoustic ≥ 0.5 fires; fallback substring match | `logic/test_wake_word` | exact logic | **Hard gate** |
| **Wake FPR** | false activations per 24 h passive audio | wake harness + corpus | ≤ 1 / 24 h | Manual/realmodel |
| **Wake FNR** | missed wakes / genuine wakes | wake harness + corpus | ≤ 5 % | Manual/realmodel |
| **VAD pause tolerance** | longest tolerated mid-utterance pause per pace | `logic/test_cadence_vad` | document vs 1.5–3.5 s | Reported; gap documented |
| **E2E latency** | per-profile stage decomposition (ms) | `harness/latency_probe` | < 1200 ms (< 800 ideal) | Reported per profile; routing < 200 ms gated |
| **Memory stability** | post-warmup heap/RSS growth over 1000 commands | `logic/test_stress_memory`, `harness/stress_runner` | flat | **Hard gate** < 512 KB traced growth |
| **No-network** | outbound connections during handling; source seam audit | `logic/test_offline_no_network` | zero / single seam | **Hard gate** |
| **Degradation feedback** | spoken feedback on backend failure | `logic/test_integration` | no crash | **Hard gate** no-crash; feedback documented |

## Pass/fail philosophy

* **Hard gates** protect logic that must not regress (routing, recovery bands,
  wake decision, memory, no-network, no-crash on failure).
* **Reported metrics** (WER, latency, FPR/FNR, pause tolerance) record the honest
  number for the thesis rather than forcing a pass — a profile that misses the
  latency budget is reported, not hidden.

## Severity scale (for the test-case tables)

| Severity | Meaning |
|---|---|
| Critical | No-hands user can become stuck or a destructive action misfires |
| High | Core command path fails or degrades silently |
| Medium | Recoverable error, suboptimal feedback |
| Low | Cosmetic / wording |
