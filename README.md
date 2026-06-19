# EchoBase

Voice control for Linux desktops. Fully local, no cloud, Wayland-native.

Say "Hey {Name}" and control your desktop with your voice — where {Name} is whatever you choose at startup.

![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)
![Desktop](https://img.shields.io/badge/desktop-GNOME%20%7C%20Wayland-green.svg)
![Status](https://img.shields.io/badge/status-Alpha-orange.svg)

> **Early development.** This project works but is not polished. Expect bugs, incomplete docs, and changes without notice.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Where We Started](#where-we-started)
3. [What We Modified and Implemented](#what-we-modified-and-implemented)
4. [Architecture Overview](#architecture-overview)
5. [Project Structure](#project-structure)
6. [Technology Stack](#technology-stack)
7. [Requirements](#requirements)
8. [Installation](#installation)
9. [Usage](#usage)
10. [Head Tracking — Setup & Tutorial](#head-tracking--setup--tutorial)
11. [Commands Reference](#commands-reference)
12. [Plugin System](#plugin-system)
13. [Troubleshooting](#troubleshooting)
14. [License](#license)
15. [Acknowledgments](#acknowledgments)

---

## Introduction

EchoBase is a fully local voice assistant for Linux desktops running GNOME on Wayland. It provides hands-free control over your desktop: launch applications, navigate the web, dictate text, control media, manage windows and workspaces, and move the mouse cursor — all through voice commands.

Unlike cloud-based assistants, all speech processing happens on your machine. No audio leaves your computer. No accounts, no subscriptions, no data collection.

EchoBase is built for people with RSI, accessibility needs, hands-busy workflows, or anyone who wants to talk to their computer.

---

## Where We Started

EchoBase began as a fork of an open-source voice control project ([ctsdownloads/EchoBase](https://github.com/ctsdownloads/EchoBase)) built around a fixed set of tools:

- **OpenWakeWord** for wake word detection — a pre-trained ML model that only recognized the phrase "Hey Jarvis"
- **faster-whisper** for speech-to-text transcription
- **Piper** for text-to-speech responses
- A **GNOME Shell extension** providing D-Bus interfaces for mouse control, grid overlays, and window management on Wayland
- A **plugin architecture** where Python files dropped into `plugins/` are auto-loaded at startup

The original project had a single-file core (`main.py`) that handled the entire voice assistant loop: wake word detection, audio recording, transcription, command routing, and speech synthesis. The UI was minimal — the application ran in a terminal with basic colored log output.

### Original Limitations

1. **Hardcoded identity** — The assistant name was "Jarvis" everywhere: in the code, the UI, the wake word. There was no way to change it.

2. **Fixed wake word** — OpenWakeWord uses pre-trained neural network models. The `hey_jarvis` model only responds to "Hey Jarvis". Supporting a different wake phrase would require training an entirely new model, which is impractical for end users.

3. **Energy-based silence detection** — The original code used audio energy levels (RMS amplitude) to detect when the user started and stopped speaking. It had hardcoded thresholds (e.g., `SILENCE_THRESHOLD = 300`) that assumed a quiet environment.

4. **No launcher integration** — The application had to be started from a terminal manually. There was no GNOME app icon, no `.desktop` file, and no way to launch it from the app grid.

5. **No name selection UI** — Users had no way to personalize the assistant.

6. **Verbose comments** — The codebase had lengthy file-level docstrings and block comments that were more noise than signal.

---

## What We Modified and Implemented

### 1. Customizable Assistant Name (Name Selection UI)

**File: `src/core/ui.py`**

We implemented a full terminal-based name selection interface that appears when EchoBase starts. The user sees a boxed menu with five default names and the option to enter a custom one:

```
  ╔══════════════════════════════════════════════╗
  ║        Choose your assistant name            ║
  ╠══════════════════════════════════════════════╣
  ║                                              ║
  ║   [1]  Jarvis                                ║
  ║   [2]  Echo                                  ║
  ║   [3]  Nova                                  ║
  ║   [4]  Atlas                                 ║
  ║   [5]  Sage                                  ║
  ║                                              ║
  ║   [6]  Custom name...                        ║
  ║                                              ║
  ╚══════════════════════════════════════════════╝

  Enter choice (1-6):
```

The function `select_assistant_name()` handles input validation, clears the screen after selection, and returns the chosen name to the main application. The selected name propagates throughout the entire UI — the banner, the ready hint, and the wake detection all use the persona name.

### 2. GNOME Desktop Launcher

**Files: `echobase.sh`, `echobase.desktop`**

We created a complete GNOME app grid integration so users can launch EchoBase by clicking an icon:

**`echobase.sh`** — A bash wrapper script that launches the application inside Ptyxis (Fedora 43's terminal emulator, which replaced `gnome-terminal`):

```bash
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec ptyxis -s -- "$DIR/.venv/bin/EchoBase"
```

**`echobase.desktop`** — A freedesktop-compliant `.desktop` entry installed to `~/.local/share/applications/`:

```ini
[Desktop Entry]
Type=Application
Name=EchoBase
Comment=Voice control for Linux
Exec=/path/to/echobase.sh
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Accessibility;
```

The flow is: user clicks the icon in the GNOME app grid, Ptyxis opens, the name selection screen appears, user picks a name, the screen clears, and the main voice assistant UI takes over — all in a single terminal window.

### 3. Whisper-Based Wake Word Detection (Replacing OpenWakeWord)

**File: `src/core/main.py`**

This was the most significant architectural change. The original system used OpenWakeWord's pre-trained `hey_jarvis` model for wake word detection:

```python
# BEFORE (OpenWakeWord — only recognizes "Hey Jarvis")
from openwakeword.model import Model as WakeWordModel
self.wakeword = WakeWordModel()

while True:
    pcm = self.stream.read(1280)
    audio_data = np.frombuffer(pcm, dtype=np.int16)
    prediction = self.wakeword.predict(audio_data)
    score = prediction.get("hey_jarvis", 0)
    if score > WAKE_THRESHOLD:
        # wake detected...
```

This approach is fast and CPU-efficient but fundamentally limited: the model can only recognize what it was trained on, and there is no `hey_sage` or `hey_nova` model available.

**Our solution: Whisper-based wake detection.** Instead of a dedicated wake word model, we use the same Whisper speech-to-text engine that already handles command transcription. The system continuously records short audio windows (3 seconds), transcribes them, and checks if the transcription contains the wake phrase:

```python
# AFTER (Whisper-based — works with ANY name)
wake_phrase = f"hey {self.name.lower()}"

while True:
    audio = self.record(LISTEN_WINDOW)  # 3 seconds
    text = self.transcribe(audio, prompt=f"Hey {self.name}")
    
    if not text:
        continue
    
    lowered = text.lower().strip(".,!? ")
    if wake_phrase not in lowered:
        continue
    
    # Wake detected — check for inline command or beep and record
```

Key design decisions:

- **`LISTEN_WINDOW = 3` seconds** — Short enough that the user doesn't wait too long after saying the wake phrase, long enough for Whisper to get useful context.
- **Whisper initial prompt** — We pass `"Hey {Name}"` as the `initial_prompt` parameter to bias Whisper toward recognizing the wake phrase correctly. This significantly improves recognition accuracy for unusual names.
- **Inline command extraction** — If the user says "Hey Sage, exit" in one breath within the 3-second window, the system detects the wake phrase AND extracts the command ("exit") from the same transcription. No need for a second recording.
- **Cooldown** — `WAKE_COOLDOWN = 3.0` seconds prevents double-triggers from echoes or repeated recognition.

**Tradeoffs:**
- More CPU usage than OpenWakeWord (Whisper runs every ~3 seconds vs. OpenWakeWord's lightweight neural net running on every audio frame)
- Slightly higher latency (up to ~4 seconds worst case: 3s recording + ~1s transcription)
- But it works with **any name** — the whole point of the change

### 4. Fixed Audio Recording (Replacing Broken Silence Detection)

**File: `src/core/main.py`**

The original code used energy-based silence detection to determine when the user started and stopped speaking. It measured the RMS amplitude of audio frames and compared against a threshold:

```python
# ORIGINAL — broken on many microphones
SILENCE_THRESHOLD = 300
energy = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
if energy > SILENCE_THRESHOLD:
    # speech detected
```

**The problem:** On the target hardware, ambient noise registered at ~13,000 energy and speech at ~10,655 energy. Both values were far above any reasonable threshold, and speech was actually *quieter* than ambient noise. An attempt to auto-calibrate (setting threshold to 1.8x ambient) produced a threshold of ~24,000, which was above speech energy — so the system never detected speech at all.

**Our solution:** We removed all energy-based detection entirely. The `record()` method now takes a fixed number of seconds and returns the audio:

```python
def record(self, seconds=RECORD_SECONDS):
    frames = []
    for _ in range(int(seconds * 16000 / 1600)):
        frames.append(self.stream.read(1600, exception_on_overflow=False))
    return b"".join(frames)
```

We rely on Whisper's built-in VAD (Voice Activity Detection) filter (`vad_filter=True` in the transcribe call) to handle silence. If the recording is pure silence, Whisper returns an empty string. This is more robust than manual energy thresholding because Whisper's VAD uses a proper ML model (Silero VAD) trained to distinguish speech from noise.

The `wait_for_speech()` and `record_until_silence()` methods were preserved as simple wrappers for backward compatibility with plugins that call them (mousegrid, eyetrack, browser, dictation):

```python
def wait_for_speech(self, timeout=5):
    return self.stream.read(1600, exception_on_overflow=False)

def record_until_silence(self):
    return self.record()
```

### 5. Wake Phrase Stripping (Route Cleaning)

**File: `src/core/main.py`**

The `route_clean()` method strips the wake phrase from the transcribed text before routing the command. It handles multiple variations of how Whisper might transcribe the wake phrase:

```python
def route_clean(self, text):
    cmd = text.lower()
    names = {"jarvis"}
    if self.name.lower() != "jarvis":
        names.add(self.name.lower())
    for n in names:
        for pat in [
            f"hey {n}", f"hey {n},", f"hey, {n}", f"hey, {n},",
            f"hey {n}.", n, f"{n},",
        ]:
            cmd = cmd.replace(pat, "").strip()
    return cmd.strip(".,!? ")
```

This ensures that if the user says "Hey Sage, open downloads", the command routed to plugins is just "open downloads" — with all wake phrase artifacts removed.

### 6. Lazy Imports (Startup Optimization)

**File: `src/core/main.py`**

Heavy dependencies (`numpy`, `pyaudio`, `faster-whisper`) were moved from top-level module imports to inside the `EchoBase.run()` method:

```python
def run(self):
    import numpy as np
    import pyaudio
    from faster_whisper import WhisperModel
    
    self._np = np
    # ...
```

This was necessary because the `--select-name` CLI mode (used by the two-terminal launcher approach during development) only needs to show the name picker and write the selection to a file — it doesn't need to load ML models. Lazy loading prevents a ~5 second startup delay for that mode.

### 7. Comment Cleanup

**All source files**

We removed verbose file-level docstrings and multi-line block comments from every source file. The original code had extensive preamble comments at the top of each file explaining what the file does. We replaced them with concise inline comments where necessary and let the code speak for itself through clear naming.

For example, the original plugin files had headers like:
```python
"""
Browser Control Plugin for EchoBase
=====================================

Provides voice control for qutebrowser web browser...
(30 lines of documentation)
"""
```

These were all removed. The `NAME`, `DESCRIPTION`, and `COMMANDS` constants at the top of each plugin already serve as self-documenting metadata.

### 8. CLI Argument Handling

**File: `src/core/main.py`**

We added argument parsing to support multiple launch modes:

```python
def run():
    import argparse
    parser = argparse.ArgumentParser(description="EchoBase voice assistant")
    parser.add_argument("--select-name", metavar="FILE")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    if args.select_name:
        name = ui.select_assistant_name()
        with open(args.select_name, "w") as f:
            f.write(name)
        return

    name = args.name or ui.select_assistant_name()
    app = EchoBase(name=name)
    app.run()
```

- `EchoBase` — Normal mode: shows name picker, then starts assistant
- `EchoBase --name Sage` — Skips name picker, uses "Sage" directly
- `EchoBase --select-name /tmp/name.txt` — Shows name picker, writes selection to file, exits (used during development for two-terminal orchestration)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        GNOME App Grid                           │
│                     echobase.desktop icon                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ click
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      echobase.sh                                │
│              ptyxis -s -- .venv/bin/EchoBase                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Name Selection UI                            │
│               ui.select_assistant_name()                        │
│         [Jarvis] [Echo] [Nova] [Atlas] [Sage] [Custom]          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ name chosen
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EchoBase Core Loop                          │
│                                                                 │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────┐             │
│  │ Record   │──▶│  Transcribe  │──▶│  Check for   │             │
│  │ 3s audio │   │  (Whisper)   │   │  wake phrase │             │
│  └──────────┘   └──────────────┘   └──────┬──────┘             │
│                                           │                     │
│                         ┌─────────────────┴─────────────────┐   │
│                         │ wake phrase detected               │   │
│                         ▼                                    │   │
│              ┌──────────────────┐                            │   │
│              │ Inline command?  │──── yes ──▶ route_command() │  │
│              └────────┬─────────┘                            │   │
│                       │ no                                   │   │
│                       ▼                                      │   │
│              ┌──────────────────┐                            │   │
│              │  Beep + Record   │──▶ transcribe ──▶ route   │   │
│              │   4s for cmd     │                            │   │
│              └──────────────────┘                            │   │
│                                                              │   │
│  route_command() iterates plugins in alphabetical order:     │   │
│  00_eyetrack → 00_mousegrid → a11y → apps → browser →       │   │
│  dictation → files → media → system → time → window →       │   │
│  zz_base                                                     │   │
└─────────────────────────────────────────────────────────────────┘
                           │
                    D-Bus calls
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                  GNOME Shell Extension                           │
│             echobase-grid@local (extension.js)                  │
│                                                                 │
│   Grid overlay · Mouse clicks · Cursor movement · Scrolling    │
│   Window management · Workspace switching                       │
└─────────────────────────────────────────────────────────────────┘
```

### Audio Pipeline

```
Microphone (16kHz, 16-bit, mono)
    │
    ▼
PyAudio stream (frames_per_buffer=1280)
    │
    ├──▶ Wake detection loop: record 3s → Whisper transcribe → string match
    │
    └──▶ Command recording: record 4s → Whisper transcribe → route to plugin
    
Whisper (faster-whisper, base.en model, int8 quantization)
    │
    ├──▶ vad_filter=True (Silero VAD) — filters silence automatically
    └──▶ initial_prompt biases recognition toward expected phrases

Piper TTS (en_US-amy-medium model)
    │
    └──▶ ffplay for audio output
```

---

## Project Structure

```
easyspeak-dev/
├── echobase.sh                 # Bash launcher (opens ptyxis terminal)
├── echobase.desktop            # GNOME .desktop file for app grid
├── extension.js                # GNOME Shell extension (grid, mouse, windows)
├── metadata.json               # Extension metadata
├── pyproject.toml              # Package config (setuptools + scm)
├── README.md                   # This file
│
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── __main__.py         # Entry: from .main import run
│   │   ├── main.py             # EchoBase class, wake detection, command routing
│   │   └── ui.py               # Name selection UI, banner, logging, panels
│   │
│   └── plugins/
│       ├── __init__.py
│       ├── 00_eyetrack.py      # Head tracking cursor control (experimental)
│       ├── 00_mousegrid.py     # Voice-controlled 3x3 grid mouse navigation
│       ├── a11y.py             # Accessibility toggles (magnifier, contrast, etc.)
│       ├── apps.py             # Launch/close applications (flatpak + local)
│       ├── browser.py          # Qutebrowser voice control (hints, tabs, scroll)
│       ├── dictation.py        # Voice-to-text via AT-SPI accessibility
│       ├── files.py            # Open folders in file manager
│       ├── media.py            # MPRIS media playback controls
│       ├── system.py           # Volume, brightness, DND, screenshots, power
│       ├── time.py             # Speak current time, date, day
│       ├── window.py           # Window/workspace management via D-Bus
│       └── zz_base.py          # Help and exit commands (loaded last)
│
└── tests/
    ├── core/
    │   ├── conftest.py
    │   ├── test_cli.py
    │   └── test_main.py
    └── plugins/
        ├── conftest.py
        ├── test_apps.py
        ├── test_browser.py
        ├── test_dictation.py
        ├── test_eyetrack.py
        ├── test_files.py
        ├── test_media.py
        ├── test_mousegrid.py
        ├── test_system.py
        └── test_zz_base.py
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Wake word detection | **faster-whisper** (Whisper base.en) | Transcribe 3s audio windows, string-match for "Hey {Name}" |
| Speech-to-text | **faster-whisper** | Transcribe voice commands after wake |
| Voice activity detection | **Silero VAD** (via faster-whisper) | Filter silence from recordings |
| Text-to-speech | **Piper** (en_US-amy-medium) | Speak responses aloud |
| Audio capture | **PyAudio** (PortAudio) | 16kHz mono microphone input |
| Mouse/window control | **GNOME Shell extension** | Clutter virtual input on Wayland |
| Browser control | **Qutebrowser IPC** | Tab/scroll/hint commands |
| Text insertion | **AT-SPI** (accessibility) | Type text into focused fields |
| Media control | **MPRIS D-Bus** | Play/pause/skip via D-Bus |
| Package management | **uv** + setuptools-scm | Editable install, virtual environment |
| Terminal emulator | **Ptyxis** | Fedora 43's default terminal |
| Desktop integration | **freedesktop .desktop file** | GNOME app grid icon |

---

## Requirements

- Linux with **GNOME Shell 47+** on Wayland
- **Python 3.12** (not 3.13/3.14 — some dependencies lack wheels)
- Working **microphone**
- ~2GB disk space for models

Tested on **Fedora 43**.

---

## Installation

### 1. Python 3.12

Fedora 43's default `python3` is 3.14. Some dependencies require 3.12:

```bash
sudo dnf install python3.12
python3.12 --version
```

### 2. System Packages

```bash
sudo dnf install \
  pipewire-utils \
  wireplumber \
  at-spi2-core \
  python3-gobject \
  qutebrowser \
  glib2 \
  ffmpeg-free \
  pulseaudio-utils \
  sound-theme-freedesktop \
  portaudio-devel \
  python3.12-devel \
  gcc
```

### 3. Python Packages

```bash
python3.12 -m venv ~/echobase-venv
source ~/echobase-venv/bin/activate
pip install faster-whisper numpy pyaudio
cd ~/EchoBase
pip install -e .
```

If you use `uv`:

```bash
uv run EchoBase
```

### 4. Piper TTS

```bash
mkdir -p ~/.local/bin
cd ~/.local/bin
wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz
tar xzf piper_linux_x86_64.tar.gz
rm piper_linux_x86_64.tar.gz

echo 'export PATH="$HOME/.local/bin/piper:$PATH"' >> ~/.bashrc
source ~/.bashrc

mkdir -p ~/.local/share/piper
cd ~/.local/share/piper
wget -O en_US-amy-medium.onnx \
  "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx"
wget -O en_US-amy-medium.onnx.json \
  "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json"
```

### 5. GNOME Shell Extension

```bash
mkdir -p ~/.local/share/gnome-shell/extensions/echobase-grid@local
cp extension.js metadata.json ~/.local/share/gnome-shell/extensions/echobase-grid@local/
```

Log out and back in, then:

```bash
gnome-extensions enable echobase-grid@local
```

### 6. Enable Accessibility

```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

### 7. Configure Qutebrowser

```bash
mkdir -p ~/.config/qutebrowser
cat > ~/.config/qutebrowser/config.py << 'EOF'
config.load_autoconfig(False)
c.hints.chars = '0123456789'
EOF
```

### 8. Desktop Launcher (Optional)

```bash
cp echobase.desktop ~/.local/share/applications/
# Edit Exec= path in the .desktop file to match your installation
```

---

## Usage

### From Terminal

```bash
source ~/echobase-venv/bin/activate
EchoBase
```

### From GNOME App Grid

Click the EchoBase icon. A terminal opens with the name selection screen. Pick a name, and the assistant starts listening.

### CLI Options

```bash
EchoBase                     # Interactive: name picker → assistant
EchoBase --name Sage         # Skip picker, use "Sage"
EchoBase --name "My Bot"     # Custom name directly
```

### How It Works

1. You choose a name (e.g., "Sage")
2. The assistant starts listening in 3-second cycles
3. Say "Hey Sage" — the system detects the wake phrase
4. If you included a command ("Hey Sage, open downloads"), it executes immediately
5. If you only said the wake phrase, you hear a beep — then speak your command within 4 seconds
6. The command is transcribed and routed to the matching plugin

---

## Head Tracking — Setup & Tutorial

Head tracking lets you move the mouse pointer by **turning your head** in front of
the webcam, and click by voice (or hands-free with dwell). It's built for users
who can't use a mouse but can move their head. Under the hood
[MediaPipe Face Mesh](https://developers.google.com/mediapipe) tracks facial
landmarks (~30 fps on CPU); the control signal is the nose tip's position
relative to the eyes (the classic "head mouse" approach), smoothed and driven
through the GNOME Shell extension.

### One-time setup

1. **Install the optional dependencies** (not pulled in by default, since not
   everyone has a webcam):

   ```bash
   pip install "mediapipe>=0.10.9,<0.10.18" opencv-python
   # or, from the project: pip install ".[head-tracking]"
   ```

   The Face Mesh model ships inside the MediaPipe wheel, so there's no extra
   download and the first `start tracking` is quick. (The version pin keeps the
   self-contained `solutions.face_mesh` API; newer MediaPipe needs a separate
   model file.)

2. **Make sure the GNOME Shell extension is enabled** (same one the mouse grid
   uses — see [Installation › GNOME Shell Extension](#5-gnome-shell-extension)).
   Head tracking moves the pointer through it, so nothing happens without it.

3. **Plug in / enable a webcam.** Detection is automatic. If you have several
   cameras and the wrong one is picked, pin the index in
   `~/.config/echobase/config.json`:

   ```json
   { "tracking_camera": 0 }
   ```

   (`"auto"` probes indices 0–3; set a number to force one.)

4. **(Optional) Pick a comfortable speed and clicking style** in the same config
   file:

   ```json
   {
     "tracking_sensitivity": "normal",     // "slow" | "normal" | "fast"
     "dwell_enabled": false,               // true = auto-click when you rest still
     "dwell_seconds": 1.5,                 // how long to rest before a dwell click
     "tracking_monitor_mode": "active"     // "active" (one screen) | "span" (all)
   }
   ```

   You can also change all of these by voice while tracking (below), including
   moving between monitors — see [Multiple monitors](#multiple-monitors).

### Using it

1. Say **"Hey \<name>, start tracking."**
2. **Look at the centre of your screen and hold still for ~1 second.** The first
   frames calibrate your neutral head position — wherever you're looking when it
   says *Calibrated* becomes "pointer centre". Turn your head right → pointer
   goes right, look up → pointer goes up.
3. **Click by voice:** say `click`, `double click`, or `right click`. The pointer
   stays where it is while you speak.
4. **Hold a position:** say `freeze` to lock the pointer (e.g. to talk without it
   drifting), then `go` to resume. While frozen you can `nudge up/down/left/right`
   for pixel-level adjustments.
5. **Hands-free clicking:** say `dwell on` — now resting the pointer still over a
   spot for `dwell_seconds` auto-clicks it (a filling ring shows progress). Say
   `dwell off` to disable.
6. **Tune on the fly:** say `faster` / `slower` to change sensitivity live, or
   `recalibrate` if your seating position changed and centre feels off.
7. Say `stop tracking` (or `stop`, `cancel`, `done`) to end.

### Multiple monitors

Head tracking works across two or more displays. By default it tracks **one
monitor at a time** (the *primary* one when you start) — this keeps the cursor
controllable, since your whole range of head motion maps to a single screen
instead of being stretched thin across all of them. Move between screens by
voice:

- **`next screen`** / **`previous screen`** — hop to the adjacent display; the
  cursor jumps to the centre of the new screen and head-forward now maps there.
- **`screen one`**, **`screen two`**, **`screen three`** … — jump straight to a
  specific display by number.

Prefer one continuous surface across all monitors? Say **`span screens`** (or set
`"tracking_monitor_mode": "span"` in the config). In span mode a single sweep of
your head travels across every display end-to-end — convenient for two equal,
side-by-side monitors, but more sensitive and harder to reach corners on mixed
layouts. Say **`single screen`** to go back to one-at-a-time tracking.

Monitor numbers follow GNOME's display order (Settings → Displays). If `screen
two` lands on the wrong display, it's the GNOME ordering — rearrange the displays
there. The layout is re-read every time you say `start tracking`, so you don't
need to restart after plugging in or unplugging a monitor.

### Tips for the best experience

- **Lighting matters.** Face a light source; strong backlight (a window behind
  you) makes head-pose estimation noisy and jumpy.
- **Sit roughly an arm's length** from the camera, face mostly visible.
- If the pointer feels **too twitchy**, say `slower`; if you have to crane your
  neck to reach the edges, say `faster` (or set `tracking_sensitivity`).
- If the pointer is **offset / drifts to one side**, you probably weren't looking
  dead-centre during calibration — say `recalibrate` and hold still on centre.
- Head tracking and the [mouse grid](#mouse-grid) complement each other: use the
  head to get *near* a target, then `freeze` + `nudge`, or just dwell-click.

> Performance note: MediaPipe Face Mesh runs at ~30 fps on CPU and gives a
> temporally stable signal, so the pointer is both responsive and smooth. The
> `tracking_smoothing` preset (`low`/`medium`/`high` in the config) trades a
> little latency for steadiness — `medium` is a good default.

### Diagnosing lag (performance stats)

If the pointer still feels sluggish, turn on the built-in instrumentation to see
the real frame rate and where the per-frame time goes. Enable it either way:

```bash
# one-off, from a terminal launch:
ECHOBASE_TRACK_PERF=1 ./echobase.sh
```

or set `"tracking_debug": true` in `~/.config/echobase/config.json` (works no
matter how you launch). Then `start tracking` and watch the console — every ~2
seconds it prints a line like:

```
[headtrack] 11.1 fps over 23 frames | infer  80.0ms | read  5.0ms | move  6.0ms | loop  90.0ms (avg/frame)
```

How to read it:

- **`fps`** — the true tracking rate. Below ~15 fps feels laggy; 25–30+ feels
  smooth.
- **`infer`** — time MediaPipe Face Mesh takes per frame (typically ~10–20 ms on
  CPU).
- **`read`** — webcam frame grab; **`move`** — the cursor `MoveTo` D-Bus call;
  **`loop`** — total per-frame time (≈ `1000 / fps`).

If the pointer is jittery rather than slow, raise `tracking_smoothing` to `high`;
if it lags, drop to `low`. Share the `[headtrack]` line and we can tune from real
numbers.

---

## Commands Reference

### Mouse Grid

The screen splits into a 3x3 layout (like a phone keypad). Say numbers to zoom in, then click.

| Command | Action |
|---------|--------|
| grid | Show grid |
| 1-9 | Zoom to zone |
| 3 7 5 | Chain zones (zoom 3 times) |
| click | Left click at center |
| double click | Double click |
| right click | Right click |
| middle click | Middle click |
| up/down/left/right | Nudge position |
| left 5, down 3 | Nudge with repeat |
| scroll up/down/left/right | Scroll at cursor |
| scroll down 3 | Scroll with repeat |
| mark | Start drag (mousedown) |
| drag | End drag (mouseup) |
| again | Reopen at last position |
| close | Hide grid |

### Head Tracking

Move the pointer with your head. Requires a webcam and
`pip install "mediapipe>=0.10.9,<0.10.18" opencv-python`. See the full
[Head Tracking — Setup & Tutorial](#head-tracking--setup--tutorial) for first-time
setup, calibration, and tips.

| Command | Action |
|---------|--------|
| start tracking | Begin head tracking (then look at centre to calibrate) |
| stop tracking / stop / cancel / done | End tracking |
| freeze | Lock cursor position |
| go | Resume tracking |
| faster / slower | Adjust sensitivity live |
| next screen / previous screen | Move tracking to the adjacent monitor |
| screen one / screen two / … | Jump tracking to a specific monitor |
| span screens / single screen | Track all monitors as one, or one at a time |
| recalibrate | Reset centre to where you're looking now |
| nudge up/down/left/right | Fine tune when frozen |
| dwell on / dwell off | Toggle hands-free auto-click on rest |
| click / double click / right click | Click at cursor |

### Browser

Works with **any** browser chosen during setup (Firefox/Chrome/Brave/qutebrowser/…). Commands use standard keyboard shortcuts plus the AT-SPI numbered-label overlay for clicking links, so behaviour is identical across browsers (see Session 5).

| Command | Action |
|---------|--------|
| browser | Enter browser mode (launches your chosen browser) |
| numbers / hints | Number the links, then say one to click |
| zero two | Click link 02 |
| new tab / close tab | Manage tabs |
| tab left / tab right | Switch tabs |
| tab 3 | Jump to tab #3 |
| undo tab | Restore closed tab |
| back / forward | Navigate history |
| reload | Refresh page |
| scroll up / scroll down | Scroll page |
| page up / page down | Scroll by page |
| top / bottom | Jump to top/bottom |
| find [text] | Search in page |
| find next / find previous | Navigate matches |
| search [query] | Web search (DuckDuckGo) |
| go to [url] | Navigate (e.g., "go to claude dot ai") |
| open youtube | Open bookmark |
| exit browser | Leave browser mode |

Built-in bookmarks: youtube, google, gmail, github, reddit, twitter, facebook, amazon, netflix, duckduckgo

### Dictation

| Command | Action |
|---------|--------|
| notes | Start dictation mode |
| stop notes | End dictation mode |
| comma / period / question mark | Insert punctuation |
| exclamation mark / colon / semicolon | More punctuation |
| new sentence | Insert ". " and capitalize |
| new line / new paragraph | Insert newlines |
| backspace / space / tab | Editing |
| apostrophe / quote / dash | Symbols |
| at sign / hashtag / percent / asterisk | More symbols |

### Apps

| Command | Action |
|---------|--------|
| open [app] | Launch application |
| close [app] | Close application |

Supports both Flatpak apps (firefox, chrome, steam, spotify, discord, slack, telegram, etc.) and local binaries (nautilus, qutebrowser, gnome-terminal, etc.). See `plugins/apps.py` for the full list.

### Files

| Command | Action |
|---------|--------|
| open documents / downloads / pictures | Open folder |
| open music / videos / home / desktop | More folders |
| open config / trash / projects | System folders |

### Media

| Command | Action |
|---------|--------|
| play / pause | Control playback |
| play pause | Toggle |
| next / skip | Next track |
| previous / back | Previous track |
| stop playback | Stop player |

### System

| Command | Action |
|---------|--------|
| volume up / down | Adjust volume |
| volume max / min / [0-100] | Set volume |
| mute / unmute | Toggle speaker mute |
| mute mic | Toggle microphone mute |
| brightness up / down | Adjust brightness |
| do not disturb on / off | Toggle notifications |
| lock / lock screen | Lock session |
| suspend / sleep | Suspend system |
| screenshot | Capture full screen |
| screenshot area | Capture a region |

### Accessibility

| Command | Action |
|---------|--------|
| magnifier on / off | Toggle screen magnifier |
| zoom in / zoom out | Step zoom level |
| high contrast on / off | Toggle high contrast |
| large text on / off | Toggle 1.5x text scaling |
| big cursor on / off | Toggle 48px cursor |
| screen reader on / off | Toggle Orca |
| on-screen keyboard on / off | Toggle GNOME OSK |
| night light on / off | Toggle blue light filter |
| sticky keys / slow keys on / off | Toggle key assists |
| read selection | Speak highlighted text aloud |

### Time

| Command | Action |
|---------|--------|
| what time / time | Speak current time |
| what date / date | Speak today's date |
| what day | Speak day of the week |

### Window Management

| Command | Action |
|---------|--------|
| minimize / maximize | Window state |
| restore window | Unmaximize |
| fullscreen / exit fullscreen | Toggle fullscreen |
| close window | Close current window |
| snap left / snap right | Tile to half screen |
| next workspace / previous workspace | Switch workspaces |
| workspace 3 | Jump to workspace #3 |

### General

| Command | Action |
|---------|--------|
| help | List all commands in terminal |
| stop / exit / quit | Exit EchoBase |

---

## Plugin System

EchoBase auto-discovers plugins from `src/plugins/`. Drop a Python file there and it gets loaded at startup.

### Plugin Template

```python
NAME = "myplugin"
DESCRIPTION = "What it does"

COMMANDS = [
    "say hello - speaks a greeting",
]

def setup(core):
    pass

def handle(cmd, core):
    if "say hello" in cmd:
        core.speak("Hello there!")
        return True
    return None
```

### Return Values

- `True` — Command was handled, stop routing
- `False` — Signal EchoBase to exit
- `None` — Not handled, try next plugin

### Core API

| Method | Description |
|--------|-------------|
| `core.speak(text)` | Text-to-speech response |
| `core.host_run(cmd)` | Run shell command (returns CompletedProcess) |
| `core.host_run(cmd, background=True)` | Run shell command in background |
| `core.transcribe(audio)` | Transcribe audio bytes to text |
| `core.transcribe(audio, prompt="...")` | Transcribe with recognition bias |
| `core.wait_for_speech()` | Read one audio frame from mic |
| `core.record_until_silence()` | Record for `RECORD_SECONDS` (4s) |
| `core.record(seconds)` | Record for specified duration |
| `core.stream` | PyAudio input stream (16kHz, mono, int16) |

### Loading Order

Plugins load alphabetically. Use number prefixes to control order:
- `00_eyetrack.py` and `00_mousegrid.py` load first (high-priority input modes)
- `zz_base.py` loads last (catch-all help/exit)

---

## Troubleshooting

### "Failed to show grid — is extension enabled?"

```bash
gnome-extensions enable echobase-grid@local
# Then log out and back in
```

### Dictation not working

```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility true
# Log out and back in
```

### Wake word not detecting

- Check microphone: `arecord -d 3 test.wav && aplay test.wav`
- Speak clearly — say "Hey {Name}" with a brief pause
- Check that you chose the right name at startup

### Commands misheard

- Speak clearly after the beep
- Keep commands short and direct
- Check terminal output — the `heard` log shows what Whisper transcribed

### Piper permission denied

```bash
chmod +x ~/.local/bin/piper/piper
chmod +x ~/.local/bin/piper/espeak-ng
```

### pip install fails with PyAV/Cython errors

You're on Python 3.14 or 3.13. Use Python 3.12:

```bash
sudo dnf install python3.12 python3.12-devel
python3.12 -m venv ~/echobase-venv
source ~/echobase-venv/bin/activate
pip install faster-whisper numpy pyaudio
pip install -e .
```

### High CPU usage during idle

Whisper runs every 3 seconds for wake detection. This is expected — it's the tradeoff for supporting custom wake names. On modern hardware (4+ cores), the impact is modest. The `base.en` model (int8 quantized) is the smallest and fastest available.

### Head tracking says "the camera is being used by another app"

A webcam can only be captured by **one** program at a time (V4L2 capture is
single-owner). If a video call, the **Camera** app, OBS, or a browser tab has the
camera open, head tracking can't grab it — and vice-versa. Close the other app,
then say **start tracking** again. Head tracking releases the camera the moment
you say **stop tracking**, so the other app can take over immediately.

If you genuinely need both at once (e.g. tracking *and* a video call), create a
virtual mirror of the camera with [`v4l2loopback`](https://github.com/umlaeute/v4l2loopback)
and point each app at a different node — that's an advanced setup and outside
EchoBase's scope.

### Only one monitor is tracked / `screen two` does nothing

Head tracking reads the monitor layout from the GNOME Shell extension. If you
**updated the extension** (e.g. to this version) you must reinstall it **and log
out / back in** so the running Shell picks up the new code — on Wayland the Shell
can't hot-reload extensions:

```bash
cp extension.js metadata.json ~/.local/share/gnome-shell/extensions/echobase-grid@local/
# then log out and back in
```

Verify the new monitor API is live (should print one entry per display, not an
error):

```bash
gdbus call --session --dest org.gnome.Shell \
  --object-path /org/EchoBase/Grid \
  --method org.EchoBase.Grid.GetMonitors
```

If that still errors with `No such method "GetMonitors"`, the old extension is
still loaded — reinstall and re-login. Monitor order follows GNOME Settings →
Displays.

---

## Development Log

### Session 1 — UI Flow, Desktop Launcher, and Wake Word Overhaul

**Date:** June 2026

**Goal:** Build a complete user-facing flow: GNOME app icon click, name selection, voice assistant — and make the wake word respond to the chosen name instead of only "Hey Jarvis".

---

#### Phase 1: Desktop Launcher and Name Selection UI

**Methods addressed:**
- Created `ui.select_assistant_name()` in `src/core/ui.py` — a boxed terminal menu with 5 defaults (Jarvis, Echo, Nova, Atlas, Sage) plus custom name input
- Created `echobase.sh` bash wrapper to launch the app inside a terminal
- Created `echobase.desktop` for GNOME app grid integration
- Added `--name` and `--select-name` CLI arguments to `main.py`'s `run()` function
- Added `ui.clear_screen()`, `ui.ready_hint(name)`, and updated `ui.banner()` to reflect the chosen persona name

**Blockage 1: `gnome-terminal` not found**
- *Problem:* The initial implementation used `gnome-terminal -e` to launch the app. Fedora 43 ships with Ptyxis as the default terminal — `gnome-terminal` is not installed.
- *Resolution:* Switched all terminal invocations to `ptyxis -s --` which is the Ptyxis equivalent of `gnome-terminal -e`.

**Blockage 2: Two-terminal orchestration failed**
- *Problem:* The original design used two separate terminals — one for name selection, one for the main app. The first terminal would run `EchoBase --select-name /tmp/name.txt`, write the chosen name to a file, then the bash script would read it and launch a second terminal with `EchoBase --name <name>`. This was unreliable: the first terminal sometimes didn't display, timing issues between the two processes, and `Terminal=true` in the `.desktop` file behaved inconsistently with Ptyxis.
- *Resolution:* Collapsed everything into a single terminal. The `.desktop` file uses `Terminal=false` and `Exec=echobase.sh`, which runs `ptyxis -s -- EchoBase`. The `EchoBase` entry point shows the name picker first, then clears the screen and starts the main assistant — all in one process, one terminal.

**Blockage 3: Top-level imports crash `--select-name` mode**
- *Problem:* When using the two-terminal approach, `--select-name` mode only needed to show the name picker and exit. But `main.py` imported `numpy`, `pyaudio`, `faster-whisper`, and `openwakeword` at the module level. These took ~5 seconds to load and `openwakeword` could crash if TensorFlow wasn't available.
- *Resolution:* Moved all heavy imports inside `EchoBase.run()`. Bound numpy as `self._np` for use in instance methods. The module-level code only imports lightweight stdlib modules and `ui`.

---

#### Phase 2: Making the Chosen Name Actually Work

**Methods addressed:**
- Modified `EchoBase.__init__()` to accept a `name` parameter (default `"Jarvis"`)
- Updated all UI output (`ready_hint()`, log messages) to display the chosen persona name
- Implemented `route_clean()` method to strip wake phrase variations from transcribed text before routing commands

**Blockage 4: Custom names don't trigger wake word detection**
- *Problem:* After implementing name selection, selecting "Sage" or "Nova" resulted in no commands being recognized. Only "Jarvis" worked. The root cause: `WAKE_WORD = "hey_jarvis"` — OpenWakeWord's pre-trained `hey_jarvis` model is a neural network trained specifically on recordings of people saying "Hey Jarvis". It literally cannot hear any other phrase. The model file cannot be swapped, reconfigured, or fine-tuned at runtime.
- *Initial attempt:* Searched for alternative OpenWakeWord models — none exist for arbitrary names.
- *Resolution:* Deferred to Phase 3 (full wake word replacement).

---

#### Phase 3: Silence Detection Debugging

**Methods addressed:**
- Investigated energy-based silence detection in the recording pipeline
- Implemented audio calibration: recording 1 second of ambient noise and setting threshold to 1.8x the average energy

**Blockage 5: Energy-based silence detection completely broken**
- *Problem:* The original code used `SILENCE_THRESHOLD = 300` to detect when the user started/stopped speaking. On the target microphone, ambient noise had an average energy of ~13,000 and speech averaged ~10,655. Both values were orders of magnitude above the threshold, and speech was actually *quieter* than ambient noise. The calibration attempt (1.8x ambient = ~24,000 threshold) made things worse — it set the threshold *above* speech energy, so the system never detected speech at all.
- *Resolution:* Removed ALL energy-based silence detection. Replaced with fixed-duration recording (`record(seconds=4)`) and delegated silence filtering to Whisper's built-in `vad_filter=True` (Silero VAD). If a recording is pure silence, Whisper returns an empty string. This is robust regardless of mic characteristics.

**Blockage 6: Plugins depend on removed methods**
- *Problem:* After removing silence detection, the methods `wait_for_speech()` and `record_until_silence()` no longer existed. But four plugins called them: `dictation.py`, `browser.py`, `00_mousegrid.py`, and `00_eyetrack.py`. These plugins use a pattern of `first = core.wait_for_speech()` followed by `audio = first + core.record_until_silence()`.
- *Resolution:* Added both methods back as simple wrappers. `wait_for_speech()` reads one audio frame (1600 samples). `record_until_silence()` delegates to `record()` (4 seconds). The plugins continue to work unchanged, and the combined audio (one frame + 4 seconds) is transcribed by Whisper with VAD filtering.

---

#### Phase 4: Replacing OpenWakeWord with Whisper-Based Wake Detection

**Methods addressed:**
- Removed `openwakeword` import and `WakeWordModel` instantiation from `EchoBase.run()`
- Removed constants: `WAKE_WORD = "hey_jarvis"`, `WAKE_THRESHOLD = 0.5`
- Removed `self.wakeword` from `__init__`
- Added constant: `LISTEN_WINDOW = 3` (seconds per wake detection cycle)
- Rewrote the main loop in `EchoBase.run()` to use Whisper-based wake detection
- Used `initial_prompt=f"Hey {self.name}"` to bias Whisper transcription toward the wake phrase
- Implemented inline command extraction: if "Hey Sage, exit" is spoken in one breath, both wake detection and command routing happen from a single transcription
- Built `wake_phrase = f"hey {self.name.lower()}"` dynamically from the chosen persona name

**Blockage 7: Wake word only responds to "Hey Jarvis" regardless of chosen name**
- *Problem:* Even after all the UI changes, the core wake detection loop was still using OpenWakeWord's `hey_jarvis` model. The `predict()` method returned scores for "hey_jarvis" only. No amount of name changes in the UI could affect what the neural network recognized in audio.
- *Failed approach:* An earlier attempt at Whisper-based wake detection (`_loop_whisper_wake`) failed because it still relied on energy-based silence detection to know when to transcribe, and silence detection was broken (see Blockage 5).
- *Final resolution:* With fixed-duration recording now working (Phase 3), the Whisper-based approach became viable. The main loop records 3-second audio windows in a continuous cycle, transcribes each one, and checks if the text contains the wake phrase via simple string matching (`if wake_phrase not in lowered: continue`). OpenWakeWord was removed entirely as a dependency.

**Blockage 8: Stale `__pycache__` causing import confusion**
- *Problem:* After modifying `main.py` multiple times, Python's bytecode cache served stale versions of the module. Changes to imports and method signatures didn't take effect.
- *Resolution:* Cleared `__pycache__` directories recursively (`find src -type d -name __pycache__ -exec rm -rf {} +`) and reinstalled the editable package (`SETUPTOOLS_SCM_PRETEND_VERSION=0.0.1 uv pip install -e .`). This was done multiple times throughout development whenever behavior didn't match the source code.

**Blockage 9: Wake threshold too high after adjustment**
- *Problem:* During one debugging iteration, the `WAKE_THRESHOLD` was increased from 0.5 to 0.8 in an attempt to reduce false positives. This made the OpenWakeWord model too strict — it stopped recognizing even "Hey Jarvis" reliably. The user reported: "It still takes my wake word command only with Jarvis and does not take the command after it. I saw that you increased the threshold higher and maybe that's why it does not take the commands I give."
- *Resolution:* The threshold became irrelevant once OpenWakeWord was replaced with Whisper-based detection. The new system uses string matching (exact substring check), which has no threshold — either the wake phrase is in the transcription or it isn't. The `WAKE_THRESHOLD` constant was removed entirely.

---

#### Summary of All Files Modified

| File | Changes |
|------|---------|
| `src/core/main.py` | Replaced OpenWakeWord with Whisper wake detection, removed energy-based silence detection, added name parameter, lazy imports, CLI args, route_clean() |
| `src/core/ui.py` | Added select_assistant_name(), clear_screen(), ready_hint(name), color constants, panel() |
| `src/core/__init__.py` | Removed verbose docstring |
| `src/core/__main__.py` | Minimal entry point |
| `echobase.sh` | New file — bash launcher for Ptyxis |
| `echobase.desktop` | New file — GNOME .desktop entry |
| All plugin files | Removed file-level docstrings, kept inline comments concise |

---

### Session 2 — Voice UX, Voice-Controlled OOBE, and Motor-Accessibility Expansion

**Date:** June 2026

**Goal:** Make the assistant feel human (friendly, varied spoken replies), replace the one-shot text name picker with a persistent, fully voice-controlled first-run setup that includes a masculine/feminine voice selector, and substantially expand the tooling for locomotory-impaired users (grid, head tracking, keyboard-by-voice, dwell click, window switching, native-app hints).

---

#### Phase 1: Friendly Voice Messages (the "voice UX" layer)

**Methods addressed:**
- Added `src/core/phrases.py` — interchangeable line banks (greetings, lead-ins, generic "done", farewells, "didn't catch that", "didn't hear anything") with `pick()` that avoids back-to-back repeats per category.
- **Predecessor greetings:** a bare wake word ("Hey Nova") or a spoken "hello/hi/good morning" now answers with a warm, personalised line instead of a chime.
- **Successor confirmations:** the first positive confirmation of a handled command is prefixed with a varied lead-in ("On it! Volume up."), applied globally in `EchoBase.speak()`/`route_command()` so every plugin benefits without edits. Gated by a `friendly_messages` toggle.

**Blockage 1: Cheerful lead-ins glued onto error messages**
- *Problem:* Prefixing "Certainly!" onto every routed `speak()` produced nonsense like "Sure! Install gnome-screenshot…".
- *Resolution:* Added a `_NEG_MARKERS` guard (not/no/install/nothing/fail/found/goodbye/…) plus a length cap, so lead-ins only attach to short, positive confirmations.

**Blockage 2: Double-speak of the generic confirmation**
- *Problem:* When a plugin already spoke its own result, the core still appended a generic "All set."
- *Resolution:* Added a `_route_spoke` flag set inside `speak()`; the generic confirmation only fires when a handled command produced no speech of its own.

---

#### Phase 2: Persistent, Voice-Controlled OOBE + Voice Selector

**Methods addressed:**
- Added `src/core/config.py` — persists setup to `~/.config/echobase/config.json` (assistant name, user name, voice gender, speech rate, friendly toggle, accessibility prefs). Atomic save, defaults-merge on load.
- Added `src/core/oobe.py` — a fully voice-controlled wizard (with keyboard fallback) that collects user name, assistant name, **masculine/feminine voice** (with a live spoken sample), speech rate, and friendly-replies preference, then saves and marks setup complete.
- Wired `speak()` to use the chosen Piper model + `--length_scale` (speech rate); added `apply_voice()` and `config.ensure_voice()` (downloads a voice if missing, graceful fallback).
- Restructured `run()` so Whisper + microphone come up *before* the OOBE, allowing voice answers.

**Blockage 3: Only a feminine Piper voice was installed**
- *Problem:* The masculine option had no model on disk (`en_US-amy-medium` only).
- *Resolution:* Downloaded `en_US-ryan-medium` from the rhasspy/piper-voices repo; `ensure_voice()` fetches a missing model on demand and falls back to feminine, then to any model present.

---

#### Phase 3: "Factory Reset" (debug) That Truly Resets

**Methods addressed:**
- Spoken **"factory reset"** (also `--reset-oobe` / `ECHOBASE_RESET=1`) re-runs the wizard. The trigger is anchored on the distinctive word "factory" (`_is_reset_phrase`), so it can't be misheard as a normal command or fire accidentally.
- The reset **deletes the saved config immediately** (`config.reset()`) before the wizard runs.

**Blockage 4: Old config persisted if the app was closed mid-reset**
- *Problem:* The original reset only re-saved at the end of the wizard, so closing the app during setup left the previous configuration on disk.
- *Resolution:* Wipe the config file up front (in `_maybe_reset()` and on the `--reset-oobe` path); a mid-reset close now leaves nothing stale and the next launch starts fresh in the OOBE.

---

#### Phase 4: Motor-Accessibility Expansion (12 items)

**Improvements to existing tools:**
- **Mouse grid** (`00_mousegrid.py`): "back"/"undo" zooms out one level via a `grid_history` stack; added **hover** (move without click), **triple-click**, and **hold/release** (press-and-hold).
- **Head tracking** (`00_eyetrack.py`): **camera auto-detect** (`open_camera()` replaces the hard-coded `VideoCapture(1)`, speaks on failure); live **"faster"/"slower"** sensitivity; **instant recalibrate** via a flag (no thread restart); **dwell click** with an on-screen countdown ring.
- **a11y** (`a11y.py`): added dwell-click, mouse-keys, bounce keys, key-repeat toggles plus pointer-speed and double-click-delay stepping.

**New features:**
- **Keyboard by voice** (`keyboard.py` + extension virtual keyboard `PressKey`/`KeyCombo`): named keys, arrows, page/home/end, "press control c", and shortcuts (copy/paste/cut/undo/redo/select-all/save/print/alt-tab).
- **Window switcher** (`windows.py`): "switch to firefox", "list windows", "next/previous window", plus a **numbered window picker** overlay.
- **Voice macros / repeat** (core): "repeat that", "do that N times", and record/play ("start recording" → … → "stop recording" → "play macro").
- **Native-app click hints** (`labels.py`): an isolated AT-SPI subprocess walk numbers clickable controls; the extension draws vimium-style badges (`ShowHints`); say a number to click.
- **OOBE accessibility step**: dwell on/off + head-tracking sensitivity are now collected during setup and read by the head tracker at startup.

**GNOME Shell extension (`extension.js`) additions:** `TripleClick`, `PressKey`/`KeyCombo` (virtual keyboard device), `ShowDwell`/`HideDwell` (countdown ring), `ShowWindowPicker`/`HideWindowPicker`, and `ShowHints`/`HideHints`.

**Blockage 5: Repeat phrases — "twice"/"thrice" not detected, "twenty" missing, and bare "again" hijacked**
- *Problem:* `_repeat_spec()` only triggered on the substring "times", so "do that twice" was ignored; `_parse_times()` lacked teens/twenty; and treating "again" as a repeat would have stolen it from the grid's "again" command.
- *Resolution:* Broadened the trigger to repeat-ish phrases with a count word (times/twice/thrice), added 11–20 to the number map, and deliberately excluded bare "again".

**Blockage 6: Dwell click never accumulated**
- *Problem:* The head-tracking loop `continue`s early when the head is still (velocity gate) — exactly the moment a dwell should count down — so the dwell logic placed after cursor movement never ran while resting.
- *Resolution:* Call `dwell_tick()` inside the velocity-gate "still" branch as well; factored the dwell state machine into testable `dwell_update()`/`dwell_tick()` with reset/progress/click/held states (no re-click until the cursor moves away).

**Blockage 7: New plugins hijacking other commands**
- *Problem:* The a11y double-click-delay handler could swallow the grid's bare "double click"; the keyboard plugin's arrow keys could clash with grid nudge; and "switch window" (picker) overlapped "switch window to X" (focus).
- *Resolution:* Required qualifier words (the a11y handler only fires with slower/faster/longer/shorter); arrows only act via an explicit "press"; and the picker matches "switch window" exactly while "switch window to …" falls through to the focus prefix. All verified with unit tests.

**Blockage 8: AT-SPI fragility on Wayland**
- *Problem:* Walking the accessibility tree in-process risks blocking and varies by toolkit; some apps expose no usable coordinates.
- *Resolution:* Ran the AT-SPI walk in a sandboxed `python3 -c` subprocess that prints JSON, with a timeout and graceful "couldn't find any labelled controls" fallback.

**Deployment note:** the `extension.js` changes (keyboard injection, dwell ring, window picker, hints) require reinstalling the GNOME Shell extension and a **logout/login** (Shell reload) on Wayland before those four features work; the rest function without a reload.

---

#### Summary of Files Modified (Session 2)

| File | Changes |
|------|---------|
| `src/core/main.py` | Friendly lead-ins/greetings, config load + voice/rate, OOBE trigger, factory-reset (wipe), repeat + macros, `_dispatch()` split |
| `src/core/config.py` | New — persistent config, voice download/ensure, speech-rate + accessibility prefs |
| `src/core/phrases.py` | New — varied greeting/lead-in/done/farewell/recovery phrase banks |
| `src/core/oobe.py` | New — voice-controlled first-run wizard (name, voice selector, rate, accessibility, friendly) |
| `src/plugins/00_mousegrid.py` | Back/undo history, hover, triple-click, hold/release |
| `src/plugins/00_eyetrack.py` | Camera auto-detect, live sensitivity, instant recalibrate, dwell click |
| `src/plugins/a11y.py` | Dwell-click/mouse-keys/bounce/key-repeat toggles, pointer-speed & double-click-delay |
| `src/plugins/keyboard.py` | New — keys and shortcuts by voice |
| `src/plugins/windows.py` | New — window switching + numbered picker |
| `src/plugins/labels.py` | New — AT-SPI numbered click-hints for native apps |
| `extension.js` | TripleClick, virtual keyboard (PressKey/KeyCombo), dwell ring, window picker, hints overlays |
| `src/plugins/zz_base.py` | Varied farewells via `phrases` |

---

### Session 3 — Test-Suite Stabilization, Head-Tracking Latency, and Multi-Monitor Support

**Date:** June 2026

**Goal:** Unblock and green the test suite (a hanging test plus stale failures), eliminate the head-tracking lag, make the cursor reach every monitor, fail gracefully when the webcam is held by another app, and add opt-in performance instrumentation to pin down any remaining latency with real numbers.

---

#### Phase 1: Test-Suite Stabilization

**Methods addressed:**
- Greened the full suite (672 tests). Adopted an OS-level `timeout` + `faulthandler` workflow to capture stack dumps from hanging tests instead of re-running blind.

**Blockage 1: A `run()` test hung the whole suite indefinitely**
- *Problem:* `test_run_exit_command` spun forever in the `while True` loop. The stack dump showed the cause: the tests construct `EchoBase()`, which loads the developer's **real** saved config (assistant name `"Slave"`). That name has no pretrained wake model, so wake detection falls back to Whisper transcription matching `"hey slave"` — and against a stream mock that returns the same frame forever, the match never happens and the loop never exits.
- *Resolution:* Added a class-scoped autouse fixture (`_isolate_config`) pinning a deterministic config (name `"Jarvis"` → mockable wake-model branch, `oobe_completed: true` → skip the wizard) and no-opping `apply_voice` (avoids a network voice fetch). Tests are now isolated from the developer's config.

**Blockage 2: Five stale tests against the refactored API**
- *Problem:* `is_silence` had been replaced by the Silero VAD; `route_command`'s reply became a randomized `phrases.not_understood()`; `run()` gained argparse; and the `EchoBase` console-script test failed because the package wasn't installed.
- *Resolution:* Dropped the two dead `is_silence` tests; updated the no-match test to assert a `_NOT_UNDERSTOOD` phrase with `allow_lead=False`; patched `sys.argv`/`os.environ` for `run()` and asserted `EchoBase(name=None, reset_oobe=False)`; installed the package editable (`SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0 uv pip install -e . --no-deps`, since the dir isn't a git repo so setuptools_scm couldn't otherwise derive a version). Suite went from hanging → all green.

---

#### Phase 2: Head-Tracking Latency

**Methods addressed (`00_eyetrack.py`):**
- **Removed the 15-frame rolling average** stacked on top of the One-Euro filter — at ~10–15 fps that was ~0.6–1.2 s of group delay, the dominant cause of the trailing cursor.
- **Fixed the One-Euro timebase:** the filter now takes a real per-frame timestamp and derives the true sampling rate (clamped 5–120 Hz), instead of a hardcoded `freq=30` that mis-tuned the cutoff.
- **Removed the artificial `time.sleep(0.033)`** frame cap on the active path; head-pose inference is the natural throttle now.
- **Throttled redundant `MoveTo`** calls (skip when the integer position is unchanged) to avoid a gdbus spawn per frame.
- Retuned filter constants (`min_cutoff 0.8→1.2`, `beta 0.005→0.02`) for a snappier response on the corrected timebase. Added a **Head Tracking — Setup & Tutorial** section to this README.

---

#### Phase 3: Multi-Monitor Support

**Methods addressed:**
- **Extension:** added a `GetMonitors` D-Bus method returning every monitor's global-coordinate geometry as JSON (mirrors `GetWindows`).
- **Tracker:** head pose now maps into a **region rectangle** in the compositor's global coordinate space rather than a primary-monitor-sized box at the origin, so a secondary monitor sitting at a non-zero origin is reachable. Two modes — **`active`** (one monitor at a time, switchable) and **`span`** (all monitors as one surface) — via `get_monitors()`, `refresh_monitors()`, `tracking_region()`, `switch_monitor()`, `set_monitor_mode()`, plus live voice commands (`next screen`, `previous screen`, `screen two`, `span screens`, `single screen`). New config key `tracking_monitor_mode`.

**Blockage 3: Only one monitor was recognised (laptop + external)**
- *Problem:* Live diagnosis showed the compositor *did* see both displays (`eDP-1` + `HDMI-1`), but `gdbus … GetMonitors` returned `No such method` — the running GNOME Shell was still executing the **old installed extension** (a copy, not a symlink), so Python fell back to primary-only.
- *Resolution:* Bumped the extension to `version 3` and reinstalled it into `~/.local/share/gnome-shell/extensions/`; requires a logout/login on Wayland to load. Documented the symptom, the fix, and a `GetMonitors` verification command in Troubleshooting.

---

#### Phase 4: Camera-Conflict Handling

**Methods addressed (`00_eyetrack.py`):**
- A webcam is single-owner under V4L2 — head tracking and a camera app cannot share it. `open_camera()` now enumerates `/dev/video*`, retries a few frames (warm-up tolerance), and classifies failure as **`busy`** (a device exists but couldn't be grabbed → another app holds it) vs **`missing`** (no camera at all), speaking the accurate reason. The camera is released the instant tracking stops. Added a Troubleshooting entry (including the `v4l2loopback` route for genuinely simultaneous use).

---

#### Phase 5: Lag Instrumentation

**Methods addressed:**
- Added an opt-in `PerfMonitor` to the tracking loop (enable via `ECHOBASE_TRACK_PERF=1` or `"tracking_debug": true`). Every ~2 s it prints fps plus per-stage averages — camera **read**, model **infer**ence, cursor **move**, total **loop** — wired into every loop branch so the fps reflects all frames. This is the instrument for deciding whether remaining lag is CPU inference (→ GPU / lighter model / smaller frame) or elsewhere. Documented under **Diagnosing lag** in the tutorial.

---

#### Answered (no code change)

- **"After a factory reset, do I need to re-record head tracking?"** No. Head tracking persists nothing — it calibrates live in memory from the first ~10 frames each time you `start tracking`. Factory reset only deletes `config.json` (preferences); there is no recorded or trained calibration to redo.

---

**Deployment note:** the `extension.js` change (`GetMonitors`) requires reinstalling the GNOME Shell extension and a **logout/login** on Wayland before multi-monitor tracking works.

---

#### Summary of Files Modified (Session 3)

| File | Changes |
|------|---------|
| `src/plugins/00_eyetrack.py` | Latency fixes (drop moving-average, real One-Euro timebase, no frame cap, `MoveTo` throttle); multi-monitor regions + voice switching; camera busy/missing detection; `PerfMonitor` instrumentation |
| `extension.js` | New `GetMonitors` D-Bus method (per-monitor global geometry) |
| `metadata.json` | Extension `version` 2 → 3 |
| `src/core/config.py` | New defaults: `tracking_monitor_mode`, `tracking_debug` |
| `tests/core/test_main.py` | `_isolate_config` autouse fixture; updated stale tests (dropped `is_silence`, randomized not-understood, `run()` argv) |
| `tests/core/test_cli.py` | `test_main_run` patched for argparse/env |
| `tests/plugins/test_eyetrack.py` | Tests for monitors/regions/switching, camera classification, perf monitor |
| `README.md` | Head-tracking tutorial, multi-monitor + diagnosing-lag sections, camera/monitor troubleshooting, this log |

---

### Session 4 — Head-Tracking Quality: Directional Fix, Smoothing, and the MediaPipe Migration

**Date:** June 2026

**Goal:** Make head tracking genuinely usable as a head-controlled mouse for users with locomotor disabilities — the pointer was reaching only one corner, jittering badly, and lagging. Work proceeded data-first: instrument, read the numbers, fix the actual cause, repeat.

---

#### Phase 1: The pointer only moved one way (directional fix)

**Methods addressed:**
- Added an **angle probe** (under `tracking_debug`): a few times a second it prints the model's raw angle, the calibrated centre, and the resulting offset, so the head signal can be observed directly while moving up/down/left/right.

**Blockage 1: "Look up or down, the pointer only goes down; tilt left or right, it only goes left"**
- *Problem:* The probe showed the offsets actually swung **both** ways (yaw −9…+21, pitch −16…+14) — so signs and calibration were correct. The culprit was the mapping curve: it **squared** the offset (`EXPO = 2.0`). Any offset past ~11° mapped straight to the screen edge, and natural head movement is 10–20°, so the pointer lived in the corners with no usable middle.
- *Resolution:* Replaced the squared curve with a **linear, proportional map** — a head turn of `HEAD_RANGE_*` degrees reaches the edge, everything between maps 1:1. Verified on the captured data: a 12° offset went from `959px` (slammed to edge) to `432px` (proportional).

---

#### Phase 2: Jitter and instability (smoothing overhaul)

**Blockage 2: The pointer was unstable — continuous shimmer plus sudden jumps**
- *Problem:* A second capture showed two noise sources: continuous ±3°/frame jitter at rest, and occasional **single-frame pose spikes** (e.g. pitch flicking −15 → −4 → −15) that jerked the cursor.
- *Resolution:* A three-stage pipeline tuned by a new `tracking_smoothing` preset (`low`/`medium`/`high`): a **median pre-filter** kills single-frame spikes, a stronger **One-Euro** stage smooths residual jitter, and **cursor easing** low-passes the on-screen motion. The old **velocity gate was removed** — with easing it would freeze the cursor short of its target (undershoot); easing toward a stable target settles on its own.

---

#### Phase 3: Camera-vs-monitor geometry + the real ceiling

**Methods addressed:**
- The probe also revealed the practical issue that the **webcam is on the laptop while the user tracks the external monitor**, forcing a large, asymmetric neutral head pose. Documented the "track the screen the camera faces" guidance.

**Blockage 3: Even at maximum smoothing the signal had a floor**
- *Problem:* SixDRepNet runs at only ~15 fps on CPU with ±3° per-frame noise. You can't filter past a noisy 15 Hz signal without adding lag — every gain in smoothness cost responsiveness.
- *Resolution:* This motivated replacing the pose source entirely (Phase 4).

---

#### Phase 4: MediaPipe Face Mesh (new tracking backend)

**Methods addressed:**
- Replaced SixDRepNet with **MediaPipe Face Mesh** (`create_face_mesh()` + `estimate_pose()`). The control signal is the **nose tip's position relative to the eye-line, normalised by inter-ocular distance** — head orientation invariant to how far the user sits. This is the established "head mouse" approach (cf. Camera Mouse), a clean, citable method for the thesis.
- The **entire downstream pipeline is reused unchanged**: calibration, median + One-Euro + easing, linear mapping, multi-monitor regions/switching, dwell, voice commands. The new backend simply feeds `(yaw, pitch)` in.
- Pinned `mediapipe>=0.10.9,<0.10.18` for the self-contained `solutions.face_mesh` API (model bundled in the wheel — no separate download, reproducible).

**Result (measured on the user's machine):** frame rate ~15 → **30 fps**, inference ~56 ms → **3.5 ms**, rest jitter ±3° → **±1**. Fast and smooth at the same time, instead of trading one for the other.

**Blockage 4: MediaPipe flooded the console**
- *Problem:* Its protobuf dependency emits a `GetPrototype() is deprecated` `UserWarning` on every frame, and its C++ core logs to stderr — burying the debug output.
- *Resolution:* `create_face_mesh()` installs a targeted warning filter and sets `GLOG_minloglevel`, silencing both. (The unrelated ALSA `unable to open slave` messages are harmless libasound probing from PyAudio at startup.)

---

**Test status:** 678 tests pass. Added the angle probe, `tracking_smoothing` presets, `estimate_pose`/`create_face_mesh` (incl. distance-invariance and warning-suppression), and reworked the run-tracking scenario test for the pose interface.

---

#### Summary of Files Modified (Session 4)

| File | Changes |
|------|---------|
| `src/plugins/00_eyetrack.py` | Linear proportional mapping (was squared `EXPO`); median + One-Euro + cursor-easing smoothing with `tracking_smoothing` presets; removed velocity gate; angle probe; **MediaPipe Face Mesh backend** (`create_face_mesh`/`estimate_pose`) replacing SixDRepNet; protobuf/glog noise suppression |
| `src/core/config.py` | New default: `tracking_smoothing` |
| `pyproject.toml` | `[head-tracking]` extra now `mediapipe` (pinned) + `opencv-python`, was `sixdrepnet` |
| `tests/plugins/test_eyetrack.py` | Pose-interface scenario test; `estimate_pose` (centre/turn/distance-invariance/no-face), `create_face_mesh`, warning-suppression tests |
| `README.md` | Head-tracking tutorial/troubleshooting rewritten for MediaPipe; this log |

---

### Session 5 — Automation, Multitasking, Cross-Browser, Snap-to-Button, and "Did You Mean?"

**Date:** June 2026

**Goal:** A professor advised that actions should be far more **automated** for users with severe locomotor disabilities — design target: a person with **no hands**, relying entirely on voice + head tracking. Audit the command set from that lens, add automations that remove multi-step friction, and fix five concrete pain points.

---

#### New shared foundations

- **`src/core/atspi.py`** (new): the AT-SPI accessibility helpers (clickable-element walk, focused-field text insert, active-window text read) were previously inlined in individual plugins; they are now one reusable module consumed by labels, browser link-clicking, click-by-name, snap-to-button, snippets, and read-screen.
- Shared **yes/no** vocabulary moved into `phrases.py` (`YES_WORDS`/`NO_WORDS`/`wants_yes`); `core.listen_yes_no()`, `core.type_text()`, `core.active_mode`, and `core.run_global_command()` added.

#### The five fixes

1. **Use other commands while a mode is active.** Mode listen-loops (head tracking especially) now re-route anything that isn't a mode command through `run_global_command()`, which **skips the blocking-mode plugins** so a second mode can't nest. So volume/brightness/apps/scroll work while tracking stays live.
   - *Blockage:* the in-mode Whisper prompt is biased to that mode's vocabulary, mangling general commands. *Resolution:* on a non-mode phrase, **re-transcribe the same audio** with the general prompt before global routing.
2. **Hang onto buttons (snap-to-element).** A background thread caches clickable rects from AT-SPI; the tracking loop pulls — and holds — the cursor onto the nearest control (`_snap_center`), so dwell clicks land reliably. The AT-SPI query is too slow per-frame, so it runs on a ~0.7 s timer in its own thread.
3. **Steadier pointer.** Retuned all three `tracking_smoothing` presets; snap removes the remaining drift near targets.
4. **Cross-browser commands.** OOBE now auto-detects installed browsers and stores the choice; `browser.py` was rewritten from qutebrowser-only IPC to **portable keyboard shortcuts** (`KeyCombo`: Ctrl+T/W/L, Alt+Left…), wheel `Scroll`, and the **AT-SPI numbered-label overlay** for link clicking — identical behaviour on Firefox/Chrome/Brave/qutebrowser.
   - *Blockage:* under the runtime loader the plugin is `plugins.labels`, but `browser` imports `EchoBase.plugins.labels` — a different module object whose `core` was never set. *Resolution:* `labels.show()` adopts the passed `core` into its module global. *Known risk:* link clicking depends on the browser exposing web content over AT-SPI (accessibility integration enabled).
5. **"Did you mean…?" recovery.** On an unmatched command, `difflib` finds the closest known phrase and asks to confirm; on "yes" it re-dispatches. Each plugin contributes canonical `PHRASES` (incl. common `open <app>` forms) so misses like *"open fire folks"* → *"open firefox"* resolve.

#### New automations

- **Global / continuous scroll** (`scroll.py`): "scroll down" works anywhere — including at the live tracked cursor during head tracking — and "keep scrolling" auto-scrolls until "stop".
- **Click by name** (`labels.py`): "click submit" clicks a labelled control directly via AT-SPI, skipping the number step.
- **Personal text snippets** (`snippets.py`): "type my email/phone/address/name" inserts details collected in OOBE.
- **Read screen aloud** (`a11y.py`): "read the page" speaks the active window's text via AT-SPI.

**Test status:** 630 tests pass (48 new). `browser` tests rewritten for the universal implementation; added tests for the new plugins, snap, fuzzy recovery, and config/browser helpers.

---

#### Summary of Files Modified (Session 5)

| File | Changes |
|------|---------|
| `src/core/atspi.py` | **New** — shared AT-SPI clickables / text-insert / window-text helpers |
| `src/core/main.py` | `active_mode`, `run_global_command`, `type_text`, `listen_yes_no`, `known_phrases`, "did you mean?" recovery |
| `src/core/config.py` | `browser` + snippet keys; `detect_browsers`/`browser_command` |
| `src/core/oobe.py` | Browser-selection and snippets steps |
| `src/core/phrases.py` | Shared `YES_WORDS`/`NO_WORDS`/`wants_yes` |
| `src/plugins/00_eyetrack.py` | Snap-to-button magnetism + cache thread; in-mode global routing; tuned smoothing |
| `src/plugins/browser.py` | Rewritten browser-agnostic (KeyCombo + AT-SPI labels) |
| `src/plugins/labels.py` | Uses `atspi`; `click_by_name`; reusable `show()` |
| `src/plugins/scroll.py`, `snippets.py` | **New** plugins |
| `src/plugins/a11y.py`, `apps.py` | Read-screen; `open <app>` PHRASES |

---

### Session 6 — Recognition Precision for Dysarthric Speech, and Dictation Command Disambiguation

**Date:** June 2026

**Goal:** Many target users (e.g. hemiparesis) also have **dysarthria** — slurred, slow, or imprecise speech — so recognition must be as forgiving as possible. Also fix dictation mishandling text-editing words: *"I need space to think"* became *"I needto think"* because `space`/`enter`/`backspace` were substituted **anywhere** in an utterance.

---

#### Part A — recognition precision

- **Accuracy as a setup choice.** Whisper model/beam are now configurable (`whisper_model`/`whisper_beam` + `recognition_settings`); OOBE asks accuracy-vs-speed — "accuracy" loads `small.en` + beam search, "speed" keeps `base.en`.
  - *Blockage:* the model is needed to hear OOBE answers, before the user has chosen one. *Resolution:* run the wizard on the saved default, then **reload the model once after OOBE** if the choice differs (`_ensure_whisper_model`).
- **Speech pace.** A `speech_pace` setting (normal/relaxed/slow → `pace_timing`) lengthens the trailing-silence threshold and the max-utterance cap in `record_until_silence`, so slow or effortful speakers aren't cut off mid-sentence.
- **Auto/ask fuzzy recovery.** The miss path now recovers **every** command: ≥ `AUTO_CUTOFF` (0.85) **auto-runs** the closest known phrase silently; 0.6–0.85 **asks** "did you mean?"; this also covers commands issued **mid-mode** (auto-run only) and the **strict exact-match plugins**. Input filler ("please…", "…please") is stripped first (`_normalize_command`).
- **Command audit.** The fragile exact-match plugins (`time`, `window`, `windows`, `media`, `keyboard`, `system`, `zz_base`) gained explicit `PHRASES` so every command is recoverable (registry 167 → 187). Verified: "volume op"→volume up, "minimise"→minimize, "close windo"→close window auto-correct; "what thyme"→what time asks.

#### Part B — dictation: command vs. literal word

- **Principle:** dictation already records **one utterance at a time**, so an editing/structural word is a command **only when the whole short utterance is just that word** (`parse_editing_command`) — e.g. a deliberate "new line", or a sequence like "backspace backspace". Embedded in prose, the same word is inserted **literally**.
  - *Blockage / earlier behaviour:* `format_text` regex-substituted `space`/`tab`/`enter`/`new line`/`backspace`/`delete` everywhere. *Resolution:* those structural/editing replacements were **removed** from `format_text` (so they stay literal in a sentence) and handled only by the standalone parser; punctuation/symbol words (`comma`, `period`, …) remain inline as before.
  - Verified: *"new line"* → newline; *"press enter to continue"* → typed literally; *"I need space to think"* → unchanged.

**Test status:** 660 tests pass. Updated `format_text` assertions for the now-literal editing words; added `parse_editing_command` cases (incl. prose → `None`), normalization / `_closest_phrase` / `_recover` (auto-run vs ask) tests, and config-helper tests.

---

#### Summary of Files Modified (Session 6)

| File | Changes |
|------|---------|
| `src/core/config.py` | `whisper_model`/`whisper_beam`/`speech_pace` keys; `recognition_settings`/`pace_timing` |
| `src/core/main.py` | Config-driven model/beam (+ post-OOBE reload), pace-driven endpointing, `_normalize_command`/`_closest_phrase`/`_recover` (auto-run ≥0.85, ask ≥0.6) |
| `src/core/oobe.py` | `_step_recognition`, `_step_pace` |
| `src/plugins/dictation.py` | `parse_editing_command` (standalone-only editing words); trimmed `format_text` |
| `src/plugins/{time,window,windows,media,keyboard,system,zz_base}.py` | `PHRASES` for fuzzy recovery |

---

### Session 7 — Recognition-Profile Picker (Fastest → Most Accurate) in OOBE

Session 6 made recognition a **binary** accuracy-vs-speed toggle. That under-served the most-impaired users, so it's now a **4-level numbered profile picker** spanning fastest → most accurate, chosen by **saying a number** (consistent with the `windows.py` window picker and `labels.py` numbered hints), with the keyboard fallback kept.

#### The four profiles

| # | Name | Model | Beam | Bias (`initial_prompt`) | auto/ask cutoffs | n-best |
|---|------|-------|------|-------------------------|------------------|--------|
| 1 | Fast | `base.en` | 1 | command (today's `COMMAND_PROMPT`) | 0.85 / 0.60 | 1 |
| 2 | Balanced *(recommended)* | `small.en` | 5 | command | 0.85 / 0.60 | 1 |
| 3 | Accurate | `medium.en` | 8 | phrases (COMMAND_PROMPT + known vocabulary) | 0.80 / 0.55 | 1 |
| 4 | Maximum | `distil-large-v3` | 8 | phrases-strong (full known-phrase list) | 0.72 / 0.50 | 3 |

Profiles 1 and 2 **reproduce Session 6's *fast* and *accurate* behaviour exactly** (same model, beam, prompt, and cutoffs), so nothing regresses. Tier 4 is the dysarthria-robust tier — it's *allowed* to be slow and pairs with a relaxed `speech_pace`.

- **Profile as the source of truth.** A new `recognition_profile` (1–4) expands via `recognition_settings` into model/beam **plus** an `initial_prompt` biasing level, recovery-cutoff overrides (`auto_cutoff`/`ask_cutoff`), and an `nbest` count. `recognition_settings` now returns a structured `RecognitionSettings` namedtuple instead of a `(model, beam)` tuple; all callers/tests updated.
- **Stronger biasing.** Tiers 3–4 build the Whisper `initial_prompt` from the live command vocabulary (`known_phrases`) so the decoder leans toward things the user can actually say.
- **Profile-4 n-best.** *Blockage:* faster-whisper 1.2.1 returns only the single best transcript per call. *Resolution:* `transcribe_nbest` re-decodes at increasing temperatures (0.0/0.2/0.4), collects distinct hypotheses, and `_pick_best_candidate` keeps the one whose closest known phrase scores highest — then routes it through the normal recovery path.
- **More forgiving recovery per tier.** `_recover` reads its auto/ask cutoffs from the active profile (canonical defaults moved into `config.py`), so slurred near-misses the 0.85 default would drop are recovered on tiers 3–4.
- **Bootstrap.** *Blockage:* OOBE must hear answers before the user has picked a model. *Resolution:* with no profile chosen yet, the config resolves to the light `base.en` boot model; after the picker, the chosen model reloads **once** via the existing post-OOBE `_ensure_whisper_model` call. Heavy tiers (medium/distil-large) get a spoken "this may take a moment" before loading.
- **Hardware.** Target dev machine is an RTX 3050 (~4 GB) + Ryzen 7 5800H + 16 GB RAM; `compute_type="int8"` keeps all four tiers within VRAM, and `distil-large-v3` (≈6× faster, ~half the VRAM of large-v3, near-identical English accuracy) makes tier 4 practical.

**Test status:** 703 tests pass (was 660). Updated the `recognition_settings` tests for the structured return and added profile-expansion (incl. profile 1/2 == legacy exactly), `profile_for_config` migration, per-profile cutoff override, bias-prompt, `transcribe_nbest`/`_pick_best_candidate`, model-reload-and-warn, and a new `tests/core/test_oobe.py` for the numbered picker (spoken number, homophones, reprompt-on-garbage, keyboard fallback, default-to-Balanced). One pre-existing unrelated failure remains: `test_cli.py::test_entrypoint` (the `EchoBase` console script isn't installed on PATH in this venv).

#### Summary of Files Modified (Session 7)

| File | Changes |
|------|---------|
| `src/core/config.py` | `recognition_profile` key; `RECOGNITION_PROFILE_TABLE` (replaces `RECOGNITION_PROFILES`); structured `RecognitionSettings` + expanded `recognition_settings`; `profile_for_config`; cutoff defaults (`SUGGEST_CUTOFF`/`AUTO_CUTOFF`) |
| `src/core/main.py` | `_command_prompt` biasing, `transcribe`/`_audio_to_wav`/`_whisper_text` refactor, `transcribe_nbest` + `_pick_best_candidate`, profile-driven cutoffs in `_recover`, heavy-model heads-up in `_ensure_whisper_model`, n-best routing in the listen loop |
| `src/core/oobe.py` | `_step_recognition` → numbered profile picker; `_parse_choice` + `_CHOICE_WORDS`/`_PROFILE_CONFIRM` |
| `tests/core/test_new_features.py`, `tests/core/test_oobe.py` | profile/migration/recovery/n-best/reload + OOBE-picker tests |

#### Follow-up — AT-SPI clickable-label query timeout

A live session surfaced `labels · accessibility query failed (… timed out after 8 seconds)`: the `get_clickables` AT-SPI walk (`atspi.py` `_CLICKABLES_SCRIPT`) hung on a busy window.

- *Cause:* the walk recursed into **every** subtree of the active window — including hidden/offscreen ones (background browser tabs, collapsed panels) — over the synchronous AT-SPI/D-Bus bridge, fetching each node's state-set twice. On a heavy window that's thousands of round-trips, blowing the 8 s subprocess timeout and returning nothing.
- *Resolution:*
  - **Prune hidden subtrees** — stop descending into any node that isn't `SHOWING` (below the active top-level frame); its descendants aren't clickable anyway, and this removes the runaway traversal.
  - **Hard visit budget** (`MAX_VISITS = 4000`) bounds total nodes touched, not just the 60-hit cap.
  - **One state-set fetch per node** (reused for the prune + clickable checks) instead of two.
  - **Per-call AT-SPI timeout** via `Atspi.set_timeout(800, 3000)` (guarded) so a single wedged toolkit reply fails fast instead of eating the whole budget.
  - Subprocess ceiling 8 s → **12 s** for cold-bridge headroom (pruning keeps the common case well under a second). The same `set_timeout` guard and showing-prune/visit-budget were applied to the "read the screen" walk, which had the identical risk.
- *Test isolation:* picking "Accurate" in the new OOBE picker changed the dev machine's saved config (`recognition_profile: 3`, `speech_pace: slow`), which then leaked into two tests that built `EchoBase()` without pinning config. Pinned `app.config = {}` in the `_recover` tests (default 0.85/0.6 cutoffs) and normal-pace endpointing in `test_record_until_silence`, so they no longer depend on the developer's saved settings.

**Test status:** 703 tests pass (one pre-existing, environment-only failure: `test_cli.py::test_entrypoint`, which checks the `EchoBase` console script is installed on PATH).

#### Summary of Files Modified (Session 7 follow-up)

| File | Changes |
|------|---------|
| `src/core/atspi.py` | `_CLICKABLES_SCRIPT`/`_READ_SCRIPT`: hidden-subtree prune, `MAX_VISITS` budget, single state-set fetch, `Atspi.set_timeout` guard (all three scripts); `get_clickables` subprocess timeout 8 s → 12 s |
| `tests/core/test_new_features.py` | pinned `app.config = {}` in the `_recover` tests |
| `tests/core/test_main.py` | pinned normal-pace endpointing in `test_record_until_silence` |

---

## License

GPL-3.0 License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) — Speech recognition (wake detection + command transcription)
- [Piper](https://github.com/OHF-Voice/piper1-gpl) — Text-to-speech (last standalone binary from [rhasspy/piper](https://github.com/rhasspy/piper))
- [Silero VAD](https://github.com/snakers4/silero-vad) — Voice activity detection (integrated via faster-whisper)
- [Talon](https://talonvoice.com/) — Inspiration for voice control concepts
- [EchoBase upstream](https://github.com/ctsdownloads/EchoBase) — Original project by Matt Hartley
