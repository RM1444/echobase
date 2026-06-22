## End-to-end latency decomposition per recognition profile

| profile | profile_name | stage | measured | ms_mean | ms_p50 | ms_p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Fast | transcribe | offline | 1470.4 | 1444.72 | 1496.09 |
| 1 | Fast | route | offline | 0.6 | 0.46 | 0.75 |
| 1 | Fast | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | transcribe | offline | 4504.24 | 4486.13 | 4522.34 |
| 2 | Balanced | route | offline | 0.45 | 0.44 | 0.45 |
| 2 | Balanced | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | transcribe | offline | 20472.09 | 20338.65 | 20605.54 |
| 3 | Accurate | route | offline | 0.44 | 0.4 | 0.49 |
| 3 | Accurate | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | transcribe | offline | 21992.16 | 21716.18 | 22268.14 |
| 4 | Maximum | route | offline | 0.46 | 0.44 | 0.47 |
| 4 | Maximum | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |

*Section 3.1 -- offline-measurable stages; live stages via ECHOBASE_TRACK_PERF.*
