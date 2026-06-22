# EchoBase Validation Suite

A thesis-grade validation suite for **EchoBase** (fully-local, Wayland-native,
English-only voice assistant for Linux/GNOME; users with locomotor disabilities
and dysarthria). It is **separate from and does not touch** the existing `tests/`
suite (704 tests). Everything is adapted to what EchoBase actually does — see
`docs/methodology.md` for the reconciliation against the generic test plan.

## Layout

```
validation/
  automated/
    logic/        fast, mocked tests (routing, recovery, wake, cadence, stress,
                  no-network, integration, metric self-checks) — no models needed
    realmodel/    heavy tests on real faster-whisper + recorded audio
                  (WER, noise/SNR, latency); gated by ECHOBASE_VALIDATION_REAL
  harness/        reusable measurement scripts (metrics, wer, snr_mixer,
                  latency_probe, stress_runner, routing_eval, dysarthria_sim,
                  whisper_runner, corpus, echobase_factory)
  corpora/        recorded passages, noise, dysarthric, wake audio (you provide)
  protocols/      human-run QA: far_field, multimodal_feedback, uat_scenarios,
                  test_case_template
  results/        run artifacts (CSV + JSON + Markdown) for the thesis
  docs/           methodology, metrics_definitions, chapter_map
```

Each report section maps 1:1 to an artifact — see `docs/chapter_map.md`.

## Running

Use the project virtualenv interpreter (it has EchoBase + the native stack):

```bash
# Fast logic tier (offline, no models). Deselect the 1000-command stress with -m:
.venv/bin/python -m pytest validation/automated/logic/
.venv/bin/python -m pytest validation/automated/logic/ -m "not slow"

# Real-model tier — needs models present + recorded passages in corpora/.
# Run it in its OWN session (never mixed with logic/, whose import-time stubs
# would poison the real model):
ECHOBASE_VALIDATION_REAL=1 .venv/bin/python -m pytest validation/automated/realmodel/
ECHOBASE_VALIDATION_PROFILE=1 ECHOBASE_VALIDATION_REAL=1 \
    .venv/bin/python -m pytest validation/automated/realmodel/   # pick a profile
```

> Note: `uv run` may fail to resolve on Python 3.12/3.13 because the optional
> head-tracking dependency `tflite-runtime` has no wheel there; use the existing
> `.venv` interpreter directly.

### Standalone harness (regenerate thesis tables)

```bash
.venv/bin/python -m validation.harness.routing_eval
.venv/bin/python -m validation.harness.stress_runner --count 1000
ECHOBASE_VALIDATION_REAL=1 .venv/bin/python -m validation.harness.wer --profile 2
ECHOBASE_VALIDATION_REAL=1 .venv/bin/python -m validation.harness.latency_probe sample.wav
.venv/bin/python -m validation.harness.snr_mixer in.wav out.wav --noise pink --snr 50
.venv/bin/python -m validation.harness.dysarthria_sim in.wav out.wav --pauses 3 --stretch 1.3
```

### End-to-end air-gapped check (section 3.2)

The in-process guard runs in the logic tier. For a full air-gapped run, launch the
app under a network namespace and confirm every feature still works:

```bash
sudo unshare -n -- sudo -u "$USER" .venv/bin/python -m EchoBase.core
```

## Results format

Every metric run writes three files into `results/`:
`<name>.csv` (raw rows), `<name>.json` (summary + rows), `<name>.md` (paste-ready
table). See `docs/chapter_map.md` for which artifact backs which report section.

## Keeping `tests/` green and separate

`validation/` is a top-level sibling of `tests/`. It adds **no** root `conftest.py`
and **no** `[tool.pytest.ini_options]` to `pyproject.toml` (its config lives in
`validation/pytest.ini`). Logic-tier native-stack stubbing is confined to
`automated/logic/conftest.py`. Run the original suite as before:
`.venv/bin/python -m pytest tests/`.
