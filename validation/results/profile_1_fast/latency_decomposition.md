## End-to-end latency decomposition per recognition profile

| profile | profile_name | stage | measured | ms_mean | ms_p50 | ms_p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Fast | transcribe | offline | 1416.46 | 1383.59 | 1449.33 |
| 1 | Fast | route | offline | 0.6 | 0.46 | 0.74 |
| 1 | Fast | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | transcribe | offline | 4479.82 | 4455.09 | 4504.55 |
| 2 | Balanced | route | offline | 0.43 | 0.42 | 0.44 |
| 2 | Balanced | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | transcribe | offline | 20307.48 | 20062.36 | 20552.59 |
| 3 | Accurate | route | offline | 0.44 | 0.43 | 0.45 |
| 3 | Accurate | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | transcribe | offline | 20915.67 | 20868.77 | 20962.58 |
| 4 | Maximum | route | offline | 0.48 | 0.46 | 0.5 |
| 4 | Maximum | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |

*Section 3.1 -- offline-measurable stages; live stages via ECHOBASE_TRACK_PERF.*
