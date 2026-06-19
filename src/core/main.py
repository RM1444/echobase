#!/usr/bin/env python3
import difflib
import importlib
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import openwakeword
import pyaudio
from faster_whisper import WhisperModel
from openwakeword.model import Model as WakeWordModel
from openwakeword.vad import VAD

from . import atspi, audiofx, config, oobe, phrases, ui

WHISPER_MODEL = "base.en"

# Plugins that take over the microphone with their own blocking loop ("modes").
# While one is active the others must not be entered (you can't be in two at
# once), and one-off global commands routed mid-mode skip them — see
# ``run_global_command``. Keyed by each plugin's ``NAME``.
BLOCKING_MODES = {"headtrack", "mousegrid", "browser", "dictation"}

# Fuzzy command recovery thresholds (similarity to the closest known phrase).
# At/above AUTO_CUTOFF we silently run the match (no prompt) — this is what makes
# slurred/imprecise speech usable. Between SUGGEST_CUTOFF and AUTO_CUTOFF we ask
# "did you mean …?". Below SUGGEST_CUTOFF we give up. These are the defaults
# (profiles 1-2); a chosen recognition profile can relax them (see _recover and
# config.recognition_settings). Canonical values live in config so both agree.
SUGGEST_CUTOFF = config.SUGGEST_CUTOFF
AUTO_CUTOFF = config.AUTO_CUTOFF

# Whisper models large enough that loading (and possibly downloading) them is
# worth a spoken heads-up, so a tier-3/4 pick doesn't feel like a hang.
_HEAVY_WHISPER_MODELS = {"medium.en", "distil-large-v3", "large-v3"}

# Temperatures sampled (in order) when a profile asks for n-best hypotheses; the
# first is the deterministic best, the rest add decoding diversity.
_NBEST_TEMPERATURES = (0.0, 0.2, 0.4)

# Leading/trailing filler stripped before matching, so politeness or hesitation
# ("please open files", "open files please") doesn't defeat exact matches.
_FILLER_PREFIXES = (
    "please ",
    "can you ",
    "could you ",
    "would you ",
    "can you please ",
    "i want to ",
    "i would like to ",
    "i'd like to ",
    "um ",
    "uh ",
)
_FILLER_SUFFIXES = (" please", " thanks", " thank you")
WAKE_COOLDOWN = 3.0
LISTEN_WINDOW = 3
RECORD_SECONDS = 4

# Wake-word detection (openwakeword). A frame is 80 ms of 16 kHz audio, the
# chunk size the pretrained models expect.
WAKE_FRAME = 1280
WAKE_THRESHOLD = 0.5  # model score above which the wake phrase counts as heard

# Pretrained openwakeword models, keyed by the spoken assistant name. Names not
# listed here have no acoustic model, so detection falls back to Whisper (see
# _wake_detected) — that keeps arbitrary custom wake names working.
WAKE_MODELS = {
    "jarvis": "hey_jarvis_v0.1.onnx",
    "alexa": "alexa_v0.1.onnx",
    "mycroft": "hey_mycroft_v0.1.onnx",
    "marvin": "hey_marvin_v0.1.onnx",
}

# Voice-activity detection (Silero, bundled with openwakeword) for endpointing
# the command utterance instead of recording a fixed window.
VAD_FRAME = 1280
VAD_THRESHOLD = 0.5  # speech probability above which a frame is "speech"
VAD_SILENCE_HANG = 0.6  # seconds of trailing silence that ends the utterance
VAD_MAX_SECONDS = 8.0  # hard cap on a single utterance

# Short chime acknowledging the wake word before we start listening.
WAKE_SOUND = "/usr/share/sounds/freedesktop/stereo/message.oga"

COMMAND_PROMPT = (
    "numbers, scroll, click, open, close, back, forward, volume, brightness, stop"
)

# Spoken openers that should be answered with a friendly greeting rather than
# routed to a plugin (predecessor "voice UX").
GREET_WORDS = {
    "hello",
    "hi",
    "hey",
    "howdy",
    "greetings",
    "yo",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
    "hey there",
    "hello there",
}

# Substrings that mark a reply as negative/neutral, so we don't glue a cheerful
# lead-in like "Certainly!" in front of an error or a farewell.
_NEG_MARKERS = (
    "not ",
    " no ",
    "no.",
    "n't",
    "install",
    "nothing",
    "fail",
    " found",
    "empty",
    "goodbye",
    "bye",
    "sorry",
    "unable",
    "error",
    "no file",
    "no text",
)


def _is_reset_phrase(cmd):
    """True for the spoken "factory reset" command (debug affordance).

    The trigger is anchored on the word "factory", which appears in no other
    command, so it is hard to mishear as something else and won't be set off by
    normal use. A few close mishearings of "reset" are tolerated.
    """
    if "factory" not in cmd:
        return False
    return any(
        w in cmd for w in ("reset", "rest", "resit", "recent", "restart", "reboot")
    )


# Number words for "do that <N> times".
_NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twice": 2,
    "thrice": 3,
    "couple": 2,
    "few": 3,
    "to": 2,
    "too": 2,
    "for": 4,
    "ate": 8,
}

# Bare "repeat" requests (exactly one more time).
_REPEAT_ONCE = {
    "repeat that",
    "do that again",
    "do it again",
    "same again",
    "once more",
    "one more time",
    "repeat",
    "repeat command",
}


def _parse_times(cmd):
    """Pull a repeat count out of a phrase like 'do that three times'."""
    m = re.search(r"\b(\d{1,2})\b", cmd)
    if m:
        return max(1, min(20, int(m.group(1))))
    for word, n in _NUM_WORDS.items():
        if re.search(rf"\b{word}\b", cmd):
            return max(1, min(20, n))
    return 1


def _repeat_spec(cmd):
    """Return how many times to repeat the last command, or None if not a
    repeat request. 'repeat that' -> 1; 'do that 3 times' -> 3; 'do that twice'
    -> 2. Bare 'again' is intentionally NOT a repeat (the grid uses it)."""
    if cmd in _REPEAT_ONCE:
        return 1
    repeatish = any(k in cmd for k in ("repeat that", "repeat the", "do that", "do it"))
    has_count = "times" in cmd or "twice" in cmd or "thrice" in cmd
    if repeatish and has_count:
        return _parse_times(cmd)
    return None


# Macro record/play control phrases.
_MACRO_START = {"start recording", "record macro", "start macro", "record a macro"}
_MACRO_STOP = {
    "stop recording",
    "stop macro",
    "save macro",
    "end macro",
    "end recording",
}
_MACRO_PLAY = {
    "play macro",
    "run macro",
    "replay macro",
    "play my macro",
    "run my macro",
}


class EchoBase:
    def __init__(self, name=None, reset_oobe=False):
        # Persisted user config (assistant name, voice, personalisation).
        self.config = config.load()
        self._name_override = name  # explicit --name wins over saved config

        # A reset wipes the saved config and starts the wizard from clean
        # defaults, so closing the app before setup finishes leaves nothing stale.
        if reset_oobe:
            config.reset()
            self.config = dict(config.DEFAULTS)
        self.need_oobe = reset_oobe or not self.config.get("oobe_completed")

        self.plugins = []
        self.known_phrases = []  # canonical command phrases for "did you mean?"
        # Name of the blocking mode currently running its own listen loop
        # (e.g. "headtrack"), or None. Set/cleared by the mode plugins.
        self.active_mode = None
        self.whisper = None
        self.wakeword = None  # openwakeword Model, or None -> Whisper fallback
        self._vad = None  # lazily created Silero VAD for command endpointing
        self.audio = None
        self.stream = None
        self.last_wake_time = 0

        # Friendly-message bookkeeping (see speak()/route_command()).
        self._in_route = False
        self._lead_used = False
        self._route_spoke = False

        # Repeat / macro state.
        self.last_command = None  # last successfully handled command
        self.recording = None  # list while recording a macro, else None
        self.macro = []  # last saved macro (command strings)

        self._apply_config(self.config, ensure=False)

    # --- Config / voice ---------------------------------------------------

    def _apply_config(self, cfg, ensure=True):
        """Adopt *cfg* as the live settings. With ``ensure`` the chosen voice
        model is downloaded if missing (skip during __init__ to avoid network)."""
        self.config = cfg
        self.name = self._name_override or cfg.get("name") or "Jarvis"
        self.user_name = cfg.get("user_name") or ""
        self.friendly_messages = bool(cfg.get("friendly_messages", True))
        self.voice_gender = cfg.get("voice_gender", "feminine")
        self.speech_rate = cfg.get("speech_rate", "normal")
        self.length_scale = config.length_scale(self.speech_rate)
        # Endpointing tolerance for the speaker's pace (slow speech needs a
        # longer pause before we stop listening, and a higher utterance cap).
        self.vad_silence_hang, self.vad_max_seconds = config.pace_timing(cfg)
        if ensure:
            self.apply_voice(self.voice_gender, self.speech_rate)
        else:
            self.voice_model = str(config.voice_model_path(self.voice_gender))
        self.wake_phrase = f"hey {self.name.lower()}"

    def apply_voice(self, gender, rate):
        """Switch the speaking voice/speed now, fetching the model if needed."""
        self.voice_gender = gender
        self.speech_rate = rate
        self.length_scale = config.length_scale(rate)
        self.voice_model = config.ensure_voice(
            gender, log=lambda m: ui.log("voice", m, ui.DIM)
        )

    def host_run(self, cmd, background=False):
        if background:
            return subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        return subprocess.run(cmd, capture_output=True, text=True)

    def _decorate(self, text, allow_lead):
        """Prefix a varied, friendly lead-in onto the first positive
        confirmation spoken while handling a command (successor "voice UX")."""
        if not allow_lead or not self.friendly_messages:
            return text
        if not self._in_route or self._lead_used:
            return text
        if not text or len(text) > 100:
            return text
        low = text.lower()
        if any(m in low for m in _NEG_MARKERS):
            return text
        self._lead_used = True
        return f"{phrases.lead_in()} {text}"

    def speak(self, text, allow_lead=True):
        text = self._decorate(text, allow_lead)
        ui.log("reply", text, ui.MAGENTA)
        self._route_spoke = True

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_file = f.name

        subprocess.Popen(
            [
                "piper",
                "--model",
                self.voice_model,
                "--length_scale",
                str(self.length_scale),
                "--output_file",
                output_file,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).communicate(input=text.encode())

        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", output_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.remove(output_file)

    def load_plugins(self):
        plugins_dir = Path(__file__).parent.parent / "plugins"
        if not plugins_dir.exists():
            ui.log("error", "No plugins directory found", ui.RED)
            return

        sys.path.insert(0, str(plugins_dir.parent))

        for file in sorted(plugins_dir.glob("*.py")):
            if file.name.startswith("_"):
                continue

            module_name = f"plugins.{file.stem}"
            try:
                module = importlib.import_module(module_name)

                if hasattr(module, "NAME") and hasattr(module, "handle"):
                    if hasattr(module, "setup"):
                        module.setup(self)

                    self.plugins.append(module)
                    ui.log("ok", module.NAME, ui.GREEN)
                else:
                    ui.log("skip", f"{file.name} (no NAME or handle)", ui.YELLOW)
            except Exception as e:
                ui.log("fail", f"{file.name} · {e}", ui.RED)

        self._collect_phrases()

    def _collect_phrases(self):
        """Gather every plugin's canonical spoken phrases into one list, used by
        the "did you mean …?" near-miss recovery. A plugin opts in with a
        module-level ``PHRASES`` list; otherwise we fall back to the leading
        phrase of each ``COMMANDS`` help line (text before the first " - ")."""
        seen = set()
        phrases_out = []
        for plugin in self.plugins:
            items = getattr(plugin, "PHRASES", None)
            if not isinstance(items, (list, tuple)):
                items = []
                commands = getattr(plugin, "COMMANDS", None)
                if isinstance(commands, (list, tuple)):
                    for line in commands:
                        if not isinstance(line, str):
                            continue
                        head = line.split(" - ")[0].split("/")[0].strip().lower()
                        # Skip placeholder-only help like "[number] - ...".
                        if head and "[" not in head:
                            items.append(head)
            for phrase in items:
                if not isinstance(phrase, str):
                    continue
                p = phrase.lower().strip()
                if p and p not in seen:
                    seen.add(p)
                    phrases_out.append(p)
        self.known_phrases = phrases_out

    def type_text(self, text):
        """Type *text* into the focused editable field via AT-SPI. Shared by
        dictation, the browser address bar, and personal text snippets."""
        return atspi.insert_text(text)

    def listen_yes_no(self, prompt=None, default=None):
        """Speak *prompt* (if given), capture one spoken reply, and return True
        for yes, False for no, or *default* when the answer is unclear/silent."""
        if prompt:
            self.speak(prompt, allow_lead=False)
        self.flush_stream()
        first = self.wait_for_speech(timeout=6)
        if not first:
            return default
        audio = first + self.record_until_silence()
        said = (self.transcribe(audio, prompt="yes no") or "").lower().strip(".,!? ")
        if not said:
            return default
        ui.log("heard", said, ui.YELLOW)
        words = set(said.split())
        if words & phrases.NO_WORDS:
            return False
        if words & phrases.YES_WORDS:
            return True
        return default

    def get_all_commands(self):
        commands = []
        for plugin in self.plugins:
            if hasattr(plugin, "COMMANDS"):
                commands.extend(plugin.COMMANDS)
        return commands

    def greet(self):
        """Speak a friendly greeting (no lead-in stacking)."""
        self.speak(phrases.greeting(self.user_name), allow_lead=False)

    def _maybe_reset(self, cmd):
        """Handle the spoken "factory reset" command. Returns True if it ran.

        The saved config is deleted *immediately*, before the wizard runs, so if
        the app is closed mid-setup nothing stale is left on disk — the next
        launch starts fresh from the OOBE.
        """
        if not config.debug_enabled() or not _is_reset_phrase(cmd):
            return False
        ui.log("debug", "factory reset — clearing saved configuration", ui.YELLOW)
        config.reset()  # wipe the persisted config now
        self.need_oobe = True
        self.speak(
            "Okay, restoring factory settings. Let's set things up again.",
            allow_lead=False,
        )
        self._name_override = None  # let the wizard pick the name afresh
        self._apply_config(oobe.run(self, dict(config.DEFAULTS)))
        self.need_oobe = False  # setup completed and saved
        ui.log("ready", f'listening for "Hey {self.name}"', ui.CYAN)
        return True

    def route_command(self, cmd):
        cmd = self.route_clean(cmd)

        if not cmd:
            return True

        # Repeat the previous command ("repeat that", "do that 3 times").
        spec = _repeat_spec(cmd)
        if spec is not None:
            return self._run_repeat(spec)

        # Macro record/play control.
        macro_result = self._handle_macro_control(cmd)
        if macro_result is not None:
            return macro_result

        return self._dispatch(cmd)

    def _dispatch(self, cmd, skip_blocking=False, announce_unknown=True, recover=True):
        """Route a single command to the plugins (the real work).

        ``skip_blocking`` skips the mode plugins (head tracking, grid, browser,
        dictation) so a command issued from *inside* one of those modes can run a
        global action without trying to enter another mode. ``announce_unknown``
        controls whether an unmatched command speaks the "didn't understand"
        reply (off when routing mid-mode, so leftovers fail quietly). ``recover``
        enables the fuzzy near-miss recovery; it is turned off when re-dispatching
        a recovered phrase so recovery can't recurse."""
        cmd = self._normalize_command(cmd)

        # Debug: spoken setup reset.
        if self._maybe_reset(cmd):
            return True

        # Predecessor greeting: "hey <name>, hello" -> a warm reply.
        if self.friendly_messages and cmd in GREET_WORDS:
            self.greet()
            return True

        self._in_route = True
        self._lead_used = False
        self._route_spoke = False
        handled = None
        try:
            for plugin in self.plugins:
                if skip_blocking and getattr(plugin, "NAME", "") in BLOCKING_MODES:
                    continue
                try:
                    result = plugin.handle(cmd, self)
                    if result is True:
                        handled = True
                        break
                    if result is False:
                        handled = False
                        break
                except Exception as e:
                    ui.log("error", f"{plugin.NAME} · {e}", ui.RED)
        finally:
            self._in_route = False

        if handled is True:
            # Remember it for "repeat that" and for an in-progress macro.
            self.last_command = cmd
            if self.recording is not None:
                self.recording.append(cmd)
            # The action ran but said nothing — add a friendly confirmation.
            if self.friendly_messages and not self._route_spoke:
                self.speak(phrases.done(), allow_lead=False)
            return True
        if handled is False:
            return False

        # Nothing matched. Try fuzzy recovery (auto-run a very close match, or
        # ask "did you mean …?" on a medium one).
        if recover:
            recovered = self._recover(cmd, skip_blocking, announce_unknown)
            if recovered is not None:
                return recovered

        if not announce_unknown:
            # Routing mid-mode: leftovers fail quietly, no suggestion prompt.
            return None

        self.speak(phrases.not_understood(), allow_lead=False)
        return True

    @staticmethod
    def _normalize_command(cmd):
        """Strip leading/trailing filler and collapse whitespace, so politeness
        or hesitation doesn't defeat the (often exact) command matchers."""
        c = " ".join((cmd or "").split())
        changed = True
        while changed:
            changed = False
            for pre in _FILLER_PREFIXES:
                if c.startswith(pre) and len(c) > len(pre):
                    c = c[len(pre) :]
                    changed = True
            for suf in _FILLER_SUFFIXES:
                if c.endswith(suf) and len(c) > len(suf):
                    c = c[: -len(suf)]
                    changed = True
        return c.strip()

    def _closest_phrase(self, cmd):
        """Return (phrase, score) for the known command phrase most similar to
        *cmd* (``difflib`` ratio), or (None, 0.0) when nothing is known."""
        best, best_score = None, 0.0
        matcher = difflib.SequenceMatcher(a=cmd)
        for phrase in self.known_phrases:
            matcher.set_seq2(phrase)
            score = matcher.ratio()
            if score > best_score:
                best, best_score = phrase, score
        return best, best_score

    def _recover(self, cmd, skip_blocking, announce_unknown):
        """Fuzzy near-miss recovery. Returns the dispatch result when it handled
        the command, or None to let the caller fall through to "not understood".

        - score ≥ auto cutoff: silently re-dispatch the matched phrase.
        - ask cutoff ≤ score < auto cutoff and announce_unknown: ask the user.
        - otherwise: None (no recovery).

        Cutoffs come from the active recognition profile, so the more forgiving
        tiers (Accurate/Maximum) recover slurred speech the defaults would drop."""
        if not self.known_phrases:
            return None
        settings = config.recognition_settings(self.config)
        auto_cutoff, ask_cutoff = settings.auto_cutoff, settings.ask_cutoff
        guess, score = self._closest_phrase(cmd)
        if not guess or guess == cmd or score < ask_cutoff:
            return None

        if score >= auto_cutoff:
            ui.log("autocorrect", f"{cmd} -> {guess} ({score:.2f})", ui.GREEN)
            return self._dispatch(
                guess,
                skip_blocking=skip_blocking,
                announce_unknown=announce_unknown,
                recover=False,
            )

        # Medium confidence: only ask when we're allowed to speak up (not mid-mode).
        if not announce_unknown:
            return None
        if self.listen_yes_no(f"Did you mean, {guess}?", default=False):
            ui.log("suggest", f"{cmd} -> {guess}", ui.GREEN)
            return self._dispatch(guess, recover=False)
        self.speak(phrases.not_understood(), allow_lead=False)
        return True

    def run_global_command(self, cmd):
        """Run a one-off global command from inside an active mode's listen loop.

        Skips the blocking-mode plugins so it can't nest a second mode, and stays
        quiet on a miss — but still auto-runs a very close fuzzy match (no prompt),
        so slurred mid-mode commands still work. Returns the dispatch result."""
        cmd = self.route_clean(cmd)
        if not cmd:
            return None
        return self._dispatch(cmd, skip_blocking=True, announce_unknown=False)

    def _run_repeat(self, times):
        """Re-run the last successfully handled command *times* times."""
        if not self.last_command:
            self.speak("There's nothing to repeat yet.", allow_lead=False)
            return True
        cmd = self.last_command
        ui.log("repeat", f"{cmd} ×{times}", ui.YELLOW)
        for _ in range(times):
            if self._dispatch(cmd) is False:
                return False
        return True

    def _handle_macro_control(self, cmd):
        """Handle macro record/save/play phrases. Returns True/False when it
        owns the command, or None to let normal routing continue."""
        if cmd in _MACRO_START:
            self.recording = []
            self.speak(
                "Recording. Say the commands you want, then say stop recording.",
                allow_lead=False,
            )
            return True
        if cmd in _MACRO_STOP:
            if self.recording is None:
                self.speak("I wasn't recording anything.", allow_lead=False)
                return True
            self.macro = list(self.recording)
            self.recording = None
            n = len(self.macro)
            self.speak(
                f"Saved a macro with {n} step{'s' if n != 1 else ''}."
                if n
                else "Nothing was recorded.",
                allow_lead=False,
            )
            return True
        if cmd in _MACRO_PLAY:
            if not self.macro:
                self.speak("I don't have a macro saved yet.", allow_lead=False)
                return True
            ui.log("macro", f"playing {len(self.macro)} steps", ui.YELLOW)
            for step in self.macro:
                if self._dispatch(step) is False:
                    return False
            return True
        return None

    def flush_stream(self):
        try:
            self.stream.read(
                self.stream.get_read_available(),
                exception_on_overflow=False,
            )
        except:
            pass

    # --- Wake word + voice-activity detection -----------------------------

    def _load_wake_model(self):
        """Load the pretrained openwakeword model for the configured name, or
        return None when there is no model for it (custom names fall back to
        Whisper-based wake detection)."""
        fname = WAKE_MODELS.get(self.name.lower())
        if not fname:
            return None
        try:
            path = os.path.join(
                os.path.dirname(openwakeword.__file__), "resources", "models", fname
            )
        except (TypeError, AttributeError):
            # openwakeword stubbed out (e.g. under test) — pass the bare name and
            # let it resolve.
            path = fname
        return WakeWordModel(wakeword_model_paths=[path])

    def _wake_detected(self, pcm, buffer):
        """True when the wake phrase is heard in the latest audio.

        With a pretrained model this is a cheap per-frame acoustic check. Without
        one (custom name) we fall back to transcribing the rolling ``buffer`` and
        substring-matching the wake phrase, as the predecessor did."""
        if self.wakeword is not None:
            samples = np.frombuffer(pcm, dtype=np.int16)
            scores = self.wakeword.predict(samples)
            best = max(scores.values()) if scores else 0.0
            return best >= WAKE_THRESHOLD

        # Whisper fallback for names without an acoustic model.
        frames_needed = int(LISTEN_WINDOW * 16000 / WAKE_FRAME)
        if len(buffer) < frames_needed:
            return False
        text = self.transcribe(b"".join(buffer), prompt=f"Hey {self.name}")
        buffer.clear()
        return self.wake_phrase in text.lower().strip(".,!? ")

    def _get_vad(self):
        if self._vad is None:
            self._vad = VAD()
        return self._vad

    def _is_speech(self, vad, chunk):
        samples = np.frombuffer(chunk, dtype=np.int16)
        try:
            return vad.predict(samples) >= VAD_THRESHOLD
        except Exception:
            # If the VAD model hiccups, fall back to a simple energy gate so we
            # never wedge the loop.
            rms = np.sqrt(np.mean((samples.astype(np.float32) / 32768.0) ** 2))
            return rms > 0.01

    def wait_for_speech(self, timeout=5):
        """Block until speech starts, up to ``timeout`` seconds. Returns the
        first speech frame's audio, or None if nothing was said."""
        vad = self._get_vad()
        vad.reset_states()
        start = time.time()
        while time.time() - start < timeout:
            chunk = self.stream.read(VAD_FRAME, exception_on_overflow=False)
            if self._is_speech(vad, chunk):
                return chunk
        return None

    def record_until_silence(self):
        """Record from now until the speaker pauses (VAD endpointing), capturing
        exactly the utterance instead of a fixed window. The trailing-silence
        threshold and the hard cap come from the speaker's configured pace (see
        ``config.pace_timing``), so slow/effortful speech isn't cut off early."""
        vad = self._get_vad()
        frames = []
        silence = 0.0
        silence_hang = getattr(self, "vad_silence_hang", VAD_SILENCE_HANG)
        max_seconds = getattr(self, "vad_max_seconds", VAD_MAX_SECONDS)
        start = time.time()
        while time.time() - start < max_seconds:
            chunk = self.stream.read(VAD_FRAME, exception_on_overflow=False)
            frames.append(chunk)
            if self._is_speech(vad, chunk):
                silence = 0.0
            else:
                silence += VAD_FRAME / 16000.0
                if silence >= silence_hang:
                    break
        return b"".join(frames)

    def record(self, seconds=RECORD_SECONDS):
        frames = []
        for _ in range(int(seconds * 16000 / 1600)):
            frames.append(self.stream.read(1600, exception_on_overflow=False))
        return b"".join(frames)

    def _command_prompt(self):
        """Default Whisper ``initial_prompt`` for the active recognition profile.

        ``command`` biasing reuses today's COMMAND_PROMPT (so profiles 1-2 behave
        exactly as before); ``phrases``/``phrases-strong`` additionally enumerate
        the known command vocabulary so the decoder leans toward things the user
        can actually say — markedly better for slurred or effortful speech."""
        settings = config.recognition_settings(self.config)
        vocab = getattr(self, "known_phrases", None) or []
        if settings.bias == "command" or not vocab:
            return COMMAND_PROMPT
        joined = ", ".join(vocab)
        if settings.bias == "phrases-strong":
            # Lead with the full spoken vocabulary for the strongest biasing.
            return f"{joined}. {COMMAND_PROMPT}"
        return f"{COMMAND_PROMPT}, {joined}"

    def _audio_to_wav(self, audio_data):
        """Preprocess (optional) and write mono 16 kHz PCM to a temp .wav, return
        its path. The caller owns the file and must remove it."""
        # Clean + level the mic signal so cheap microphones reach the quality
        # Whisper expects (see audiofx). Toggleable for A/B measurement.
        if self.config.get("audio_preprocessing", True):
            audio_data = audiofx.preprocess(audio_data)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wf = wave.open(f.name, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_data)
            wf.close()
            return f.name

    def _whisper_text(self, path, prompt, beam, temperature=None):
        """Run one faster-whisper pass over *path* and join the segments. A
        ``temperature`` is only passed for n-best re-decoding; the normal path
        omits it so the library's default fallback ladder is unchanged."""
        kwargs = {"initial_prompt": prompt, "beam_size": beam, "vad_filter": True}
        if temperature is not None:
            kwargs["temperature"] = temperature
        segments, _ = self.whisper.transcribe(path, **kwargs)
        return " ".join(s.text for s in segments).strip()

    def transcribe(self, audio_data, prompt=None):
        settings = config.recognition_settings(self.config)
        use_prompt = prompt if prompt else self._command_prompt()
        path = self._audio_to_wav(audio_data)
        try:
            return self._whisper_text(path, use_prompt, settings.beam)
        finally:
            os.remove(path)

    def transcribe_nbest(self, audio_data, prompt=None, n=3):
        """Transcribe *audio_data* a few times with increasing temperature and
        return the distinct hypotheses (most-likely first). faster-whisper only
        exposes one transcript per call, so diversity comes from re-decoding —
        used by the Maximum profile to reconcile candidates against PHRASES."""
        settings = config.recognition_settings(self.config)
        use_prompt = prompt if prompt else self._command_prompt()
        path = self._audio_to_wav(audio_data)
        try:
            out = []
            for temp in _NBEST_TEMPERATURES[: max(1, n)]:
                text = self._whisper_text(path, use_prompt, settings.beam, temp)
                if text and text not in out:
                    out.append(text)
            return out
        finally:
            os.remove(path)

    def _pick_best_candidate(self, candidates):
        """From n-best hypotheses, return the one whose closest known command
        phrase scores highest, so a clearer runner-up decoding can win when it
        lands nearer a real command. Ties keep the primary (first) hypothesis."""
        best_text = candidates[0] if candidates else ""
        best_score = -1.0
        for text in candidates:
            _guess, score = self._closest_phrase(text.lower().strip(".,!? "))
            if score > best_score:
                best_text, best_score = text, score
        return best_text

    def _ensure_whisper_model(self):
        """Load (or reload) the Whisper model for the active recognition profile.
        The first use of a not-yet-downloaded model fetches it from the hub; the
        heavier tiers get a spoken heads-up so the load doesn't feel like a hang."""
        model = config.recognition_settings(self.config).model
        if getattr(self, "_whisper_model_name", None) == model and self.whisper:
            return
        if model in _HEAVY_WHISPER_MODELS:
            self.speak("This may take a moment while I load the most accurate model.")
        ui.step("speech-to-text", f"loading whisper ({model})...")
        self.whisper = WhisperModel(model, compute_type="int8")
        self._whisper_model_name = model

    def run(self):
        ui.banner()
        ui.section("startup")
        self._ensure_whisper_model()
        ui.step("wake-word", f'openwakeword · "Hey {self.name}"')
        self.wakeword = self._load_wake_model()
        ui.step("text-to-speech", f"piper · {self.voice_gender} voice")

        # Microphone up early so the OOBE can be answered by voice.
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=WAKE_FRAME,
        )

        try:
            # Make sure the configured voice is actually downloaded.
            self.apply_voice(self.voice_gender, self.speech_rate)

            # First run (or debug reset): voice-controlled setup wizard.
            if self.need_oobe:
                self._apply_config(oobe.run(self, self.config))
                # If the user chose higher accuracy in setup, load that model now
                # so the choice applies this session (not just the next launch).
                self._ensure_whisper_model()

            ui.section("plugins")
            self.load_plugins()
            if not self.plugins:
                ui.log("error", "No plugins loaded. Exiting.", ui.RED)
                return

            ui.ready_hint(self.name)
            ui.log("ready", f'listening for "Hey {self.name}"', ui.CYAN)

            # Rolling window of recent frames — feeds the Whisper wake fallback
            # and is bounded so it can't grow without limit.
            audio_buffer = []

            while True:
                pcm = self.stream.read(WAKE_FRAME, exception_on_overflow=False)
                audio_buffer.append(pcm)
                if len(audio_buffer) > 50:
                    audio_buffer.pop(0)

                if not self._wake_detected(pcm, audio_buffer):
                    continue

                now = time.time()
                if now - self.last_wake_time < WAKE_COOLDOWN:
                    continue
                self.last_wake_time = now

                ui.log("wake", f'"Hey {self.name}"', ui.GREEN)

                # Acknowledge with a chime, then capture the command by voice
                # activity rather than a fixed window.
                self.flush_stream()
                subprocess.run(["paplay", WAKE_SOUND], capture_output=True)
                self.flush_stream()

                speech = self.wait_for_speech(timeout=5)
                if speech is None:
                    self.speak("I didn't hear anything.")
                    continue

                audio = speech + self.record_until_silence()
                settings = config.recognition_settings(self.config)
                if settings.nbest > 1:
                    candidates = self.transcribe_nbest(audio, n=settings.nbest)
                    if len(candidates) > 1:
                        ui.log("n-best", " | ".join(candidates), ui.DIM)
                    text = self._pick_best_candidate(candidates)
                else:
                    text = self.transcribe(audio)
                if text:
                    ui.log("heard", text, ui.YELLOW)
                    if not self.route_command(text.lower().strip(".,!? ")):
                        break

                self.flush_stream()
                ui.log("ready", f'listening for "Hey {self.name}"', ui.CYAN)

        except KeyboardInterrupt:
            print()
            ui.log("bye", "shutting down", ui.DIM)
        finally:
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()

    def route_clean(self, text):
        """Strip wake phrases and return the remaining command text."""
        cmd = text.lower()
        names = {"jarvis"}
        if self.name.lower() != "jarvis":
            names.add(self.name.lower())
        for n in names:
            for pat in [
                f"hey {n}",
                f"hey {n},",
                f"hey, {n}",
                f"hey, {n},",
                f"hey {n}.",
                n,
                f"{n},",
            ]:
                cmd = cmd.replace(pat, "").strip()
        return cmd.strip(".,!? ")


def run():
    import argparse

    parser = argparse.ArgumentParser(description="EchoBase voice assistant")
    parser.add_argument(
        "--name",
        default=None,
        help="override the saved assistant name for this run",
    )
    parser.add_argument(
        "--reset-oobe",
        action="store_true",
        help="re-run the first-time setup wizard (debug)",
    )
    args = parser.parse_args()

    # Debug reset can also be requested via the environment.
    env_reset = os.environ.get("ECHOBASE_RESET", "").lower() in ("1", "true", "yes")
    reset = args.reset_oobe or env_reset

    app = EchoBase(name=args.name, reset_oobe=reset)
    app.run()
