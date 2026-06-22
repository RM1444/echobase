"""Persistent user configuration for EchoBase.

Holds the result of the first-run setup (OOBE): the assistant name, the voice
to speak with, speech rate, and personalisation. The config lives at
``~/.config/echobase/config.json`` so the user never has to repeat setup.

A small *debug* affordance is built in: while developing, the OOBE can be
re-triggered at any time (spoken "factory reset", the ``--reset-oobe`` flag, or
``ECHOBASE_RESET=1``). Each of these deletes the saved config first, so the
setup truly resets rather than persisting. See :func:`debug_enabled`.
"""

import json
import os
import shutil
import sys
import urllib.request
from collections import namedtuple
from pathlib import Path

CONFIG_DIR = Path(os.path.expanduser("~/.config/echobase"))
CONFIG_FILE = CONFIG_DIR / "config.json"

PIPER_DIR = Path(os.path.expanduser("~/.local/share/piper"))

# --- Autostart (start on login) ---------------------------------------------
# "Start when my computer starts" is implemented with the cross-desktop XDG
# autostart spec: a .desktop file dropped in ~/.config/autostart is launched at
# login by GNOME, KDE, XFCE, etc. Enabling writes the file; disabling removes it.
AUTOSTART_DIR = Path(os.path.expanduser("~/.config/autostart"))
AUTOSTART_FILE = AUTOSTART_DIR / "echobase.desktop"

# --- Voices -----------------------------------------------------------------
# Map a spoken gender choice to a Piper voice. Both ship as a .onnx model plus
# a .onnx.json config sitting next to it in PIPER_DIR.
VOICES = {
    "feminine": "en_US-amy-medium",
    "masculine": "en_US-ryan-medium",
}

# Where to fetch a voice from if it is not present locally (no trailing ext).
_VOICE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US"
VOICE_URLS = {
    "en_US-amy-medium": f"{_VOICE_BASE}/amy/medium/en_US-amy-medium",
    "en_US-ryan-medium": f"{_VOICE_BASE}/ryan/medium/en_US-ryan-medium",
}

# Spoken speech-rate choice -> Piper --length_scale (higher = slower).
RATE_LENGTH_SCALE = {
    "slow": 1.35,
    "normal": 1.0,
    "fast": 0.8,
}

# --- Accessibility tuning ---------------------------------------------------
# Spoken sensitivity name -> multiplier applied to head-tracking pixel/degree
# gains. Higher = the cursor travels further for the same head movement.
TRACKING_SENSITIVITY = {
    "slow": 0.6,
    "normal": 1.0,
    "fast": 1.6,
}

# Allowed mouse-grid densities (NxN cells). 3 is the classic recursive grid.
GRID_DENSITIES = (3, 4)

# --- Browser -----------------------------------------------------------------
# Friendly browser name -> candidate executables to look for. The first one that
# resolves on PATH is used. Order within each list is "most common first".
# This lets the browser commands drive whatever browser the user picked in the
# OOBE, instead of being hardwired to one (previously qutebrowser).
BROWSERS = {
    "firefox": ["firefox", "firefox-esr"],
    "chrome": ["google-chrome", "google-chrome-stable"],
    "chromium": ["chromium", "chromium-browser"],
    "brave": ["brave-browser", "brave"],
    "edge": ["microsoft-edge", "microsoft-edge-stable"],
    "vivaldi": ["vivaldi", "vivaldi-stable"],
    "epiphany": ["epiphany"],
    "qutebrowser": ["qutebrowser"],
}

# Spoken aliases -> friendly browser key (for choosing one by voice in the OOBE).
BROWSER_ALIASES = {
    "firefox": "firefox",
    "fire fox": "firefox",
    "mozilla": "firefox",
    "chrome": "chrome",
    "google": "chrome",
    "google chrome": "chrome",
    "chromium": "chromium",
    "brave": "brave",
    "edge": "edge",
    "microsoft edge": "edge",
    "vivaldi": "vivaldi",
    "epiphany": "epiphany",
    "gnome web": "epiphany",
    "web": "epiphany",
    "qutebrowser": "qutebrowser",
    "qute": "qutebrowser",
}


def detect_browsers():
    """Return [(friendly_name, executable), ...] for browsers installed on PATH,
    in BROWSERS declaration order. Used to offer real choices during the OOBE."""
    found = []
    for name, candidates in BROWSERS.items():
        for binary in candidates:
            if shutil.which(binary):
                found.append((name, binary))
                break
    return found


def browser_command(cfg):
    """Resolve the configured browser to an executable on PATH.

    Honours the saved ``browser`` preference (a friendly name or an executable);
    falls back to the first browser actually installed, then to ``xdg-open``."""
    pref = (cfg or {}).get("browser", "") or ""
    pref = pref.strip().lower()
    if pref:
        # Stored as a friendly key?
        for binary in BROWSERS.get(pref, []):
            if shutil.which(binary):
                return binary
        # Stored as a bare executable name?
        if shutil.which(pref):
            return pref
    found = detect_browsers()
    if found:
        return found[0][1]
    return "xdg-open"


DEFAULTS = {
    "oobe_completed": False,
    "name": "Jarvis",  # assistant wake name
    "user_name": "",  # what the assistant calls the user (optional)
    "voice_gender": "feminine",
    "speech_rate": "normal",
    "friendly_messages": True,  # greetings + chatty confirmations
    # --- startup ---
    "start_on_boot": False,  # launch EchoBase automatically at login (XDG autostart)
    # --- motor-accessibility preferences ---
    "dwell_enabled": False,  # auto-click when the cursor rests still
    "dwell_seconds": 1.5,  # how long to rest before a dwell click fires
    "grid_density": 3,  # mouse-grid cells per side (see GRID_DENSITIES)
    "tracking_sensitivity": "normal",  # head-tracking speed (see TRACKING_SENSITIVITY)
    "tracking_camera": "auto",  # webcam index, or "auto" to detect
    "tracking_monitor_mode": "active",  # "active" (one screen, switchable) or "span"
    "tracking_smoothing": "medium",  # head-tracking stability: low | medium | high
    "tracking_snap": True,  # pull/hold the tracked cursor onto nearby buttons
    "tracking_debug": False,  # print head-tracking fps/timing stats to the console
    # --- browser ---
    "browser": "",  # preferred browser (friendly name); "" -> first installed
    # --- personal text snippets (spoken "type my …"); blank = unset ---
    "snippet_name": "",
    "snippet_email": "",
    "snippet_phone": "",
    "snippet_address": "",
    # --- audio interpretation ---
    "audio_preprocessing": True,  # clean/level the mic before STT (see audiofx)
    # --- speech recognition (profile picker, and slow-speech pacing) ---
    # recognition_profile (1-4) is the source of truth once the user picks one in
    # the OOBE. While it's unset (fresh first run), whisper_model/whisper_beam below
    # drive a fast base.en boot so the wizard can be answered by voice before any
    # heavier model is loaded. The two raw keys are also kept for back-compat with
    # configs saved before profiles existed.
    "recognition_profile": None,  # 1 Fast | 2 Balanced | 3 Accurate | 4 Maximum
    "whisper_model": "base.en",  # boot/legacy model: base.en (fast) | small.en | medium.en | distil-large-v3
    "whisper_beam": 1,  # decoding beam size; 1 = greedy (fast), higher = beam search
    "speech_pace": "normal",  # endpointing tolerance: normal | relaxed | slow
}

# Default fuzzy command-recovery thresholds (difflib similarity to the closest
# known phrase). At/above AUTO_CUTOFF a near-miss is run silently; between
# SUGGEST_CUTOFF and AUTO_CUTOFF the user is asked "did you mean …?"; below
# SUGGEST_CUTOFF we give up. These are the values profiles 1-2 use; tiers 3-4
# relax them (see the table). main.py imports these as its module defaults.
SUGGEST_CUTOFF = 0.6
AUTO_CUTOFF = 0.85

# Recognition profiles (1-4), fastest -> most accurate. Each expands into the
# whisper model + beam, an initial-prompt biasing level, fuzzy-recovery cutoff
# overrides, and an n-best count (>1 only for the dysarthria-robust top tier).
#   - bias: "command" reuses today's COMMAND_PROMPT; "phrases"/"phrases-strong"
#     additionally enumerate the known command vocabulary (built in main.py).
#   - auto_cutoff/ask_cutoff: difflib thresholds for _recover; tiers 3-4 are more
#     forgiving of slurred/imprecise speech.
#   - nbest: number of transcription hypotheses to reconcile against PHRASES.
# Profiles 1 and 2 reproduce the old "fast" and "accurate" behaviour exactly.
RECOGNITION_PROFILE_TABLE = {
    1: {
        "name": "Fast",
        "model": "base.en",
        "beam": 1,
        "bias": "command",
        "auto_cutoff": AUTO_CUTOFF,
        "ask_cutoff": SUGGEST_CUTOFF,
        "nbest": 1,
    },
    2: {
        "name": "Balanced",
        "model": "small.en",
        "beam": 5,
        "bias": "command",
        "auto_cutoff": AUTO_CUTOFF,
        "ask_cutoff": SUGGEST_CUTOFF,
        "nbest": 1,
    },
    3: {
        "name": "Accurate",
        "model": "medium.en",
        "beam": 8,
        "bias": "phrases",
        "auto_cutoff": 0.80,
        "ask_cutoff": 0.55,
        "nbest": 1,
    },
    4: {
        "name": "Maximum",
        "model": "distil-large-v3",
        "beam": 8,
        "bias": "phrases-strong",
        "auto_cutoff": 0.72,
        "ask_cutoff": 0.50,
        "nbest": 3,
    },
}

# Default profile recommended in the OOBE picker and written when the user accepts
# it. Kept out of DEFAULTS (above) so a not-yet-configured config still boots fast.
DEFAULT_RECOGNITION_PROFILE = 2

# Spoken speech-pace -> (silence_hang_seconds, max_utterance_seconds). A longer
# silence hang stops the recogniser cutting off slow or effortful speakers
# mid-sentence; a higher cap lets a long, halting utterance finish.
PACE_TIMING = {
    "normal": (0.6, 8.0),
    "relaxed": (1.0, 11.0),
    "slow": (1.4, 14.0),
}


# Resolved recognition settings. ``model``/``beam`` feed faster-whisper; ``bias``
# selects the initial-prompt strength (expanded against the command vocabulary in
# main.py); ``auto_cutoff``/``ask_cutoff`` override the fuzzy-recovery thresholds;
# ``nbest`` is how many transcription hypotheses to reconcile against PHRASES.
RecognitionSettings = namedtuple(
    "RecognitionSettings",
    ["model", "beam", "bias", "auto_cutoff", "ask_cutoff", "nbest"],
)


def recognition_settings(cfg):
    """Resolve *cfg* into the active :class:`RecognitionSettings`.

    A valid ``recognition_profile`` (1-4) is authoritative and expands from
    ``RECOGNITION_PROFILE_TABLE``. Otherwise — a config saved before profiles
    existed, or a fresh pre-choice boot — we fall back to the raw
    ``whisper_model``/``whisper_beam`` keys with today's command biasing and
    default cutoffs, so legacy behaviour is reproduced exactly."""
    cfg = cfg or {}
    profile = cfg.get("recognition_profile")
    row = RECOGNITION_PROFILE_TABLE.get(profile) if profile is not None else None
    if row is not None:
        return RecognitionSettings(
            model=row["model"],
            beam=max(1, int(row["beam"])),
            bias=row["bias"],
            auto_cutoff=row["auto_cutoff"],
            ask_cutoff=row["ask_cutoff"],
            nbest=max(1, int(row["nbest"])),
        )

    model = cfg.get("whisper_model") or DEFAULTS["whisper_model"]
    try:
        beam = int(cfg.get("whisper_beam", DEFAULTS["whisper_beam"]))
    except (TypeError, ValueError):
        beam = DEFAULTS["whisper_beam"]
    return RecognitionSettings(
        model=model,
        beam=max(1, beam),
        bias="command",
        auto_cutoff=AUTO_CUTOFF,
        ask_cutoff=SUGGEST_CUTOFF,
        nbest=1,
    )


def profile_for_config(cfg):
    """Return the recognition profile number (1-4) that best describes *cfg*.

    Uses an explicit ``recognition_profile`` when present, else reverse-maps the
    saved ``whisper_model`` to the nearest tier. Display/migration only — it never
    changes recognition behaviour."""
    cfg = cfg or {}
    profile = cfg.get("recognition_profile")
    if profile in RECOGNITION_PROFILE_TABLE:
        return profile
    model = (cfg.get("whisper_model") or DEFAULTS["whisper_model"]).lower()
    if "distil" in model or "large" in model:
        return 4
    if "medium" in model:
        return 3
    if "small" in model:
        return 2
    return 1


def pace_timing(cfg):
    """Return (silence_hang, max_seconds) endpointing for the saved speech pace."""
    pace = (cfg or {}).get("speech_pace", "normal")
    return PACE_TIMING.get(pace, PACE_TIMING["normal"])


def tracking_multiplier(name):
    """Head-tracking gain multiplier for a spoken sensitivity name."""
    return TRACKING_SENSITIVITY.get(name, 1.0)


def grid_density(value):
    """Clamp an arbitrary grid-density value to a supported NxN size."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 3
    return n if n in GRID_DENSITIES else 3


def debug_enabled():
    """True when developer affordances (spoken/flag OOBE reset) are active.

    On by default so setup can be re-run at will during development. Set
    ``ECHOBASE_DEBUG=0`` to lock it down for an end-user build.
    """
    return os.environ.get("ECHOBASE_DEBUG", "1").lower() not in ("0", "false", "no", "")


def load():
    """Return the saved config merged over defaults (never raises)."""
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        pass
    return cfg


def save(cfg):
    """Persist config atomically to ``CONFIG_FILE``."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    tmp.replace(CONFIG_FILE)


def reset():
    """Delete the saved config so the OOBE runs again. Returns True if a file
    was removed. Debug helper — see :func:`debug_enabled`."""
    try:
        CONFIG_FILE.unlink()
        return True
    except FileNotFoundError:
        return False


def autostart_command():
    """Best-effort command line that relaunches EchoBase at login.

    Prefers the installed ``EchoBase`` console script; in a dev checkout falls
    back to the launcher script shipped at the repo root; finally re-runs the
    module with the current interpreter so autostart still works from source.
    """
    exe = shutil.which("EchoBase")
    if exe:
        return exe
    script = Path(__file__).resolve().parents[2] / "echobase.sh"
    if script.exists():
        return str(script)
    return f"{sys.executable} -m EchoBase.core.main"


def _autostart_desktop_entry():
    """Render the XDG autostart .desktop file contents."""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=EchoBase\n"
        "Comment=Voice control for Linux\n"
        f"Exec={autostart_command()}\n"
        "Icon=audio-input-microphone\n"
        "Terminal=false\n"
        "Categories=Utility;Accessibility;\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def set_autostart(enabled):
    """Enable or disable launching EchoBase at login. Returns True on success.

    Enabling writes ``~/.config/autostart/echobase.desktop``; disabling removes
    it. Never raises — a filesystem error just returns False so the caller can
    tell the user it couldn't be set up.
    """
    try:
        if enabled:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FILE.write_text(_autostart_desktop_entry())
        else:
            AUTOSTART_FILE.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def autostart_enabled():
    """True when the XDG autostart entry is present."""
    return AUTOSTART_FILE.exists()


def length_scale(rate):
    """Piper --length_scale for a spoken speech-rate name."""
    return RATE_LENGTH_SCALE.get(rate, 1.0)


def voice_name(gender):
    return VOICES.get(gender, VOICES["feminine"])


def voice_model_path(gender):
    """Local .onnx path for a gender (whether or not it exists yet)."""
    return PIPER_DIR / f"{voice_name(gender)}.onnx"


def _download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def ensure_voice(gender, log=None):
    """Return a usable .onnx path for *gender*, downloading the model if missing.

    Falls back to the feminine default if the requested voice cannot be
    obtained, and finally to any model already present. ``log`` is an optional
    ``log(message)`` callback for progress.
    """

    def _say(msg):
        if log:
            log(msg)

    for candidate in (gender, "feminine"):
        name = voice_name(candidate)
        model = PIPER_DIR / f"{name}.onnx"
        conf = PIPER_DIR / f"{name}.onnx.json"
        if model.exists() and conf.exists():
            return str(model)

        url = VOICE_URLS.get(name)
        if not url:
            continue
        try:
            _say(f"downloading {candidate} voice ({name})...")
            if not model.exists():
                _download(f"{url}.onnx", model)
            if not conf.exists():
                _download(f"{url}.onnx.json", conf)
            if model.exists() and conf.exists():
                _say(f"{candidate} voice ready")
                return str(model)
        except Exception as e:  # network/disk — degrade gracefully
            _say(f"voice download failed: {e}")

    # Last resort: any onnx already on disk.
    existing = sorted(PIPER_DIR.glob("*.onnx"))
    return str(existing[0]) if existing else str(voice_model_path("feminine"))
