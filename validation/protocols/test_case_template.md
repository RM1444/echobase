# Formal test-case tables (section 6)

The formal test-case (TC) format for the thesis appendix. Each TC has: ID,
component, severity, preconditions, steps, expected result, status. Below is the
template followed by filled EchoBase examples spanning the validated areas.

## Template

| Field | Value |
|---|---|
| **ID** | TC-XXX |
| **Component** | (plugin / subsystem) |
| **Severity** | Critical / High / Medium / Low |
| **Preconditions** | (state required before the test) |
| **Steps** | 1. … 2. … |
| **Expected** | (observable result) |
| **Status** | Pass / Fail / Blocked / Not run |

## Filled examples

| ID | Component | Severity | Preconditions | Steps | Expected | Status |
|---|---|---|---|---|---|---|
| TC-001 | wake / openwakeword | High | Built-in name "Jarvis"; quiet room | 1. Say "Hey Jarvis" | Wake fires (score ≥ 0.5), chime plays | Pass |
| TC-002 | wake / cooldown | Medium | Just woke < 3 s ago | 1. Say "Hey Jarvis" again immediately | Ignored until WAKE_COOLDOWN (3 s) elapses | Pass |
| TC-003 | routing / apps | High | Firefox installed | 1. "open firefox" | Routes to `apps`; "Opening firefox." | Pass |
| TC-004 | routing / collision | Medium | — | 1. "next workspace" | **Known issue:** intercepted by `media` (matches "next") | Fail (documented) |
| TC-005 | recovery / auto | High | Profile 2 | 1. "opn firefox" | Auto-corrected (score ≥ 0.85) → opens Firefox | Pass |
| TC-006 | recovery / ask | Medium | Profile 2 | 1. say a phrase scoring 0.6–0.85 | "Did you mean …?"; yes runs it | Pass |
| TC-007 | recovery / reject | Low | — | 1. say gibberish | "I didn't understand" (no action) | Pass |
| TC-008 | cadence / slow pace | Critical | `speech_pace=slow` | 1. speak, pause ~1.3 s mid-utterance | Utterance not cut | Pass |
| TC-009 | cadence / dysarthria gap | Critical | `speech_pace=slow` | 1. pause ≥ 1.5 s mid-utterance | **Known gap:** utterance cut (hang 1.4 s) | Fail (documented) |
| TC-010 | meta / cancel | Critical | In a blocking mode | 1. say "stop"/"cancel" | Mode exits cleanly | Pass |
| TC-011 | destructive / no-confirm | High | — | 1. "lock the screen" | Locks immediately, **no confirmation** | Pass (by design; flagged) |
| TC-012 | integration / D-Bus down | High | Extension disabled | 1. "minimize" | No action; **silent** (terminal log only) | Fail (documented feedback gap) |
| TC-013 | integration / false confirm | High | No media player running | 1. "play" | **Known issue:** says "Playing." though nothing played | Fail (documented) |
| TC-014 | privacy / no-network | Critical | Network disabled (`unshare -n`) | 1. run a command session | All features work; zero outbound connections | Pass |
| TC-015 | stress / memory | High | — | 1. run 1000 commands | Heap/RSS flat after warmup | Pass |
| TC-016 | latency / per profile | Medium | Profile 1 (Fast) | 1. issue a command, measure E2E | Within budget for small profile | Reported |

Statuses above reflect the automated suite's findings; re-run to refresh before
submission.
