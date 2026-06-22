## End-to-end latency decomposition per recognition profile

| profile | profile_name | stage | measured | ms_mean | ms_p50 | ms_p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Fast | transcribe | offline | 1435.79 | 1413.0 | 1458.59 |
| 1 | Fast | route | offline | 0.61 | 0.45 | 0.77 |
| 1 | Fast | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | transcribe | offline | 4599.2 | 4594.72 | 4603.68 |
| 2 | Balanced | route | offline | 0.44 | 0.42 | 0.47 |
| 2 | Balanced | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | transcribe | offline | 20747.53 | 20515.15 | 20979.9 |
| 3 | Accurate | route | offline | 0.49 | 0.47 | 0.51 |
| 3 | Accurate | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | transcribe | offline | 21891.1 | 21622.49 | 22159.72 |
| 4 | Maximum | route | offline | 0.46 | 0.45 | 0.48 |
| 4 | Maximum | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |

*Section 3.1 -- offline-measurable stages; live stages via ECHOBASE_TRACK_PERF.*
