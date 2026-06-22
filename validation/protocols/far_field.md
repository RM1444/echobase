# Far-field recognition protocol (section 2.2)

**Goal:** quantify how WER and command accuracy degrade with microphone distance
and angle, using EchoBase's single 16 kHz mono mic (PyAudio).

**Why manual:** distance/angle cannot be simulated faithfully; it requires a real
room, mic and speaker.

## Equipment
- The EchoBase microphone in its normal position.
- A tape measure and a way to mark 0°, 45°, 90° relative to the mic axis.
- The command list below (read aloud, one command per trial).

## Conditions
Distances: **1 m, 3 m, 5 m**. Angles: **0°, 45°, 90°**. → 9 cells.
Per cell, speak the 10 calibration commands once each (90 utterances/run).

## Calibration commands (non-blocking, one-shot)
`open firefox`, `scroll down`, `volume up`, `minimize`, `maximize`, `copy`,
`paste`, `play`, `pause`, `what day is it`.

## Procedure
1. Quiet room (note ambient dB if a meter is available).
2. For each (distance, angle) cell: position, then speak each command after the
   wake word; record whether EchoBase (a) woke, (b) transcribed correctly,
   (c) performed the correct action.
3. Log results in the data sheet. Repeat 3× per cell for a mean.

## Data sheet (copy per run → `validation/results/far_field_results.csv`)

| distance_m | angle_deg | command | woke (y/n) | transcript | correct_action (y/n) |
|---|---|---|---|---|---|
| 1 | 0 | open firefox |  |  |  |
| … | … | … |  |  |  |

## Reporting
Per cell: wake success rate, command accuracy (correct_action / 10), and (if
transcripts are logged) WER via `harness.metrics.word_error_rate`. Present as a
3×3 heat-grid of command accuracy vs distance/angle.
