# Multimodal TTS feedback audit (section 2.4)

**Goal:** verify that every successful action produces a **descriptive spoken
confirmation** (Piper via `EchoBase.speak`), not an ambiguous beep — and document
where feedback is missing or misleading.

**Why manual:** judging whether spoken feedback is *descriptive and unambiguous*
is a perceptual judgement; the automated `test_integration` only records whether
*some* speech occurred.

## Procedure
For each command below, issue it to a live EchoBase and record the spoken reply
verbatim, then rate it.

Rating:
- **Descriptive** — names the action/result (e.g. "Minimized.", "Opening firefox.")
- **Generic** — a non-specific filler ("Done.")
- **Silent** — no speech
- **Misleading** — claims success when the action did not occur

## Commands to audit (one per plugin family)
| plugin | command |
|---|---|
| apps | open firefox |
| apps | open notavalidapp *(expect failure feedback)* |
| window | minimize / maximize / snap left |
| media | play / pause / next |
| keyboard | copy / paste |
| system | volume up / lock the screen |
| a11y | high contrast on |
| scroll | scroll down |
| time | what time is it |
| dictation | notes → (speak a sentence) → stop notes |

## Data sheet (→ feedback audit table in the thesis)
| command | spoken reply (verbatim) | rating | notes |
|---|---|---|---|
|  |  |  |  |

## Cross-reference (already-known findings)
- `integration_degradation` shows **media** and **system** can speak success
  ("Playing.", "Volume up.") even when the backend fails → check for the
  **Misleading** rating on those when the extension/player is down.
- A downed GNOME Shell extension makes window/keyboard actions **Silent** on
  failure — confirm and note as a feedback gap.
