"""Out-of-box experience (OOBE): the first-run setup wizard.

This replaces the old text-only name picker. It is **fully voice-controlled** so
a locomotory-impaired user can complete setup hands-free, while still accepting
typed answers as a fallback (handy for development and noisy rooms).

It runs *after* Whisper and the microphone are up (so it can listen) but *before*
the main command loop. It collects:

  1. the user's name (for personalised greetings),
  2. the assistant's wake name,
  3. a masculine or feminine voice (with a spoken sample),
  4. speech rate,
  5. accessibility prefs (dwell clicking, head-tracking sensitivity),
  6. whether to use friendly, chatty replies,

then saves the config and marks the OOBE complete.

While developing, the whole flow can be re-triggered at any time — say
"factory reset", pass ``--reset-oobe``, or set ``ECHOBASE_RESET=1``. Any of
these wipes the saved config first, so a fresh setup always starts clean.
"""

import re

from . import config, phrases, ui

# Yes/no recognition now lives in ``phrases`` so the command-recovery flow can
# share it; kept as module aliases for the local steps below.
_YES = phrases.YES_WORDS
_NO = phrases.NO_WORDS

_MASCULINE = {
    "masculine",
    "male",
    "man",
    "men",
    "boy",
    "deeper",
    "deep",
    "ryan",
    "him",
    "he",
}
_FEMININE = {
    "feminine",
    "female",
    "woman",
    "women",
    "girl",
    "lady",
    "amy",
    "her",
    "she",
    "higher",
}

_RATES = {
    "slow": "slow",
    "slower": "slow",
    "slowly": "slow",
    "normal": "normal",
    "medium": "normal",
    "regular": "normal",
    "default": "normal",
    "fast": "fast",
    "faster": "fast",
    "quick": "fast",
    "quickly": "fast",
    "quicker": "fast",
}

_SKIP = {"skip", "none", "nothing", "no name", "later", "pass"}

# A short, friendly sentence used to demo a chosen voice / speed.
_SAMPLE = "Hi, this is how I'll sound when I talk to you."


# --- Listening --------------------------------------------------------------


def _listen(core, bias=""):
    """Capture one spoken answer and return it lower-cased (or "" on silence)."""
    core.flush_stream()
    first = core.wait_for_speech(timeout=8)
    if not first:
        return ""
    audio = first + core.record_until_silence()
    text = core.transcribe(audio, prompt=bias or None)
    return (text or "").lower().strip(".,!? ")


def _ask(core, question, bias="", tries=3, allow_type=True):
    """Speak *question*, then listen. After *tries* silent attempts, fall back
    to a typed answer so setup can never get permanently stuck."""
    for attempt in range(tries):
        core.speak(
            question if attempt == 0 else "Sorry, I didn't catch that. " + question
        )
        ui.log("listen", "say your answer...", ui.CYAN)
        ans = _listen(core, bias)
        if ans:
            ui.log("heard", ans, ui.YELLOW)
            return ans
    if allow_type:
        try:
            typed = input("  (type your answer): ").strip()
            if typed:
                return typed.lower().strip(".,!? ")
        except (EOFError, KeyboardInterrupt):
            pass
    return ""


def _wants_yes(text, default=True):
    return phrases.wants_yes(text, default)


# --- Steps ------------------------------------------------------------------


def _step_user_name(core, cfg):
    ans = _ask(
        core,
        "First, what should I call you? Say your first name, or say skip.",
    )
    if not ans or ans in _SKIP or any(w in _SKIP for w in ans.split()):
        cfg["user_name"] = ""
        core.speak("No problem, we'll keep it casual.")
        return
    # Take the first word as the name, title-cased.
    name = ans.split()[0].strip(".,!?").title()
    cfg["user_name"] = name
    core.speak(f"Nice to meet you, {name}.")


def _step_assistant_name(core, cfg):
    options = ", ".join(ui._DEFAULT_NAMES[:-1]) + f", or {ui._DEFAULT_NAMES[-1]}"
    bias = "Jarvis Echo Nova Atlas Sage"
    ans = _ask(
        core,
        f"What would you like to name me? You can pick {options}, or say your own name.",
        bias=bias,
    )
    chosen = None
    if ans:
        for name in ui._DEFAULT_NAMES:
            if name.lower() in ans:
                chosen = name
                break
        if not chosen:
            # Treat the (first) spoken word as a custom name.
            chosen = ans.split()[0].strip(".,!?").title()
    cfg["name"] = chosen or "Jarvis"
    core.speak(f"Great. You can wake me by saying, Hey {cfg['name']}.")


def _step_voice(core, cfg):
    while True:
        ans = _ask(
            core,
            "Would you prefer a masculine or a feminine voice?",
            bias="masculine feminine male female",
        )
        words = set(ans.split())
        if words & _MASCULINE:
            gender = "masculine"
        elif words & _FEMININE:
            gender = "feminine"
        else:
            gender = cfg.get("voice_gender", "feminine")

        cfg["voice_gender"] = gender
        core.apply_voice(gender, cfg.get("speech_rate", "normal"))
        core.speak(_SAMPLE)

        confirm = _ask(
            core,
            "Do you like this voice? Say yes to keep it, or no to switch.",
            bias="yes no",
        )
        if _wants_yes(confirm, default=True):
            core.speak(f"The {gender} voice it is.")
            return


def _step_rate(core, cfg):
    ans = _ask(
        core,
        "How fast should I speak? Say slow, normal, or fast.",
        bias="slow normal fast",
    )
    rate = "normal"
    for word in ans.split():
        if word in _RATES:
            rate = _RATES[word]
            break
    cfg["speech_rate"] = rate
    core.apply_voice(cfg.get("voice_gender", "feminine"), rate)
    core.speak(f"Okay, I'll speak at a {rate} pace.")


def _step_accessibility(core, cfg):
    # Hands-free dwell clicking (opt-in).
    ans = _ask(
        core,
        "Would you like hands-free dwell clicking? When it's on, resting the "
        "pointer still for a moment clicks by itself. Say yes or no.",
        bias="yes no",
    )
    cfg["dwell_enabled"] = _wants_yes(ans, default=False)
    core.speak(
        "Dwell clicking is on." if cfg["dwell_enabled"] else "Dwell clicking is off."
    )

    # Head-tracking sensitivity.
    ans = _ask(
        core,
        "How sensitive should head tracking be? Say slow, normal, or fast.",
        bias="slow normal fast",
    )
    sens = "normal"
    for word in ans.split():
        if word in _RATES:
            sens = _RATES[word]
            break
    cfg["tracking_sensitivity"] = sens
    core.speak(f"Head tracking set to {sens}.")


# Spoken-number words (plus common Whisper homophones) for the profile picker.
_CHOICE_WORDS = {
    "one": 1, "won": 1,
    "two": 2, "to": 2, "too": 2,
    "three": 3, "tree": 3, "free": 3,
    "four": 4, "for": 4, "fore": 4,
}

# Short voice confirmation for each profile, spoken back after the choice.
_PROFILE_CONFIRM = {
    1: "Fast it is — quickest responses.",
    2: "Balanced it is — a good mix of speed and accuracy.",
    3: "Accurate it is — better with slurred or effortful speech, a bit slower.",
    4: "Maximum it is — the most accurate and forgiving, and the slowest.",
}


def _parse_choice(text, lo=1, hi=4):
    """Return a menu number in [lo, hi] spoken or typed in *text*, or None.

    Digits win first (``"3"`` / ``"option 2"``); otherwise a number word or one
    of its frequent Whisper homophones (``"to"`` -> 2). Mirrors the numbered
    pickers in windows.py / labels.py."""
    for m in re.findall(r"\b(\d+)\b", text):
        n = int(m)
        if lo <= n <= hi:
            return n
    for word, n in _CHOICE_WORDS.items():
        if lo <= n <= hi and re.search(rf"\b{word}\b", text):
            return n
    return None


def _step_recognition(core, cfg):
    """Numbered profile picker for how the app understands speech, fastest ->
    most accurate. The user just says a number (with the usual typed fallback);
    the chosen profile expands into the whisper model/beam plus biasing, recovery
    cutoffs, and n-best, and is confirmed back by voice. Defaults to the
    recommended Balanced profile if nothing is understood."""
    menu = (
        "Choose how I understand your speech. Say a number. "
        "One, Fast — quickest, lighter on your computer; best if your speech is clear. "
        "Two, Balanced — a good mix of speed and accuracy; recommended for most people. "
        "Three, Accurate — better with accents and slurred or effortful speech; a bit slower. "
        "Four, Maximum — the most accurate and most forgiving of unclear speech; "
        "the slowest, and needs more memory."
    )
    core.speak(menu)
    choice = None
    for attempt in range(3):  # re-ask on silence or an unparseable answer
        if attempt:
            core.speak("Please say a number from one to four.")
        ui.log("listen", "say a number (1-4)...", ui.CYAN)
        ans = _listen(core, bias="one two three four 1 2 3 4")
        if ans:
            ui.log("heard", ans, ui.YELLOW)
            choice = _parse_choice(ans)
            if choice is not None:
                break
    if choice is None:
        # Typed fallback so setup can never get permanently stuck (as in _ask).
        try:
            choice = _parse_choice(input("  (type a number 1-4): ").strip())
        except (EOFError, KeyboardInterrupt):
            choice = None
    if choice is None:
        choice = config.DEFAULT_RECOGNITION_PROFILE
        core.speak("I'll go with Balanced, a good mix of speed and accuracy.")
    else:
        core.speak(_PROFILE_CONFIRM[choice])

    # recognition_profile is the source of truth; the expanded whisper keys are
    # written too so configs stay readable by code that predates profiles.
    row = config.RECOGNITION_PROFILE_TABLE[choice]
    cfg["recognition_profile"] = choice
    cfg["whisper_model"] = row["model"]
    cfg["whisper_beam"] = row["beam"]


def _step_pace(core, cfg):
    """Endpointing tolerance for the speaker's pace, so slow or effortful speech
    isn't cut off mid-sentence."""
    ans = _ask(
        core,
        "Do you speak at a normal, relaxed, or slow pace? If you say slow, I'll "
        "wait longer before I stop listening.",
        bias="normal relaxed slow regular",
    )
    if "slow" in ans:
        pace = "slow"
    elif "relax" in ans:
        pace = "relaxed"
    else:
        pace = "normal"
    cfg["speech_pace"] = pace
    core.speak(f"Okay, I'll listen at a {pace} pace.")


def _step_browser(core, cfg):
    """Pick which installed browser the browser commands should drive."""
    found = config.detect_browsers()
    if not found:
        cfg["browser"] = ""
        core.speak("I didn't find a web browser installed, but you can set one later.")
        return
    names = [n for n, _ in found]
    if len(names) == 1:
        cfg["browser"] = names[0]
        core.speak(f"I'll use {names[0]} as your browser.")
        return

    spoken = ", ".join(names[:-1]) + f", or {names[-1]}"
    ans = _ask(
        core,
        f"Which web browser should I use? You have {spoken}.",
        bias=" ".join(config.BROWSER_ALIASES),
    )
    chosen = None
    for alias, key in config.BROWSER_ALIASES.items():
        if key in names and alias in ans:
            chosen = key
            break
    if not chosen:
        for n in names:
            if n in ans:
                chosen = n
                break
    cfg["browser"] = chosen or names[0]
    core.speak(f"Okay, I'll use {cfg['browser']}.")


def _step_snippets(core, cfg):
    """Optionally collect personal text shortcuts ("type my email", etc.).

    These are precise (emails/addresses), so they're typed rather than dictated.
    Entirely optional — skipping leaves them unset and the snippets silent."""
    ans = _ask(
        core,
        "Would you like to set up text shortcuts, so you can say things like "
        "type my email? Say yes or no.",
        bias="yes no",
    )
    if not _wants_yes(ans, default=False):
        core.speak("No problem, skipping text shortcuts.")
        return

    fields = [
        ("snippet_name", "your full name"),
        ("snippet_email", "your email address"),
        ("snippet_phone", "your phone number"),
        ("snippet_address", "your address"),
    ]
    core.speak("Type each one, or just press enter to skip it.")
    for key, label in fields:
        try:
            val = input(f"  {label}: ").strip()
        except (EOFError, KeyboardInterrupt):
            val = ""
        cfg[key] = val
    core.speak("Saved your text shortcuts.")


def _step_autostart(core, cfg):
    """Offer to launch EchoBase automatically when the computer starts.

    Writing/removing the XDG autostart entry happens here so the choice takes
    effect immediately, not just on the next setup. If the entry can't be
    written we tell the user and leave the preference off."""
    ans = _ask(
        core,
        "Would you like me to start automatically when you turn on your "
        "computer? Say yes or no.",
        bias="yes no",
    )
    enabled = _wants_yes(ans, default=False)
    ok = config.set_autostart(enabled)
    cfg["start_on_boot"] = enabled and ok
    if enabled:
        core.speak(
            "Okay, I'll start up with your computer."
            if ok
            else "I couldn't set that up, but you can turn it on later."
        )
    else:
        core.speak("Okay, I won't start automatically.")


def _step_friendly(core, cfg):
    ans = _ask(
        core,
        "Last thing. Would you like me to use friendly, chatty replies? Say yes or no.",
        bias="yes no",
    )
    cfg["friendly_messages"] = _wants_yes(ans, default=True)
    core.speak(
        "I'll keep things friendly."
        if cfg["friendly_messages"]
        else "Understood, I'll keep replies short."
    )


# --- Entry point ------------------------------------------------------------


def run(core, cfg=None):
    """Run the wizard against an already-initialised *core* and return the
    saved config dict. *core* must have ``speak``, ``apply_voice`` and the
    audio/transcription helpers available."""
    cfg = dict(config.DEFAULTS) if cfg is None else dict(cfg)

    ui.section("setup")
    ui.panel(
        "first-time setup",
        [
            "answer out loud — I'm listening",
            ui.c(ui.DIM, "you can also type if needed"),
        ],
        color=ui.CYAN,
    )
    core.speak("Welcome to EchoBase. Let's set things up. You can answer me out loud.")

    _step_user_name(core, cfg)
    _step_assistant_name(core, cfg)
    _step_voice(core, cfg)
    _step_rate(core, cfg)
    _step_recognition(core, cfg)
    _step_pace(core, cfg)
    _step_accessibility(core, cfg)
    _step_browser(core, cfg)
    _step_snippets(core, cfg)
    _step_autostart(core, cfg)
    _step_friendly(core, cfg)

    cfg["oobe_completed"] = True
    config.save(cfg)

    who = cfg.get("user_name") or ""
    tail = ""
    if config.debug_enabled():
        tail = ' You can start over any time by saying, "factory reset".'
    core.speak((f"All set{', ' + who if who else ''}! I'm ready when you are." + tail))
    ui.log("ok", "setup complete", ui.GREEN)
    return cfg
