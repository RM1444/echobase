import json
import re
import time

from EchoBase.core import ui

NAME = "windows"
DESCRIPTION = "Switch focus between open windows by voice"

COMMANDS = [
    "switch to [app] - focus a window by name (e.g. 'switch to firefox')",
    "focus [app] / bring up [app] - same as switch to",
    "list windows / what's open - read out open windows",
    "next window / previous window - cycle through windows",
]

# Canonical spoken forms for the fuzzy near-miss recovery (main._recover).
# ("switch to <app>" is dynamic/prefix-based, so only the fixed phrases listed.)
PHRASES = [
    "list windows",
    "next window",
    "previous window",
    "pick window",
    "switch window",
]

core = None

# Spoken prefixes that mean "focus the window matching the rest".
_FOCUS_PREFIXES = (
    "switch to ",
    "switch window to ",
    "focus ",
    "focus on ",
    "bring up ",
    "bring me ",
    "activate ",
    "show me ",
    "go to window ",
)

_LIST_PHRASES = {
    "list windows",
    "show windows",
    "what windows are open",
    "what's open",
    "whats open",
    "what is open",
    "open windows",
    "which windows are open",
}

# Show the numbered overlay and pick by number.
_PICK_PHRASES = {
    "pick window",
    "pick a window",
    "choose window",
    "choose a window",
    "window picker",
    "window numbers",
    "number the windows",
    "switch window",
    "switch windows",
}

# Spoken numbers for picking 1-9.
_PICK_NUMBERS = {
    "one": 1,
    "won": 1,
    "two": 2,
    "to": 2,
    "too": 2,
    "three": 3,
    "tree": 3,
    "four": 4,
    "for": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "ate": 8,
    "nine": 9,
}

_PICK_CANCEL = {"cancel", "close", "never mind", "nevermind", "exit", "stop", "escape"}


def setup(c):
    global core
    core = c


def _dbus(method, *args, parse="bool"):
    """Call a window method on the GNOME Shell extension.

    ``parse`` selects how stdout is interpreted: "bool" (FocusWindow),
    "json" (GetWindows), "int" (GetCurrentWorkspace) or "raw".
    Returns None when the extension is unavailable.
    """
    cmd = [
        "gdbus",
        "call",
        "--session",
        "--dest",
        "org.gnome.Shell",
        "--object-path",
        "/org/EchoBase/Grid",
        "--method",
        f"org.EchoBase.Grid.{method}",
    ]
    cmd.extend(str(a) for a in args)
    result = core.host_run(cmd)
    if result.returncode != 0:
        ui.log(
            "error",
            f"windows · {result.stderr.strip() or 'extension not enabled'}",
            ui.RED,
        )
        return None
    return _parse(result.stdout, parse)


def _parse(stdout, parse):
    out = (stdout or "").strip()
    if parse == "bool":
        return "true" in out.lower()
    if parse == "int":
        m = re.search(r"-?\d+", out)
        return int(m.group()) if m else None
    if parse == "json":
        # gdbus wraps the JSON string in a tuple with single quotes:
        # ('[{"title": "..."}]',)  -> pull out the inner string and decode.
        m = re.search(r"'(.*)'", out, re.S)
        payload = m.group(1) if m else out
        try:
            return json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            ui.log("error", "windows · could not parse window list", ui.RED)
            return None
    return out


def get_windows():
    """Return a list of window dicts (id, title, wm_class, focused, ...) or []."""
    data = _dbus("GetWindows", parse="json")
    return data if isinstance(data, list) else []


def _label(win):
    """A short, speakable name for a window."""
    title = (win.get("title") or "").strip()
    wm = (win.get("wm_class") or "").strip()
    return title or wm or "untitled window"


def _focus(target):
    """Focus a window whose title/class contains *target*. Speaks the result."""
    target = target.strip(".,!? ").strip()
    if not target:
        return True

    # Prefer a precise match against the live list so we can give good feedback
    # and avoid focusing our own terminal by accident.
    windows = get_windows()
    match = _best_match(target, windows)
    if match is None and not windows:
        # Extension may be down, or query failed — still try the raw call.
        ok = _dbus("FocusWindow", target)
        if ok:
            core.speak(f"Switching to {target}.")
        else:
            core.speak(f"I couldn't find a window for {target}.")
        return True

    if match is None:
        core.speak(f"I don't see a window for {target}.")
        return True

    ok = _dbus("FocusWindow", match.get("title") or target)
    if ok:
        core.speak(f"Switching to {_label(match)}.")
    else:
        core.speak(f"I couldn't switch to {target}.")
    return True


def _best_match(target, windows):
    """Pick the window best matching *target* (substring on title/class)."""
    t = target.lower()
    scored = []
    for win in windows:
        title = (win.get("title") or "").lower()
        wm = (win.get("wm_class") or "").lower()
        if t in title or t in wm or title in t or wm in t:
            # Prefer matches on the shorter field (more specific) and class hits.
            score = 0
            if t in wm or wm in t:
                score += 2
            if t in title:
                score += 1
            scored.append((score, win))
    if not scored:
        return None
    scored.sort(key=lambda s: s[0], reverse=True)
    return scored[0][1]


def _cycle(step):
    """Focus the next/previous window relative to the focused one."""
    windows = get_windows()
    if not windows:
        core.speak("I don't see any open windows.")
        return True
    if len(windows) == 1:
        core.speak("There's only one window open.")
        return True
    idx = next((i for i, w in enumerate(windows) if w.get("focused")), 0)
    nxt = windows[(idx + step) % len(windows)]
    if _dbus("FocusWindow", nxt.get("title") or ""):
        core.speak(f"Switching to {_label(nxt)}.")
    return True


def _list():
    windows = get_windows()
    if not windows:
        core.speak("I don't see any open windows.")
        return True
    names = [_label(w) for w in windows]
    ui.panel(
        "open windows", [f"{i + 1}. {n}" for i, n in enumerate(names)], color=ui.BLUE
    )
    count = len(names)
    spoken = "; ".join(names[:6])
    core.speak(f"{count} window{'s' if count != 1 else ''} open: {spoken}.")
    return True


def _parse_pick_number(text):
    """Return a window number 1-9 from spoken text, or None."""
    m = re.search(r"\b([1-9])\b", text)
    if m:
        return int(m.group(1))
    for word, n in _PICK_NUMBERS.items():
        if re.search(rf"\b{word}\b", text):
            return n
    return None


def _pick():
    """Show the numbered window overlay and focus the one the user names."""
    windows = get_windows()
    if not windows:
        core.speak("I don't see any open windows.")
        return True

    windows = windows[:9]  # single-digit selection
    labels = [_label(w) for w in windows]
    _dbus("ShowWindowPicker", json.dumps(labels), parse="raw")
    ui.panel(
        "pick a window", [f"{i + 1}. {n}" for i, n in enumerate(labels)], color=ui.BLUE
    )
    core.speak("Say the number of the window you want.")

    try:
        for _ in range(3):  # a few attempts before giving up
            core.flush_stream()
            time.sleep(0.1)
            first = core.wait_for_speech(timeout=8)
            audio = first + core.record_until_silence()
            said = core.transcribe(
                audio, prompt="one two three four five six seven eight nine cancel"
            )
            said = (said or "").lower().strip(".,!? ")
            if not said:
                continue
            ui.log("heard", said, ui.YELLOW)

            if any(w in said for w in _PICK_CANCEL):
                core.speak("Cancelled.")
                return True

            num = _parse_pick_number(said)
            if num and 1 <= num <= len(windows):
                target = windows[num - 1]
                if _dbus("FocusWindow", target.get("title") or ""):
                    core.speak(f"Switching to {_label(target)}.")
                return True
            core.speak("Say a number from the list, or cancel.")
        core.speak("Okay, leaving the window picker.")
        return True
    finally:
        _dbus("HideWindowPicker", parse="raw")


def handle(cmd, core):
    c = cmd.lower().strip(".,!? ")

    if c in _PICK_PHRASES:
        return _pick()

    if c in _LIST_PHRASES:
        return _list()

    if c in ("next window", "window next", "cycle window", "cycle windows"):
        return _cycle(+1)
    if c in ("previous window", "last window", "window previous", "previous app"):
        return _cycle(-1)

    for prefix in _FOCUS_PREFIXES:
        if c.startswith(prefix):
            return _focus(c[len(prefix) :])

    return None
