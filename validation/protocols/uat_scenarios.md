# User-acceptance scenarios (sections 5.1 & 5.2)

Two end-to-end, voice-only scenarios for a no-hands user. Run on a live EchoBase
with the GNOME Shell extension enabled. Record completion, time, and any
recoveries needed.

---

## 5.1 — Critical zero-touch recovery (tight time budget)

**Premise:** the user is stuck inside a blocking mode (e.g. head tracking or the
mouse grid) and must exit and run a global command entirely by voice, quickly.

EchoBase basis: blocking modes (`headtrack`, `mousegrid`, `browser`, `dictation`)
each expose a stop/cancel vocabulary; global commands route via
`run_global_command`.

**Steps & expected:**
| # | Spoken | Expected | Budget |
|---|---|---|---|
| 1 | "Hey Jarvis" | wakes (chime) | — |
| 2 | "start head tracking" | enters head-tracking mode, says "Tracking" | — |
| 3 | "stop" (or the mode's cancel word) | exits the mode cleanly | ≤ 3 s |
| 4 | "Hey Jarvis, lock the screen" | screen locks | ≤ 5 s |
| **Total** | | recovered + critical action done | **≤ ~15 s** |

**Pass:** mode exited and the critical action ran, voice-only, within budget.
**Record:** wall-clock per step, # of repeats, any misrecognitions.

> Note (finding): there is **no confirmation gate** before `lock the screen`; it
> executes immediately. This is by design in the current build — relevant to the
> "critical action safety" discussion.

---

## 5.2 — Routine desktop workflow

**Premise:** a realistic everyday flow. EchoBase routes **one command at a time**
(no compound intents) — issue commands sequentially.

**Steps & expected:**
| # | Spoken | Expected |
|---|---|---|
| 1 | "Hey Jarvis, open firefox" | Firefox launches; "Opening firefox." |
| 2 | "scroll down" | page scrolls at the pointer |
| 3 | "switch to firefox" *(if needed)* | focuses the window |
| 4 | "notes" | enters dictation; "Dictation" |
| 5 | (dictate a sentence) | text appears in the focused field |
| 6 | "stop notes" | exits dictation; "Done" |
| 7 | "Hey Jarvis, minimize" | window minimises |

**Pass:** the full flow completes voice-only. **Record:** per-step success, total
time, recoveries, and any command that needed the "did you mean…?" prompt.

---

## Reporting
For each scenario: success (y/n), total time, number of recoveries, and a short
narrative. Aggregate across ≥ 3 runs (and ideally ≥ 1 target user) for the thesis.
