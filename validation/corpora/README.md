# Corpora

Audio and reference data for the real-model tests. Most files here are **provided
by you** (recordings); the suite ships templates and skips gracefully until the
audio exists.

## reading_passages/  (sections 1.1, 1.4, 2.4)
English passages you record reading aloud, with command phrases woven in as
ordinary words. Each passage is a trio:

```
passage_NN.txt            reference transcript (ground truth for WER)
passage_NN.clean.wav      your recording — mono, 16 kHz, 16-bit PCM
passage_NN.commands.json  embedded commands + expected routing plugin
```

`commands.json` schema:
```json
{ "commands": [ {"phrase": "open firefox", "expected_plugin": "apps"} ] }
```

**Recording tips:** mono, 16 kHz (EchoBase's rate), quiet room for the "clean"
take. The noisy conditions are generated from the clean take by `snr_mixer`, so
you do not need to re-record for noise. The same recording doubles as dictation
material (section 2.4). `passage_01.*` is a template — replace it.

## noise/  (section 1.4)
Optional `babble.wav` for babble-noise mixing (e.g. multi-talker cafeteria
audio). White and pink noise are generated synthetically by `snr_mixer` and need
no files here.

## dysarthric/  (section 2.3)
- `simulated/` — generated from clean recordings by `dysarthria_sim` (seeded,
  reproducible). Run: `python -m validation.harness.dysarthria_sim
  reading_passages/passage_01.clean.wav dysarthric/simulated/passage_01.sim.wav`.
- `external/` — drop real atypical-speech files here (TORGO / UASpeech-style).
  Recommended layout: `external/<speaker>/<utterance>.wav` plus a `manifest.csv`
  (`wav,reference,speaker,severity`). Real-sample results override simulated ones
  in the thesis. This directory is git-ignored by convention (large / licensed).

## wake/  (section 1.3)
- `positive/` — clips of the wake phrase: "Hey Jarvis" (openwakeword path) and,
  for the fallback path, "Hey <custom name>".
- `passive/` — long recordings containing **no** wake phrase (TV, conversation)
  for the false-positive-per-24h estimate.
