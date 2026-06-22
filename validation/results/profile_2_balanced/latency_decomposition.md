## End-to-end latency decomposition per recognition profile

| profile | profile_name | stage | measured | ms_mean | ms_p50 | ms_p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Fast | transcribe | offline | 1487.3 | 1479.93 | 1494.67 |
| 1 | Fast | route | offline | 0.56 | 0.43 | 0.69 |
| 1 | Fast | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 1 | Fast | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | transcribe | offline | 4592.63 | 4541.32 | 4643.94 |
| 2 | Balanced | route | offline | 0.46 | 0.41 | 0.5 |
| 2 | Balanced | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 2 | Balanced | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | transcribe | offline | 20606.63 | 20556.08 | 20657.17 |
| 3 | Accurate | route | offline | 0.42 | 0.4 | 0.44 |
| 3 | Accurate | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 3 | Accurate | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | transcribe | offline | 21916.06 | 21755.16 | 22076.96 |
| 4 | Maximum | route | offline | 0.43 | 0.42 | 0.43 |
| 4 | Maximum | record_vad | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | plugin | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |
| 4 | Maximum | tts | live-only (ECHOBASE_TRACK_PERF protocol) |  |  |  |

*Section 3.1 -- offline-measurable stages; live stages via ECHOBASE_TRACK_PERF.*
