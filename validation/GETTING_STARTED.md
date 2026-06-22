# Getting Started — exact steps to produce the thesis results

Follow these in order. Every command assumes you are in the project root:
`/home/razvan/FACULTATE/LICENTA/easyspeak-dev`. Always use `.venv/bin/python`
(NOT `uv run`). Copy-paste the commands as written.

---

## PHASE 0 — Sanity check (5 minutes, do this first)

This proves the suite works on your machine before you record anything.

```bash
cd /home/razvan/FACULTATE/LICENTA/easyspeak-dev
.venv/bin/python -m pytest validation/automated/logic/ -q
```
**Expected:** `84 passed` (or similar), 0 failed.
If you see failures, stop and tell me. If it passes, continue.

---

## PHASE 1 — Record the reading-passage corpus (the main manual task)

This is the data that produces WER, command-recognition, noise/SNR and latency
numbers. You will create **3 to 5 passages**. Each passage = 3 files with the
SAME base name (`passage_01`, `passage_02`, …).

### Step 1.1 — Delete the template
The shipped `passage_01` is a placeholder. Remove it:
```bash
rm validation/corpora/reading_passages/passage_01.txt
rm validation/corpora/reading_passages/passage_01.commands.json
```

### Step 1.2 — Write each passage's text (the `.txt` file)
Create `validation/corpora/reading_passages/passage_01.txt`. Rules:
- Write a short English paragraph (≈ 60–120 words).
- **Weave real EchoBase commands into it as ordinary words** (see the vetted
  command list in the Appendix). Example sentence:
  *"Every morning I open firefox, scroll down through the news, turn the volume
  up while music plays, then minimize every window before I lock the screen."*
- The `.txt` must contain **exactly the words you will read aloud** — it is the
  ground-truth transcript. Don't add anything you won't say.

Repeat for `passage_02.txt`, `passage_03.txt`, etc. Aim for **≥ 15 embedded
commands total** across all passages.

### Step 1.3 — Record yourself reading each passage
Record each passage as a WAV file named `passage_NN.clean.wav` in the same folder.
The file **must be mono, 16 kHz, 16-bit PCM**.

**Easiest dumb-proof method** — record however you like (phone, Audacity, OBS),
then convert with ffmpeg:
```bash
# replace 'my_recording.wav' (or .m4a/.mp3) with your file
ffmpeg -i my_recording.wav -ac 1 -ar 16000 -sample_fmt s16 \
  validation/corpora/reading_passages/passage_01.clean.wav
```
(No ffmpeg? `sudo dnf install ffmpeg`. Or in Audacity: set "Project Rate" to
16000, Tracks→Mix→Stereo to Mono, then File→Export→WAV "16-bit PCM".)

### Step 1.4 — Verify each recording's format
```bash
.venv/bin/python -c "import wave,sys; w=wave.open(sys.argv[1]); \
print('channels',w.getnchannels(),'rate',w.getframerate(),'width',w.getsampwidth())" \
validation/corpora/reading_passages/passage_01.clean.wav
```
**Expected:** `channels 1 rate 16000 width 2`. If not, redo Step 1.3.

### Step 1.5 — List the embedded commands (the `.commands.json` file)
For each passage create `passage_NN.commands.json` listing ONLY the commands that
actually appear in that passage's text, with the plugin that should handle each
(Appendix has the mapping). Exact format:
```json
{
  "commands": [
    {"phrase": "open firefox",   "expected_plugin": "apps"},
    {"phrase": "scroll down",    "expected_plugin": "scroll"},
    {"phrase": "volume up",      "expected_plugin": "system"},
    {"phrase": "minimize",       "expected_plugin": "window"},
    {"phrase": "lock the screen","expected_plugin": "system"}
  ]
}
```
Rules:
- `phrase` must appear **verbatim** (same words) in the `.txt`.
- Use only phrases + plugins from the Appendix (or verify — see Appendix end).

### Step 1.6 — Confirm the loader sees your corpus
```bash
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); \
from validation.harness import corpus as c; \
ps=c.passages_with_audio(); \
print('passages with audio:', [p.name for p in ps]); \
print('total embedded commands:', sum(len(p.commands) for p in ps))"
```
**Expected:** your passage names listed and a non-zero command count. If the list
is empty, a `.clean.wav` is missing or misnamed.

---

## PHASE 2 — Run the real-model tests (produces the headline numbers)

Run the heavy tier in its **own** session (never together with `logic/`). The
first run downloads Whisper models if missing (needs internet once).

```bash
# Default profile (2 = Balanced):
ECHOBASE_VALIDATION_REAL=1 .venv/bin/python -m pytest validation/automated/realmodel/ -q

# Repeat per profile to compare Fast..Maximum (1=Fast,2=Balanced,3=Accurate,4=Maximum):
ECHOBASE_VALIDATION_PROFILE=1 ECHOBASE_VALIDATION_REAL=1 .venv/bin/python -m pytest validation/automated/realmodel/ -q
ECHOBASE_VALIDATION_PROFILE=3 ECHOBASE_VALIDATION_REAL=1 .venv/bin/python -m pytest validation/automated/realmodel/ -q
ECHOBASE_VALIDATION_PROFILE=4 ECHOBASE_VALIDATION_REAL=1 .venv/bin/python -m pytest validation/automated/realmodel/ -q
```
**Expected:** tests pass (or report numbers). Then look at the results:
```bash
cat validation/results/wer_clean.md
cat validation/results/wer_vs_snr.md
cat validation/results/latency_decomposition.md
```
These `.md` tables paste straight into the thesis. (Re-running overwrites them, so
copy out a profile's tables before switching profile if you want to keep each.)

---

## PHASE 3 — (Optional) wake-word and dysarthric audio

Only if you want FPR/FNR and real-dysarthria numbers.

- **Wake clips:** put "Hey Jarvis" recordings in `validation/corpora/wake/positive/`
  and long no-wake recordings (TV, talking) in `validation/corpora/wake/passive/`.
- **Simulated dysarthria** (no recording needed) — generate from a clean passage:
  ```bash
  .venv/bin/python -m validation.harness.dysarthria_sim \
    validation/corpora/reading_passages/passage_01.clean.wav \
    validation/corpora/dysarthric/simulated/passage_01.sim.wav --pauses 3 --stretch 1.3
  ```
- **Real dysarthric data:** drop files into `validation/corpora/dysarthric/external/`
  as described in `validation/corpora/README.md`.

---

## PHASE 4 — Manual protocols (live machine, can't be automated)

Do these on the actual GNOME desktop with the EchoBase extension enabled. Open
each file, follow it, and fill the data sheet inside:
```bash
ls validation/protocols/
# far_field.md           -> distance/angle WER  (section 2.2)
# multimodal_feedback.md -> spoken-confirmation audit (section 2.4)
# uat_scenarios.md       -> the two end-to-end scenarios (5.1, 5.2)
# test_case_template.md  -> formal TC tables (section 6)
```
Save your filled-in numbers as new files in `validation/results/` (e.g.
`far_field_results.csv`).

---

## PHASE 5 — Air-gapped privacy run (section 3.2)

The automated test already proves no outbound code path. For the end-to-end claim,
run the whole app with networking disabled and confirm features still work:
```bash
sudo unshare -n -- sudo -u "$USER" .venv/bin/python -m EchoBase.core
```
Use a few voice commands; confirm nothing breaks and there is no network access.

---

## PHASE 6 — Assemble results for the thesis

All machine-generated tables/figures are here:
```bash
ls validation/results/
```
For each report section, `validation/docs/chapter_map.md` tells you exactly which
file backs it. The `.md` files are paste-ready; `.csv` are for recompute/figures.
Read `validation/docs/methodology.md` (formulas + findings) and
`validation/docs/metrics_definitions.md` (targets) for the write-up.

---

## PHASE 7 — Commit (when ready)

Nothing is committed yet. When you're happy:
```bash
git add validation/
git commit -m "Add EchoBase validation suite"
```
(Ask me and I'll do this on a branch with a proper message.)

---

## APPENDIX

### A. Things you must NOT touch
- `tests/` — the original suite. Leave it alone.
- `pyproject.toml`, root `conftest.py` — do not add pytest config there.
- `uv.lock` — don't run `uv run` (it fails here anyway and rewrites the lockfile).

### B. Valid `expected_plugin` values
`apps`, `browser`, `dictation`, `files`, `keyboard`, `labels`, `media`, `scroll`,
`snippets`, `system`, `time`, `window`, `windows`, `a11y`, `base`,
`headtrack`, `mousegrid`.

### C. Vetted command → plugin cheat sheet (safe to embed)
| phrase (use verbatim) | expected_plugin |
|---|---|
| open firefox / open chrome / open spotify | apps |
| close firefox | apps |
| scroll down / scroll up | scroll |
| volume up / volume down / mute | system |
| brightness up / brightness down | system |
| lock the screen | system |
| minimize / maximize / close window | window |
| snap left / snap right | window |
| switch to firefox | windows |
| copy / paste / undo / redo | keyboard |
| play / pause / next track / previous track | media |
| what day is it / what date is it | time |
| high contrast on / magnifier on | a11y |

AVOID these in `commands.json` (known routing quirks): "next workspace",
"previous workspace", "next window", "previous window" (grabbed by media), and
"what time is it" (does not match — use "what day is it" instead).

### D. Verify any phrase routes before using it
```bash
.venv/bin/python -m validation.harness.routing_eval
cat validation/results/routing_per_plugin.md
```
This regenerates the routing report; any phrase with `correct = true` in
`validation/results/routing_accuracy.csv` is safe to embed.

### E. Troubleshooting
- **`uv run` errors about tflite-runtime** → ignore `uv`; use `.venv/bin/python`.
- **Real-model tests all SKIP** → you didn't set `ECHOBASE_VALIDATION_REAL=1`, or
  no `.clean.wav` exists yet (Phase 1).
- **`test_cli.py::test_entrypoint` fails in `tests/`** → pre-existing, unrelated
  (the `EchoBase` console script isn't on PATH). Optional fix: `.venv/bin/pip
  install -e .`.
- **Wrong WAV format** → re-run the ffmpeg command in Step 1.3.
